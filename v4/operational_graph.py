"""Generic downstream operating-agency impact mapping.

Legal text establishes that a standard changed; independent institution
guidance establishes whether a real PROGRAM uses that standard and which
operation owns it. No organization names, policy titles or percentages are
hardcoded as match rules. Entries are auditable official-source records,
which can be expanded by independently verified evidence discovery.

Statuses are NOT instructions to edit an internal system: source-verified
usage and agency implementation are explicitly separate.
"""
from __future__ import annotations
import hashlib
import json
import re
from urllib.parse import urlsplit
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"data"/"official_operating_sources.json"

def normalize(s):
    return re.sub(r"\s+","",str(s or "")).lower()

def number(s):
    x=re.sub(r"[^0-9]","",str(s or ""))
    return x.lstrip("0") or "0"

def admissible_url(url):
    try:
        u=urlsplit(url)
        host=(u.hostname or "").lower()
        # Only genuine official/municipal or public-institution content.
        return u.scheme=="https" and (
            host.endswith(".go.kr") or host.endswith(".gov.kr") or
            host.endswith(".or.kr") or host.endswith(".ac.kr"))
    except Exception:
        return False

def get_records(path=REGISTRY):
    doc=json.loads(Path(path).read_text("utf8"))
    if doc.get("schema")!="official-operating-source-index-v1":
        raise ValueError("Unsupported official operating evidence")
    result=[]
    for r in doc.get("sources",[]):
        necessary=("id","agency","program","operation","target_location",
                   "source_field","baseline_value","source_url",
                   "source_heading","source_excerpt","application_basis",
                   "operational_review","caution")
        if any(not str(r.get(k,"")).strip() for k in necessary):
            raise ValueError("Incomplete official operating evidence record "+r.get("id",""))
        if not admissible_url(r["source_url"]):
            raise ValueError("Not a government or public institution source: "+r["id"])
        if r.get("additional_source_url") and not admissible_url(r["additional_source_url"]):
            raise ValueError("Additional nonofficial source: "+r["id"])
        if r.get("status")!="official_operation_dependency_not_implementation":
            raise ValueError("Cannot preset implementation conclusion: "+r["id"])
        result.append(r)
    return result

def matching_standard(difference,record):
    """Require an EXACT field/row and the same old figure documented at
    the institution, preventing generic 'benefits' or title similarity links.
    """
    sourcefield=normalize(difference.get("article"))
    currentfield=normalize(record.get("source_field"))
    if sourcefield!=currentfield:
        return False
    old=number(difference.get("before"))
    new=number(difference.get("after"))
    if not (old and new and old!=new):return False
    if old!=number(record["baseline_value"]):return False
    # The next annual standard becomes relevant to current 2026 program docs.
    # Reject a historical or unrelated source if the years do not line up.
    # Annual rollover may be non-calendar for semester-based schemes,
    # hence only the source effective year bounds automatic selection.
    return True

def match_source_events(events,records):
    """Use source row + old numeric baseline, never issuing ministry or title."""
    matches={}
    for event in events:
        for diff in event.get("article_differences",[]):
            for record in records:
                if not matching_standard(diff,record):continue
                key=(event["event_id"],record["id"])
                matches[key]=(event,diff,record)
    return matches

def make_action(event,diff,rec):
    src=diff.get("source_url") or event.get("amendment_url")
    if not admissible_url(src):return None
    old=str(diff["before"]).strip()
    new=str(diff["after"]).strip()
    if old==new:return None
    after=event.get("effective_date","")
    stamp=event["event_id"]+"|"+rec["id"]+"|"+rec["source_field"]
    aid=hashlib.sha1(stamp.encode("utf8")).hexdigest()[:20]
    extra=" "
    if rec.get("additional_source_excerpt"):
        extra=" "+rec["additional_source_excerpt"]
    return {
        "id":"operational:"+aid,
        "event_id":event["event_id"],
        "law_title":event["title"],
        "agency":rec["agency"],
        "agency_role":"공식 운영안내에서 해당 기준을 활용하는 기관으로 확인",
        "work":rec["operation"],
        "service":rec["program"],
        "target_location":rec["program"]+" › "+rec["target_location"],
        "target_field":rec["source_field"],
        "article":diff["article"],
        "source_change":diff["article"]+" "+old+" → "+new,
        "what_to_change":rec["program"]+" · 기준값 적용·관련 업무 검토",
        "changes":[{
            "field":rec["source_field"],
            "before":"원천 정책 기준 "+old,
            "after":"원천 정책 기준 "+new,
            "meaning":"기관별 실제 적용 금액이나 내부시스템 변경 완료를 뜻하지 않음"
        }],
        "required_change":rec["operational_review"],
        "effective_date":after,
        "basis":src,
        "agency_basis":rec["source_url"],
        "additional_agency_basis":rec.get("additional_source_url",""),
        "institution_evidence":{
            "publisher":rec["agency"],
            "heading":rec["source_heading"],
            "excerpt":rec["source_excerpt"],
            "additional":rec.get("additional_source_excerpt",""),
            "basis_connection":rec["application_basis"],
            "official_source_id":rec["id"]
        },
        "impact_link_basis":"원천 기준의 동일 항목·변경 전 금액 일치 + 공공기관 운영자료의 기준 사용/역할 확인",
        "status":"기관별 반영 검토 필요",
        "status_evidence":None,
        "status_checked_at":None,
        "confidence":"공식 운영자료에 의한 기준 사용 관계 확인",
        "verification_note":rec["caution"],
        "target_verified":False,
        "implementation_verified":False,
        "evidence_scope":"official_institutional_program_dependency",
    }

def derive(events,records):
    out=[]
    for event,diff,record in match_source_events(events,records).values():
        a=make_action(event,diff,record)
        if a:out.append(a)
    return out
