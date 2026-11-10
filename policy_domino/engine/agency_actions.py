"""Verified official changed-article evidence -> presentable agency actions.

This layer extracts directly supported operating changes. It does not infer
other agencies merely from a shared policy theme or a ministerial mention.
"""
from __future__ import annotations
import collections
import difflib
import hashlib
import re


ORG_TITLE=re.compile(
    r"^(.+?)(?:와 그 소속기관|과 그 소속기관)?\s*직제(?:\s*시행규칙)?$")
HEADING=re.compile(r"제\s*\d+조(?:의\s*\d+)?\s*\(([^)]{3,100})\)")
FIELD_RULES=(
    ("정원",re.compile("정원|직급|직렬|인력|공무원|임기제"),"조직·정원 운영","정원·직급·인력 배정"),
    ("업무분장",re.compile("담당업무|분장사무|소관업무|담당사무|하부조직|소속기관"),"조직·업무분장","담당 조직·부서의 업무 범위"),
    ("급여",re.compile("중위소득|지원액|급여|지급액|수수료|부담금|요율|금액|산정"),"금액·급여 산정","대상별 산정·지급 기준"),
    ("자격",re.compile("자격|선정|신청요건|대상자|소득인정액|지원대상"),"대상자·자격 심사","선정·자격 판정 조건"),
    ("서식",re.compile("제출서류|별지|신청서|구비서류|서식"),"접수·서식 관리","신청·제출서류 확인 기준"),
    ("인허가",re.compile("승인|허가|검사|등록|신고"),"인허가·검사 운영","허가·검사·신고 심사조건"),
    ("기한",re.compile("기간|기한|[0-9]+일\s*이내"),"처리기한·시행","접수·처리·유예기간"),
)
STAFF_QUANTITY=re.compile(r"(\d[\d,]*)\s*명")
TRUSTED="https://www.law.go.kr"

def clean(text):
    return " ".join(str(text or "").split()).strip()

def source_url(value):
    url=str(value or "")
    return url if url.startswith(("https://www.law.go.kr/","https://law.go.kr/")) else TRUSTED

def idof(value):
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:20]

def article_key(s):
    return re.sub(r"\s+","",str(s or ""))

def owner(title):
    match=ORG_TITLE.fullmatch(clean(title))
    if match:
        return match.group(1)
    return ""

def class_of(text):
    text=clean(text)
    for _,pattern,work,where in FIELD_RULES:
        if pattern.search(text):return work,where
    return "업무 기준 검토","변경된 조문의 담당업무"

def most_common_heading(docs):
    headings=collections.Counter()
    for d in docs:
        names=set()
        for p in d.get("excerpts",[]):
            m=HEADING.search(p.get("after",""))
            if m:names.add(clean(m.group(1)))
        headings.update(names)
    if not headings:return ""
    best,n=headings.most_common(1)[0]
    return best if n>=2 or len(docs)==1 else ""

def textual_edits(old, new, limit=3):
    """Return whole changed numeric values, never a single changed digit.

    SequenceMatcher on characters may report 192 -> 197 as 2 -> 7.
    We align whole numeric tokens first and keep the nearby official field
    label, or fall back to a compact changed phrase.
    """
    a, b = clean(old), clean(new)
    if not (a and b):
        return []
    token_pattern = re.compile(r"\d[\d,]*(?:\.\d+)?%?|[^\d\s]+|\s+")
    before_tokens = list(token_pattern.finditer(a))
    after_tokens = list(token_pattern.finditer(b))
    matcher = difflib.SequenceMatcher(
        None, [m.group() for m in before_tokens],
        [m.group() for m in after_tokens], autojunk=False
    )
    out = []
    for tag, i, j, k, l in matcher.get_opcodes():
        if tag == "equal":
            continue
        before = "".join(x.group() for x in before_tokens[i:j]).strip()
        after = "".join(x.group() for x in after_tokens[k:l]).strip()
        if not before or not after or len(before) > 80 or len(after) > 80:
            continue
        whole_number = r"\d[\d,]*(?:\.\d+)?%?"
        if re.fullmatch(whole_number, before) and re.fullmatch(whole_number, after):
            context = a[max(0, before_tokens[i].start()-75):before_tokens[i].start()].strip()
            label = re.split(r"[.;:\n]|[①②③④⑤]\s*", context)[-1][-50:]
            if not re.search(r"정원|총계|급여|기준|금액|직급|인력|기간|소득", label):
                continue
            out.append({"field": label or "변경 수치",
                        "before": before, "after": after})
        elif len(before) >= 3 or len(after) >= 3:
            out.append({"field": "변경 문구", "before": before,
                        "after": after})
        if len(out) >= limit:
            break
    return out


