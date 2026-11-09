"""Policy Domino Classic / rebuild actionable V2-style view from source evidence.

No hardcoded law names, sectors, agency IDs or numeric policy examples.
V4 source-backed articles and V2's *original official amendment directives*
remain independent, visibly labelled provenance. Old V2-derived actions are
never represented as freshly checked/confirmed implementation.
"""
from __future__ import annotations
import collections
import difflib
import hashlib
import json
import re
from pathlib import Path
from v4 import institutional_impact

ROOT=Path(__file__).resolve().parents[1]
V4=ROOT/"site"/"v4"/"data.json"
LEGACY=ROOT/"site"/"classic"/"legacy_source.json"
DEST=ROOT/"site"/"classic"/"data.json"

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

def textual_edits(old,new,limit=3):
    # Extract only changed NUMERIC tokens in their original source positions;
    # a bare 192->197 without a field label will NOT be a confirmed change.
    a,b=clean(old),clean(new)
    if not (a and b):return []
    matcher=difflib.SequenceMatcher(None,a,b,autojunk=True)
    out=[]
    for tag,i,j,k,l in matcher.get_opcodes():
        if tag=="equal":continue
        before=a[i:j].strip()
        after=b[k:l].strip()
        if not before or not after or len(before)>80 or len(after)>80:continue
        if before.isdigit() and after.isdigit():
            context=a[max(0,i-75):i].strip()
            label=re.split(r"[.;:\n]|[①②③④⑤]\s*",context)[-1][-50:]
            if not re.search(r"정원|총계|급여|기준|금액|직급|인력|기간|소득",label):
                continue
            out.append({"field":label or "변경 수치","before":before,"after":after})
        elif len(before)>=3 or len(after)>=3:
            out.append({"field":"변경 문구","before":before,"after":after})
        if len(out)>=limit:break
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

