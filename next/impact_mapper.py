"""Trace enacted legal amendments to a named agency's concrete operational change.

This is an evidence-first action mapper, NOT a claim that an agency is out of
compliance. The changed legal text is the CAUSE; an operational field/workflow
is the DESTINATION. Unverified IT system names and cross-agency relationships
are never invented.
"""
from __future__ import annotations
import re, hashlib
from datetime import date
from typing import Any

QUOTED = r'["“]([^"”]{1,180})["”]'
PAIR = re.compile(QUOTED+r'\s*(?:을|를|에서)\s*'+QUOTED+r'\s*(?:로|으로|로서|으로서)')
QUOTE = re.compile(QUOTED)

def compact(text):
    return re.sub(r"\s+"," ",text or "").strip()

def key(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:18]

def source_agency(law,directive=""):
    """Name the governed organization or explicitly assigned legal actor."""
    title=law.get("title","")
    if "개 법령" in title or "일괄개정" in (law.get("revision") or ""):
        return None
    base=title.split("와 그 소속기관",1)[0].split("과 그 소속기관",1)[0]
    for suffix in (" 직제 시행규칙"," 직제"," 운영규정"," 시행규칙"):
        if base.endswith(suffix):base=base[:-len(suffix)]
    if "직제" in title and base and len(base)<26:
        return base
    for role in ("시장·군수·구청장","시·도지사","교육감","국민건강보험공단"):
        if role in directive:return role
    return law.get("ministry") or None

def change_pairs(directive):
    """All explicit quoted old→new value pairs, including more than one in a table."""
    pairs=[]
    for m in PAIR.finditer(directive or ""):
        old,new=(compact(x) for x in m.groups())
        if not old or not new or old==new:continue
        prefix=compact(directive[max(0,m.start()-135):m.start()])
        # Get nearest full label since a punctuation/conjunction boundary.
        prefix=re.split(r'(?:로,|으로,|하고,|한다\.|중\s+)',prefix)[-1]
        field=compact(prefix[-90:]).strip(' ,')
        if re.fullmatch(r"[\d,.]+",old):
            # Do not claim a bare number alone describes a specific operational field.
            # The complete official directive remains available as evidence.
            label=field if field else "해당 기준 수치"
            before=f"{label} {old}"
            after=f"{label} {new}"
        else:
            before,after=old,new
            label=field or "기준 문구"
        pairs.append({"field":label[:110],"before":before[:190],"after":after[:190],
                      "old_literal":old,"new_literal":new})
    return pairs[:25]

def additions(directive):
    text=directive or ""
    rows=[]
    for m in re.finditer(QUOTE.pattern+r'\s*(?:을|를)?\s*신설',text):
        rows.append(compact(m.group(1)))
    return rows[:12]

def operational_area(law,directive):
    name=law.get("title","")
    text=directive or ""
    if "직제" in name:
        if any(w in text for w in ("정원","별표","사무관","전문관","주사","서기관")):
            return ("인사·정원 운영","직급·직렬별 정원 배정 및 관리","인력·정원 운영기준")
        return ("조직·업무분장 운영","담당 조직·보조기관 및 직위별 사무 배정","조직·업무분장 기준")
    if any(w in text for w in ("지원금","급여","지급액","부담금","수수료","기준액","비율","계산","산정")):
        return ("급여·금액 산정","지급·부담·수수료 산정 기준 및 계산 기능","지급·산정 규칙")
    if any(w in text for w in ("자격","대상자","소득기준","선정","연령","신청요건")):
        return ("신청·자격 심사","대상자 선정·자격 판정 조건","자격·선정 기준")
    if any(w in text for w in ("신청서","제출서류","구비서류","별지","서식")):
        return ("신청·민원 처리","신청서 항목 및 제출서류 검증","신청·서류 처리 기준")
    if any(w in text for w in ("신고","허가","등록","승인","검사")):
        return ("인허가·신고 처리","허가·신고·등록 심사조건","인허가 처리기준")
    if any(w in text for w in ("기한","기간","개월","일 이내")):
        return ("처리기한 운영","접수·처리·유예기간 판정","기한 산정 규칙")
    return None