def choose_excerpts(doc):
    items=doc.get("excerpts",[])
    dedup=[];seen=set()
    for p in items:
        pair=(article_key(p.get("article")),clean(p.get("before")),clean(p.get("after")))
        if pair in seen:continue
        seen.add(pair)
        # A lone heading without operative material is weak evidence.
        if p.get("before")=="" and len(clean(p.get("after","")))<38:continue
        dedup.append(p)
    scored=[]
    for p in dedup:
        t=clean(p.get("after") or p.get("before"))
        score=0
        if p.get("before") and p.get("after"):score+=5
        if re.search(r"정원|담당|배정|급여|선정|기간|인허가|제출|직급|업무",t):score+=3
        if t.startswith(("①","②","③")):score+=2
        if "별표" in p.get("article",""):score+=1
        scored.append((score,p))
    return [p for _,p in sorted(scored,key=lambda x:x[0],reverse=True)]

def new_action(doc,p,event_id):
    agency=owner(doc.get("title",""))
    # Additional authorities only qualify when explicitly present in a
    # verified actor_duties element for that exact article.
    matching=[a for a in doc.get("actor_duties",[])
              if article_key(a.get("article"))==article_key(p.get("article"))]
    if not agency and matching:
        agency=matching[0].get("agency","")
    if not agency:return None
    article=clean(p.get("article",""))
    before=clean(p.get("before",""))
    after=clean(p.get("after",""))
    if not article or not (before or after):return None
    work,where=class_of(after+" "+before)
    changed=clean(after) if after else "해당 조항 삭제"
    if before and after:
        pair=[{"before":before[:600],"after":after[:600]}]
    elif after:
        pair=[{"before":"신설 이전 규정 없음","after":after[:600]}]
    else:
        pair=[{"before":before[:600],"after":"해당 조항 삭제"}]
    t=after or before
    title=HEADING.search(t)
    brief=(title.group(1)+" 관련 기준 신설" if title and not before else
           article+"의 "+work+" 관련 규정 변경")
    if before and after:
        changes=textual_edits(before,after)
        if changes and len(changes)==1:
            brief=article+" · "+changes[0]["before"]+" → "+changes[0]["after"]
    elif after:
        lead=re.sub(r"^제\s*\d+조(?:의\s*\d+)?\s*\([^)]*\)\s*","",after)
        brief="신설 · "+(lead[:115] if lead else article)
    return {
        "id":idof(event_id+"|"+agency+"|"+article+"|"+work+"|"+brief),
        "event_id":event_id,"agency":agency,
        "agency_role":"개정 직제의 직접 규율 대상 기관" if owner(doc.get("title","")) else
                      "변경된 조문에 명시된 집행기관",
        "work":work,"target_location":article+" · "+where,
        "what_to_change":brief[:200],"changes":pair,
        "required_change":(
            f"{agency}의 {where}에서 {article}의 변경 내용을 확인하고 "
            "해당 운영 기준·업무분장표 반영 필요 여부를 검토"
        ),
        "article":article,"law_title":doc.get("title",""),
        "effective_date":doc.get("effective",""),
        "basis":source_url(p.get("source_url") or doc.get("url")),
        "impact_link_basis":"동일 법령의 공식 이전·현재 조문 직접 비교",
        "status":"반영 확인 필요",
        "confidence":"공식 신구 조문 확인",
        "verification_note":"업무 기준 변경 사실은 확인했지만 해당 기관의 내부 시스템·반영 상태는 확인되지 않음",
        "evidence_scope":"v4_verified_source"
    }

