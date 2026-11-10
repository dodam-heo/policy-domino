"""Policy Domino Classic / rebuild actionable V2-style view from source evidence.

No hardcoded law names, sectors, agency IDs or numeric policy examples.
V4 source-backed articles and V2's *original official amendment directives*
remain independent, visibly labelled provenance. Old V2-derived actions are
never represented as freshly checked/confirmed implementation.
"""
from __future__ import annotations
import collections
import json
from pathlib import Path
from policy_domino.engine.classic_pages import publish_pages
from policy_domino.engine.impact_scope import assess_impact_scope
from policy_domino.engine.agency_actions import TRUSTED, group_event, unique_actions
from policy_domino.engine.legacy_recheck import legacy_fallback
from policy_domino.analysis_evidence import has_verified_action, evidence_identity
from policy_domino.public_services import load_catalog, service_edges, agency_service_action

ROOT=Path(__file__).resolve().parents[2]
V4=ROOT/"site"/"v4"/"data.json"
LEGACY=ROOT/"site"/"classic"/"legacy_source.json"
DEST=ROOT/"site"/"classic"/"data.json"

def build(v4,legacy,service_catalog=None):
    events=[];actions=[]
    source_titles=set()
    for g in v4.get("featured_events",[])+v4.get("other_events",[]):
        e,aa=group_event(g)
        if not e:continue
        events.append(e);actions+=aa
        source_titles.update(doc.get("title","") for doc in g.get("source_docs",[])
                             if doc.get("verification","").startswith("verified_"))
    old_events,old_actions=legacy_fallback(legacy,source_titles)
    events+=old_events;actions+=old_actions
    actions=unique_actions(actions)
    # One source-verified public-service dependency path, not example-specific
    # agency mappings. The independent Gov24 catalogue is used read-only.
    if service_catalog is None:
        service_catalog = load_catalog()
    event_by_id = {e["event_id"]: e for e in events}
    service_links = service_edges(events, service_catalog)
    for edge in service_links:
        actions.append(agency_service_action(event_by_id[edge["event_id"]], edge))
    event_ids={e["event_id"] for e in events}
    actions=[a for a in actions if a.get("event_id") in event_ids]
    # Rank policy events first by VERIFIED operational work and cross-institution
    # dependencies. Old V2 items remain clearly marked historic recheck.
    action_counts=collections.Counter(a["event_id"] for a in actions)
    for e in events:
        e.update(assess_impact_scope(e,actions))
        e["impact_priority"]=e.get("impact_priority",0)+min(40,action_counts[e["event_id"]]*3)
    events.sort(key=lambda e:(e["impact_priority"],e.get("promulgated_at","")),reverse=True)
    # Exactly one canonical evidence hash, shared by both the LLM cache and
    # browser presentation. AI never writes into or overrides official facts.
    event_index = {e["event_id"]: e for e in events}
    for action in actions:
        if has_verified_action(action) and action.get("event_id") in event_index:
            action["evidence_fingerprint"] = evidence_identity(
                event_index[action["event_id"]], action
            )
    checked=v4.get("collection",{})
    return {
        "schema":"policy-domino-next-v1",
        "generated_at":v4.get("generated_at"),
        "health":{
            "source_status":"공식 공포·개정문 연결",
            "partial":True,
            "official_records":len(events),
            "compared":len([e for e in events if e["presentation_source"]=="v4_official_source"]),
            "amendments_read":len(events),
            "amendments_verified_total":checked.get("detailed_checked",0),
            "catalogue_candidates":checked.get("official_catalogue",0),
            "v4_official_index":checked.get("fresh_official_index",0),
            "pending_details":checked.get("pending_details",0),
            "legacy_recheck":len(old_events),
            "public_service_catalogue":len(service_catalog.get("services", {})),
            "public_service_dependencies":len(service_links),
            "error":"기관별 조치 카드에 표시된 내용은 검토 대상이며, 실제 반영 상태는 미확인입니다."
        },
        "events":events,
        "actions":actions,
        "status_counts":{},
        "disclaimer":"공식 신구 조문 대조와 이전 V2 개정 지시문은 출처와 검증 상태를 구분했습니다."
    }

def run():
    v4=json.loads(V4.read_text("utf8"))
    legacy=json.loads(LEGACY.read_text("utf8"))
    if v4.get("schema")!="policy-domino-v4":raise ValueError("Invalid V4 source")
    if legacy.get("schema")!="policy-domino-next-v1":raise ValueError("Invalid classic baseline")
    result=build(v4,legacy)
    assert result["events"]
    assert all(x.get("basis","").startswith(TRUSTED) for x in result["actions"])
    assert all(a["event_id"] in {e["event_id"] for e in result["events"]}
               for a in result["actions"])
    DEST.write_text(json.dumps(result,ensure_ascii=False,indent=2),"utf8")
    publish_pages()
    by_source=collections.Counter(a["evidence_scope"] for a in result["actions"])
    print("CLASSIC_V2_UX_V4_SOURCE",
          json.dumps({"events":len(result["events"]),"actions":len(result["actions"]),
            "by_source":dict(by_source),
            "original_v2_recheck":result["health"]["legacy_recheck"],
            "first_titles":[e["title"] for e in result["events"][:8]],
            "public_service_dependencies":result["health"]["public_service_dependencies"],
            "public_service_catalogue":result["health"]["public_service_catalogue"]},ensure_ascii=False))
    return result

if __name__=="__main__":run()
