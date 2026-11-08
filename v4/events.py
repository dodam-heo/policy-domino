"""Policy Domino v4 / build source-grounded legal change events.

Every event is backed by an official promulgation/history record and uses
two named OFFICIAL versions of the *same* regulation when claiming an
amendment. Annual successor notices with different IDs are a separate,
explicitly qualified comparison. Never use one act's numbers for another.
"""
from __future__ import annotations
import re,datetime as dt,hashlib
from v2 import collector as api
from v3 import semantic_diff

ACTORS=re.compile(
 r"(?<![가-힣])([가-힣]{2,35}(?:부장관|청장|처장|위원장|공단|공사|"
 r"재단|교육청|이사장|관리공단)|시장|군수|구청장|교육감)\s*(?:은|는|이|가)\s*"
)
DUTY=re.compile(
 r"하여야\s*한다|하여야\s*하며|해야\s*한다|적용한다|산정한다|선정한다|"
 r"지급한다|검사한다|검토한다|처리한다|관리한다|접수한다|시행한다|"
 r"담당한다|통지한다|허가한다|발급한다|제출한다|신고한다|정한다"
)
REPEAL=re.compile(r"(?:폐지|실효|효력종료)")
YEAR=re.compile(r"(?:19|20)\d{2}\s*년(?:도)?")
MAX_ARTICLES=70
MAX_EXCERPTS=10

def key(r):
    return api.uid(r["source"],r["stable_id"],r["serial"])

def label_revision(revision):
    t=str(revision or "")
    if REPEAL.search(t) and "제정" not in t:return "repeal"
    if "제정" in t and "개정" not in t:return "enactment"
    if "정정" in t:return "correction"
    return "amendment"

def history_rows(record,fetch=None):
    """Fetch previous official serial/version, not the last cached snapshot.

    Replaying historical versions MUST NOT compare with a *newer* cached act.
    """
    fetch=fetch or api.request
    src=record["source"]
    if src=="law":
        root=fetch("eflaw",LID=record["stable_id"],nw="1,2,3",
                   sort="ddes",display=100,page=1)
    elif src in ("admrul","ordin"):
        root=fetch(src,query=record["title"],nw="2",
                   sort="ddes",display=100,page=1)
    else:return []
    out=[]
    for node in root.iter():
        if node is root:continue
        if not any(c.tag.split("}")[-1] in
                   ("법령일련번호","행정규칙일련번호","자치법규일련번호") for c in list(node)):
            continue
        from v4.collect_index import as_record
        cand=as_record(node,src)
        if (cand and cand["stable_id"]==record["stable_id"] and
            cand["serial"]!=record["serial"] and
            cand["published_at"]<record["published_at"]):
            out.append(cand)
    return sorted(out,key=lambda x:(x["published_at"],x["serial"]),reverse=True)

def predecessor(record,records=None,fetch=None):
    """Find the immediate prior promulgated version of this same stable ID."""
    records=records or []
    cached=[x for x in records if x.get("source")==record["source"] and
            x.get("stable_id")==record["stable_id"] and
            x.get("serial")!=record["serial"] and
            x.get("published_at","")<record["published_at"]]
    try:
        official=history_rows(record,fetch)
    except Exception:
        official=[]
    versions=official+cached
    if not versions:return None
    return max(versions,key=lambda x:(x["published_at"],x["serial"]))

def annual_baseline(record,fetch=None):
    """Separate annual rule, separate legal identity; do not label amendment."""
    if record["source"]!="admrul":return None
    match=YEAR.search(record.get("title",""))
    if not match:return None
    year=int(re.search(r"\d{4}",match.group()).group())
    previous=record["title"][:match.start()]+str(year-1)+record["title"][match.start()+4:]
    fetch=fetch or api.request
    options=[]
    for nw in ("1","2"):
        root=fetch("admrul",query=previous,nw=nw,sort="ddes",display=100,page=1)
        from v4.collect_index import as_record
        for node in root.iter():
            if node is root:continue
            if not any(x.tag.split("}")[-1]=="행정규칙일련번호" for x in list(node)):
                continue
            item=as_record(node,"admrul")
            if item and api.normalize(item["title"])==api.normalize(previous) and (
                    item["published_at"]<record["published_at"]):
                options.append(item)
        if options:break
    return max(options,key=lambda x:(x["published_at"],x["serial"])) if options else None

def text_value(code):
    return str(code or "").strip()

def complete_text(clauses):
    return all(len(s)<12000 for s in clauses.values()) and bool(clauses)

def excerpts(changes,limit=MAX_EXCERPTS):
    """Full corresponding legal statements, not separated tokens."""
    result=[]
    for change in changes:
        matches=semantic_diff.pairs(change,limit=10)
        for x in matches:
            if x.get("before") and x.get("after") and (
                    len(x["before"])<14 or len(x["after"])<14):
                continue
            result.append({
                "article":change["article"],"before":x["before"],
                "after":x["after"],"kind":x["kind"],
                "quality":"complete_statement",
                "source_url":change.get("source_url","")
            })
            if len(result)>=limit:return result
    return result

def duties(pairs):
    """Only a full modified duty statement may qualify an actor.

    An agency's internal system, team, budget and compliance status remain
    unknown unless separately confirmed; don't generate such instructions.
    """
    unique={}
    for p in pairs:
        before,after=p["before"],p["after"]
        if not (before and after):continue
        for m in ACTORS.finditer(after):
            post=after[m.end():]
            duty=DUTY.search(post)
            if not duty or duty.start()>220:continue
            who=m.group(1)
            # An actor repeated in an unchanged lead-in is not evidence that
            # that actor owns an otherwise unrelated sentence.
            span=(who,p["article"])
            if span not in unique:
                unique[span]={"agency":who,"article":p["article"],
                   "status":"official_duty_changed",
                   "basis":"동일 변경 조문에서 기관명과 변경 의무 문장 확인",
                   "before":before,"after":after,
                   "action":"해당 조문에 명시된 업무 의무의 변경 내용 확인",
                   "implementation_verified":False}
    return list(unique.values())

