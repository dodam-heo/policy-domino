"""Identify affected executing organizations from the *full, current* official rule,
not just the newly changed sentence or its issuing ministry.

The result is an evidenced review task, never a claim that the institution's
internal rule or software is already non-compliant.
"""
from __future__ import annotations

import re
from v3 import impact

WORD= re.compile(r"([가-힣]{2,25}(?:부장관|청장|처장|위원장|이사장|원장|공단|공사|재단|진흥원|심사평가원|교육청|보건소장|교육감|구청장|시장|군수|위원회))(?=\s*(?:은|는|이|가|에게|에서|을|를|의|및|·|ㆍ))")
VERB=re.compile(r"하여야|한다|수행|담당|운영|심사|선정|결정|접수|산정|지급|승인|통보|발급|관리|시행|처리")
GENERIC=("각종 위원회","해당 기관","관계기관","기관의 장","관련 기관","위원회","공무원")
MAX_TEXT=45000

def compact(s):
    return " ".join(str(s or "").split())

def actor_candidates(text):
    found=[]
    for agency,forms in impact.ROLES:
        for form in forms:
            idx=text.find(form)
            if idx>=0 and agency not in found:found.append(agency)
    for match in WORD.finditer(text):
        candidate=match.group(1)
        if len(candidate)<3 or candidate in GENERIC or candidate in found:continue
        if candidate.startswith(("해당","관련","관계")):continue
        found.append(candidate)
        if len(found)>60:break
    return found

def find_actors_in_provisions(clauses):
    """Only consider exact official provisions with operative verbs."""
    result=[]
    for article,text in list(clauses.items())[:300]:
        body=compact(text)[:MAX_TEXT]
        if not VERB.search(body):continue
        for actor in actor_candidates(body):
            positions=[m.start() for m in re.finditer(re.escape(actor),body)]
            for pos in positions[:2]:
                excerpt=body[max(0,pos-105):min(len(body),pos+170)]
                if not VERB.search(excerpt):continue
                result.append({"agency":actor,"article":article,
                               "excerpt":excerpt,"full_clause":body[:1800]})
                break
    # A role mentioned as a background reference elsewhere is not an
    # implementation authority without a nearby operative verb.
    return result[:100]

def shared_operational_language(text,effect):
    """Tie a source-provision duty to the changed task, not merely the same law."""
    text=compact(text)
    for operation in effect.get("operations",[]):
        match=next((x for x in impact.OPERATIONS if x[0]==operation),None)
        if match and any(word in text for word in match[1]):
            return operation,match[2]
    return None

def assign(event,clauses):
    changes=event.get("effects",[])
    if not changes or not isinstance(clauses,dict):return []
    candidates=find_actors_in_provisions(clauses)
    result=[]
    known={(a.get("agency"),a.get("work")) for a in event.get("institution_actions",[])}
    seen=set()
    for actor in candidates:
        # Do not infer actors from unrelated internal org chart/personnel text.
        for change in changes[:24]:
            operation=shared_operational_language(actor["excerpt"],change)
            if not operation:continue
            work,target=operation
            key=(actor["agency"],work)
            if key in seen or key in known:continue
            seen.add(key)
            prior=compact(change.get("old",""))
            new=compact(change.get("new",""))
            delta=(prior+" → "+new) if prior and new else ("신설: "+new) if new else ("삭제: "+prior)
            result.append({
                "agency":actor["agency"],
                "work":work,
                "target_location":target,
                "what_to_change":delta[:270],
                "required_change":f"{work} 업무에서 변경된 내용의 적용 여부와 {target} 갱신 필요성을 확인",
                "article":change.get("article",""),
                "basis_article":actor["article"],
                "basis_excerpt":actor["excerpt"],
                "evidence_type":"공식 규정의 집행주체·업무조항 확인",
                "verified_location":False,
                "actual_system_verified":False,
                "status":"집행기관 업무 영향 검토 필요"
            })
            if len(result)>=28:return result
    return result
