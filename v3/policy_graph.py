"""Source-grounded regulatory dependency graph.

Do NOT create compliance tasks or name executing agencies from same-year,
same-word or same-law similarities. Only an actual textual reference in
official target source can establish a reference edge. A reference still
does not establish that one promulgation caused another.
"""
from __future__ import annotations
import re
from v2 import collector

CITATION=re.compile(r"「([^」]{2,120})」")
OPERATIVE=re.compile(r"준용|적용|따라|따른|산정|기준으로|사용|지급|산출|계산")
YEAR=re.compile(r"(?:19|20)\d{2}\s*년(?:도)?\s*")
STANDARD_SUFFIX=re.compile(r"기준|요율|금액|급여|임금|소득|산식|단가|수수료|한도|부담률")
WORD=re.compile(r"[가-힣]{2,}")
FILLER={"관한","대한","것을","위한","지침","법령","대상","사항","규칙","운영","고시",
        "시행","제정","개정","일부","기본","관련","및"}

def normalized(value):
    return re.sub(r"\s+"," ",str(value or "")).strip()

def rule_text(event,snapshots):
    snap=snapshots.get(collector.uid(event["source"],event["stable_id"]),{})
    if str(snap.get("serial"))!=str(event.get("serial")):return ""
    return " ".join(str(v or "") for v in snap.get("clauses",{}).values())[:120000]

def potential_names(title):
    title=normalized(title)
    without_year=normalized(YEAR.sub("",title))
    results=[title]
    if len(without_year)>7 and without_year not in results:results.append(without_year)
    words=WORD.findall(without_year)
    # A named multi-word standard may appear without the year in dependent
    # regulations. Generic words such as "operation" never become an edge.
    for size in (4,3,2):
        for i in range(len(words)-size+1):
            group=words[i:i+size]
            if not STANDARD_SUFFIX.search(group[-1]):continue
            if any(x in FILLER for x in group):continue
            phrase=" ".join(group)
            if len(phrase)>=7 and phrase not in results:results.append(phrase)
    return results[:18]

def matched_reference(parent,child_text):
    names=potential_names(parent.get("title",""))
    if not child_text:return None
    cites=CITATION.findall(child_text)
    for name in names:
        if name in cites:
            for hit in re.finditer(re.escape("「"+name+"」"),child_text):
                nearby=child_text[hit.start():min(len(child_text),hit.end()+110)]
                if OPERATIVE.search(nearby):
                    return {"phrase":name,"excerpt":normalized(
                      child_text[max(0,hit.start()-70):hit.end()+110])[:240],
                      "basis":"공식 대상 규정에서 변경 기준을 명시적으로 인용·적용"}
    # Exact full title in operative context is also a valid source reference,
    # provided it is not a single broad topical token.
    for name in names[:2]:
        if len(name)<8:continue
        pos=child_text.find(name)
        if pos<0:continue
        tail=child_text[pos+len(name):pos+len(name)+90]
        if OPERATIVE.search(tail):
            return {"phrase":name,
                    "excerpt":normalized(child_text[max(0,pos-70):pos+len(name)+90])[:240],
                    "basis":"공식 대상 규정에서 기준 전체 명칭과 적용 표현 확인"}
    # A short derived standard phrase requires an exact quoted citation,
    # never a loose topical keyword or shared parent statute.
    return None

def link_documents(events,snapshots,limit_per_source=15):
    for e in events:
        e["policy_links"]=[]
        e["upstream_policy_links"]=[]
        e["dependency_actions"]=[]
    texts={e["id"]:rule_text(e,snapshots) for e in events}
    active=[e for e in events if e.get("impact_category")=="제도·업무 변경" and e.get("effects")]
    edges=[]
    for parent in active:
        for child in active:
            if parent["id"]==child["id"]:continue
            linked=matched_reference(parent,texts.get(child["id"],""))
            if not linked:continue
            edges.append({
                "source_id":parent["id"],"target_id":child["id"],
                "source_title":parent["title"],"target_title":child["title"],
                "target_ministry":child.get("ministry",""),
                "target_url":child.get("url",""),
                "reference":linked["phrase"],"excerpt":linked["excerpt"],
                "relation":linked["basis"],
                "verified_reference":True,
                "causation_verified":False,
                "implementation_verified":False,
            })
    # Do not guess direction of mutual references.
    by_id={e["id"]:e for e in events}
    seen=set();used={}
    for edge in sorted(edges,key=lambda x:len(x["reference"]),reverse=True):
        pair=frozenset((edge["source_id"],edge["target_id"]))
        if pair in seen or used.get(edge["source_id"],0)>=limit_per_source:continue
        seen.add(pair);used[edge["source_id"]]=used.get(edge["source_id"],0)+1
        by_id[edge["source_id"]]["policy_links"].append(edge)
        by_id[edge["target_id"]]["upstream_policy_links"].append(edge)
    total=sum(len(e["policy_links"]) for e in events)
    return {"links":total,"explicit_standard_uses":total,
            "shared_statutory_basis_candidates":0,
            "note":"인용·적용 문맥 확인만 집계. 기관 조치 또는 인과관계는 자동 확정하지 않음"}
