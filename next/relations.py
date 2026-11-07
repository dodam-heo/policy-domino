"""Link dependent changes only when an official amendment reason explicitly cites the source law's promulgation number."""
from __future__ import annotations
import re

REFERENCE = re.compile(r"(대통령령|총리령|법률|[가-힣]{2,16}부령)\s*(제\s*\d+\s*호)")

def norm_number(number):
    return re.sub(r"\s+","",str(number or ""))

def link_proven_dependencies(events,actions):
    by_number={}
    by_id={}
    for event in events:
        by_id[event["event_id"]]=event
        kind=(event.get("law_type") or "").strip()
        number=norm_number(event.get("promulgation_number"))
        if kind and number:by_number[(kind,number)]=event
        event["downstream_changes"]=[]
        event["upstream_changes"]=[]
    found=set()
    for child in events:
        evidence=child.get("amendment_reason","")
        for m in REFERENCE.finditer(evidence):
            parent=by_number.get((m.group(1),norm_number(m.group(2))))
            if not parent or parent["event_id"]==child["event_id"]:continue
            key=(parent["event_id"],child["event_id"])
            if key in found:continue
            found.add(key)
            child["upstream_changes"].append({
                "event_id":parent["event_id"],
                "title":parent.get("title",""),
                "reference":m.group(0),
                "basis_url":child.get("amendment_url") or child.get("url","")
            })
            parent["downstream_changes"].append({
                "event_id":child["event_id"],"title":child.get("title",""),
                "institution":child.get("ministry",""),
                "effective_date":child.get("effective_date",""),
                "amendment_url":child.get("amendment_url") or child.get("url",""),
                "status":"연관 규정 개정 확인",
                "evidence":"해당 제·개정이유에서 "+m.group(0)+"를 직접 인용"
            })
    by_child={x["event_id"]:[p["event_id"] for p in x["upstream_changes"]] for x in events}
    for action in actions:
        action["upstream_event_ids"]=by_child.get(action["event_id"],[])
        action["impact_link_basis"]=(
            "하위 시행규칙의 제·개정이유가 상위 법령의 공포번호를 명시"
            if action["upstream_event_ids"] else
            "해당 개정문에서 기관별 업무 기준을 직접 변경"
        )
    return {"relationships":len(found),
            "source_events_with_dependents":sum(bool(x["downstream_changes"]) for x in events),
            "linked_institutions":len({x.get("ministry") for x in events if x["upstream_changes"]})}
