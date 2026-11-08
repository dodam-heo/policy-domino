"""Evidence-first policy-impact analysis independent of any registered policy area.

An official document is an input, not a user-facing 'policy change' by default.
Only an observed before/after and a supported practical consequence may be
surfaced as an actionable impact. Documents without such evidence stay searchable.
"""
from __future__ import annotations

import datetime as dt
import difflib
import re
from collections import defaultdict

TOKEN = re.compile(r"\s+|\d+(?:,\d{3})*(?:\.\d+)?|[가-힣]+|[A-Za-z]+|[^\s]")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?(?:\s*(?:원|만원|%|퍼센트|명|세|일|개월|년))?")
ROLES = (
    ("시장·군수·구청장", ("시장·군수·구청장", "시장ㆍ군수ㆍ구청장", "시장, 군수 또는 구청장")),
    ("시·도지사", ("시·도지사", "시ㆍ도지사", "특별시장", "광역시장", "도지사")),
    ("교육감", ("교육감",)),
    ("국민건강보험공단", ("국민건강보험공단",)),
    ("근로복지공단", ("근로복지공단",)),
    ("한국장학재단", ("한국장학재단",)),
    ("시장", ("시장은", "시장에게", "시장이")),
    ("군수", ("군수는", "군수에게", "군수가")),
    ("구청장", ("구청장은", "구청장에게", "구청장이")),
)
# General operational classes, not registered laws, institutions, benefits or examples.
OPERATIONS = (
    ("선정·자격 판정", ("선정기준", "자격", "대상자", "소득인정", "자격요건", "지원대상", "지원자격"), "대상자 판정 규칙"),
    ("금액·산식 적용", ("금액", "산정", "요율", "급여", "지원금", "부담금", "수수료", "보조금", "기준액", "지급", "단가"), "산정·지급 기준표"),
    ("신청·접수 처리", ("신청서", "신청", "구비서류", "증빙", "별지", "제출서류", "첨부"), "신청서·접수 검증 항목"),
    ("심사·인허가", ("심사", "허가", "신고", "승인", "등록", "지정", "인증", "검사"), "심사·인허가 판단 기준"),
    ("처리기한·시행", ("기한", "기간", "경과조치", "유예", "시행일", "개월 이내", "일 이내", "이내"), "처리기한·적용시점"),
    ("고지·안내", ("안내", "공시", "공고", "고지", "통지", "공개"), "고지문·대외 안내 기준"),
    ("점검·제재", ("과태료", "벌금", "점검", "감독", "위반", "금지", "준수", "의무"), "점검·위반 판단 기준"),
    ("조직·인력", ("직제", "정원", "직급", "직렬", "사무분장", "소속기관", "하부조직"), "조직·정원 배정표"),
)
STRUCTURAL = ("직제", "정원", "사무분장", "인사규정", "기구", "하부조직", "전문직공무원")
INTERNAL = ("승진", "상훈", "공적심사", "인사관리", "포상", "공무원임용", "보통승진심사")
INDIVIDUAL = ("변경승인", "실시계획 변경", "통계작성의 변경승인", "사업계획 변경 승인")
SUBJECT = re.compile(r"(?:^|[\s,.;(])([가-힣]{2,22}(?:부장관|청장|처장|위원장|이사장|교육감|구청장|시장|군수|교육청|공단|공사|재단|기관장|원장))(?=은|는|이|가|에게|의|\s)")
TABLE_ART = re.compile(r"[┃│┏┓┗┛━┼┤├─┬┴]")

CAUSATION = re.compile(r"(?:개정|변경|신설|조정|인상|인하)(?:되었|됨|함|된|에)?\s*(?:에\s*)?따라")
SOURCE_REF = re.compile(r"「([^」]{2,110})」")

def tokens(value):
    return TOKEN.findall(value or "")

def trimmed(s, maxlen=140):
    return " ".join(str(s or "").split())[:maxlen]

def spans(before, after, max_items=8):
    """Extract local replacements, not repeat entire unchanged paragraphs."""
    a, b = tokens(before), tokens(after)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    result = []
    for operation, a0, a1, b0, b1 in matcher.get_opcodes():
        if operation == "equal":
            continue
        left = "".join(a[a0:a1]).strip()
        right = "".join(b[b0:b1]).strip()
        pre = "".join(b[max(0,b0-14):b0])
        post = "".join(b[b1:min(len(b),b1+14)])
        context = (pre+" "+right+" "+post).strip()
        if not left and not right:
            continue
        result.append({"before":trimmed(left,120), "after":trimmed(right,120),
                       "context":trimmed(context,170),
                       "old_context":trimmed("".join(a[max(0,a0-14):min(len(a),a1+14)]),170),
                       "kind":operation})
        if len(result)>=max_items:
            break
    return result