def group_event(g):
    docs=g.get("source_docs",[])
    if not docs:return None,[]
    common=most_common_heading(docs)
    count=g.get("source_count",len(docs))
    num_actual=len({owner(d.get("title","")) for d in docs if owner(d.get("title",""))})
    if count>1 and common:
        title=f"{common} · 관련 법령 {count}건 동시 개정"
    elif count>1:
        title=f"{count}개 법령 동시 개정 · "+docs[0].get("title","")
    else:title=docs[0].get("title","")
    v4id="v4:"+g["id"]
    valid_docs=[d for d in docs if d.get("verification") in (
        "verified_changed_clauses","verified_annual_replacement",
        "verified_enactment","verified_repeal_notice")]
    authorities=sorted({clean(d.get("ministry")) for d in docs if clean(d.get("ministry"))})
    issuer=(" · ".join(authorities) if len(authorities)<=2 else
            authorities[0]+f" 외 {len(authorities)-1}개 기관") if authorities else ""
    e={
        "event_id":v4id,"title":title,
        "issuing_authorities":authorities,
        "source_verification":(
            "verified_changed_clauses" if any(d.get("verification") in
                ("verified_changed_clauses","verified_annual_replacement") for d in docs)
            else "verified_other" if valid_docs
            else "official_index_only" if all(d.get("verification")=="official_index_only"
                for d in docs) else "detail_pending"
        ),
        "source_documents":[{"title":d.get("title",""),"kind":d.get("kind",""),
                             "url":source_url(d.get("url","")),
                             "verification":d.get("verification",""),
                             "needs_attachment_check":d.get("needs_attachment_check",False),
                             "unresolved_attachments":d.get("unresolved_attachments",[])}
                            for d in docs if d.get("title")],
        "promulgated_at":g.get("date",""),
        "effective_date":g.get("effective_at",""),
        "revision":docs[0].get("revision","개정"),
        "law_type":("동일 공포번호 법령 "+str(count)+"건" if count>1 else docs[0].get("kind","법령")),
        "ministry":issuer,
        "url":source_url(docs[0].get("url")),
        "amendment_url":source_url(docs[0].get("url")),
        "amendment_reason":(
            f"공식 공포번호 {g.get('number','')}의 동일 변경 사건. "+
            (common+" 관련 규정을 변경." if common else
             "관련 법령들의 실제 신구 조문을 아래에서 확인할 수 있습니다.")
            if count>1 else ""),
        "article_differences":[],
        "change_summary":"",
        "change_count":sum(len(d.get("changed_articles",[])) for d in valid_docs),
        "comparison_status":"공식 신구 본문 대조 (기관별 반영 여부 미확인)",
        "policy_profile":bool(g.get("dependencies")),
        # These sections describe sourced legal relationships, not agency
        # implementation. The actual documents/citations are preserved and
        # presented in separate disclosures above the institution browser.
        "simultaneous_laws":[{
            "title":doc.get("title",""),
            "kind":doc.get("kind",""),
            "revision":doc.get("revision",""),
            "effective_date":doc.get("effective",""),
            "changed_articles":list(dict.fromkeys(doc.get("changed_articles",[]))),
            "url":source_url(doc.get("url","")),
        } for doc in docs if doc.get("title") and
             doc.get("url","").startswith(("https://www.law.go.kr/","https://law.go.kr/"))]
             if count>1 and g.get("official_common_promulgation") else [],
        "citing_regulations":[{
            "title":a.get("target_title",""),
            "source_title":a.get("source_title",""),
            "source_article":a.get("source_article",""),
            "target_article":a.get("target_article",""),
            "excerpt":a.get("excerpt","")[:520],
            "proof":a.get("proof",""),
            "url":source_url(a.get("target_url","")),
        } for a in g.get("dependencies",[]) if a.get("affected_verified") is True
             and a.get("target_title") and
             a.get("target_url","").startswith(("https://www.law.go.kr/","https://law.go.kr/"))],
        "downstream_changes":[{
            "title":a.get("target_title",""),
            "institution":a.get("target_ministry",""),
            "evidence":a.get("proof",""),
            "article":a.get("source_article",""),
            "basis_url":a.get("target_url",""),
            "status":"변경 조항 적용 관계 확인",
        } for a in g.get("dependencies",[])],
        "presentation_source":"v4_official_source",
        "impact_priority":min(200,(count*3 if count>1 else 0)+g.get("agency_count",0)*4+
                              len(g.get("dependencies",[]))*9+num_actual*4)
    }
    actions=[]
    for doc in valid_docs:
        for p in choose_excerpts(doc)[:3]:
            a=new_action(doc,p,v4id)
            if a:actions.append(a)
            e["article_differences"].append({
                "article":(doc.get("title","")+" · " if count>1 else "")+p.get("article",""),
                "type":p.get("kind","개정"),
                "before":p.get("before","")[:750],
                "after":p.get("after","")[:750],
                "source_url":source_url(p.get("source_url")),
                "directive":"",
            })
    pairs=[x for x in e["article_differences"] if x.get("before")!=x.get("after")]
    labels=[]
    for item in pairs[:3]:
        article=clean(item.get("article")) or "변경 조항"
        edits=textual_edits(item.get("before"),item.get("after"),limit=1)
        if edits:
            labels.append(article+" "+edits[0]["before"]+" → "+edits[0]["after"])
        else:
            labels.append(article+" "+("신설" if not item.get("before") else
                "폐지" if not item.get("after") else "개정"))
    e["change_summary"]=" · ".join(labels) if labels else "공식 신구 조문 대조 중"
    actions=unique_actions(actions)
    # Source-backed direct actors for general non-organization law events are
    # also permitted, but no names are taken from incidental fulltext mentions.
    return e,actions

def unique_actions(actions):
    merged={}
    for a in actions:
        key=(a.get("event_id"),a.get("agency"),article_key(a.get("article")),a.get("work"))
        if key not in merged:
            merged[key]=a
        else:
            initial=merged[key]
            seen={(p["before"],p["after"]) for p in initial["changes"]}
            for p in a.get("changes",[]):
                if (p["before"],p["after"]) not in seen and len(initial["changes"])<3:
                    initial["changes"].append(p)
                    seen.add((p["before"],p["after"]))
            initial["verification_note"]+=" · 동일 조문 내 변경사항 통합 표시"
    return list(merged.values())

