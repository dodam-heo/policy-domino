"""Verify candidate downstream documents using their actual official clause text.

A confirmed *reference* is not proof that an agency has failed to update its
system. Dependent-rule evidence is separate from system implementation status.
"""
from __future__ import annotations
import re
from v2.collector import read_clauses

USE = re.compile(r"따른다|따라|적용|준용|산정|기준으로|근거로|비율|퍼센트|%|곱하여|정한다|정하여|사용")
QUOTED = re.compile(r"「([^」]{2,110})」")

def compact(x):
    return " ".join(str(x or "").split())

def anchors(parent):
    title=compact(parent.get("title",""))
    without_year=re.sub(r"(?:19|20)\d{2}\s*년(?:도)?\s*", "", title).strip()
    # Only use descriptive phrases, never a broad single-word overlap.
    possible=[title]
    if len(without_year)>=8 and without_year!=title:
        possible.append(without_year)
    for diff in parent.get("effects",[])[:5]:
        ctx=diff.get("context","")
        for phrase in re.findall(r"[가-힣 ]{6,40}(?:선정기준|산정기준|지원기준|기준액|요율|수수료)",ctx):
            phrase=compact(phrase)
            if len(phrase)>=8:possible.append(phrase)
    return sorted(set(x for x in possible if len(x)>=8),key=len,reverse=True)[:8]

def evidence(parent, candidate, contents):
    """The target rule must actually USE a specific reference near an operative verb.
    A title hit alone does not establish dependency.
    """
    text=compact(contents)
    matches=[]
    for ref in anchors(parent):
        p=0
        while True:
            pos=text.find(ref,p)
            if pos<0:break
            start=max(0,pos-140);end=min(len(text),pos+len(ref)+160)
            snippet=text[start:end]
            if USE.search(snippet):
                exact=("「"+ref+"」") in snippet
                matches.append({"reference":ref,"excerpt":snippet,"exact_title_citation":exact,
                                "basis":"공식 본문에서 해당 기준을 준용·적용하는 문장 확인"
                                        if exact else
                                        "공식 본문에 기준 명칭과 적용·산정 표현이 함께 확인됨 · 의존관계 추가 검토"})
            p=pos+len(ref)
            if len(matches)>=6:break
        if matches:break
    if not matches:
        return None
    verified=any(x["exact_title_citation"] for x in matches)
    return {
        "target_title":candidate.get("title",""),
        "target_ministry":candidate.get("ministry",""),
        "target_url":candidate.get("url",""),
        "source_url":parent.get("url",""),
        "reference":matches[0]["reference"],
        "excerpt":matches[0]["excerpt"],
        "relation_level":"직접 인용·적용 문구 확인" if verified else "기준 사용 문맥 확인 · 추가 검증 필요",
        "cause_verified":False,  # official citation does not prove a change event caused this rule
        "real_system_status":"미확인",
        "source_changes":[{"article":x.get("article"),"before":x.get("old"),"after":x.get("new")} 
                          for x in parent.get("effects",[])[:3]],
    }

def discover(events, maximum=14, cache=None):
    cache=cache if cache is not None else {}
    new_checks=0; errors=[]
    priority=sorted((e for e in events if e.get("effects") and e.get("reference_candidates")),
                    key=lambda e:(e.get("priority",0),e.get("promulgated_at","")),reverse=True)
    for parent in priority[:12]:
        parent["dependent_rules"]=[]
        for item in parent.get("reference_candidates",[])[:6]:
            if new_checks>=maximum:break
            serial=item.get("serial")
            if not serial:continue
            key=parent["id"]+"|"+item["source"]+"|"+serial
            if key in cache:
                recorded=cache[key]
                if recorded:parent["dependent_rules"].append(recorded)
                continue
            new_checks+=1
            try:
                rec={"source":item["source"],"serial":serial}
                clauses=read_clauses(rec)
                finding=evidence(parent,item," ".join(clauses.values()))
                cache[key]=finding
                if finding:parent["dependent_rules"].append(finding)
            except Exception as exc:
                errors.append({"policy":parent.get("title",""),"target":item.get("title",""),
                               "error":type(exc).__name__+" "+str(exc)[:100]})
        if new_checks>=maximum:break
    return cache, {"checked":new_checks,
                   "verified_dependents":sum(len(e.get("dependent_rules",[])) for e in events),
                   "errors":errors}

def add_dependency_agencies(events):
    """Public downstream offices are *candidates* to act, not implementation facts."""
    for parent in events:
        seen={(x["agency"],x["work"],x["article"]) for x in parent.get("institution_actions",[])}
        for rule in parent.get("dependent_rules",[]):
            who=rule.get("target_ministry")
            if not who:continue
            key=(who,"관련 규정에 따른 기준 적용",rule["target_title"])
            if key in seen:continue
            seen.add(key)
            parent.setdefault("dependency_actions",[]).append({
                "agency":who,"work":"관련 규정에 따른 기준 적용","target_location":rule["target_title"],
                "what_to_change":"상위 변경 기준을 준용하는 하위 규정의 적용값·자격·업무처리 기준 재검토",
                "required_change":"아래 공식 인용 문맥에서 상위 변경 기준을 실제로 사용하는지 대조하고, 달라진 기준을 적용하는 업무 항목을 확인",
                "basis":rule["target_url"],"basis_excerpt":rule["excerpt"],
                "status":"후속 기관 검토 필요","actual_system_verified":False})
