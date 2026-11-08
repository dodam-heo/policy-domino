"""Re-evaluate stored source-backed changes after an agency-scope bugfix.

This only interprets already cached official before/after texts; it does not
claim a new external crawl or invent verified links or numeric changes.
"""
from __future__ import annotations
import json
from pathlib import Path
from v2 import collector
from v3 import impact,agency_resolver,policy_graph,dependencies

ROOT=Path(__file__).resolve().parents[1]

def run():
    path=ROOT/"site"/"data.json"
    current=json.loads(path.read_text("utf8"))
    if current.get("schema")!="policy-domino-impact-v3":
        raise ValueError("Expected previously collected official impact data")
    src={x["id"]:x for x in current["events"]}
    model=impact.analyze({"events":current["events"],
                          "generated_at":current.get("generated_at",""),
                          "health":current.get("source_health",{})})
    snapshots=json.loads((ROOT/"data"/"v2_state.json").read_text("utf8")).get("snapshots",{})
    extra=0
    for event in model["events"]:
        source=snapshots.get(collector.uid(event["source"],event["stable_id"]),{})
        if str(source.get("serial",""))==str(event.get("serial","")):
            actors=agency_resolver.assign(event,source.get("clauses",{}))
            event["institution_actions"].extend(actors)
            extra+=len(actors)
    model["impact_health"]["direct_actor_actions"]+=extra
    model["impact_health"]["full_source_actor_actions"]=extra
    model["impact_health"]["cross_policy_links"]=policy_graph.link_documents(model["events"],snapshots)
    for event in model["events"]:
        # A previously verified dependent rule can be retained with its official
        # excerpt, but never transplant speculative org cross-links.
        if impact.organization_owner(event):continue
        original=src[event["id"]]
        verified=[x for x in original.get("dependent_rules",[])
                  if x.get("excerpt") and x.get("target_url")]
        event["dependent_rules"]=verified
    dependencies.add_dependency_agencies(model["events"])
    model["impact_health"]["dependent_rules_found"]=sum(
        len(e.get("dependent_rules",[])) for e in model["events"])
    model["impact_health"]["dependency_actors_to_review"]=sum(
        len(e.get("dependency_actions",[])) for e in model["events"])
    model["method"]={"collection":"기존 법제처 공식 신구조문 데이터 (재수집 아님)",
                     "impact":"변경 조문과 실제 업무주체 관계 재분석",
                     "note":"부처별 정원은 해당 직제 표에 한하여 적용; 타 기관 자동 전파 차단"}
    target=[e for e in model["events"] if e["title"]=="개인정보 보호위원회 직제"]
    if target:
        e=target[0]
        assert len(e["institution_actions"])==1, "Spurious staffing agency cards remain"
        a=e["institution_actions"][0]
        assert a["agency"]=="개인정보 보호위원회"
        assert "공무원 정원 총계 192명 → 197명" in a["what_to_change"]
        assert not e.get("dependency_actions")
        assert not e.get("policy_links")
        print("REAL_STAFFING_CORRECTION",json.dumps({
            "owner":a["agency"],"target":a["target_location"],
            "change":a["what_to_change"],"other_agencies":0
        },ensure_ascii=False))
    model["corrected_from_snapshot"]=True
    path.write_text(json.dumps(model,ensure_ascii=False,indent=2),"utf8")
    return model

if __name__=="__main__":run()