def concrete_action(law,diff):
    """Return an operational target only when at least one actual amendment directive exists."""
    directive=compact(diff.get("directive") or "")
    previous=compact(diff.get("before") or "")
    revised=compact(diff.get("after") or "")
    if not directive and previous and revised and previous!=revised:
        directive=revised
    if not directive:return None
    agency=source_agency(law,directive)
    if not agency:return None
    area=operational_area(law,directive)
    if not area:return None
    domain,location,field=area
    pairs=change_pairs(directive)
    additions_list=additions(directive)
    article=diff.get("article","")
    before_literal=compact(diff.get("before") or "")
    after_literal=compact(diff.get("after") or "")
    if not pairs and before_literal and after_literal and before_literal!=after_literal:
        pairs=[{"field":field,"before":before_literal,"after":after_literal,
                "old_literal":before_literal,"new_literal":after_literal}]
    if pairs:
        summary="; ".join(f"{p['before']} → {p['after']}" for p in pairs[:3])
        what=("변경된 수치·문구를 "+domain+"의 실제 운영 기준과 적용 기능에 동일하게 설정하고, "
              "종전 기준이 남아 있지 않은지 확인")
        if len(pairs)>3:summary+=f" 외 {len(pairs)-3}개 항목"
    elif additions_list:
        summary="신설: "+"; ".join(additions_list[:3])
        what="신설된 항목을 "+domain+"의 대상 목록과 적용 기준에 추가하고 관련 업무 담당 범위를 확인"
    elif "신설" in directive:
        summary=directive[:240]
        what="신설 조항에 따른 담당 조직·업무 범위를 운영 기준에서 확인하고 적용"
    elif "삭제" in directive:
        summary=directive[:240]
        what="삭제된 조건이나 항목이 실제 업무 기준에 남아 있는지 확인하고 필요한 경우 제거"
    elif "개정" in directive or "한다" in directive:
        summary=directive[:240]
        what="변경된 기준이 실제 업무·서비스 처리조건에 적용되도록 항목별 확인"
    else:
        return None
    is_future=bool(law.get("effective_date") and law["effective_date"]>date.today().isoformat())
    confidence=("공식 변경 원문에서 전후 내용 확인" if pairs else
                "신설·삭제 지시가 개정문에 명시됨" if additions_list or "신설" in directive or "삭제" in directive else
                "법적 변경은 확인·실무 적용 대상은 검증 필요")
    id_=key("|".join((law.get("id",""),law.get("promulgated_at",""),
                       law.get("promulgation_number",""),agency,article,directive)))
    return {
        "id":id_,
        "event_id":key(law["id"]+law["promulgated_at"]+law["promulgation_number"]),
        "law_id":law.get("id",""),"law_title":law.get("title",""),
        "change_date":law.get("promulgated_at",""),"ministry":law.get("ministry",""),
        "agency":agency,"agency_role":"해당 법령에서 조직·업무를 정하는 직접 적용 기관" if "직제" in law.get("title","") else "소관기관 · 하위 집행기관 별도 추적 필요",
        "agency_level":"직접 영향 · 기타 기관 추가 분석 필요",
        "agency_basis":"변경 법령 제목과 소관기관 정보",
        "work":domain,"category":domain,
        "service":location, "target_location":location,
        "target_field":field, "target_verified":False,
        "verification_note":"정확한 기관별 업무시스템·서비스명 및 실제 적용 상태는 추가 확인이 필요합니다.",
        "source_change":summary,"required_change":what,
        "what_to_change":summary,
        "changes":pairs,
        "new_items":additions_list,
        "article":article,"before":before_literal[:2500],"after":after_literal[:2500],
        "directive":directive[:2100],"change_type":diff.get("type","개정"),
        "effective_date":law.get("effective_date",""),
        "basis":diff.get("source_url") or law.get("url",""),
        "status":"시행 예정" if is_future else "반영 확인 필요",
        "status_evidence":None,"status_checked_at":None,
        "confidence":confidence,
        "note":"개정문의 명시적 변경 지시와 해당 기관의 법정 기능을 연결한 조치 검토항목입니다. 실제 적용 확인 전 미조치로 판단하지 않습니다.",
    }

def map_actions(law,diffs):
    actions=[]
    for difference in diffs:
        item=concrete_action(law,difference)
        if item:actions.append(item)
    return list({x["id"]:x for x in actions}.values())
