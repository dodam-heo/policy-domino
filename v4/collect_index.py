"""Policy Domino v4 / official-source indexing.

The index is a catalogue of promulgated legal versions, not a catalogue of
"affected" policies. No title search, agency whitelist or policy-name enrolment.
Every date window reports exactly how many records the official API returned.
"""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass,asdict
from typing import Callable
from v2 import collector as api

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
    candidate={"law":"law","admrul":"admrul","ordin":"ordin"}[target]
    return [x for x in root.iter() if x.tag.split("}")[-1].lower()==candidate]

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

def page_query(source,first,last,page):
    key={"law":"ancYd","admrul":"prmlYd","ordin":"ancYd"}[source]
    args={"display":100,"page":page,"sort":"ddes",
          key:first.replace("-","")+"~"+last.replace("-","")}
    # Explicitly request current official administrative rules / ordinances.
    if source in ("admrul","ordin"):args["nw"]="1"
    return args

def scan_window(source,first,last,fetch=None,max_pages=50):
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
            root=fetch(source,**page_query(source,first,last,page))
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

def bisect_window(source,first,last,fetch=None,max_pages=50,max_splits=10):
    """Recursively split an incomplete date range, retaining audit failures.

    If a single day remains oversubscribed, never silently drop its results.
    """
    rows,stat=scan_window(source,first,last,fetch,max_pages)
    if stat.complete or first==last or max_splits<=0 or stat.reported==-1:
        return rows,[stat]
    a=dt.date.fromisoformat(first);b=dt.date.fromisoformat(last)
    mid=a+(b-a)//2
    if mid>=b:return rows,[stat]
    left,lstats=bisect_window(source,str(a),str(mid),fetch,max_pages,max_splits-1)
    right,rstats=bisect_window(source,str(mid+dt.timedelta(days=1)),
                               str(b),fetch,max_pages,max_splits-1)
    out={(r["source"],r["stable_id"],r["serial"]):r for r in left+right}
    return list(out.values()),lstats+rstats

def ingest_index(state,source,date_windows,fetch=None,max_pages=30):
    """Store every official version by stable ID + serial, never first 500 only."""
    ledger=state.setdefault("catalog",{})
    audits=state.setdefault("coverage",[])
    found=0
    for first,last in date_windows:
        rows,windows=bisect_window(source,first,last,fetch,max_pages)
        for r in rows:
            key=api.uid(r["source"],r["stable_id"],r["serial"])
            if key not in ledger:found+=1
            ledger[key]=r
        audits.extend(x.as_dict() for x in windows)
    return {"new_versions":found,"total_versions":len(ledger),
            "complete_windows":sum(x["complete"] for x in audits),
            "incomplete_windows":[x for x in audits if not x["complete"]]}
