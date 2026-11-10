"""Read-only compatibility bridge for older V2 official amendment directives.

Legacy actions require a matching literal before/after in the official
directive and stay explicitly marked for current-source re-verification.
"""
from __future__ import annotations
import collections
from v4.agency_actions import TRUSTED, article_key, clean, source_url, unique_actions


def legacy_event_ok(e):
    return bool(e.get("event_id") and e.get("title") and
                e.get("article_differences") and
                all(str(x.get("source_url","")).startswith(TRUSTED)
                    for x in e.get("article_differences",[]) if x.get("source_url")))

def legacy_action_ok(a,e):
    # Every old V2 card must have a MATCHING official amendment directive.
    # An inferred cross-ministry role with no old-new literal pair is not
    # reliable enough to be promoted as a fresh official change action.
    pairs=a.get("changes",[])
    if not pairs:return False
    # Annual official standards can identify a table row by field rather
    # than the host act's article number; the field must match the ACTUAL
    # official-before/after source data, not an unrelated subject term.
    row_names={article_key(p.get("field")) for p in pairs}
    diffs=[d for d in e.get("article_differences",[])
           if article_key(d.get("article"))==article_key(a.get("article"))
           or article_key(d.get("article")) in row_names]
    if not diffs:return False
    for d in diffs:
        directive=clean(d.get("directive"))
        if not directive or not str(d.get("source_url","")).startswith(TRUSTED):
            continue
        for p in pairs:
            candidates=[
                (clean(p.get("old_literal")),clean(p.get("new_literal"))),
                (clean(p.get("before")),clean(p.get("after")))
            ]
            if any(old and new and old in directive and new in directive
                   for old,new in candidates):
                return True
    return False

def legacy_fallback(source,verified_titles):
    extra_events=[];extra_actions=[]
    group_actions=collections.defaultdict(list)
    for a in source.get("actions",[]):
        group_actions[a.get("event_id","")].append(a)
    for e in source.get("events",[]):
        if not legacy_event_ok(e) or e.get("title") in verified_titles:continue
        valid=[a for a in group_actions.get(e["event_id"],[]) if legacy_action_ok(a,e)]
        if not valid:continue
        event=dict(e)
        event["event_id"]="legacy:"+e["event_id"]
        event["comparison_status"]="이전 V2 공식 개정문 확인 · 최신 버전 재검증 대기"
        event["presentation_source"]="legacy_official_directive_awaiting_recheck"
        # Source-backed numeric standard announcements are visible alongside
        # organization changes; user experience must not be dominated by
        # a simultaneous restructuring decree simply because it has 8 files.
        event["impact_priority"]=10+len(valid)*2+(
            30 if e.get("law_type")=="고시·행정규칙" else 0)
        event["amendment_reason"]=clean(event.get("amendment_reason")) or (
            "이전 V2가 확보한 공식 개정문. 최신 법령 개정 여부와 기관별 "
            "반영 상태는 아직 재검증되지 않았습니다."
        )
        extra_events.append(event)
        for old in valid:
            a=dict(old)
            a["id"]="legacy:"+a["id"]
            a["event_id"]=event["event_id"]
            a["status"]="최신 근거 재확인 필요"
            a["confidence"]="이전 V2 공식 개정 지시문 대조"
            a["evidence_scope"]="legacy_official_directive_awaiting_recheck"
            a["verification_note"]=(
                "개정 지시문에 전후 값이 명시된 것은 확인했으나, "
                "최신 법령·하위규정과 실제 기관별 반영 상태는 검증 전입니다."
            )
            # Old system generated overly prescriptive compliance commands.
            # Rephrase as review task, while preserving EXACT actual changed
            # old/new values and field names sourced from the directive.
            a["required_change"]=(
                f"{a.get('agency','해당 기관')}의 {a.get('service','관련 업무')} "
                "운영 기준에서 해당 공식 개정 지시문에 명시된 변경값이 반영될 "
                "필요가 있는지 확인"
            )
            a["basis"]=source_url(a.get("basis"))
            extra_actions.append(a)
    return extra_events,unique_actions(extra_actions)

