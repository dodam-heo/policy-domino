"""Policy Domino v4 / clause-scoped dependency proof.

"Mentions the same law" is a citation, not a domino. A possible domino
requires either (1) an explicit reference to the exact CHANGED article with
an operative legal dependency or (2) an actual formula using a changed named
standard. Neither by itself proves what an institution has implemented.
"""
from __future__ import annotations
import re

LAW_CITE=re.compile(r"「([^」]{2,120})」")
ART=re.compile(r"제\s*(\d+)\s*조(?:의\s*(\d+))?")
OPERATES=re.compile(r"따라|따른|준용|적용|기준으로|규정에\s*의하여|산정|계산")
PARAGRAPHS="①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
PARA_NUMBER={ch:"제"+str(i+1)+"항" for i,ch in enumerate(PARAGRAPHS)}
PARA_MARKER=re.compile("["+PARAGRAPHS+"]")
SUBSECTION=re.compile(r"제\s*(\d+)\s*항")
FORMULA=re.compile(r"(?:(?:의|에\s*따라|을|를)\s*\d[\d,.]*\s*(?:%|퍼센트|배|원|만원|명)|(?:에\s*따라|을\s*적용하여|를\s*기준으로)\s*(?:산정|선정|지급|계산))")
YEAR=re.compile(r"(?:19|20)\d{2}\s*년(?:도)?")
STANDARD=re.compile(r"([가-힣][가-힣\s]{2,30}?(?:소득|산정기준|선정기준|기준액|요율|단가|지원기준|지급기준|최저보장수준))")
GENERIC={"법률","규칙","고시","기준","지침"}
NUMERIC_STANDARD=re.compile(r"(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(원|만원|%|퍼센트|배|명|세)(?![가-힣])")

def substantive_standard_change(change):
    # A reference to a standard is not an affected formula if the published
    # edit only changed unrelated prose or the document's annual title.
    before=set(NUMERIC_STANDARD.findall(change.get("before","")))
    after=set(NUMERIC_STANDARD.findall(change.get("after","")))
    return bool(before and after and before!=after) or (
        change.get("type")=="신설" and bool(after))

def norm(s):
    return re.sub(r"\s+","",str(s or ""))

def paragraph_sections(text):
    text=str(text or "")
    matches=list(PARA_MARKER.finditer(text))
    if not matches:return None
    return {PARA_NUMBER[m.group()]:norm(text[m.start():
              matches[i+1].start() if i+1<len(matches) else len(text)])
            for i,m in enumerate(matches)}

def changed_paragraphs(parent,article):
    """A cited 제2항 cannot inherit a change to 제1항 in the same article."""
    matching=[x for x in parent.get("changes",[])
              if norm(x.get("article"))==norm(article)]
    if not matching:return None
    changed=set()
    for x in matching:
        old=paragraph_sections(x.get("before",""))
        new=paragraph_sections(x.get("after",""))
        if old is None or new is None:return None
        changed.update(k for k in set(old)|set(new) if old.get(k)!=new.get(k))
    return changed

def articles_of(event):
    return {norm(c.get("article")) for c in event.get("changes",[])
            if c.get("article") and c.get("before")!=c.get("after")
            and c.get("type")!="연도별 고시 교체 · 수치표 별도 확인"}

def reference_tokens(text,parent_title):
    """Locate an exact cited title and a clause token within that citation's
    immediate sentence, never borrowing '제35조' from a different quotation.
    """
    parent=norm(parent_title)
    for match in LAW_CITE.finditer(text):
        if norm(match.group(1))!=parent:continue
        after=text[match.end():]
        stop_positions=[p for p in (after.find("「"),after.find("。"),
                                      after.find("."),after.find("\n"),after.find(";"))
                        if p>=0]
        after=after[:min(stop_positions)] if stop_positions else after
        # An article citation must immediately qualify the preceding law
        # within 38 characters; a distant other statute is not accepted.
        short=after[:38]
        art=ART.search(short)
        if art and art.start()<=12:
            number="제"+art.group(1)+"조"+("의"+art.group(2) if art.group(2) else "")
            remainder=short[art.end():]
            sub=SUBSECTION.search(remainder[:20])
            paragraph=("제"+str(int(sub.group(1)))+"항") if sub and sub.start()<=4 else None
            yield {"article":number,"paragraph":paragraph,
                "excerpt":text[max(0,match.start()-45):
                    min(len(text),match.end()+125)],
                "text":short,"title":match.group(1)}
        else:
            yield {"article":None,"paragraph":None,
                "excerpt":text[max(0,match.start()-45):
                    min(len(text),match.end()+125)],
                "text":short,"title":match.group(1)}

