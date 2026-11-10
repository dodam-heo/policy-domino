"""Policy Domino v4 / staged official-source pipeline.

No keyword-to-agency inference. Publication of an announcement, verified
textual change, downstream legal dependency and actual implementation are
four DIFFERENT states. This pipeline never silently treats one as another.
"""
from __future__ import annotations
import datetime as dt,json,os,re,time
from pathlib import Path
from policy_domino import official_api as api
from policy_domino.engine import collect_index,events,relationships,official_links,dependents,source_change

ROOT=Path(__file__).resolve().parents[2]
STATE=ROOT/"data"/"v4_state.json"
OUTPUT=ROOT/"site"/"v4"/"data.json"
SUPPORTED=("law","admrul","ordin")

def load_json(path,default):
    # A corrupt/partially written persisted crawl must never reset years of
    # official evidence to an empty catalogue.
    if not path.exists():
        return default
    return json.loads(path.read_text("utf8"))

def save_json(path,item):
    """Atomically persist source snapshots; a crash cannot empty the cache."""
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(item,ensure_ascii=False,indent=2),"utf8")
    temporary.replace(path)

def scan_new(state,today,checkpoint=None):
    """Bounded overlapping discovery and resumable sector-neutral backfill.

    Each six-hour run prioritizes newly promulgated law/rule/ordinance records,
    retries unconfirmed pages, fills past-year gaps, and advances an independent
    long-term cursor. The official version catalogue is never reset.
    """
    api.official_oc()
    state["coverage_plan"]="official_incremental_rolling_sources_v3"
    state.setdefault("backfill_cursor_days",365)
    state.setdefault("recent_backfill_cursor_days",8)
    history=list(state.get("coverage",[]))
    state["coverage"]=[]
    for audit in history:
        collect_index.record_coverage(state,audit)
    state["_source_pages_confirmed"]=0

    horizon=max(365,min(10950,int(os.getenv("PD_HISTORY_DAYS","3650"))))
    span=max(7,min(31,int(os.getenv("PD_BACKFILL_WINDOW_DAYS","28"))))
    budget=max(1,min(4,int(os.getenv("PD_BACKFILL_WINDOWS_PER_RUN","2"))))
    retry_budget=max(1,min(8,int(os.getenv("PD_RETRY_WINDOWS_PER_RUN","2"))))
    def checkpoint_if_possible():
        if checkpoint:checkpoint(state)

    # Recheck the last two dates at every run. Older dates inside an eight-day
    # overlap are queried only if official coverage has never been confirmed.
    recent=[str(today-dt.timedelta(days=i)) for i in range(8)]
    recent_days=[day for i,day in enumerate(recent)
                 if i<2 or not collect_index.window_covered(
                     state,"law_history",day,day,"history")]
    if recent_days:
        collect_index.ingest_changes(state,recent_days,max_pages=12)
        checkpoint_if_possible()
    last_two=(recent[1],recent[0])
    for source in SUPPORTED:
        collect_index.ingest_index(state,source,[last_two],max_pages=20)
        checkpoint_if_possible()

    # Do not retry every historical gap in the same run: one bad endpoint
    # must not starve recent announcements and prevent publishing altogether.
    failures=[row for row in state.get("coverage",[])
              if not row.get("complete") and row.get("source") in (*SUPPORTED,"law_history")
              and row.get("first") and row.get("last")]
    failures.sort(key=lambda row:(row.get("last",""),row.get("source","")),reverse=True)
    seen=set()
    for row in failures:
        source,first,last=row["source"],row["first"],row["last"]
        edition=row.get("edition","current")
        identity=(source,first,last,edition)
        if identity in seen:continue
        seen.add(identity)
        if source=="law_history":
            days=[str(dt.date.fromisoformat(first)+dt.timedelta(days=i))
                  for i in range((dt.date.fromisoformat(last)-
                                  dt.date.fromisoformat(first)).days+1)]
            collect_index.ingest_changes(state,days,max_pages=20)
        else:
            collect_index.ingest_index(state,source,[(first,last)],max_pages=20)
        checkpoint_if_possible()
        if len(seen)>=retry_budget:break

    # Independently walk the past 365 days first. A very old cursor from a
    # previous software version must not postpone recent notice discovery.
    recent_budget=1
    for _ in range(recent_budget):
        offset=max(8,min(364,int(state.get("recent_backfill_cursor_days",8))))
        first=str(today-dt.timedelta(days=min(364,offset+span-1)))
        last=str(today-dt.timedelta(days=offset))
        for source in SUPPORTED:
            if all(collect_index.window_covered(state,source,first,last,edition)
                   for edition in (("current","history") if source in ("admrul","ordin")
                                   else ("current",))):
                continue
            collect_index.ingest_index(state,source,[(first,last)],max_pages=20)
        state["recent_backfill_cursor_days"]=8+(offset-8+span)%(365-8)
        checkpoint_if_possible()

    # Long history advances separately and never displaces past-year coverage.
    for _ in range(max(0,budget-recent_budget)):
        if horizon<=365:break
        start=max(365,int(state.get("backfill_cursor_days",365)))
        offset=365+(start-365)%(horizon-365)
        first=str(today-dt.timedelta(days=min(horizon-1,offset+span-1)))
        last=str(today-dt.timedelta(days=offset))
        for source in SUPPORTED:
            if all(collect_index.window_covered(state,source,first,last,edition)
                   for edition in (("current","history") if source in ("admrul","ordin")
                                   else ("current",))):
                continue
            collect_index.ingest_index(state,source,[(first,last)],max_pages=20)
        state["backfill_cursor_days"]=365+(offset-365+span)%(horizon-365)
        checkpoint_if_possible()

    successful=state.pop("_source_pages_confirmed",0)
    if not successful:
        state["last_official_scan_error"]="No fully confirmed official collection window"
        checkpoint_if_possible()
        raise RuntimeError("Official APIs returned no confirmed complete collection window")
    state.pop("last_official_scan_error",None)
    state["latest_official_scan"]=today.isoformat()
    checkpoint_if_possible()


