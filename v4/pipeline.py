"""Policy Domino v4 / staged official-source pipeline.

No keyword-to-agency inference. Publication of an announcement, verified
textual change, downstream legal dependency and actual implementation are
four DIFFERENT states. This pipeline never silently treats one as another.
"""
from __future__ import annotations
import datetime as dt,json,os,re
from pathlib import Path
from v2 import collector as api
from v4 import collect_index,events,relationships,official_links,dependents

ROOT=Path(__file__).resolve().parents[1]
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
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(item,ensure_ascii=False,indent=2),"utf8")

def bootstrap_old_index(state):
    """Retain older official citations as an index, not as trusted findings.

    The V2 comparison/extracted agency cards are discarded. Only stable
    metadata (ID, serial, promulgation date) may enter v4 candidate queue.
    """
    if state.get("bootstrapped"):return
    earlier=load_json(ROOT/"data"/"v2_state.json",{})
    raw=[x for x in earlier.get("pending",[]) if isinstance(x,dict)]
    raw +=[x for x in earlier.get("events",{}).values() if isinstance(x,dict)]
    for x in raw:
        source=x.get("source")
        if source not in ("law","admrul"):continue
        issued=x.get("published_at") or x.get("promulgated_at")
        if not all((x.get("stable_id"),x.get("serial"),issued,x.get("title"))):
            continue
        rec={k:x.get(k,"") for k in
             ("source","stable_id","serial","title","published_at",
              "effective_date","number","revision","kind","ministry","url")}
        rec["published_at"]=issued
        rec["discovery_kind"]="legacy_index_only_not_verified"
        state.setdefault("catalog",{})[events.key(rec)]=rec
    state["bootstrapped"]=True
    state["bootstrap_records"]=len(state.get("catalog",{}))

def scan_new(state,today):
    # The change-history index is the primary legal event entry point.
    # Yesterday and recent days are rescanned to tolerate delayed indexing.
    days=[str(today-dt.timedelta(days=i)) for i in range(1,5)]
    collect_index.ingest_changes(state,days,max_pages=10)
    backfill=state.get("backfill_cursor_days",0)
    # A moving 7-day sweep discovers administrative acts that became public
    # before this monitor was installed. It never searches hardcoded sectors.
    first=str(today-dt.timedelta(days=backfill+10))
    last=str(today-dt.timedelta(days=backfill+4))
    for source in SUPPORTED:
        collect_index.ingest_index(state,source,[(first,last)],max_pages=12)
    state["backfill_cursor_days"]=0 if backfill>=210 else backfill+7
    state["latest_official_scan"]=today.isoformat()

