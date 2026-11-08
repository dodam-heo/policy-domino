"""Recalculate evidence-gated agency effects from stored official source texts.

Used for rapid, safe UI correction. Never fabricates new data, and never
assumes a particular agency, law name, prior amount, or change event.
"""
import json
from pathlib import Path
from v3 import impact,policy_graph

ROOT=Path(__file__).resolve().parents[1]

def run():
    path=ROOT/"site"/"data.json"
    source=json.loads(path.read_text("utf8"))
    if source.get("schema")!="policy-domino-impact-v3":
        raise RuntimeError("Expected previously collected official source data")
    model=impact.analyze({"events":source.get("events",[]),
        "health":source.get("source_health",{}),
        "generated_at":source.get("generated_at","")})
    snaps=json.loads((ROOT/"data"/"v2_state.json").read_text("utf8")).get("snapshots",{})
    model["impact_health"]["cross_policy_links"]=policy_graph.link_documents(model["events"],snaps)
    # Retain only references whose official evidence includes a quoted exact
    # standard (not a keyword or law-name similarity). Even these references
    # remain research leads, not inferred agency obligations.
    for e in model["events"]:
        if e.get("impact_category")=="폐지·효력종료":
            e["dependent_rules"]=[];continue
        old=next((x for x in source["events"] if x["id"]==e["id"]),{})
        e["dependent_rules"]=[
            x for x in old.get("dependent_rules",[])
            if x.get("verified_reference") and
            x.get("reference") and
            "「"+x["reference"]+"」" in x.get("excerpt","")
        ]
    model["impact_health"]["dependent_rules_found"]=sum(
        len(e.get("dependent_rules",[])) for e in model["events"])
    model["impact_health"]["dependency_actors_to_review"]=0
    model["corrected_from_snapshot"]=True
    model["method"]={
        "collection":"기존 공식 법령·행정규칙 수집자료의 재평가 (실시간 재수집 아님)",
        "agency":"변경된 동일 조문에서 집행주체와 명시적 의무가 함께 확인된 경우만 조치 생성",
        "dependencies":"공식적 명시 인용·적용 문맥만 연결, 기관 의무 자동 생성 금지",
        "repeal":"규정 폐지는 독립 사건, 이전 문서의 의무를 새 기관 의무로 전환하지 않음"
    }
    assert all(not e.get("institution_actions")
               for e in model["events"] if "폐지" in str(e.get("revision","")))
    assert all(not e.get("dependency_actions") for e in model["events"])
    print("GATED_REEVALUATION",json.dumps({
        "documents":len(model["events"]),
        "repeals":model["impact_health"]["repeal_events"],
        "confirmed_actor_tasks":model["impact_health"]["direct_actor_actions"],
        "official_reference_links":model["impact_health"]["cross_policy_links"]["links"],
        "old_event_actions":sum(len(e.get("institution_actions",[]))
            for e in source["events"]),
    },ensure_ascii=False))
    path.write_text(json.dumps(model,ensure_ascii=False,indent=2),"utf8")
    return model

if __name__=="__main__":run()