def inspect(record,records=None,load=None,history=None,annual=None):
    """Produce one honest event, even if official detail extraction fails."""
    source=record
    record_id=key(source)
    event={
       "id":record_id,"title":source["title"],"source":source["source"],
       "stable_id":source["stable_id"],"serial":source["serial"],
       "promulgated_at":source.get("published_at",""),
       "effective_date":source.get("effective_date",""),
       "revision":source.get("revision",""),"kind":source.get("kind",""),
       "ministry":source.get("ministry",""),"url":source.get("url",""),
       "promulgation_number":source.get("number",""),
       "discovery":source.get("discovery_kind","official_date_index"),
       "lifecycle":label_revision(source.get("revision")),
       "verification":"official_record_only",
       "comparison":None,"changed_articles":[],"excerpts":[],"actors":[],
       "notes":[],"needs_attachment_check":False}
    load=load or api.read_clauses
    history=history or predecessor
    annual=annual or annual_baseline
    if event["lifecycle"]=="repeal":
        event["verification"]="verified_repeal_notice"
        event["notes"].append("폐지 사실 확인. 과거 조문에 등장한 기관의 새 의무를 추정하지 않음")
        return event,{}
    try:
        current=load(record)
    except Exception as exc:
        event["notes"].append("공식 현재 본문 조회 실패: "+str(exc)[:130])
        event["verification"]="detail_failed"
        return event,{}
    if not complete_text(current):
        event["notes"].append("별표 또는 장문 조문이 잘렸거나 읽히지 않아 완전 비교가 불가능함")
        event["needs_attachment_check"]=True
        event["verification"]="partial_official_text"
        return event,{}
    if event["lifecycle"]=="enactment":
        event["verification"]="verified_enactment"
        event["changed_articles"]=list(current)[:MAX_ARTICLES]
        event["notes"].append("새 규정의 제정 사실 확인. 별도 집행기관 의무 추론 금지")
        return event,current
    try:
        prior=history(record,records)
    except TypeError:
        prior=history(record)
    if not prior and source["source"]=="admrul":
        try:prior=annual(record)
        except Exception:prior=None
        if prior:event["comparison"]="annual_successor_standard"
    if not prior:
        event["notes"].append("정확한 구 버전 미확보. 변경값을 추정하지 않음")
        return event,current
    try:
        previous=load(prior)
    except Exception as exc:
        event["notes"].append("이전 버전 본문 확인 실패: "+str(exc)[:140])
        return event,current
    if not complete_text(previous):
        event["notes"].append("이전 버전 조문 또는 수치표가 불완전함")
        event["needs_attachment_check"]=True
        return event,current
    changes=api.compare(previous,current,record)
    if len(changes)>=MAX_ARTICLES:
        event["needs_attachment_check"]=True
        event["notes"].append("변경 조문 수가 처리 한도에 도달함. 일부 결과만 표시")
    event["changed_articles"]=[c["article"] for c in changes]
    event["excerpts"]=excerpts(changes)
    event["actors"]=duties(event["excerpts"])
    annual_type=(event.get("comparison")=="annual_successor_standard")
    event["comparison"]={
        "kind":"annual_successor" if annual_type else "same_regulation_version",
        "before_serial":prior["serial"],"after_serial":record["serial"],
        "before_title":prior["title"],"after_title":record["title"],
        "before_published":prior["published_at"],
        "after_published":record["published_at"],
        "same_stable_id":prior["stable_id"]==record["stable_id"],
        "source":"법제처 공식 이전·현재 본문"
    }
    event["verification"]="verified_annual_replacement" if annual_type else "verified_changed_clauses"
    if annual_type and not changes:
        event["needs_attachment_check"]=True
        event["notes"].append("연도별 고시 교체 확인. 첨부 표의 세부 금액은 아직 검증되지 않음")
    return event,current

def cluster_promulgations(events):
    """A real omnibus act may amend many different laws on ONE official
    promulgation number/date. This is an official common event identity, not
    an NLP title similarity edge.
    """
    clusters={}
    for e in events:
        number=str(e.get("promulgation_number","")).strip()
        day=e.get("promulgated_at","")
        src=e.get("source","")
        if src=="law" and day and number:
            group_key="law|"+day+"|"+number
        else:
            group_key=e["id"]
        group=clusters.setdefault(group_key,{"id":group_key,
            "date":day,"number":number if src=="law" else "",
            "members":[],"official_common_promulgation":src=="law"})
        group["members"].append(e)
    result=[]
    for g in clusters.values():
        members=g["members"]
        proven=sum(m["verification"].startswith("verified_") for m in members)
        agency_count=len({a["agency"] for m in members for a in m.get("actors",[])})
        g["summary"]=(
            f"공식 동일 공포번호 변경 법령 {len(members)}개" if len(members)>1 and
            g["official_common_promulgation"] else members[0]["title"])
        g["source_count"]=len(members)
        g["verified_count"]=proven
        g["agency_count"]=agency_count
        g["effective_at"]=min((x["effective_date"] for x in members
                        if x.get("effective_date")),default="")
        result.append(g)
    return sorted(result,key=lambda x:(x["verified_count"]>0,
            x["source_count"]>1,x["source_count"],x["date"]),reverse=True)
