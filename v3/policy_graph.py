"""Cross-policy link discovery from official current texts and legal citations.

An observed reference to a standard is stronger than similar titles or dates.
Shared parent legislation is an investigation link, *not* proven causation.
All sectors are analyzed by the same algorithm.
"""
from __future__ import annotations
import re
from collections import Counter
from v2 import collector

CITATION = re.compile(r"「([^」]{2,120})」")
WORDS = re.compile(r"[가-힣]{3,}")
USES = re.compile(r"따라|준용|적용|사용|산정|선정|지급|기준으로|이하|초과|미만|%|퍼센트|비율|인정액")
TOO_GENERIC = {
 "선정기준","최저보장수준","개정","시행","기준","규정","법률","시행규칙","시행령",
 "관리기준","운영기준","기본계획","정책","업무","지원","행정규칙","지침","대상",
 "소관기관","규칙","사항","급여의","수급자","최저보장","최저기준"
}

def flatten(clauses):
    return " ".join(str(v or "") for v in clauses.values())[:100000]

def substantive(event):
    return bool(event.get("effects")) and event.get("impact_category") in (
      "제도·업무 변경","조직개편·업무이관")

def scope_year(event):
    a=event.get("effective_date","")
    if len(a)>=4 and a[:4].isdigit() and 2000<=int(a[:4])<2200:return int(a[:4])
    match=re.search(r"(?:19|20)\d{2}",event.get("title",""))
    return int(match.group()) if match else None

def keywords(event,frequency,total):
    title=re.sub(r"(?:19|20)\d{2}\s*년(?:도)?","",event.get("title",""))
    words=[]
    for token in WORDS.findall(title):
        token=token.rstrip("을를의에에서과와은는") or token
        if len(token)<4 or token in TOO_GENERIC:continue
        if frequency[token] > max(2,int(total*0.32)):continue
        if token not in words:words.append(token)
    return words[:12]

def official_text_and_citations(event,snapshots):
    key=collector.uid(event["source"],event["stable_id"])
    snap=snapshots.get(key,{})
    clauses=snap.get("clauses",{}) if snap.get("serial")==event.get("serial") else {}
    body=flatten(clauses)
    cited=set(CITATION.findall(body))
    cited.update(event.get("citations") or [])
    return body,cited

def use_excerpt(body,word):
    start=0
    for _ in range(8):
        pos=body.find(word,start)
        if pos<0:return None
        context=body[max(0,pos-100):min(len(body),pos+len(word)+125)]
        if USE.search(context):
            return " ".join(context.split())[:250]
        start=pos+len(word)
    return None

def link_documents(events,snapshots,limit_per_source=12):
    data={e["id"]:official_text_and_citations(e,snapshots) for e in events}
    freq=Counter()
    for e in events:
        plain=re.sub(r"(?:19|20)\d{2}\s*년(?:도)?","",e.get("title",""))
        for x in set(WORDS.findall(plain)):
            x=x.rstrip("을를의에에서과와은는") or x
            freq[x]+=1
    active=[e for e in events if substantive(e)]
    edges=[]
    for parent in active:
        atext,arefs=data[parent["id"]]
        tokens=keywords(parent,freq,len(events))
        if not tokens and not arefs:continue
        origin_year=scope_year(parent)
        for child in active:
            if child["id"]==parent["id"]:continue
            child_year=scope_year(child)
            # Annual standards can come from unrelated ministries; a common
            # effective year narrows but never independently proves a link.
            if origin_year and child_year and origin_year != child_year:continue
            btext,brefs=data[child["id"]]
            matched=[(word,use_excerpt(btext,word)) for word in tokens]
            matched=[(word,snippet) for word,snippet in matched if snippet]
            shared=sorted(arefs & brefs,key=len,reverse=True)
            if matched:
                term,snippet=max(matched,key=lambda item:len(item[0]))
                evidence="공식 하위 규정 본문의 기준 사용 문구"
                kind="기준명·산정문맥 확인"
                verified=True
            elif shared and any(term in parent["title"] and term in child["title"]
                                for term in ("선정기준","지원기준","산정기준","기준액","요율")):
                term=shared[0]
                snippet="공통 법적 근거: 「"+term+"」 · 두 기준의 산식·적용관계는 별도 확인"
                evidence="공통 상위법 인용"
                kind="동일 법적 근거 · 연쇄 적용 추가 확인"
                verified=False
            else:continue
            # Prefer a general source whose named standard is used by a
            # more specific target. Do not report a two-way causal dependency.
            if verified and any(word in atext for word in keywords(child,freq,len(events))):
                # If both texts use each other's name, mark investigation only.
                verified=False
                kind="상호 기준 사용 · 방향 추가 검증"
            edges.append({"source_id":parent["id"],"target_id":child["id"],
                "source_title":parent["title"],"target_title":child["title"],
                "target_ministry":child.get("ministry",""),"target_url":child.get("url",""),
                "reference":term,"excerpt":snippet,"evidence":evidence,
                "relation":kind,"verified_reference":verified,
                "causation_verified":False,"effective_year":origin_year or child_year})
    edges.sort(key=lambda e:(e["verified_reference"],len(e["reference"])),reverse=True)
    # Per-target citation evidence can be bidirectional. Retain the most
    # specific edge as the public link, without inventing direction proof.
    seen=set();final=[];counts=Counter()
    for edge in edges:
        pair=frozenset((edge["source_id"],edge["target_id"]))
        if pair in seen or counts[edge["source_id"]]>=limit_per_source:continue
        seen.add(pair);final.append(edge);counts[edge["source_id"]]+=1
    by_id={e["id"]:e for e in events}
    for e in events:e["policy_links"]=[];e["upstream_policy_links"]=[]
    for edge in final:
        by_id[edge["source_id"]]["policy_links"].append(edge)
        by_id[edge["target_id"]]["upstream_policy_links"].append(edge)
        source=by_id[edge["source_id"]]
        child=by_id[edge["target_id"]]
        # This is an evidence-backed task to review the target rule, not proof
        # that any particular local service has failed to comply.
        linked_actions=child.get("institution_actions",[])+child.get("agency_candidates",[])
        if not linked_actions and child.get("ministry"):
            linked_actions=[{"agency":child["ministry"],"work":"관련 기준 적용 검토",
                             "target_location":child["title"]}]
        for a in linked_actions[:4]:
            who=a.get("agency")
            if not who:continue
            existing={(x.get("agency"),x.get("target_location"))
                      for x in source.get("dependency_actions",[])}
            if (who,child["title"]) in existing:continue
            source.setdefault("dependency_actions",[]).append({
               "agency":who,
               "work":a.get("work") or "연동 기준 적용 검토",
               "target_location":child["title"],
               "what_to_change":"연관된 변경 고시의 적용 기준 검토: "+child["title"],
               "required_change":(
                 "하위 규정의 기준값·선정 절차가 변경된 상위 기준을 사용해야 하는지 대조. "
                 "개정 전후의 정확한 금액·시스템 반영 상태는 별도 확인."),
               "basis":child.get("url") or "",
               "basis_excerpt":edge["excerpt"],
               "evidence_type":edge["relation"],
               "verified_location":False,
               "actual_system_verified":False,
               "status":"연관 제도 적용 검토 · 미확정" if not edge["verified_reference"] else
                        "공식 사용 문구 확인 · 실제 반영 검토"
            })
    return {"links":len(final),"explicit_standard_uses":
             sum(bool(x["verified_reference"]) for x in final),
            "shared_statutory_basis_candidates":
             sum(not x["verified_reference"] for x in final)}
