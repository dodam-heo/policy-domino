"""Evidence gate for policy consequences. No registered law, agency or policy examples.

Separate: (1) official changed document, (2) verified statutory duty of
an actor, (3) sourced regulatory reference, and (4) unknown implementation.
Do not synthesize agency instructions from keywords, shared titles, or
an issuer's identity.
"""
from __future__ import annotations
import re
from v3 import impact,semantic_diff

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
    revision=str(event.get("revision",""))
    # Repeal-and-enact (폐지제정) publishes a successor rule, so it must
    # not be discarded as a pure cessation of legal effect.
    return bool(TERMINATION.search(revision)) and "제정" not in revision

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
    # Only full corresponding source statements may generate operational
    # effects. The legacy word-level SequenceMatcher remains available for
    # the separate, explicitly verified organization staffing table parser.
    event["effects"]=semantic_diff.evidence_effects(event,impact.OPERATIONS)
    grouped={}
    for effect in event["effects"]:
        new_sentence=effect.get("new","")
        if not new_sentence:
            # A deletion of an old obligation does not create a NEW duty for
            # that former actor; report it as an official source change only.
            continue
        # An agency is an executor only if the same actual changed statement
        # assigns it a duty. Do not mine entire chapters or neighbouring text.
        for match in ACTOR.finditer(new_sentence):
            name=match.group(1)
            tail=new_sentence[match.end():]
            duty=DUTY.search(tail)
            if not duty or duty.start()>230:
                continue
            work=(effect.get("operations") or ["업무 운영 기준"])[0]
            article=effect["article"]
            key=(name,article,work)
            pair={"before":effect.get("old",""),
                  "after":effect["new"],"article":article,
                  "confidence":effect.get("match_confidence","")}
            if key not in grouped:
                grouped[key]={
                    "agency":name,"article":article,"work":work,
                    "target_location":article+" · 변경된 업무 의무",
                    "what_to_change":article+"의 "+work+" 관련 문장이 변경됨",
                    "required_change":(
                        article+"에 명시된 "+name+"의 변경된 업무 의무를 "
                        "기존 운영 기준과 대조하여 실제 반영 필요 여부를 확인"
                    ),
                    "change_pairs":[],
                    "evidence_type":"변경된 동일 조문 내 업무주체·의무문 확인",
                    "source_url":effect["source_url"],
                    "verified_location":False,
                    "actual_system_verified":False,
                    "status":"법정 업무주체 확인 · 내부 반영 여부 미확인"
                }
            existing=grouped[key]["change_pairs"]
            if not any(x["before"]==pair["before"] and x["after"]==pair["after"]
                       for x in existing) and len(existing)<3:
                existing.append(pair)
    actions=list(grouped.values())[:32]
    event["institution_actions"]=actions
    if actions:
        event["analysis_quality"]="변경 전후 전체 문장과 조문 내 집행기관 의무 확인"
        event["impact_summary"]=(
            f"{len({a['agency'] for a in actions})}개 기관의 "
            f"{len(actions)}개 조문·업무 항목에서 문장 단위 변경 확인"
        )
    else:
        event["analysis_quality"]=(
            "문장 단위 변경은 확인했으나 기관별 의무 직접 연결 미검증"
            if event["effects"] else "원문 조문 변경은 확인했으나 문장 대응관계 미검증"
        )
        event["impact_summary"]=(
            "공식 신구 조문이 변경되었지만 서로 대응하는 완전한 업무 문장과 "
            "기관별 반영 의무는 확인되지 않았습니다. 원문 대조가 필요합니다."
            if not event["effects"] else
            "공식 변경 문장은 확인했으나 특정 기관이 해당 변경을 실제 운영에 "
            "반영해야 한다는 직접 근거는 아직 확인되지 않았습니다."
        )
    return event

def apply_all(model):
    for e in model.get("events",[]):
        rebuild_event(e)
    h=model.get("impact_health",{})
    h["direct_actor_actions"]=sum(len(e.get("institution_actions",[])) for e in model.get("events",[]))
    h["agency_owners_to_verify"]=0
    h["substantive_policy_events"]=sum(bool(e.get("effects")) and e.get("impact_category") in ("제도·업무 변경","조직개편·업무이관") for e in model.get("events",[]))
    h["evidence_gated"]=True
    h["repeal_events"]=sum(is_repeal(e) for e in model.get("events",[]))
    return model
