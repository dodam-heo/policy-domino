"""Source-verified policy domino edges using national regulatory data.

The official link API finds law -> local ordinance references.
Full-text legal/regulatory/ordinance searches find possible standard users.
A link is never treated as proof of a missed update or a change obligation.
"""
from __future__ import annotations

import re
from v2.collector import read_clauses, request, field, normalize

USE = re.compile(r"따른다|따라|준용|적용|산정|기준으로|근거로|요율|산식|비율|곱하여|정한다|정하여|사용|선정|의무")
TAG = re.compile(r"「([^」]{2,110})」")
NONWORD = re.compile(r"\s+")
YEAR = re.compile(r"(?:19|20)\d{2}\s*(?:년(?:도)?|양곡연도)?")
SENTENCE = re.compile(r"[.。;\n]")

def plain(value):
    return NONWORD.sub(" ", str(value or "")).strip()

def anchors(parent):
    """Find phrases from the data; never register an eligible policy or threshold."""
    title = plain(parent.get("title",""))
    words = []
    if len(title)>=7:words.append(title)
    normalized = plain(YEAR.sub("",title)).strip(" -·")
    if len(normalized)>=8:words.append(normalized)
    # Other documents frequently use the named standard rather than the year's notice title.
    for value in [title,normalized]+[x.get("context","") for x in parent.get("effects",[])[:5]]:
        for match in re.finditer(r"[가-힣][가-힣 ]{3,27}(?:기준|중위소득|금액|요율|부담률|대상|지원액|최저임금)",value):
            candidate=plain(match.group()).strip()
            candidate=YEAR.sub("",candidate).strip()
            if 7<=len(candidate)<=31:words.append(candidate)
    # Strip the leading administrative label, not arbitrary keywords.
    uniq=[]
    for item in words:
        if item not in uniq:uniq.append(item)
    return uniq[:8]

def parse_local_item(node):
    title=field(node,"자치법규명")
    serial=field(node,"자치법규일련번호")
    ident=field(node,"자치법규ID")
    if not title or not (serial or ident):
        return None
    return {"title":title,"serial":serial,"stable_id":ident,
            "source":"ordin","ministry":field(node,"지자체기관명"),
            "url":"https://www.law.go.kr/자치법규/"+__import__("urllib.parse",fromlist=["quote"]).quote(title),
            "relation_hint":"법제처 법령-자치법규 공식 연계"}

def linked_ordinances(parent,limit=35):
    """The law ID is required by the official lnkLsOrd API (knd)."""
    if parent.get("source")!="law" or not parent.get("stable_id"):
        return []
    root=request("lnkLsOrd",knd=parent["stable_id"],display=min(100,limit),page=1)
    out=[]
    for node in root.iter():
        if node is root:continue
        if any(child.tag.split("}")[-1]=="자치법규명" for child in list(node)):
            item=parse_local_item(node)
            if item and item["serial"] not in {x["serial"] for x in out}:
                out.append(item)
                if len(out)>=limit:break
    return out

def local_clauses(record):
    # Ordinance detail uses MST=serial, not ID=serial.
    root=request("ordin",endpoint="lawService.do",MST=record["serial"]) if record.get("serial") else request("ordin",endpoint="lawService.do",ID=record["stable_id"])
    owner=field(root,"지자체기관명")
    dept=field(root,"담당부서명")
    parts=[]
    for node in root.iter():
        tag=node.tag.split("}")[-1]
        if tag in ("조내용","조문내용","별표내용","제개정이유내용"):
            txt=plain("".join(node.itertext()))
            if txt:parts.append(txt)
    return " ".join(dict.fromkeys(parts))[:90000],owner,dept

def generic_clauses(item):
    if item["source"]=="ordin":
        return local_clauses(item)
    if not item.get("serial"):return "",item.get("ministry",""),""
    clauses=read_clauses({"source":item["source"],"serial":item["serial"]})
    return " ".join(clauses.values())[:90000],item.get("ministry",""),""

def evidence(parent,candidate,contents,official_link=False):
    """Require official text and in-context reference; do not equate search hit with a domino."""
    body=plain(contents)
    if not body:return None
    findings=[]
    for phrase in anchors(parent):
        start=0
        while True:
            pos=body.find(phrase,start)
            if pos<0:break
            excerpt=body[max(0,pos-110):min(len(body),pos+len(phrase)+125)]
            # Search by *text span* around the exact reference; not document-wide keywords.
            if USE.search(excerpt):
                exact="「"+phrase+"」" in excerpt
                findings.append((int(exact),len(phrase),phrase,excerpt))
            start=pos+len(phrase)
            if len(findings)>=8:break
    if not findings:
        # An official law-to-ordinance registry establishes a documented reference,
        # but not an obligation to change this ordinance.
        if not official_link:return None
        for phrase in [parent.get("title","")]+list(parent.get("citations",[])):
            if phrase and phrase in body:
                pos=body.find(phrase)
                findings.append((0,len(phrase),phrase,body[max(0,pos-85):pos+len(phrase)+120]))
                break
        if not findings:return None
    findings.sort(reverse=True)
    exact,_,ref,excerpt=findings[0]
    level=("명시적 인용·적용 확인" if exact else
           "공식 법령-자치법규 연계 및 본문 확인" if official_link else
           "공식 규정에서 관련 기준 사용 문구 확인")
    return {"target_title":candidate.get("title",""),"target_ministry":candidate.get("ministry",""),
            "target_url":candidate.get("url",""),"target_source":candidate.get("source",""),
            "reference":ref,"excerpt":excerpt,"relation_level":level,
            "verified_reference":bool(exact or official_link),
            "cause_verified":False,"real_system_status":"미확인",
            "source_changes":[{"article":x.get("article"),"before":x.get("old"),"after":x.get("new")}
                              for x in parent.get("effects",[])[:3]]}

