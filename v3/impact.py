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

TOKEN = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?|[가-힣]+|[A-Za-z]+|[^\s]")
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
    return result[:7]

def document_only(event):
    title=event.get("title","")
    return any(term in title for term in STRUCTURAL)

def effects(event):
    output=[]
    for change in event.get("changes",[]):
        for item in spans(change.get("before",""), change.get("after","")):
            cls=operations(change,[item])
            if cls:
                output.append({"article":change.get("article",""),"old":item["before"],
                               "new":item["after"],"context":item["context"],"kind":item["kind"],
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
    if event.get("comparison_status") not in ("신구 본문 비교 완료","연도별 기준 비교 완료"):
        return {"effects":[], "actions":[], "candidate_agencies":[], "quality":"전후 미검증", "priority":-1}
    changes=event.get("changes",[])
    parsed=effects(event)
    items=[]
    candidate=[]
    seen=set()
    for ch in changes:
        local=spans(ch.get("before",""), ch.get("after",""))
        local_ops=operations(ch,local)
        affected=explicit_roles(ch)
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
            candidate.append({"agency":event["ministry"],"work":local_ops[0][0],
                              "evidence_type":"소관 부처 정보","status":"집행기관 추가 조사 필요"})
    structural = document_only(event)
    number_pairs=sum(bool(x["old"] or x["new"]) and any(c.isdigit() for c in x["old"]+x["new"]) for x in parsed)
    substantive=len(parsed)>0
    priority=(100 if items else 65 if parsed else 10) + min(20,number_pairs*4) + min(10,len(items)*2)
    if structural:priority-=70
    quality="업무주체 명시" if items else "실질 변경 확인·집행기관 추적 필요" if parsed else "영향 미도출"
    return {"effects":parsed,"actions":items[:100], "candidate_agencies":candidate[:10],
            "quality":quality,"priority":priority, "category":"조직·인사" if structural else
            "제도·업무 변경" if substantive else "기타 변경"}

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
    for source in raw.get("events",[]):
        event=dict(source)
        identified=identify(event)
        event.update({"effects":identified["effects"],"institution_actions":identified["actions"],
                      "agency_candidates":identified["candidate_agencies"],
                      "analysis_quality":identified["quality"],"priority":identified["priority"],
                      "impact_category":identified["category"]})
        action_count+=len(identified["actions"])
        events.append(event)
    verified=[e for e in events if e.get("comparison_status") in ("신구 본문 비교 완료","연도별 기준 비교 완료")]
    operational=[e for e in verified if e["effects"] and e["impact_category"]!="조직·인사"]
    groups=group_events(events)
    return {"schema":"policy-domino-impact-v3","generated_at":raw.get("generated_at",""),
            "source_health":raw.get("health",{}),"events":events,"groups":groups,
            "impact_health":{"events":len(events),"verified_documents":len(verified),
                             "substantive_policy_events":len(operational),
                             "direct_actor_actions":action_count,
                             "limitations":"특정 기관 내부규정·시스템 변경 여부는 공식자료만으로 확정할 수 없음"}}
