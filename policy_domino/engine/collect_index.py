"""Policy Domino v4 / official-source indexing.

The index is a catalogue of promulgated legal versions, not a catalogue of
"affected" policies. No title search, agency whitelist or policy-name enrolment.
Every date window reports exactly how many records the official API returned.
"""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass,asdict
from typing import Callable
from policy_domino import official_api as api

@dataclass
class WindowResult:
    source:str
    first:str
    last:str
    reported:int
    collected:int
    pages:int
    complete:bool
    error:str=""
    def as_dict(self):return asdict(self)

def tags(root,target):
    # The ordinance XML uses Korean row tags (자치법규), not "ordin".
    # Detect record structures using direct official serial/title fields;
    # this remains stable if the wrapper node name changes.
    needed={"law":("법령일련번호","법령명한글"),
            "admrul":("행정규칙일련번호","행정규칙명"),
            "ordin":("자치법규일련번호","자치법규명")}[target]
    result=[]
    for node in root.iter():
        if node is root:continue
        fields={x.tag.split("}")[-1] for x in list(node)}
        if all(t in fields for t in needed):result.append(node)
    return result

def as_record(node,source):
    if source in ("law","admrul"):
        return api.row_of(node,source)
    title=api.field(node,"자치법규명")
    stable=api.field(node,"자치법규ID")
    serial=api.field(node,"자치법규일련번호")
    issued=api.ymd(api.field(node,"공포일자"))
    if not all((title,stable,serial,issued)):return None
    return {"source":"ordin","title":title,"stable_id":stable,
        "serial":serial,"published_at":issued,
        "effective_date":api.ymd(api.field(node,"시행일자")),
        "revision":api.field(node,"제개정구분명"),
        "kind":"자치법규","number":api.field(node,"공포번호"),
        "ministry":api.field(node,"지자체기관명"),
        "url":"https://www.law.go.kr/자치법규/"+__import__("urllib.parse",fromlist=["quote"]).quote(title)}

def page_query(source,first,last,page,edition="1"):
    key={"law":"ancYd","admrul":"prmlYd","ordin":"ancYd"}[source]
    args={"display":100,"page":page,"sort":"ddes",
          key:first.replace("-","")+"~"+last.replace("-","")}
    # Explicitly request current official administrative rules / ordinances.
    if source in ("admrul","ordin"):args["nw"]=edition
    return args

def scan_window(source,first,last,fetch=None,max_pages=50,edition="1"):
    """Return rows plus an audit record; incomplete never counts as success.

    A date window is exhausted only when page count matches official totalCnt
    or the server unequivocally supplies the final partial page.
    """
    if source not in ("law","admrul","ordin"):raise ValueError("unsupported official source")
    fetch=fetch or api.request
    first,last=str(first),str(last)
    all_records={};reported=None;pages=0;failure=""
    for page in range(1,max_pages+1):
        try:
            root=fetch(source,**page_query(source,first,last,page,edition))
            raw_count=api.field(root,"totalCnt")
            if not raw_count or not raw_count.isdigit():
                raise ValueError("Official totalCnt absent: cannot confirm coverage")
            count=int(raw_count)
            if reported is None:reported=count
            elif count!=reported:
                raise ValueError("Official collection changed during pagination")
            entries=tags(root,source)
            if count and not entries:
                raise ValueError("Nonempty official result with missing source rows")
            for node in entries:
                rec=as_record(node,source)
                if rec:
                    # Do not accidentally include records outside the requested
                    # promulgation window even when API search is unreliable.
                    if first<=rec["published_at"]<=last:
                        all_records[(source,rec["stable_id"],rec["serial"])]=rec
            pages=page
            if not count or page*100>=count or len(entries)<100:
                complete=(len(all_records)==count)
                return list(all_records.values()),WindowResult(
                    source,first,last,count,len(all_records),page,complete,
                    "" if complete else "Returned rows do not match totalCnt")
        except Exception as exc:
            failure=type(exc).__name__+": "+str(exc)[:180]
            break
    return list(all_records.values()),WindowResult(
        source,first,last,reported if reported is not None else -1,
        len(all_records),pages,False,
        failure or "Page limit reached before exhausting official totalCnt")

def bisect_window(source,first,last,fetch=None,max_pages=50,max_splits=10,edition="1"):
    """Recursively split an incomplete date range, retaining audit failures.

    If a single day remains oversubscribed, never silently drop its results.
    """
    rows,stat=scan_window(source,first,last,fetch,max_pages,edition)
    if stat.complete or first==last or max_splits<=0 or stat.reported==-1:
        return rows,[stat]
    a=dt.date.fromisoformat(first);b=dt.date.fromisoformat(last)
    mid=a+(b-a)//2
    if mid>=b:return rows,[stat]
    left,lstats=bisect_window(source,str(a),str(mid),fetch,max_pages,max_splits-1,edition)
    right,rstats=bisect_window(source,str(mid+dt.timedelta(days=1)),
                               str(b),fetch,max_pages,max_splits-1,edition)
    out={(r["source"],r["stable_id"],r["serial"]):r for r in left+right}
    return list(out.values()),lstats+rstats