def candidate_rank(record,today):
    """Document-wide generic signals only: source proof, dates, lifecycle.

    An issuing ministry's name and policy title keywords are not relevance
    scores; neither can prove an impact.
    """
    kind=record.get("discovery_kind","")
    future=record.get("effective_date","")>today.isoformat()
    age=record.get("published_at","")
    recent=age>=str(today-dt.timedelta(days=180))
    verified_history=kind=="official_law_change_history"
    priority=(85 if verified_history else 0)+(30 if future else 0)+(
       40 if recent else 0)
    first_seen=record.get("first_seen_at","")
    if first_seen and first_seen>=str(today-dt.timedelta(days=14)):
        priority+=35
    if events.label_revision(record.get("revision")) in ("enactment","repeal"):
        priority+=12
    # Older official historical documents are still discoverable in the
    # complete catalogue but should not displace this year's changes.
    if age<str(today-dt.timedelta(days=365)):priority-=30
    return (priority,age,record.get("serial",""))

def pick_work(state,today,limit):
    catalog=state.get("catalog",{})
    processed=state.get("inspected",{})
    attempts=state.get("attempts",{})
    def eligible(k,record):
        if record.get("discovery_kind")=="legacy_index_only_not_verified":
            return False
        old=processed.get(k)
        if old is None:
            return True
        if (old.get("verification") not in (
                "detail_failed","partial_official_text","official_record_only")
                and not old.get("needs_attachment_check")):
            return False
        return state.get("retry_after",{}).get(k,"")<=today.isoformat()
    waiting=[x for k,x in catalog.items() if eligible(k,x)]
    ranked=sorted(waiting,key=lambda x:(
        candidate_rank(x,today)[0]-(attempts.get(events.key(x),0)*16),
        candidate_rank(x,today)[1],
        candidate_rank(x,today)[2]),reverse=True)
    # Different regulatory types must receive detail capacity even while
    # another type has a much larger backlog. No policy name or ministry quota.
    selected=[];seen=set()
    types=[source for source in SUPPORTED if any(x["source"]==source for x in ranked)]
    quota=max(1,limit//max(1,len(types)))
    for source in types:
        for record in (x for x in ranked if x["source"]==source):
            if sum(x["source"]==source for x in selected)>=quota:
                break
            selected.append(record)
            seen.add(events.key(record))
            if len(selected)>=limit:
                return selected
    for record in ranked:
        if len(selected)>=limit:
            break
        if events.key(record) not in seen:
            selected.append(record)
            seen.add(events.key(record))
    return selected

def read_document(record):
    """One source-body adapter for laws, administrative rules and ordinances."""
    if record.get("source") not in SUPPORTED:
        raise ValueError("Unsupported official document type")
    return api.read_clauses(record)


def prepare_document_record(record,state):
    """Fetch a source record; do not replace existing verified evidence with
    a lexical hit or a lower-trust V2 snapshot.
    """
    snapshots=state.setdefault("verified_snapshots",{})
    def load(r):
        """One persistent source cache for current AND prior official versions.

        Store complete extracted original articles once; a later run does not
        request them again. Partial annexes never become verified cache hits.
        """
        key=events.key(r)
        existing=snapshots.get(key,{})
        clauses=existing.get("clauses",{})
        if (existing.get("complete_source") is True
                and isinstance(clauses,dict) and events.complete_text(clauses)):
            return api.ExtractedClauses(clauses)
        obtained=read_document(r)
        if (events.complete_text(obtained)
                and not getattr(obtained,"unresolved_attachments",[])):
            snapshots[key]={
                "source":r["source"],"stable_id":r["stable_id"],
                "serial":r["serial"],"source_url":r.get("url",""),
                "clauses":dict(obtained),"complete_source":True,
                "observed_at":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            }
        return obtained
    def prior(r,records=None):
        return events.predecessor(r,state.get("catalog",{}).values())
    def annual(r):
        return events.annual_baseline(r,records=state.get("catalog",{}).values())
    return events.inspect(record,state.get("catalog",{}).values(),
                          load=load,history=prior,annual=annual)

def output_groups(state):
    inspected=state.get("inspected",{})
    # Officially discovered but not yet analyzed is a valid *pending* item.
    # Historical unverified index metadata is not promoted into source truth.
    pending=[events.index_only(record) for key,record in state.get("catalog",{}).items()
             if key not in inspected and
             record.get("discovery_kind")!="legacy_index_only_not_verified"]
    all_events=list(inspected.values())+pending
    verified=[e for e in all_events if e["verification"].startswith("verified_")]
    # Only v4-retrieved official source bodies support graph edges.
    snapshots={}
    for row in state.get("verified_snapshots",{}).values():
        key=(row["source"],row["stable_id"],row["serial"])
        snapshots[key]=row["clauses"]
    docs=[e for e in all_events if
          (e["source"],e["stable_id"],e["serial"]) in snapshots]
    graph=relationships.build_graph(
        [e for e in verified if e.get("changed_articles") and
         e.get("verification")=="verified_changed_clauses"],
        docs,snapshots)
    # Independently queried official downstream documents may not themselves
    # be recently revised. Include only those whose actual text was reread
    # and passed the same provision/formula proof.
    confirmed=list(state.get("confirmed_dependencies",{}).values())
    edges=graph["impacts"]+confirmed
    seen=set();valid=[]
    for edge in edges:
        key=(edge["source_event"],edge.get("target_serial",edge["target_document"]),
             edge.get("source_article"),edge.get("target_article"),edge["type"])
        if key not in seen and edge.get("affected_verified"):
            seen.add(key);valid.append(edge)
    graph["impacts"]=valid
    graph["statistics"]["actual_dependencies"]=len(valid)
    groups=events.cluster_promulgations(all_events)
    delegated=state.get("delegation_links",{})
    downstream_by_source={}
    for link in graph["impacts"]:
        downstream_by_source.setdefault(link["source_event"],[]).append(link)
    primary=[]
    auxiliary=[]
    for g in groups:
        members=g["members"]
        links=[x for m in members for x in downstream_by_source.get(m["id"],[])]
        g["dependencies"]=links
        g["official_review_candidates"]=[x for m in members for x in delegated.get(m["id"],{}).get("links",[])]
        g["source_docs"]=[{
            "id":m["id"],"title":m["title"],"kind":m["kind"],
            "verification":m["verification"],"lifecycle":m["lifecycle"],
            "revision":m["revision"],"ministry":m["ministry"],
            "url":m["url"],"published":m["promulgated_at"],
            "effective":m["effective_date"],
            "changed_articles":m.get("changed_articles",[])[:18],
            "excerpts":m.get("excerpts",[])[:12],
            # The public comparison must not be limited by how many
            # agency-action excerpts can be generated from this law.
            "source_pairs":source_change.source_pairs(m.get("changes",[])),
            "actor_duties":m.get("actors",[])[:20],
            "needs_attachment_check":m.get("needs_attachment_check",False),
            "notes":m.get("notes",[]),
            "unresolved_attachments":m.get("unresolved_attachments",[]),
            "comparison":m.get("comparison")} for m in members]
        del g["members"]
        g["importance"]=(min(8,len(links))*12+
                         min(15,len(members))*4+
                         min(20,g["agency_count"])*3+
                         (20 if g["verified_count"] else 0))
        # A change with content, a real dependent rule, or an actual official
        # multi-law promulgation is the default. Other entries remain in
        # the complete, searchable Official Changes tab.
        if links or (g["source_count"]>1 and g["verified_count"]>0) or any(
            m["verification"] in ("verified_changed_clauses",
                                  "verified_annual_replacement",
                                  "verified_enactment","verified_repeal_notice")
            and (m.get("changed_articles") or m["lifecycle"] in ("enactment","repeal"))
            for m in members):
            primary.append(g)
        else:auxiliary.append(g)
    def recency(group):return group.get("date","")
    primary.sort(key=lambda g:(g["importance"],recency(g)),reverse=True)
    auxiliary.sort(key=recency,reverse=True)
    return primary,auxiliary,graph

def build(state,today):
    groups,other,graph=output_groups(state)
    coverage=state.get("coverage",[])
    # Every page declares how much of the official catalogue has not yet had
    # a checked before/after version. Do not claim complete collection.
    incomplete=[s for s in coverage if not s["complete"]]
    official={key for key,row in state["catalog"].items()
              if row.get("discovery_kind")!="legacy_index_only_not_verified"}
    checked=set(state["inspected"]) & official
    report={
        "schema":"policy-domino-v4",
        "generated_at":api.stamp(),
        "status":"PARTIAL" if incomplete or len(official)>len(checked) else "COMPLETE",
        "collection":{
            "official_catalogue":len(official),
            "fresh_official_index":len(official),
            "legacy_index_pending_recheck":sum(x.get("discovery_kind") == "legacy_index_only_not_verified"
                for x in state["catalog"].values()),
            "detailed_checked":len(checked),
            "pending_details":len(official-checked),
            "retry_pending":sum(x.get("verification") in
                 ("detail_failed","partial_official_text","official_record_only")
                 for x in state["inspected"].values()),
            "pending_downstream_verification":len(state.get("dependent_queue",{})),
            "downstream_documents_checked":len(state.get("dependent_checked",{})),
            "windows_checked":len(coverage),
            "incomplete_windows":len(incomplete),
            "recent_incomplete":incomplete[-8:],
            "backfill_cursor_days":state.get("backfill_cursor_days",0),
            "latest_official_scan":state.get("latest_official_scan",""),
            "last_official_scan_error":state.get("last_official_scan_error",""),
            "retained_complete_clause_versions":sum(
                bool(x.get("complete_source")) for x in state.get("verified_snapshots",{}).values()),
            "detail_work_budget_exceeded":bool(state.get("detail_work_budget_exceeded")),
            "scope":"공식 변경이력·법령·행정규칙·자치법규 변경일 기준",
            "whole_corpus_complete":False},
        "links":{
            "confirmed_provision_or_formula_use":graph["statistics"]["actual_dependencies"],
            "title_or_wrong_article_only":graph["statistics"]["noncausal_citations"],
            "official_delegation_review_candidates":sum(len(x.get("official_review_candidates",[])) for x in groups+other),
            "unverified_implementation":True
        },
        "featured_events":groups,
        "other_events":other,
        "explanation":"문서명 인용만으로 정책 파급 또는 기관별 조치가 확정되지 않습니다."}
    return report

def run():
    started=time.monotonic()
    # Leave room for canonical publication and GitHub commit in the 50-minute
    # Actions job. Incomplete verification remains queued for the next run.
    deadline=started+max(180,min(2400,int(os.getenv(
        "PD_V4_RUN_BUDGET_SECONDS","1200"))))
    state=load_json(STATE,{"catalog":{},"inspected":{},"coverage":[],
                           "verified_snapshots":{},"attempts":{}})
    today=dt.date.today()
    scanning=True
    if os.getenv("PD_V4_OFFLINE")=="1":scanning=False
    if scanning:
        try:
            scan_new(state,today,checkpoint=lambda current:save_json(STATE,current))
        finally:
            # Write partial official evidence and coverage failures on exception.
            # A later run resumes from this same append-only official catalogue.
            save_json(STATE,state)
    workload=pick_work(state,today,int(os.getenv("PD_V4_DETAILS","14")))
    state["detail_work_budget_exceeded"]=False
    for record in workload:
        if time.monotonic()>=deadline:
            state["detail_work_budget_exceeded"]=True
            break
        k=events.key(record)
        try:
            item,contents=prepare_document_record(record,state)
            previous=state["inspected"].get(k,{})
            if not (previous.get("verification","").startswith("verified_") and
                    not item["verification"].startswith("verified_")):
                state["inspected"][k]=item
            if item["verification"] in ("detail_failed","partial_official_text"):
                state.setdefault("retry_after",{})[k]=str(today+dt.timedelta(days=2))
            elif item.get("needs_attachment_check"):
                state.setdefault("retry_after",{})[k]=str(today+dt.timedelta(days=7))
            elif item["verification"]=="official_record_only":
                state.setdefault("retry_after",{})[k]=str(today+dt.timedelta(days=21))
            else:
                state.setdefault("retry_after",{}).pop(k,None)
            # prepare_document_record already captured only complete,
            # annex-checked source text for both document versions.
        except Exception as exc:
            # Failure is explicitly recorded and retried; never converted to
            # a fabricated "changed policy" or deleted from the queue.
            state["attempts"][k]=state["attempts"].get(k,0)+1
            state.setdefault("retry_after",{})[k]=str(today+dt.timedelta(days=2))
            state.setdefault("errors",[]).append({"id":k,
                "error":type(exc).__name__+": "+str(exc)[:140]})
        if (len(state.get("inspected",{}))+len(state.get("attempts",{})))%12==0:
            save_json(STATE,state)
    # Official delegation endpoint is an independent source of clause-scoped
    # review candidates; it is not an automatic impact or compliance order.
    todo=[x for x in state["inspected"].values() if
          x.get("source")=="law" and x.get("changed_articles") and
          x["id"] not in state.setdefault("delegation_links",{})]
    todo.sort(key=lambda x:x.get("promulgated_at",""),reverse=True)
    for event in todo[:int(os.getenv("PD_V4_DELEGATIONS","4"))]:
        if time.monotonic()>=deadline:
            state["detail_work_budget_exceeded"]=True
            break
        try:
            record=state["catalog"][event["id"]]
            state["delegation_links"][event["id"]]=official_links.delegated_changed_articles(
                record,event["changed_articles"])
        except Exception as exc:
            state.setdefault("errors",[]).append({"source":"lsDelegated",
                "title":event["title"],"error":type(exc).__name__+": "+str(exc)[:140]})
    if os.getenv("PD_V4_SKIP_DEPENDENTS")!="1" and time.monotonic()<deadline:
        try:
            dstatus=dependents.search_and_process(state,read_document,
                max_parents=int(os.getenv("PD_V4_SEARCH_PARENTS","2")),
                max_docs=int(os.getenv("PD_V4_VERIFY_DEPENDENTS","12")))
            state["dependent_last_status"]=dstatus
        except Exception as exc:
            state.setdefault("errors",[]).append({"source":"downstream",
                "error":type(exc).__name__+": "+str(exc)[:150]})
    if time.monotonic()>=deadline:
        state["detail_work_budget_exceeded"]=True
    data=build(state,today)
    save_json(STATE,state)
    save_json(OUTPUT,data)
    print("V4_RUN",json.dumps({
        "official_catalogue":data["collection"]["official_catalogue"],
        "verified_details":data["collection"]["detailed_checked"],
        "pending":data["collection"]["pending_details"],
        "featured":len(data["featured_events"]),
        "actual_dependencies":data["links"]["confirmed_provision_or_formula_use"],
        "incomplete_windows":data["collection"]["incomplete_windows"]
    },ensure_ascii=False))
    return data

if __name__=="__main__":run()