def changed_standards(parent):
    if not parent.get("changes"):return []
    out=set()
    # A standard is a named variable explicitly seen in the actual amended
    # text. A law title by itself (e.g. '해운법') is never a numeric standard.
    for change in parent["changes"]:
        if not substantive_standard_change(change):
            continue
        parts=[change.get("after",""),change.get("before",""),parent.get("title","")]
        for content in parts:
            clean=YEAR.sub("",content)
            for m in STANDARD.finditer(clean):
                phrase=" ".join(m.group(1).split()).strip(" ·,-")
                if 5<=len(norm(phrase))<=35 and phrase not in GENERIC:
                    out.add(phrase)
    return sorted(out,key=len,reverse=True)[:20]

def formula_ref(parent,child_text):
    for standard in changed_standards(parent):
        target=norm(standard)
        source=re.sub(r"\s+","",child_text)
        start=source.find(target)
        if start<0:continue
        after=source[start+len(target):start+len(target)+70]
        if FORMULA.search(after):
            return {"type":"formula_dependency","reference":standard,
                    "excerpt":source[max(0,start-45):start+len(target)+85],
                    "changed_articles":sorted(articles_of(parent)),
                    "proof":"실제 변경 기준명과 대상 규정의 산식·적용 관계"}
    return None

def evaluate(parent,child,child_clauses):
    if parent.get("id")==child.get("id"):return None
    if parent.get("source")==child.get("source") and parent.get("stable_id")==child.get("stable_id"):
        return None
    if not parent.get("changes") or not child_clauses:return None
    changed=articles_of(parent)
    source_title=parent.get("title","")
    candidates=[]
    for article,body in child_clauses.items():
        body=str(body or "")
        for cite in reference_tokens(body,source_title):
            target=norm(cite["article"])
            subsections=changed_paragraphs(parent,cite["article"]) if cite["paragraph"] else None
            paragraph_applies=(not cite["paragraph"] or
                (subsections is not None and cite["paragraph"] in subsections))
            actual=bool(target in changed and paragraph_applies and OPERATES.search(cite["text"]))
            candidates.append({
                "type":"cited_changed_provision" if actual else "citation_only",
                "source_event":parent["id"],"target_document":child.get("id",""),
                "source_article":cite["article"],
                "source_paragraph":cite["paragraph"],
                "target_article":article,
                "reference":cite["title"],"excerpt":cite["excerpt"][:250],
                "proof":"공식 대상 조문에서 실제 변경된 조항을 직접 인용·적용"
                        if actual else "문서 또는 다른 조항 인용만 확인",
                "affected_verified":bool(actual),
                "needs_review":bool(actual),
            })
        formula=formula_ref(parent,body)
        if formula:
            candidates.append({
                **formula,"source_event":parent["id"],"target_document":child.get("id",""),
                "source_article":", ".join(formula["changed_articles"]),
                "target_article":article,"affected_verified":True,
                "needs_review":True,
            })
    if not candidates:return None
    priority={"cited_changed_provision":3,"formula_dependency":2,"citation_only":1}
    return sorted(candidates,key=lambda c:(priority.get(c["type"],0),len(c.get("reference",""))),reverse=True)[0]

def build_graph(changes,documents,snapshots,max_links=500):
    """Only evidence-backed links go to the impact graph.

    Other citations are kept separately for document research and NEVER
    counted as affected downstream policy or agency duties.
    """
    impacts=[];references=[];stats={"tested_pairs":0,"no_detail":0}
    for parent in changes:
        for child in documents:
            if parent.get("id")==child.get("id"):continue
            key=(child.get("source"),child.get("stable_id"),child.get("serial"))
            clauses=snapshots.get(key)
            if clauses is None:
                stats["no_detail"]+=1
                continue
            stats["tested_pairs"]+=1
            edge=evaluate(parent,child,clauses)
            if not edge:continue
            edge.update({
                "source_title":parent.get("title",""),
                "target_title":child.get("title",""),
                "target_ministry":child.get("ministry",""),
                "target_url":child.get("url",""),
            })
            if edge["affected_verified"]:impacts.append(edge)
            else:references.append(edge)
    impacts=impacts[:max_links];references=references[:max_links]
    return {"impacts":impacts,"citations_only":references,
        "statistics":{**stats,"actual_dependencies":len(impacts),
                      "noncausal_citations":len(references)}}