def record_coverage(state, audit: dict) -> None:
    """Retain the latest evidence for each source, date range and edition."""
    rows = state.setdefault("coverage", [])
    if audit.get("complete"):
        state["_source_pages_confirmed"]=state.get("_source_pages_confirmed",0)+1
    fields = ("source", "first", "last", "edition")
    identity = tuple(audit.get(field, "") for field in fields)
    for i, old in enumerate(rows):
        if tuple(old.get(field, "") for field in fields) == identity:
            if old.get("complete") and not audit.get("complete"):
                old["last_retry_error"] = audit.get("error", "")
            else:
                rows[i] = audit
            return
    rows.append(audit)


def window_covered(state, source, first, last, edition) -> bool:
    """True if complete official-query intervals cover every requested day."""
    cursor = dt.date.fromisoformat(first)
    end = dt.date.fromisoformat(last)
    intervals = sorted(
        (dt.date.fromisoformat(row["first"]),
         dt.date.fromisoformat(row["last"]))
        for row in state.get("coverage", [])
        if row.get("source") == source
        and row.get("edition", "current") == edition
        and row.get("complete") and row.get("first") and row.get("last")
    )
    for a, b in intervals:
        if a <= cursor <= b:
            cursor = b + dt.timedelta(days=1)
            if cursor > end:
                return True
    return cursor > end


def ingest_index(state,source,date_windows,fetch=None,max_pages=30):
    """Store every official version by stable ID + serial, never first 500 only."""
    ledger=state.setdefault("catalog",{})
    found=0
    for first,last in date_windows:
      for edition in (("1","2") if source in ("admrul","ordin") else ("1",)):
        rows,windows=bisect_window(source,first,last,fetch,max_pages,edition=edition)
        for r in rows:
            key=api.uid(r["source"],r["stable_id"],r["serial"])
            previous=ledger.get(key,{})
            if not previous:found+=1
            r["first_seen_at"]=previous.get("first_seen_at") or dt.date.today().isoformat()
            r["discovery_kind"] = ("official_law_change_history"
                if previous.get("discovery_kind") == "official_law_change_history"
                else "official_date_index")
            ledger[key]={**previous,**r}
        for window in windows:
            record_coverage(state, {**window.as_dict(),
                "edition":"history" if edition=="2" else "current"})
    audits=state["coverage"]
    return {"new_versions":found,"total_versions":len(ledger),
            "complete_windows":sum(x["complete"] for x in audits),
            "incomplete_windows":[x for x in audits if not x["complete"]]}


def scan_official_change_day(day,fetch=None,max_pages=50):
    """Official law-change HISTORY, not the current-law-name search.

    The lsHstInf index lists amended statutes by change date, including
    consolidated or omnibus consequences. It is a separate source from
    promulgation-date current-law snapshots.
    """
    fetch=fetch or api.request
    rows={};reported=None;pages=0
    for page in range(1,max_pages+1):
        try:
            root=fetch("lsHstInf",regDt=day.replace("-",""),
                       display=100,page=page)
            total=api.field(root,"totalCnt")
            if not total.isdigit():raise ValueError("Change-history totalCnt missing")
            current=int(total)
            if reported is not None and current!=reported:
                raise ValueError("Change-history results changed during pagination")
            reported=current
            nodes=[x for x in root.iter() if x is not root and
                   any(child.tag.split("}")[-1]=="법령일련번호" for child in list(x))]
            if reported and not nodes:
                raise ValueError("Change-history records missing despite nonzero count")
            for node in nodes:
                record=api.row_of(node,"law")
                if record:
                    record["discovery_kind"]="official_law_change_history"
                    record["change_recorded_on"]=day
                    rows[(record["stable_id"],record["serial"])]=record
            pages=page
            if page*100>=reported or len(nodes)<100:break
        except Exception as exc:
            return list(rows.values()),WindowResult(
                "law_history",day,day,reported or -1,len(rows),pages,False,
                type(exc).__name__+": "+str(exc)[:180])
    complete=(reported is not None and len(rows)==reported)
    return list(rows.values()),WindowResult(
        "law_history",day,day,reported or -1,len(rows),pages,complete,
        "" if complete else "Official history not completely collected")

def ingest_changes(state,days,fetch=None,max_pages=50):
    for day in days:
        rows,audit=scan_official_change_day(day,fetch,max_pages)
        for record in rows:
            key=api.uid(record["source"],record["stable_id"],record["serial"])
            catalog=state.setdefault("catalog",{})
            previous=catalog.get(key,{})
            record["first_seen_at"]=previous.get("first_seen_at") or dt.date.today().isoformat()
            catalog[key]={**previous,**record}
        record_coverage(state, {**audit.as_dict(), "edition":"history"})
    return state