def operations(change, replacements):
    selected=[]
    original = " ".join([change.get("before",""),change.get("after","")])
    changed = " ".join(x["before"]+" "+x["after"]+" "+x["context"] for x in replacements)
    for operation,keywords,location in OPERATIONS:
        # Changed text or its immediate neighbourhood must contain the task indicator.
        if any(w in changed for w in keywords):
            selected.append((operation,location))
    if not selected:
        # A newly introduced or removed complete provision may carry a clear duty.
        if change.get("type") in ("신설","삭제"):
            for operation,keywords,location in OPERATIONS:
                if any(w in original for w in keywords):
                    selected.append((operation,location))
    return selected[:4]

def explicit_roles(change):
    text=change.get("after","")+" "+change.get("before","")
    result=[]
    for canonical, forms in ROLES:
        if any(form in text for form in forms) and canonical not in result:
            result.append(canonical)
    # Do not duplicate '시장' as well as the combined governing authority.
    if "시장·군수·구청장" in result:
        result=[x for x in result if x not in ("시장","군수","구청장")]
    for hit in SUBJECT.finditer(text):
        name=hit.group(1)
        if len(name)>=2 and name not in result:
            result.append(name)
    return result[:9]

ORG_TITLE = re.compile(r"^(.+?)(?:와 그 소속기관|과 그 소속기관)?\s*직제(?:\s*시행규칙)?$")
STAFF_FIELD = (
    ("총계", "공무원 정원 총계"),
    ("일반직 계", "일반직 공무원 정원"),
    ("3급 또는 4급 이하", "3급 또는 4급 이하 정원"),
    ("정원", "공무원 정원"),
)

def organization_owner(event):
    """A staffing table belongs to the named organization, not every agency
    mentioned anywhere in the rule's unrelated duty provisions.
    """
    if event.get("source") != "law":
        return None
    match=ORG_TITLE.fullmatch(event.get("title","").strip())
    return match.group(1).strip() if match else None

def staffing_field(change,old,new):
    if not re.fullmatch(r"\d[\d,]*",old or "") or not re.fullmatch(r"\d[\d,]*",new or ""):
        return None
    before,after=change.get("before",""),change.get("after","")
    if "정원표" not in before and "정원표" not in after:
        return None
    for needle,label in STAFF_FIELD:
        needle_pattern=r"\s*".join(map(re.escape,needle.split()))
        pattern_before=needle_pattern+r"\s*[\"“”']?"+re.escape(old)+r"(?!\d)"
        pattern_after=needle_pattern+r"\s*[\"“”']?"+re.escape(new)+r"(?!\d)"
        if re.search(pattern_before,before) and re.search(pattern_after,after):
            return label
    return None

def organization_actions(event,parsed):
    """Only a verified field in the changed appendices permits a staffing task."""
    owner=organization_owner(event)
    if not owner:
        return None
    changes={x.get("article"):x for x in event.get("changes",[])}
    actions=[]
    seen=set()
    for item in parsed:
        source=changes.get(item.get("article"),{})
        field=staffing_field(source,item.get("old",""),item.get("new",""))
        if not field:
            continue
        before=int(item["old"].replace(",",""))
        after=int(item["new"].replace(",",""))
        change=after-before
        direction=f"{change:+d}명" if change else "변동 없음"
        line=f"{field} {before:,}명 → {after:,}명 ({direction})"
        key=(item["article"],field)
        if key in seen:continue
        seen.add(key)
        actions.append({
            "agency":owner,"evidence_type":"개정된 공무원 정원표의 명시된 기관·항목",
            "work":"조직·정원 관리",
            "target_location":f"{item['article']} · {field}",
            "what_to_change":line,
            "required_change":f"{owner}의 {item['article']} 정원표에서 {field}가 {after:,}명으로 변경된 사실을 확인하고, 해당 기관의 정원·인사관리 자료 반영 여부를 점검",
            "article":item["article"],
            "source_url":item.get("source_url") or event.get("url",""),
            "basis_excerpt":re.search(
                r".{0,65}"+re.escape(item["new"])+r".{0,65}",
                source.get("after","")) .group(0) if re.search(
                r".{0,65}"+re.escape(item["new"])+r".{0,65}",
                source.get("after","")) else "",
            "verified_location":True,
            "actual_system_verified":False,
            "status":"공식 정원 변경 확인 · 기관별 반영 검토"
        })
    return actions

def document_only(event):
    title=event.get("title","")
    agency=event.get("ministry","")
    local_issuer=bool(agency and title.startswith(agency) and any(t in agency for t in ("병원","연구원","지방청","지방환경청","교육청")))
    return any(term in title for term in STRUCTURAL+INTERNAL) or local_issuer