def official_document_index(docs):
    """Names observed in OFFICIAL source documents, not enrolled program links.

    Keep source-law owners and official issuing bodies separate from actors
    explicitly named in an actually changed clause. No inferred job or
    confirmed institutional implementation is created.
    """
    found=[]
    seen=set()
    for doc in docs:
        title=clean(doc.get("title"))
        ministry=clean(doc.get("ministry"))
        law_url=str(doc.get("url",""))
        if not title or not law_url.startswith(
                ("https://www.law.go.kr/","https://law.go.kr/")):
            continue
        kind=doc.get("verification","official_record_only")
        changed=set(doc.get("changed_articles",[]))
        def add(agency,role):
            agency=clean(agency)
            if not agency:return
            key=(agency,title,law_url)
            if key in seen:return
            seen.add(key)
            found.append({
                "agency":agency,"agency_role":role,"law_title":title,
                "source_url":law_url,"verification":kind,
                "changed_article_count":len(changed),
                "actual_implementation_verified":False,
                "kind":doc.get("kind","")
            })
        direct=owner(title)
        add(direct or ministry,("직제 규정에 명시된 기관" if direct else
                               "공포·개정 소관기관 (집행기관 미확인)"))
        if kind in ("verified_changed_clauses","verified_annual_replacement"):
            for actor in doc.get("actor_duties",[]):
                if (actor.get("status")!="official_duty_changed" or
                        actor.get("article") not in changed):
                    continue
                add(actor.get("agency"),
                    "실제 변경 조문에 명시된 수행주체 (타 사업 영향 미확인)")
    return found


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
    states={d.get("verification","") for d in docs}
    if any(d.get("excerpts") and d.get("verification") in (
            "verified_changed_clauses","verified_annual_replacement") for d in docs):
        state_label="official_changes_compared"
    elif "verified_enactment" in states:
        state_label="official_enactment_only"
    elif "verified_repeal_notice" in states:
        state_label="official_repeal_only"
    else:state_label="details_not_compared"
    source_notes=list(dict.fromkeys(
        str(note)[:200] for d in docs for note in d.get("notes",[]) if note))[:6]
    e={
        "event_id":v4id,"title":title,
        "comparison_state":state_label,
        "source_notes":source_notes,
        "official_change_documents":official_document_index(docs),
        "promulgated_at":g.get("date",""),
        "effective_date":g.get("effective_at",""),
        "revision":docs[0].get("revision","개정"),
        "law_type":("동일 공포번호 법령 "+str(count)+"건" if count>1 else docs[0].get("kind","법령")),
        "ministry":(f"직접 변경 대상 기관 {num_actual}곳" if num_actual>1
                    else docs[0].get("ministry","")),
        "url":source_url(docs[0].get("url")),
        "amendment_url":source_url(docs[0].get("url")),
        "amendment_reason":(
            f"공식 공포번호 {g.get('number','')}의 동일 변경 사건. "+
            (common+" 관련 규정을 변경." if common else
             "관련 법령들의 실제 신구 조문을 아래에서 확인할 수 있습니다.")
            if count>1 else ""),
        "article_differences":[],
        "change_count":sum(len(d.get("changed_articles",[])) for d in valid_docs),
        "comparison_status":("공식 신구 문장 비교 확인" if state_label=="official_changes_compared" else
                             "제정 사실만 확인" if state_label=="official_enactment_only" else
                             "폐지 사실만 확인" if state_label=="official_repeal_only" else
                             "공식 공포 정보 확인 · 조문 비교 미완료"),
        "policy_profile":bool(g.get("dependencies")),
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
        excerpts=choose_excerpts(doc)
        # Keep every source-verified excerpt available for the reader, not
        # only the three samples from which immediate direct action cards arise.
        # Legal text and institution instructions are separate evidence layers.
        for index,p in enumerate(excerpts[:12]):
            if index<3:
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

def legacy_event_ok(e):
    return bool(e.get("event_id") and e.get("title") and
                e.get("article_differences") and
                all(str(x.get("source_url","")).startswith(TRUSTED)
                    for x in e.get("article_differences",[]) if x.get("source_url")))

def legacy_action_ok(a,e):
    # Every old V2 card must have a MATCHING official amendment directive.
    # An inferred cross-ministry role with no old-new literal pair is not
    # reliable enough to be promoted as a fresh official change action.
    pairs=a.get("changes",[])
    if not pairs:return False
    # Annual official standards can identify a table row by field rather
    # than the host act's article number; the field must match the ACTUAL
    # official-before/after source data, not an unrelated subject term.
    row_names={article_key(p.get("field")) for p in pairs}
    diffs=[d for d in e.get("article_differences",[])
           if article_key(d.get("article"))==article_key(a.get("article"))
           or article_key(d.get("article")) in row_names]
    if not diffs:return False
    for d in diffs:
        directive=clean(d.get("directive"))
        if not directive or not str(d.get("source_url","")).startswith(TRUSTED):
            continue
        for p in pairs:
            candidates=[
                (clean(p.get("old_literal")),clean(p.get("new_literal"))),
                (clean(p.get("before")),clean(p.get("after")))
            ]
            if any(old and new and old in directive and new in directive
                   for old,new in candidates):
                return True
    return False

def legacy_fallback(source,verified_titles):
    """Retain previously cited legal changes, never inherited agency instructions."""
    extra_events=[]
    for e in source.get("events",[]):
        if not legacy_event_ok(e) or e.get("title") in verified_titles:continue
        # A source event's official directive must contain both amounts itself.
        # Prior hand-registered operational roles are not evidence.
        valid=[]
        for diff in e.get("article_differences",[]):
            directive=clean(diff.get("directive"))
            before=clean(diff.get("before"))
            after=clean(diff.get("after"))
            if (directive and before and after and before!=after and
                before in directive and after in directive and
                str(diff.get("source_url","")).startswith(TRUSTED)):
                valid.append(diff)
        if not valid:continue
        event=dict(e)
        event["article_differences"]=valid
        event["event_id"]="legacy:"+e["event_id"]
        event["comparison_status"]="이전 공식 개정문 확인 · 최신 재검증 대기"
        event["presentation_source"]="legacy_official_directive_awaiting_recheck"
        event["impact_priority"]=12
        extra_events.append(event)
    return extra_events, []

def assess_impact_scope(event, actions):
    """Scope of documented institutional/regulatory consequences, not a
    judgement of severity, population affected or actual implementation.

    Titles, article mentions, total change count and the number of clauses
    never independently qualify a policy as high impact.
    """
    actors={clean(a.get("agency")) for a in actions if
            a.get("event_id")==event["event_id"] and a.get("agency") and
            a.get("evidence_scope") in (
                "v4_verified_source",
                "legacy_official_directive_awaiting_recheck",
                "official_institutional_program_dependency")}
    legal_links={
        (clean(x.get("title")),clean(x.get("article")))
        for x in event.get("downstream_changes",[])
        if x.get("status")=="변경 조항 적용 관계 확인"
        and x.get("title") and x.get("article") and x.get("evidence")
    }
    wide=len(actors)>=2 or len(legal_links)>=2
    if len(actors)>=2 and len(legal_links)>=2:
        reason=f"기관별 검토 {len(actors)}곳 · 실제 변경 조항 적용 규정 {len(legal_links)}건"
    elif len(actors)>=2:
        reason=f"변경된 업무의 직접 검토 기관 {len(actors)}곳"
    elif len(legal_links)>=2:
        reason=f"실제 변경 조항을 적용하는 다른 규정 {len(legal_links)}건"
    else:
        reason="확인된 기관·제도 영향 범위가 분류 기준에 미달"
    provisional=event.get("presentation_source")!="v4_official_source"
    return {
        "impact_level":"high" if wide else "not_assessed",
        "impact_reason":reason,
        "impact_scope":{
            "institutions":len(actors),
            "proven_dependent_rules":len(legal_links),
            "criteria":"직접 검토 기관 2곳 이상 또는 변경 조항 적용 규정 2건 이상",
            "provisional":provisional,
            "note":("이전 V2의 공식 개정문에 근거한 잠정 영향 범위이며 최신 재검증 대기"
                    if provisional else
                    "공식 신구 조문에 따른 파급 범위. 기관별 내부 반영·사회적 중요도는 미확인")
        }
    }

def source_review_candidates(event,limit=12):
    """Produce tentative work review questions from changed SOURCE wording.

    This does not discover an institution or an operational program.
    No agency/program/amount/URL can be pre-enrolled as a positive case.
    """
    if event.get("presentation_source") not in (
        "v4_official_source","legacy_official_directive_awaiting_recheck"):
        return []
    domains=(
        ("지원·지급 범위",r"지원|지급|급여|보조|비용|보상|환급",
         "해당 지원 항목·지급 판단 기준을 실제 적용하는 업무가 있는지 확인"),
        ("자격·선정 조건",r"자격|선정|소득|대상자|수급자|요건",
         "자격·대상 판단 기준을 실제 사용하는 업무가 있는지 확인"),
        ("금액·산식",r"금액|비율|산정|기준액|요율|단가",
         "해당 금액·비율의 산식이나 기준표 사용 여부를 확인"),
        ("서류·서식",r"서식|신청서|증빙|첨부|제출",
         "제출 서류·신청서 기준의 실제 반영 여부를 확인"),
        ("기한·시행",r"기한|이내|처리기간|유예|시행일",
         "처리기한·적용 시점을 실제 판정하는 업무가 있는지 확인"),
        ("허가·신고·검사",r"허가|신고|등록|검사|인증|심사",
         "허가·신고·검사 심사기준의 실제 적용 여부를 확인"),
        ("조직·정원",r"정원|직제|직급|배정|업무분장",
         "정원·직급·사무배정 기준과의 적용 관계를 확인"),
    )
    reviews=[]
    for d in event.get("article_differences",[]):
        old,new=clean(d.get("before")),clean(d.get("after"))
        article=clean(d.get("article"))
        source=str(d.get("source_url",""))
        if not(old and new and old!=new and article and
               source.startswith(("https://www.law.go.kr/","https://law.go.kr/"))):
            continue
        matcher=difflib.SequenceMatcher(None,old,new,autojunk=True)
        diffs=[]
        for tag,i,j,k,l in matcher.get_opcodes():
            if tag=="equal":continue
            previous=old[max(0,i-9):min(len(old),j+9)].strip()
            updated=new[max(0,k-9):min(len(new),l+9)].strip()
            if previous==updated:continue
            diffs.append({"before":previous[:100],"after":updated[:100]})
            if len(diffs)>=3:break
        if not diffs:continue
        heading=HEADING.search(new)
        topic=heading.group(1) if heading else article
        text=topic+" "+" ".join(x["before"]+" "+x["after"] for x in diffs)
        work=next(((label,prompt) for label,regex,prompt in domains
                   if re.search(regex,text)),
                  ("조문상 적용 기준","변경된 규정을 실제 적용하는 업무가 있는지 확인"))
        reviews.append({
            "id":idof(event["event_id"]+"|"+article+"|"+old+"|"+new),
            "article":article,"topic":topic,"work_type":work[0],
            "review_question":work[1],
            "actual_changes":diffs,
            "source_url":source,
            "status":"기관·사업 적용 여부 미확인",
            "institution_verified":False
        })
        if len(reviews)>=limit:break
    return reviews

def indexed_pending_event(item):
    """Index-only candidate; never issue an institution instruction."""
    return {
        "event_id":"pending:"+item["record_id"],
        "title":item["title"],"promulgated_at":item["published_at"],
        "effective_date":item.get("effective_date",""),
        "revision":item.get("revision",""),"law_type":item.get("kind","법령·고시"),
        "ministry":item.get("ministry",""),
        "url":source_url(item.get("url")),"amendment_url":source_url(item.get("url")),
        "article_differences":[],"downstream_changes":[],
        "official_change_documents":official_document_index([{
            "title":item.get("title",""),
            "ministry":item.get("ministry",""),
            "url":item.get("url",""),
            "kind":item.get("kind",""),
            "verification":"official_index_only"
        }]),
        "comparison_state":"official_index_only",
        "comparison_status":"공식 변경이력·목록 확인 / 본문 신구 비교 대기",
        "source_notes":["공식 변경일 기준 목록에 수록됐으나 조문 비교와 실제 기관별 영향 검증이 아직 완료되지 않았습니다."],
        "presentation_source":"official_index_pending",
        "impact_priority":0
    }

def build(v4,legacy):
    events=[];actions=[]
    source_titles=set()
    for g in v4.get("featured_events",[])+v4.get("other_events",[]):
        e,aa=group_event(g)
        if not e:continue
        events.append(e);actions+=aa
        source_titles.update(doc.get("title","") for doc in g.get("source_docs",[])
                             if doc.get("verification","").startswith("verified_"))
    # All indexed official change types must be browsable even before
    # their source content has been compared. No fabricated institution links.
    represented={d.get("id") for g in v4.get("featured_events",[])+v4.get("other_events",[])
                 for d in g.get("source_docs",[])}
    for item in v4.get("pending_index",[]):
        if item.get("record_id") in represented:continue
        if not item.get("record_id") or not item.get("title"):continue
        events.append(indexed_pending_event(item))
    old_events,old_actions=legacy_fallback(legacy,source_titles)
    events+=old_events;actions+=old_actions
    actions=unique_actions(actions)
    # Discovery only against source-verified changes; metadata cannot produce
    # a public agency task.
    grounded=[e for e in events if e.get("presentation_source") in (
        "v4_official_source","legacy_official_directive_awaiting_recheck")]
    findings,discovery_health=institutional_impact.discover(grounded)
    actions,institutional_actions=institutional_impact.connect(events,actions,findings)
    event_ids={e["event_id"] for e in events}
    actions=[a for a in actions if a.get("event_id") in event_ids]
    # A source-grounded review topic is distinct from a proven agency duty.
    for e in events:
        e["work_review_candidates"]=source_review_candidates(e)
    # Impact scoring is evidence-based, not a replacement for the public
    # chronological view of newly promulgated official events.
    action_counts=collections.Counter(a["event_id"] for a in actions)
    for e in events:
        e.update(assess_impact_scope(e,actions))
        e["impact_priority"]=e.get("impact_priority",0)+min(40,action_counts[e["event_id"]]*3)
    events.sort(key=lambda e:(e.get("promulgated_at",""),e.get("impact_priority",0)),reverse=True)
    checked=v4.get("collection",{})
    return {
        "schema":"policy-domino-next-v1",
        "generated_at":v4.get("generated_at"),
        "health":{
            "source_status":"공식 공포·개정문 연결",
            "partial":True,
            "official_records":len(events),
            "compared":sum(e.get("comparison_state")=="official_changes_compared" for e in events),
            "source_records_inspected":checked.get("detailed_checked",0),
            "official_index_waiting_visible":sum(e.get("presentation_source")=="official_index_pending" for e in events),
            "amendments_read":len(events),
            "amendments_verified_total":checked.get("detailed_checked",0),
            "catalogue_candidates":checked.get("official_catalogue",0),
            "v4_official_index":checked.get("fresh_official_index",0),
            "pending_details":checked.get("pending_details",0),
            "legacy_recheck":len(old_events),
            "institutional_dependency_actions":len(institutional_actions),
            "institutional_evidence_sources":discovery_health["pages_checked"],
            "institutional_discovery":discovery_health,
            "error":"기관별 조치 카드에 표시된 내용은 검토 대상이며, 실제 반영 상태는 미확인입니다."
        },
        "events":events,
        "actions":actions,
        "status_counts":{},
        "disclaimer":"공식 신구 조문 대조와 이전 V2 개정 지시문은 출처와 검증 상태를 구분했습니다."
    }

def run():
    v4=json.loads(V4.read_text("utf8"))
    legacy=json.loads(LEGACY.read_text("utf8"))
    if v4.get("schema")!="policy-domino-v4":raise ValueError("Invalid V4 source")
    if legacy.get("schema")!="policy-domino-next-v1":raise ValueError("Invalid classic baseline")
    result=build(v4,legacy)
    assert result["events"]
    assert all(x.get("basis","").startswith(TRUSTED) for x in result["actions"])
    assert all(a["event_id"] in {e["event_id"] for e in result["events"]}
               for a in result["actions"])
    DEST.write_text(json.dumps(result,ensure_ascii=False,indent=2),"utf8")
    # A standalone URL avoids mobile WebView serving an old cached page.
    # Keep the new impact view identical to Classic while reading Classic's
    # single updated source-of-truth data file.
    ui=(ROOT/"site"/"classic"/"index.html").read_text("utf8")
    old_fetch='fetch("./data.json?v="+Date.now(),{cache:"no-store"})'
    new_fetch='fetch("../classic/data.json?v="+Date.now(),{cache:"no-store"})'
    if old_fetch not in ui:
        raise RuntimeError("Classic source UI changed; refresh impact mirror only after review")
    impact=ROOT/"site"/"impact"
    impact.mkdir(parents=True,exist_ok=True)
    (impact/"index.html").write_text(ui.replace(old_fetch,new_fetch),"utf8")
    by_source=collections.Counter(a["evidence_scope"] for a in result["actions"])
    print("CLASSIC_V2_UX_V4_SOURCE",
          json.dumps({"events":len(result["events"]),"actions":len(result["actions"]),
            "by_source":dict(by_source),
            "original_v2_recheck":result["health"]["legacy_recheck"],
            "first_titles":[e["title"] for e in result["events"][:8]]},ensure_ascii=False))
    return result

if __name__=="__main__":run()
