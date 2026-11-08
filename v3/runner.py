"""Policy Domino impact-first production pipeline.

Stage 1: collect all official legal/regulatory revisions (v2 generic ingestion).
Stage 2: extract real before/after functional effects and affected statutory actors.
Stage 3: independently read candidate dependent rules and attach evidence.
Stage 4: publish only a transparent evidence/impact model to the public dashboard.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from v2 import collector
from v3 import impact, dependencies

ROOT=Path(__file__).resolve().parents[1]
V3_STATE=ROOT/"data"/"v3_state.json"

def load_json(path,default):
    try:return json.loads(path.read_text("utf-8"))
    except (ValueError,OSError):return default

def run():
    if os.getenv("PD_USE_EXISTING_RAW")=="1":
        raw=load_json(ROOT/"site"/"data.json",{})
        if raw.get("schema")!="policy-domino-v2":
            raise RuntimeError("실제 공식 수집 v2 자료가 없어서 통합 분석을 수행할 수 없습니다.")
    else:
        raw=collector.run()
    model=impact.analyze(raw)
    previous=load_json(V3_STATE,{"rule_cache":{}})
    cache=previous.get("rule_cache",{})
    if os.getenv("PD_SKIP_REMOTE_DEPENDENCIES")=="1":
        checked={"checked":0,"verified_dependents":0,"errors":[],"skipped":"오프라인 검증"}
    else:
        cache,checked=dependencies.discover(model["events"],maximum=14,cache=cache)
    dependencies.add_dependency_agencies(model["events"])
    model["impact_health"]["dependent_rules_checked"]=checked["checked"]
    model["impact_health"]["dependent_rules_found"]=checked["verified_dependents"]
    model["impact_health"]["dependency_errors"]=checked["errors"]
    model["impact_health"]["dependency_actors_to_review"]=sum(len(e.get("dependency_actions",[])) for e in model["events"])
    model["method"]={
        "collection":"법령·행정규칙 공식 변경목록 전체범위 순회",
        "policy_effects":"이전·현재 조문에서 실제 바뀐 문구만 추출",
        "agency_evidence":"법적 업무주체 명시와 소관기관 추적 후보를 별도 구분",
        "downstream":"공식 규정 본문의 인용·기준 적용문을 별도로 읽어 연결",
        "unverified":"실제 기관 내부 시스템 및 조치 완료 여부는 공개 데이터만으로 확정하지 않음",
    }
    output=ROOT/"site"/"data.json"
    output.write_text(json.dumps(model,ensure_ascii=False,indent=2),"utf-8")
    V3_STATE.write_text(json.dumps({"rule_cache":cache},ensure_ascii=False,indent=2),"utf-8")
    print(json.dumps({"schema":model["schema"],"input":len(model["events"]),
                      "practical":model["impact_health"]["substantive_policy_events"],
                      "named_actor_tasks":model["impact_health"]["direct_actor_actions"],
                      "referenced_dependents":checked["verified_dependents"],
                      "errors":len(checked["errors"])},ensure_ascii=False))
    return model

if __name__=="__main__":
    run()