def individual_notice(event):
    title=event.get("title","")
    # Site-specific approvals and one-off statistical registrations are official
    # acts, but not broad changed operational standards for other institutions.
    return any(term in title for term in INDIVIDUAL)

def meaningful_span(change, item):
    a,b=item["before"],item["after"]
    if not a and not b:return False
    if (len(TABLE_ART.findall(a+b+item.get("context","")))>=2 and
            not any(c.isdigit() for c in a+b)):return False
    # Reject formatting-only replacements and small dangling characters.
    norm=lambda s:re.sub(r"[^가-힣A-Za-z0-9]","",s)
    old,new=norm(a),norm(b)
    if old==new:return False
    if old and new:
        if len(old)==1 and len(new)==1 and not (old.isdigit() and new.isdigit()):return False
        return bool(len(old)>=2 and len(new)>=2 or old.isdigit() and new.isdigit())
    content=new or old
    # Explicit insertion/removal of a rule is meaningful; isolated table
    # fragments and moved article labels are not sufficient on their own.
    if change.get("type") in ("신설","삭제"):
        return len(content)>=8
    return len(content)>=5 and bool(re.search(r"가구|자격|지원|신청|급여|수수료|요율|기준|대상|의무|기한",item["context"]))

def effects(event):
    output=[]
    for change in event.get("changes",[]):
        for item in spans(change.get("before",""), change.get("after","")):
            if not meaningful_span(change,item):continue
            cls=operations(change,[item])
            if cls:
                output.append({"article":change.get("article",""),"old":item["before"],
                               "new":item["after"],"context":item["context"],"old_context":item["old_context"],"kind":item["kind"],
                               "operations":[x[0] for x in cls],
                               "source_url":change.get("source_url") or event.get("url","")})
    return output[:50]

def instruction(effect, operation, location):
    old, new = effect["old"], effect["new"]
    if old and new:
        specific = f"{old} → {new}"
    elif new:
        specific = f"신규 항목: {new}"
    else:
        specific = f"삭제 항목: {old}"
    return {"target":location,"what":specific,
            "how":f"{location}에서 변경값({specific})을 적용해야 하는지 확인하고, 해당 법정 업무를 수행하는 경우 시행일부터 적용",
            "source_article":effect["article"]}

def identify(event):
    """Distinguish an official change, a genuinely identified affected actor,
    and a ministry for which only an initial review is justified.
    """
    if event.get("comparison_status") not in ("신구 본문 비교 완료","연도별 기준 비교 완료","연도별 고시 교체 확인·수치표 미검증"):
        return {"effects":[], "actions":[], "candidate_agencies":[], "quality":"전후 미검증", "priority":-1,
                "category":"조직·내부운영" if document_only(event) else "개별 행정처분" if individual_notice(event) else "비교 미완료"}
    changes=event.get("changes",[])
    parsed=effects(event)
    owner=organization_owner(event)
    if owner:
        org_actions=organization_actions(event,parsed)
        broad="," in event.get("ministry","")
        is_substantive=bool(parsed)
        priority=(120 if broad else 45) if is_substantive else 1
        priority+=min(30,len(org_actions)*10)
        return {"effects":parsed, "actions":org_actions, "candidate_agencies":[],
                "quality":"공식 정원표 변경 항목·대상기관 확인" if org_actions else
                          "조직 관련 변경·정확한 업무 항목 추가 대조 필요",
                "priority":priority,
                "category":"조직개편·업무이관" if broad else "조직·내부운영"}
    items=[]
    candidate=[]
    seen=set()
    for ch in changes:
        local=spans(ch.get("before",""), ch.get("after",""))
        local_ops=operations(ch,local)
        # The person named elsewhere in a long article does not necessarily
        # carry responsibility for this local textual change.
        local_context=[p for p in parsed if p["article"]==ch.get("article","")]
        context_text=" ".join(p.get("context","")+" "+p.get("old_context","")
                              for p in local_context)
        affected=explicit_roles({"before":context_text,"after":""})
        for agency in affected:
            for task,location in local_ops[:3]:
                matches=[p for p in parsed if p["article"]==ch.get("article","") and task in p["operations"]]
                if not matches:
                    continue
                matching=matches[0]
                detail=instruction(matching,task,location)
                key=(agency,ch.get("article",""),task,detail["what"])
                if key in seen:continue
                seen.add(key)
                items.append({"agency":agency,"evidence_type":"법령 조문에 업무주체 명시",
                              "work":task,"target_location":location,"what_to_change":detail["what"],
                              "required_change":detail["how"],"article":detail["source_article"],
                              "source_url":matching["source_url"],"verified_location":False,
                              "status":"기관별 실제 반영 확인 필요"})
        if not affected and local_ops and event.get("ministry"):
            task,location=local_ops[0]
            matching=next((p for p in parsed if p["article"]==ch.get("article","") and task in p["operations"]),None)
            if matching:
                detail=instruction(matching,task,location)
                candidate.append({"agency":event["ministry"],"work":task,
                                  "target_location":location,"what_to_change":detail["what"],
                                  "required_change":"해당 정책의 소관기관이 "+location+"을 운영하는 부서·집행기관을 확인하고 변경값의 적용 여부를 검토",
                                  "article":ch.get("article",""),"evidence_type":"공식 문서 소관기관 정보",
                                  "status":"소관기관 확인 · 집행기관 조사 필요","verified_location":False})
    structural = document_only(event)
    single=individual_notice(event)
    broad_structure=(structural and event.get("source")=="law" and
      ("직제" in event.get("title","") or "소속기관" in event.get("title","")) and
      ("," in event.get("ministry","") or len(set(x["agency"] for x in items))>=3))
    number_pairs=sum(bool(x["old"] or x["new"]) and any(c.isdigit() for c in x["old"]+x["new"]) for x in parsed)
    substantive=len(parsed)>0
    priority=(100 if items else 65 if parsed else 10) + min(20,number_pairs*4) + min(10,len(items)*2)
    if (structural and not broad_structure) or single:priority-=70
    if broad_structure:priority+=35
    quality="업무주체 명시" if items else "실질 변경 확인·집행기관 추적 필요" if parsed else "영향 미도출"
    uniq={ (x["agency"],x["work"]):x for x in candidate }
    return {"effects":parsed,"actions":items[:100], "candidate_agencies":list(uniq.values())[:10],
            "quality":quality,"priority":priority, "category":"조직개편·업무이관" if broad_structure else "조직·내부운영" if structural else
            "개별 행정처분" if single else "제도·업무 변경" if substantive else "기타 변경"}

