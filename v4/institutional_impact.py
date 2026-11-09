"""Institution-operated policy dependencies from attributable official sources.

A generic evidence join for ANY public institution and ANY changed standard.
No institution names, program names, government ministries, hardcoded numbers
or event IDs appear in the engine. The machine-readable public-source catalogue
is a separable, auditable input rather than a list of hardcoded if/else cases.

Three stages remain distinct:
  (1) published change to a named reference value,
  (2) official institution statement that a program uses that reference,
  (3) internal operational changes (NEVER inferred as completed/mandatory).
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/"data"/"institution_policy_sources.json"
OFFICIAL_CHANGE_HOSTS=("law.go.kr","www.law.go.kr")
ELIGIBLE_RELATIONS={"numeric_formula","process_dependency"}

def compact(value):
    return re.sub(r"\s+","",str(value or "")).strip()

def usable_url(url):
    try:
        u=urlparse(str(url))
        return u.scheme=="https" and bool(u.hostname) and (
            u.hostname.endswith(".go.kr") or u.hostname.endswith(".or.kr"))
    except ValueError:
        return False

def official_law_url(url):
    return urlparse(str(url)).hostname in OFFICIAL_CHANGE_HOSTS and str(url).startswith("https://")

def load_sources(path=CATALOG):
    raw=json.loads(Path(path).read_text("utf8"))
    if raw.get("schema")!="policy-domino-institution-source-v1":
        raise ValueError("Unsupported institution source evidence")
    out=[];seen=set()
    for item in raw.get("sources",[]):
        src=item.get("source",{})
        criterion=item.get("criterion",{})
        aliases=criterion.get("aliases",[])
        if not all((
            item.get("id"),item.get("institution"),item.get("program"),
            item.get("institution_role"),item.get("target_location"),
            item.get("review_action"),item.get("work"),item.get("scope_note"),
            src.get("publisher"),src.get("evidence"),src.get("source_heading"),
            usable_url(src.get("url")),aliases,
            item.get("relation") in ELIGIBLE_RELATIONS,
            criterion.get("match")=="changed_field",
            item.get("followup_year"),
        )):
            raise ValueError("Missing or unsupported official agency dependency "+str(item.get("id")))
        if item["id"] in seen:raise ValueError("Duplicate institution evidence ID")
        if not all(len(compact(x))>=4 for x in aliases):
            raise ValueError("Generic one-word aliases are not reliable policy dependencies")
        if int(item.get("source_year",0))>int(item["followup_year"]):
            raise ValueError("Official reference cannot be from a future year")
        seen.add(item["id"])
        out.append(item)
    return out

def changed_fields(event):
    """Only the exact revised field, never the policy title or source org."""
    if not event.get("event_id") or event.get("presentation_source") not in (
        "v4_official_source","legacy_official_directive_awaiting_recheck"):
        return []
    out=[]
    for change in event.get("article_differences",[]):
        article=str(change.get("article","")).strip()
        before=str(change.get("before","")).strip()
        after=str(change.get("after","")).strip()
        if not (article and before and after and before!=after):
            continue
        if not official_law_url(change.get("source_url","")):
            continue
        # A changed source numeric standard is supported; a changed unrelated
        # prose snippet does not qualify for a formula-based dependency.
        old_digits=re.findall(r"\d[\d,]*",before)
        new_digits=re.findall(r"\d[\d,]*",after)
        if not old_digits or not new_digits or old_digits==new_digits:
            continue
        if len(before)>250 or len(after)>250:
            continue
        out.append({"field":article,"before":before,"after":after,
                    "source_url":change["source_url"]})
    return out

def relevant_change(event,entry):
    try:
        year=int(str(event.get("effective_date",""))[:4])
        if year!=int(entry["followup_year"]):return None
    except (ValueError,TypeError):
        return None
    for change in changed_fields(event):
        key=compact(change["field"])
        if any(compact(x) in key for x in entry["criterion"]["aliases"]):
            return change
    return None

def candidate_action(event,entry):
    """A verified institutional dependency becomes a *review* recommendation.

    The before/after here are the changed SOURCE STANDARD, not the
    implementing agency's own confirmed old/new rule or system status.
    """
    match=relevant_change(event,entry)
    if not match:return None
    if not usable_url(entry["source"]["url"]):return None
    unique=event["event_id"]+"|"+entry["id"]+"|"+match["field"]
    action_id="institution:"+hashlib.sha1(unique.encode()).hexdigest()[:22]
    policy_role="수치·비율 적용 기준" if entry["relation"]=="numeric_formula" else "조사·업무 절차 연계"
    status=("기관별 기준 반영 검토" if entry["relation"]=="numeric_formula"
            else "기관별 업무 연계 검토")
    official_source=entry["source"]
    return {
        "id":action_id,"event_id":event["event_id"],
        "agency":entry["institution"],
        "agency_role":entry["institution_role"],
        "work":entry["work"],
        "service":entry["program"],
        "law_title":event["title"],
        "article":match["field"],
        "effective_date":event.get("effective_date",""),
        "target_location":entry["target_location"],
        "what_to_change":entry["review_action"],
        "required_change":entry["review_action"],
        "changes":[{"field":match["field"],"before":match["before"],
                    "after":match["after"],"meaning":"원천 정책의 변경값(기관별 적용 금액 미확정)"}],
        "basis":match["source_url"],
        "agency_basis":official_source["url"],
        "institution_evidence":{
            "publisher":official_source["publisher"],
            "heading":official_source["source_heading"],
            "excerpt":official_source["evidence"],
            "source_year":entry["source_year"],
            "followup_year":entry["followup_year"],
            "program":entry["program"],"relationship":entry["relation"]
        },
        "status":status,
        "status_evidence":None,
        "confidence":"공식 운영기관의 기준 사용·업무 역할 확인",
        "verification_note":entry["scope_note"],
        "impact_link_basis":"공식 변경된 원천 기준 → 해당 기관이 공개한 기준 사용·업무 역할",
        "evidence_scope":"official_institutional_program_dependency",
        "institutional_implementation_verified":False,
        "is_direct_legal_amendment":False,
        "role_scope":policy_role,
    }

def connect(events,existing_actions,source_entries):
    """Works with any official institution source and arbitrary policy fields.

    The same institution can run two independently evidenced programs. Never
    infer policy consequences from shared words appearing only in their names.
    """
    actions=list(existing_actions)
    known={(a.get("event_id"),a.get("agency"),a.get("work"),
            compact(a.get("article"))) for a in actions}
    added=[]
    for event in events:
        for entry in source_entries:
            item=candidate_action(event,entry)
            if item is None:continue
            key=(item["event_id"],item["agency"],item["work"],compact(item["article"]))
            if key in known:continue
            actions.append(item);added.append(item);known.add(key)
    return actions,added