def search_users(parent,limit=25):
    """Find *potential* dependent sources across legal, administrative and local rules."""
    pooled={}
    # First use official citation edges for laws, then content search for any policy.
    try:
        for doc in linked_ordinances(parent):
            pooled[(doc["source"],doc["serial"])]=doc
    except Exception:
        pass
    for kind in ("ordin","admrul","law"):
        for term in anchors(parent)[:2]:
            if len(pooled)>=limit:break
            try:
                root=request(kind,search=2,query=term,display=30,page=1)
                for node in root.iter():
                    if node is root:continue
                    if kind=="ordin":
                        if not any(c.tag.split("}")[-1]=="자치법규명" for c in list(node)):continue
                        doc=parse_local_item(node)
                    else:
                        name=field(node,"행정규칙명" if kind=="admrul" else "법령명한글")
                        serial=field(node,"행정규칙일련번호" if kind=="admrul" else "법령일련번호")
                        stable=field(node,"행정규칙ID" if kind=="admrul" else "법령ID")
                        if not (name and serial):continue
                        doc={"title":name,"serial":serial,"stable_id":stable,"source":kind,
                             "ministry":field(node,"소관부처명"),
                             "url":"https://www.law.go.kr/"+("행정규칙/" if kind=="admrul" else "법령/")+__import__("urllib.parse",fromlist=["quote"]).quote(name)}
                    if not doc:continue
                    if doc.get("stable_id") and doc["stable_id"]==parent.get("stable_id") and kind==parent.get("source"):continue
                    pooled[(doc["source"],doc["serial"])]=doc
                    if len(pooled)>=limit:break
            except Exception:
                continue
    # Existing collector results are candidates only; official detail still required.
    for item in parent.get("reference_candidates",[])[:10]:
        if item.get("serial") and len(pooled)<limit:
            pooled.setdefault((item["source"],item["serial"]),item)
    return list(pooled.values())[:limit]

def discover(events,maximum=22,cache=None):
    cache=cache if cache is not None else {}
    examined=0;errors=[]
    order=sorted([e for e in events if e.get("effects") and e.get("impact_category")=="제도·업무 변경"],
                 key=lambda e:(e.get("priority",0),e.get("promulgated_at","")),reverse=True)
    for parent in order[:12]:
        parent["dependent_rules"]=[]
        items=search_users(parent,limit=24)
        for item in items:
            if examined>=maximum:break
            sid=item.get("serial")
            if not sid:continue
            key=parent["id"]+"|"+item["source"]+"|"+sid
            if key in cache:
                record=cache[key]
                if record:parent["dependent_rules"].append(record)
                continue
            examined+=1
            try:
                contents,owner,dept=generic_clauses(item)
                doc=dict(item)
                if owner:doc["ministry"]=owner
                finding=evidence(parent,doc,contents,
                                 official_link=item.get("relation_hint","")=="법제처 법령-자치법규 공식 연계")
                if finding and dept:finding["target_department"]=dept
                cache[key]=finding
                if finding:parent["dependent_rules"].append(finding)
            except Exception as exc:
                # Do not record a cache hit for network errors: retry on the next cycle.
                errors.append({"policy":parent.get("title",""),"target":item.get("title",""),
                               "error":type(exc).__name__+" "+str(exc)[:100]})
        if examined>=maximum:break
    return cache,{"checked":examined,
                  "verified_dependents":sum(len(e.get("dependent_rules",[])) for e in events),
                  "errors":errors}

def add_dependency_agencies(events):
    for event in events:
        seen={(x.get("agency"),x.get("target_location")) for x in event.get("institution_actions",[])}
        for rule in event.get("dependent_rules",[]):
            owner=rule.get("target_ministry")
            if not owner:continue
            key=(owner,rule["target_title"])
            if key in seen:continue
            seen.add(key)
            event.setdefault("dependency_actions",[]).append({
                "agency":owner,"work":"변경 기준을 인용·적용하는 하위규정 검토",
                "target_location":rule["target_title"],"what_to_change":"관련 규정에 상위 변경 기준이 반영되어야 하는지 검토",
                "required_change":"근거 조문을 대조해 변경 전후의 적용값·자격요건·신청절차에 차이가 있는지 확인",
                "basis":rule["target_url"],"basis_excerpt":rule["excerpt"],
                "evidence_type":rule["relation_level"],
                "status":"해당 기관 검토 필요","actual_system_verified":False,
                "verified_location":False})
