"""Evidence gate for policy consequences. No registered law, agency or policy examples.

Separate: (1) official changed document, (2) verified statutory duty of
an actor, (3) sourced regulatory reference, and (4) unknown implementation.
Do not synthesize agency instructions from keywords, shared titles, or
an issuer's identity.
"""
from __future__ import annotations
import re
from v3 import impact

ACTOR = re.compile(
    r"(?<![가-힣])("
    r"시장[·ㆍ, ]+군수[·ㆍ, ]+구청장|"
    r"[가-힣]{2,28}(?:부장관|청장|처장|위원장|이사장|"
    r"공단|공사|재단|원장|기관장|교육청)|"
    r"교육감|시장|군수|구청장|시[·ㆍ]도지사"
    r")\s*(?:은|는|이|가|에게|에서)\s*"
)

DUTY = re.compile(
    r"하여야\s*한다|해야\s*한다|하여야\s*하며|해야\s*하며|"
    r"할\s*수\s*있다|적용한다|산정한다|선정한다|접수한다|"
    r"지급한다|결정한다|통지한다|준수한다|등록한다|"
    r"제출한다|처리한다|인정한다|허가한다|수행한다|"
    r"관리한다|담당한다|정한다|변경한다"
)
TERMINATION = re.compile(r"폐지|실효|효력종료")
WORD = re.compile(r"[가-힣A-Za-z0-9]")
ORGANIZATION_MARKERS=("정원표","직제","부서","사무","업무","기구","소속기관")

def is_repeal(event):
    # Only authoritative document-level metadata; the word "폐지" in a
    # quoted provision does not make the entire document repealed.
    return bool(TERMINATION.search(str(event.get("revision",""))))

def local_excerpt(body, changed, width=150):
    if not body or not changed:return None
    # Avoid matching a bare one-character edit in another section.
    changed=str(changed).strip()
    if len(changed)<2 and not changed.isdigit():return None
    hit=body.find(changed)
    if hit<0:return None
    start=max(0,hit-width)
    end=min(len(body),hit+len(changed)+width)
    # Enforce the same logical sentence, not a distant role in the law.
    excerpt=body[start:end]
    return excerpt

def qualified_actor(excerpt,changed):
    if not excerpt or not DUTY.search(excerpt):return []
    actors=[]
    for match in ACTOR.finditer(excerpt):
        name=match.group(1)
        # Role must govern an operative phrase close to the changed text.
        tail=excerpt[match.end():]
        duty=DUTY.search(tail)
        if not duty or duty.start()>180:continue
        # Require the changed value/phrase in the same obligation window.
        segment=tail[:duty.end()+85]
        if changed not in segment and changed not in excerpt[max(0,match.start()-35):match.end()+50]:
            continue
        if name not in actors:actors.append(name)
    return actors[:8]

def action_for_change(event,change,effect):
    article=change.get("article","")
    new=change.get("after","")
    old=change.get("before","")
    changes=[]
    if effect.get("new"):changes.append((new,effect["new"]))
    if effect.get("old"):changes.append((old,effect["old"]))
    found=[]
    for body,changed in changes:
        excerpt=local_excerpt(body,changed)
        if not excerpt:continue
        for actor in qualified_actor(excerpt,changed):
            item={
                "agency":actor,"article":article,
                "work":(effect.get("operations") or ["업무 적용"])[0],
                "target_location":article,
                "what_to_change":(
                    (effect.get("old","")+" → "+effect.get("new",""))[:180]
                    if effect.get("old") and effect.get("new")
                    else ("신규: "+effect.get("new",""))[:180] if effect.get("new")
                    else ("삭제: "+effect.get("old",""))[:180]),
                "required_change":(
                    "변경된 공식 조문 "+article+"의 해당 업무 의무와 적용 기준을 "
                    "확인하고, 실제 담당 업무의 반영 여부를 검토"),
                "evidence_type":"변경된 동일 조문 내 업무주체·의무문 확인",
                "basis_excerpt":" ".join(excerpt.split())[:210],
                "source_url":change.get("source_url") or event.get("url",""),
                "verified_location":False,
                "actual_system_verified":False,
                "status":"법정 업무주체 확인 · 내부 반영 여부 미확인",
            }
            if item not in found:found.append(item)
    return found

def rebuild_event(event):
    """Never use previous inferred actions as evidence for new actions."""
    event["institution_actions"]=[]
    event["agency_candidates"]=[]
    event["dependency_actions"]=[]
    event["policy_links"]=[]
    event["upstream_policy_links"]=[]
    event["dependent_rules"]=[]
    if is_repeal(event):
        event["impact_category"]="폐지·효력종료"
        event["analysis_quality"]="폐지 사실 확인 · 후속 조치 주체 미확인"
        event["impact_summary"]="기존 지침·규정의 폐지 사실 확인. 대체 규정 및 후속 운영 기준은 별도 근거 확인 필요."
        event["priority"]=max(0,min(event.get("priority",0),35))
        # A repeal cannot be interpreted as the old rule's duties newly
        # binding every agency mentioned within its historical text.
        event["effects"]=[]
        return event
    owner=impact.organization_owner(event)
    if owner:
        event["institution_actions"]=impact.organization_actions(event,event.get("effects",[]))
        if event["institution_actions"]:
            event["impact_summary"]=event["institution_actions"][0]["what_to_change"]
            event["analysis_quality"]="조직별 변경 항목 공식 표 확인"
            return event
        # Other changes to a law titled "직제" (duties, department creation,
        # delegation) must still use ordinary same-clause evidentiary rules.
        # Never classify them as non-events just because no headcount changed.
    # In a general rule, an issuer/owner is not automatically the executing
    # organization. The subject and the duty must be in the actual changed
    # obligation, not just another article or a search snippet.
    by_article={}
    for effect in event.get("effects",[]):
        by_article.setdefault(effect.get("article"),[]).append(effect)
    actions=[]
    seen=set()
    for ch in event.get("changes",[]):
        for effect in by_article.get(ch.get("article"),[])[:12]:
            for a in action_for_change(event,ch,effect):
                key=(a["agency"],a["article"],a["work"],a["what_to_change"])
                if key not in seen:
                    seen.add(key);actions.append(a)
                if len(actions)>=32:break
            if len(actions)>=32:break
        if len(actions)>=32:break
    event["institution_actions"]=actions
    event["analysis_quality"]=(
        "동일 변경 조문에서 업무주체와 의무 확인" if actions else
        "공식 변경 확인 · 집행기관 직접 연결 미검증"
    )
    event["impact_summary"]=(
        "변경된 조문은 확인했지만, 특정 기관의 업무를 바꾸어야 한다는 "
        "직접 근거는 아직 확인되지 않았습니다."
        if not actions else actions[0]["what_to_change"]
    )
    return event

def apply_all(model):
    for e in model.get("events",[]):
        rebuild_event(e)
    h=model.get("impact_health",{})
    h["direct_actor_actions"]=sum(len(e.get("institution_actions",[])) for e in model.get("events",[]))
    h["agency_owners_to_verify"]=0
    h["evidence_gated"]=True
    h["repeal_events"]=sum(is_repeal(e) for e in model.get("events",[]))
    return model
