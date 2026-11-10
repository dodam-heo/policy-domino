"""Evidence-only reach assessment; distinct from social importance or implementation.

The result is determined by confirmed target institutions and confirmed
changed-provision links. Unverified mentions do not add impact.
"""
from __future__ import annotations


def _normalize(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def assess_impact_scope(event, actions):
    """Scope of documented institutional/regulatory consequences, not a
    judgement of severity, population affected or actual implementation.

    Titles, article mentions, total change count and the number of clauses
    never independently qualify a policy as high impact.
    """
    actors={_normalize(a.get("agency")) for a in actions if
            a.get("event_id")==event["event_id"] and a.get("agency") and
            a.get("evidence_scope") in (
                "v4_verified_source",
                "service_formula_dependency_verified",
            "service_cited_changed_article_verified")}
    legal_links={
        (_normalize(x.get("title")),_normalize(x.get("article")))
        for x in event.get("downstream_changes",[])
        if x.get("status")=="변경 조항 적용 관계 확인"
        and x.get("title") and x.get("article") and x.get("evidence")
    }
    wide=len(actors)>=2 or len(legal_links)>=2
    if len(actors)>=2 and len(legal_links)>=2:
        reason=f"기관별 검토 {len(actors)}곳 · 실제 변경 조항 적용 규정 {len(legal_links)}건"
    elif len(actors)>=2:
        reason=f"변경된 업무의 직접 검토 기관 {len(actors)}곳"
    elif len(legal_links)>=2:
        reason=f"실제 변경 조항을 적용하는 다른 규정 {len(legal_links)}건"
    else:
        reason="확인된 기관·제도 영향 범위가 분류 기준에 미달"
    return {
        "impact_level":"high" if wide else "not_assessed",
        "impact_reason":reason,
        "impact_scope":{
            "institutions":len(actors),
            "proven_dependent_rules":len(legal_links),
            "criteria":"직접 검토 기관 2곳 이상 또는 변경 조항 적용 규정 2건 이상",
            "provisional":False,
            "note":"공식 신구 조문에 따른 파급 범위. 기관별 내부 반영·사회적 중요도는 미확인"
        }
    }