def strong_cause(parent,child):
    """Do not group documents based on dates/keywords or a naked citation."""
    if parent["id"]==child["id"]:
        return False
    source=child.get("amendment_reason","")
    if not source:
        return False
    if parent.get("number") and parent["number"] in source and CAUSATION.search(source):
        return True
    if ("「"+parent["title"]+"」") in source and CAUSATION.search(source):
        return True
    return False

def group_events(events):
    by_id={e["id"]:e for e in events}
    outgoing=defaultdict(list)
    children=set()
    for child in events:
        for up in child.get("upstream_changes",[]):
            parent=by_id.get(up.get("event_id"))
            if not parent or not strong_cause(parent,child):
                continue
            outgoing[parent["id"]].append(child["id"])
            children.add(child["id"])
    groups=[]
    for event in events:
        if event["id"] in children:continue
        related=[by_id[x] for x in outgoing[event["id"]]]
        groups.append({"group_id":event["id"],"event_id":event["id"],
                       "linked_ids":[x["id"] for x in related],
                       "date":max([event.get("promulgated_at","")]+[x.get("promulgated_at","") for x in related])})
    return groups

def analyze(raw):
    events=[]
    action_count=0
    candidate_count=0
    for source in raw.get("events",[]):
        event=dict(source)
        # Derived impact links from an older published run are not official
        # source material. Never carry them forward when recalculating actions.
        for stale in ("effects","institution_actions","agency_candidates",
                      "dependency_actions","policy_links","upstream_policy_links",
                      "dependent_rules","analysis_quality","priority","impact_category"):
            event.pop(stale,None)
        identified=identify(event)
        event.update({"effects":identified["effects"],"institution_actions":identified["actions"],
                      "agency_candidates":identified["candidate_agencies"],
                      "analysis_quality":identified["quality"],"priority":identified["priority"],
                      "impact_category":identified["category"]})
        action_count+=len(identified["actions"])
        candidate_count+=len(identified["candidate_agencies"])
        events.append(event)
    verified=[e for e in events if e.get("comparison_status") in ("신구 본문 비교 완료","연도별 기준 비교 완료","연도별 고시 교체 확인·수치표 미검증")]
    operational=[e for e in verified if e["effects"] and e["impact_category"] in ("제도·업무 변경","조직개편·업무이관")]
    groups=group_events(events)
    return {"schema":"policy-domino-impact-v3","generated_at":raw.get("generated_at",""),
            "source_health":raw.get("health",{}),"events":events,"groups":groups,
            "impact_health":{"events":len(events),"verified_documents":len(verified),
                             "substantive_policy_events":len(operational),
                             "direct_actor_actions":action_count,
                             "agency_owners_to_verify":candidate_count,
                             "limitations":"특정 기관 내부규정·시스템 변경 여부는 공식자료만으로 확정할 수 없음"}}
