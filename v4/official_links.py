"""Official provision-level delegated-law links from law.go.kr lsDelegated.

A delegated reference is a real official citation, but it does NOT prove
that the downstream document must be amended. Only the specific changed
article and the target document's actual use can justify an impact link.
"""
from __future__ import annotations
import re,urllib.parse
from v2 import collector as api

def article(value):
    raw=str(value or "").strip()
    if not raw:return ""
    m=re.search(r"제\s*(\d+)\s*조(?:의\s*(\d+))?",raw)
    if m:return "제"+str(int(m.group(1)))+"조"+("의"+str(int(m.group(2))) if m.group(2) else "")
    digits=re.sub(r"\D","",raw)
    if len(digits)==6:
        a=int(digits[:4]);b=int(digits[4:])
        return "제"+str(a)+"조"+("의"+str(b) if b else "") if a>0 else ""
    if digits:return "제"+str(int(digits))+"조"
    return ""

def target_rows(unit):
    for category,serial_field,title_field,source in (
        ("위임법령","위임법령일련번호","위임법령제목","law"),
        ("위임행정규칙","위임행정규칙일련번호","위임행정규칙제목","admrul"),
        ("위임자치법규","위임자치법규일련번호","위임자치법규제목","ordin"),
        ("위임공공기관규정","위임규정일련번호","위임규정제목","public_rule")):
        number=api.field(unit,serial_field)
        title=api.field(unit,title_field)
        if number and title:
            yield {"reference_kind":category,"serial":number,"title":title,
                   "source":source,"url":"https://www.law.go.kr/"+
                   ("법령/" if source=="law" else "행정규칙/" if source=="admrul" else
                    "자치법규/" if source=="ordin" else "")+
                   urllib.parse.quote(title)}

def delegated_changed_articles(record,changed_articles,request=None):
    if record.get("source")!="law" or not record.get("stable_id"):
        return {"links":[],"status":"not_applicable"}
    request=request or api.request
    root=request("lsDelegated",endpoint="lawService.do",ID=record["stable_id"])
    changed={article(x) for x in changed_articles if article(x)}
    output=[]
    seen=set()
    for node in root.iter():
        if node is root:continue
        direct={x.tag.split("}")[-1] for x in list(node)}
        if "조문번호" not in direct or not (
            direct.intersection({"위임법령일련번호","위임행정규칙일련번호",
                                 "위임자치법규일련번호","위임규정일련번호"})):
            continue
        from_clause=article(api.field(node,"조문번호"))
        if not from_clause or from_clause not in changed:continue
        for target in target_rows(node):
            key=(from_clause,target["source"],target["serial"])
            if key in seen:continue
            seen.add(key)
            output.append({
                **target,"source_article":from_clause,"source_law":record["title"],
                "source_law_id":record["stable_id"],
                "delegation_type":api.field(node,"위임구분"),
                "link_text":api.field(node,"링크텍스트"),
                "line_text":api.field(node,"라인텍스트")[:300],
                "relation":"해당 변경 조항의 법제처 공식 위임·인용 관계",
                "requires_amendment_verified":False,
                "implementation_verified":False,
                "status":"official_delegation_review_candidate"})
    return {"links":output,"status":"official_endpoint_verified",
            "changed_articles":sorted(changed)}