def candidate_rank(record,today):
    """Document-wide generic signals only: source proof, dates, lifecycle.

    An issuing ministry's name and policy title keywords are not relevance
    scores; neither can prove an impact.
    """
    kind=record.get("discovery_kind","")
    future=record.get("effective_date","")>today.isoformat()
    age=record.get("published_at","")
    recent=age>=str(today-dt.timedelta(days=45))
    verified_history=kind=="official_law_change_history"
    priority=(85 if verified_history else 0)+(30 if future else 0)+(
       25 if recent else 0)
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
    waiting=[x for k,x in catalog.items() if k not in processed]
    ranked=sorted(waiting,key=lambda x:(
        candidate_rank(x,today)[0]-(attempts.get(events.key(x),0)*16),
        candidate_rank(x,today)[1],
        candidate_rank(x,today)[2]),reverse=True)
    # Keep most urgent events AND fresh official changes; do not starve newer
    # updates behind a years-old backlog.
    urgent=ranked[:max(1,(limit*2)//3)]
    seen={events.key(x) for x in urgent}
    fresh=sorted([x for x in waiting if events.key(x) not in seen],
                 key=lambda x:x.get("published_at",""),reverse=True)
    return (urgent+fresh[:max(0,limit-len(urgent))])[:limit]

def read_document(record):
    if record["source"] in ("law","admrul"):
        return api.read_clauses(record)
    # Official local rules use MST=serial; parse only real provision elements.
    root=api.request("ordin",endpoint="lawService.do",MST=record["serial"])
    clauses={}
    for unit in root.iter():
        if unit.tag.split("}")[-1] not in ("조문단위","조문"):continue
        number=api.field(unit,"조문번호")
        if not number:continue
        contents=api.field(unit,"조내용") or api.field(unit,"조문내용")
        if contents:clauses["제"+number+"조"]=contents[:12000]
    if not clauses:
        raise RuntimeError("자치법규 공식 조문 구분을 추출하지 못함")
    return clauses

def prepare_document_record(record,state):
    """Fetch a source record; do not replace existing verified evidence with
    a lexical hit or a lower-trust V2 snapshot.
    """
    def prior(r,records=None):
        return events.predecessor(r,state.get("catalog",{}).values())
    return events.inspect(record,state.get("catalog",{}).values(),
                          load=read_document,history=prior)

def output_groups(state):
    all_events=list(state.get("inspected",{}).values())
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
            "actor_duties":m.get("actors",[])[:20],
            "needs_attachment_check":m.get("needs_attachment_check",False),
            "notes":m.get("notes",[]),
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

def recent_uninspected(state,limit=300):
    """Expose actual official index rows without inventing before/after analysis.

    This only tells the interface that the version was indexed. The article,
    responsible implementing agency and duties remain UNKNOWN until inspected.
    Mix every discovered document type rather than favoring one policy area.
    """
    catalog=state.get("catalog",{})
    inspected=state.get("inspected",{})
    waiting=[
        r for key,r in catalog.items()
        if key not in inspected and r.get("discovery_kind")!="legacy_index_only_not_verified"
        and r.get("title") and r.get("published_at")
        and r.get("source") in ("law","admrul","ordin")
    ]
    waiting.sort(key=lambda r:(r["published_at"],r.get("serial","")),reverse=True)
    queues={k:[r for r in waiting if r["source"]==k]
            for k in ("law","admrul","ordin")}
    rows=[]
    while len(rows)<limit and any(queues.values()):
        for kind in ("law","admrul","ordin"):
            if len(rows)>=limit:break
            if not queues[kind]:continue
            r=queues[kind].pop(0)
            rows.append({
                "record_id":events.key(r),"title":r["title"],
                "source":r["source"],"kind":r.get("kind",""),
                "revision":r.get("revision",""),
                "published_at":r["published_at"],
                "effective_date":r.get("effective_date",""),
                "ministry":r.get("ministry",""),
                "url":r.get("url",""),
                "verification":"official_index_only",
                "source_kind":r.get("discovery_kind","")
            })
    return rows

def build(state,today):
    groups,other,graph=output_groups(state)
    coverage=state.get("coverage",[])
    # Every page declares how much of the official catalogue has not yet had
    # a checked before/after version. Do not claim complete collection.
    incomplete=[s for s in coverage if not s["complete"]]
    report={
        "schema":"policy-domino-v4",
        "generated_at":api.stamp(),
        "status":"PARTIAL" if incomplete or len(state["catalog"])>len(state["inspected"]) else "COMPLETE",
        "collection":{
            "official_catalogue":len(state["catalog"]),
            "fresh_official_index":sum(x.get("discovery_kind") != "legacy_index_only_not_verified"
                for x in state["catalog"].values()),
            "legacy_index_pending_recheck":sum(x.get("discovery_kind") == "legacy_index_only_not_verified"
                for x in state["catalog"].values()),
            "detailed_checked":len(state["inspected"]),
            "pending_details":max(0,len(state["catalog"])-len(state["inspected"])),
            "pending_downstream_verification":len(state.get("dependent_queue",{})),
            "downstream_documents_checked":len(state.get("dependent_checked",{})),
            "windows_checked":len(coverage),
            "incomplete_windows":len(incomplete),
            "recent_incomplete":incomplete[-8:],
            "backfill_cursor_days":state.get("backfill_cursor_days",0),
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
        "pending_index":recent_uninspected(state),
        "explanation":"공식 목록은 변경 사건의 존재만 확인하며 신구 조문 비교·기관별 영향은 별도 검증합니다."}
    return report

def run():
    state=load_json(STATE,{"catalog":{},"inspected":{},"coverage":[],
                           "verified_snapshots":{},"attempts":{}})
    bootstrap_old_index(state)
    today=dt.date.today()
    scanning=True
    if os.getenv("PD_V4_OFFLINE")=="1":scanning=False
    if scanning:
        scan_new(state,today)
    workload=pick_work(state,today,int(os.getenv("PD_V4_DETAILS","14")))
    for record in workload:
        k=events.key(record)
        try:
            item,contents=prepare_document_record(record,state)
            state["inspected"][k]=item
            if contents and item["verification"] in (
                "verified_changed_clauses","verified_annual_replacement",
                "verified_enactment"):
                state["verified_snapshots"][k]={
                    "source":record["source"],"stable_id":record["stable_id"],
                    "serial":record["serial"],"clauses":contents}
        except Exception as exc:
            # Failure is explicitly recorded and retried; never converted to
            # a fabricated "changed policy" or deleted from the queue.
            state["attempts"][k]=state["attempts"].get(k,0)+1
            state.setdefault("errors",[]).append({"id":k,
                "error":type(exc).__name__+": "+str(exc)[:140]})
    # Official delegation endpoint is an independent source of clause-scoped
    # review candidates; it is not an automatic impact or compliance order.
    todo=[x for x in state["inspected"].values() if
          x.get("source")=="law" and x.get("changed_articles") and
          x["id"] not in state.setdefault("delegation_links",{})]
    todo.sort(key=lambda x:x.get("promulgated_at",""),reverse=True)
    for event in todo[:int(os.getenv("PD_V4_DELEGATIONS","4"))]:
        try:
            record=state["catalog"][event["id"]]
            state["delegation_links"][event["id"]]=official_links.delegated_changed_articles(
                record,event["changed_articles"])
        except Exception as exc:
            state.setdefault("errors",[]).append({"source":"lsDelegated",
                "title":event["title"],"error":type(exc).__name__+": "+str(exc)[:140]})
    if os.getenv("PD_V4_SKIP_DEPENDENTS")!="1":
        try:
            dstatus=dependents.search_and_process(state,read_document,
                max_parents=int(os.getenv("PD_V4_SEARCH_PARENTS","2")),
                max_docs=int(os.getenv("PD_V4_VERIFY_DEPENDENTS","12")))
            state["dependent_last_status"]=dstatus
        except Exception as exc:
            state.setdefault("errors",[]).append({"source":"downstream",
                "error":type(exc).__name__+": "+str(exc)[:150]})
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
