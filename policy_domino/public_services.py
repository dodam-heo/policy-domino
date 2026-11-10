"""Official Gov24 public-service discovery and traceable policy-to-service edges.

Government24 service metadata comes from MOIS data.go.kr API 15113968.
Agency and programme names MUST originate from this catalogue; there are
no example-specific institution assignments. Linkage requires changed policy
evidence and the service's own operative criteria or changed-clause citation.
An indexed name, website keyword, or shared broad subject is never proof.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from policy_domino.engine.agency_actions import source_url

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "public_services.json"
API = "https://api.odcloud.kr/api/gov24/v3/"
SCHEMA = "policy-domino-public-services-v1"
NUMBER = re.compile(r"(?<![\d])\d[\d,]*(?:\.\d+)?\s*(?:원|만원|%)")
RATIO = re.compile(r"(?:\d{1,3}(?:\.\d+)?\s*(?:%|퍼센트)|\d(?:\.\d+)?\s*배)")
# Generic *concept types*, never institution/program names. Require an actual
# named standard; standalone vague words such as '지원', '급여' cannot link.
STANDARD_SUFFIXES = ("중위소득", "소득인정액", "최저보장수준",
                     "산정기준", "선정기준", "기준소득", "지급기준", "소득기준")
GENERIC_STANDARDS = {"산정기준", "선정기준", "지급기준", "소득기준", "기준소득"}
LAW_TITLE = re.compile(r"「([^」]{3,110})」")
ARTICLE = re.compile(r"제\s*\d+\s*조(?:의\s*\d+)?")
TRUSTED_DETAIL_HOSTS = ("gov.kr", "www.gov.kr", "m.gov.kr")


def blank_catalog() -> dict:
    return {"schema": SCHEMA, "services": {}, "next_page": 1,
            "total_reported": 0, "complete": False, "last_error": None}


def normalize_text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _public_link(value: object) -> str:
    raw = normalize_text(value)
    try:
        parsed = urlsplit(raw)
        if parsed.scheme == "https" and parsed.hostname in TRUSTED_DETAIL_HOSTS:
            return raw
    except ValueError:
        pass
    return ""


def normalize_service(row: dict) -> dict | None:
    if not isinstance(row, dict):
        return None
    sid = normalize_text(row.get("서비스ID"))
    agency = normalize_text(row.get("소관기관명"))
    title = normalize_text(row.get("서비스명"))
    if not all((sid, agency, title)) or len(sid) > 120:
        return None
    return {
        "id": sid, "agency": agency,
        "agency_code": normalize_text(row.get("소관기관코드")),
        "agency_type": normalize_text(row.get("소관기관유형")),
        "title": title,
        "criteria": normalize_text(row.get("선정기준"))[:3000],
        "eligible": normalize_text(row.get("지원대상"))[:2500],
        "benefits": normalize_text(row.get("지원내용"))[:1500],
        "description": normalize_text(row.get("서비스목적요약"))[:1000],
        "detail_url": _public_link(row.get("상세조회URL")),
        "updated": normalize_text(row.get("수정일시")),
    }


def fetch_page(endpoint: str, key: str, params: dict, timeout: int = 22) -> dict:
    if endpoint not in ("serviceList", "serviceDetail"):
        raise ValueError("Unsupported official service endpoint")
    arguments = {**params, "serviceKey": key}
    url = API + endpoint + "?" + urllib.parse.urlencode(arguments)
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "PolicyDomino/official-service-client",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(3_000_001)
        if len(raw) > 3_000_000:
            raise ValueError("Official service response too large")
        result = json.loads(raw)
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise ValueError("Malformed official service API response")
        return result
    except (OSError, ValueError) as exc:
        # Exception messages can include full URLs with a secret query key.
        raise RuntimeError("Gov24 public-service API unavailable: " +
                           type(exc).__name__) from None


def write_catalog(catalog: dict) -> None:
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CATALOG.with_suffix(".tmp")
    tmp.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(CATALOG)


def collect_services(previous: dict | None, key: str, max_pages: int = 40,
                     max_details: int = 120,
                     fetch: Callable = fetch_page,
                     checkpoint: Callable[[dict], None] | None = None) -> dict:
    """Resume full catalogue pagination; preserve prior official facts on errors.

    Detail endpoint is queried for services whose latest catalogue rows lack
    a serviceDetail snapshot. Paging never silently calls a sample a full list.
    """
    if not (1 <= max_pages <= 160 and 0 <= max_details <= 600):
        raise ValueError("Invalid public-service collection bounds")
    if not key:
        raise ValueError("Gov24 API key is required; do not publish mock services")
    catalog = (dict(previous) if isinstance(previous, dict) and
               previous.get("schema") == SCHEMA else blank_catalog())
    services = dict(catalog.get("services") or {})
    page = max(1, int(catalog.get("next_page") or 1))
    catalog["last_error"] = None
    def checkpoint_now():
        catalog["services"] = services
        if checkpoint is not None:
            checkpoint(catalog)
    for _ in range(max_pages):
        try:
            payload = fetch("serviceList", key, {"page": page, "perPage": 100})
        except (RuntimeError, ValueError) as exc:
            catalog["last_error"] = str(exc)
            break
        rows = payload.get("data")
        if not isinstance(rows, list):
            catalog["last_error"] = "Malformed public-service page"
            break
        for raw in rows:
            row = normalize_service(raw)
            if row is None:
                continue
            prior = services.get(row["id"], {})
            # Unchanged detail remains valid; modified list row invalidates it.
            if prior.get("updated") == row["updated"]:
                row["detail"] = prior.get("detail", {})
            services[row["id"]] = row
        catalog["total_reported"] = max(
            int(payload.get("totalCount") or 0),
            int(catalog.get("total_reported") or 0)
        )
        if len(rows) < 100 or page * 100 >= int(payload.get("totalCount") or 0):
            catalog["complete"] = True
            page = 1
            catalog["next_page"] = 1
            checkpoint_now()
            break
        page += 1
        catalog["next_page"] = page
        catalog["complete"] = False
        checkpoint_now()

    # A bounded round-robin detail queue gradually covers all legal references.
    # Only source-provided title/owner and body can later create a policy edge.
    for item in (s for s in services.values() if not s.get("detail")):
        if max_details <= 0:
            break
        try:
            payload = fetch("serviceDetail", key, {"page": 1, "perPage": 1,
                                                   "cond[서비스ID::EQ]": item["id"]})
        except (RuntimeError, ValueError) as exc:
            catalog["last_error"] = str(exc)
            break
        max_details -= 1
        row = next((x for x in payload.get("data", [])
                    if isinstance(x, dict) and
                    normalize_text(x.get("서비스ID")) == item["id"]), None)
        if row:
            item["detail"] = {
                "criteria": normalize_text(row.get("선정기준"))[:4000],
                "eligible": normalize_text(row.get("지원대상"))[:3000],
                "laws": normalize_text(row.get("법령"))[:3000],
                "rules": normalize_text(row.get("행정규칙"))[:3000],
                "ordinances": normalize_text(row.get("자치법규"))[:3000],
                "agency": normalize_text(row.get("소관기관명")),
                "online_url": _public_link(row.get("온라인신청사이트URL")),
            }
        else:
            item["detail"] = {"unavailable": True}
        checkpoint_now()
    checkpoint_now()
    return catalog


def load_catalog() -> dict:
    if not CATALOG.exists():
        return blank_catalog()
    try:
        result = json.loads(CATALOG.read_text("utf-8"))
        return result if result.get("schema") == SCHEMA else blank_catalog()
    except (ValueError, OSError):
        return blank_catalog()


def refresh_from_env() -> dict:
    current = load_catalog()
    key = os.getenv("PD_PUBLIC_SERVICE_KEY", "").strip()
    if not key:
        print("PUBLIC_SERVICE_CATALOG: no Gov24 API key; cached services retained")
        return current
    pages = int(os.getenv("PD_PUBLIC_SERVICE_PAGES", "40"))
    details = int(os.getenv("PD_PUBLIC_SERVICE_DETAILS", "120"))
    result = collect_services(current, key, max_pages=pages,
                              max_details=details, checkpoint=write_catalog)
    print("PUBLIC_SERVICE_CATALOG", json.dumps({
        "listed": len(result["services"]),
        "complete": result.get("complete", False),
        "next_page": result.get("next_page", 1),
        "with_details": sum(bool(x.get("detail")) for x in result["services"].values()),
        "error": result.get("last_error"),
    }, ensure_ascii=False))
    return result


def named_standard(text: str) -> set[str]:
    # Service linkage uses terms from actual policy metadata, not a sector
    # whitelist. Isolated broad nouns cannot establish a variable identity.
    parts = re.split(r"[\\s:·,/()\\[\\]{}]+", normalize_text(text))
    result = set()
    for part in parts:
        for suffix in STANDARD_SUFFIXES:
            if suffix in part:
                if suffix in GENERIC_STANDARDS:
                    # e.g. 급여선정기준, not the standalone '선정기준'
                    lead = part.split(suffix)[0].rstrip("0123456789")
                    if len(lead) < 2 or lead.endswith("년도"):
                        continue
                    concept = lead[-12:] + suffix
                else:
                    concept = suffix
                if len(concept) >= 4:
                    result.add(concept)
    return result


def changed_concepts(event: dict) -> list[dict]:
    """Only a real before/after numeric change creates an operative variable."""
    result = []
    for change in event.get("article_differences") or []:
        before, after = normalize_text(change.get("before")), normalize_text(change.get("after"))
        if not (before and after and before != after and
                (NUMBER.search(before) or NUMBER.search(after))):
            continue
        # Each changed row must carry its own named variable. Do not borrow
        # '중위소득' from an event title when this row changes an unrelated
        # benefit amount within the same multi-standard announcement.
        candidates = named_standard(
            normalize_text(change.get("article")) + " " +
            normalize_text(change.get("title")))
        if not candidates and len(event.get("article_differences") or []) == 1:
            candidates = named_standard(event.get("title", ""))
        for concept in candidates:
            result.append({"concept": concept, "before": before[:300],
                           "after": after[:300], "article": change.get("article", ""),
                           "source_url": change.get("source_url", "")})
    return result


def matched_operating_rule(concept: str, text: str) -> str:
    """A named standard must participate in an actual threshold formula."""
    normalized = normalize_text(text)
    needle = re.sub(r"\s+", "", concept)
    compact = re.sub(r"\s+", "", normalized)
    if len(needle) < 4:
        return ""
    pos = compact.find(needle)
    if pos < 0:
        return ""
    neighborhood = compact[max(0, pos - 35): pos + len(needle) + 75]
    if not RATIO.search(neighborhood):
        return ""
    return neighborhood[:160]


def changed_provisions(event: dict) -> list[dict]:
    """Actual changed clause with an unambiguous law title."""
    out = []
    for change in event.get("article_differences") or []:
        if change.get("before") == change.get("after"):
            continue
        raw = normalize_text(change.get("article"))
        hit = ARTICLE.search(raw)
        if not hit:
            continue
        law = raw.split(" · ", 1)[0].strip() if " · " in raw else ""
        if not law and event.get("presentation_source") == "v4_official_source":
            title = normalize_text(event.get("title"))
            if "동시 개정" not in title and "관련 법령" not in title:
                law = title
        if not law:
            continue
        out.append({"law": law, "article": normalize_text(hit.group()),
                    "source_url": change.get("source_url", ""),
                    "before": normalize_text(change.get("before"))[:300],
                    "after": normalize_text(change.get("after"))[:300]})
    return out


def cited_changed_provision(provisions: list[dict], service: dict) -> dict | None:
    """A serviceDetail law citation must name the SAME changed clause and
    apply it operatively; a law title alone cannot establish dependency.
    """
    detail = service.get("detail") or {}
    citations = " ".join(str(detail.get(k) or "") for k in (
        "laws", "rules", "ordinances"))
    criteria = " ".join(str(x or "") for x in (
        service.get("criteria"), detail.get("criteria"),
        service.get("eligible"), detail.get("eligible")))
    if not citations.strip() or not criteria.strip():
        return None
    compact = re.sub(r"\s+", "", citations)
    for item in provisions:
        title = re.sub(r"\s+", "", item["law"])
        article = re.sub(r"\s+", "", item["article"])
        if len(title) < 5 or not article:
            continue
        # Close adjacency prohibits importing a cited article from a second
        # unrelated statute in the public programme's legal-basis list.
        match = re.search(re.escape(title) + r".{0,35}?" + re.escape(article),
                          compact)
        if not match:
            continue
        excerpt = compact[max(0, match.start()-12):match.end()+50]
        if re.search(r"따른|따라|적용|준용|기준|해당", excerpt):
            return {**item, "excerpt": excerpt}
    return None


def service_edges(events: list[dict], catalog: dict,
                  max_edges: int = 1000) -> list[dict]:
    """No external institution inferences: owner, program and threshold must
    all appear in an official Gov24 service record.
    """
    if catalog.get("schema") != SCHEMA:
        return []
    edges, seen = [], set()
    for event in events:
        concepts = changed_concepts(event)
        provisions = changed_provisions(event)
        if not concepts and not provisions:
            continue
        for service in (catalog.get("services") or {}).values():
            agency = service.get("agency")
            program = service.get("title")
            sid = service.get("id")
            if not all((agency, program, sid)):
                continue
            detail = service.get("detail") or {}
            # An explicit service eligibility criterion is necessary; general
            # service descriptions and similar programme titles do not qualify.
            criteria = " ".join(filter(None, (
                service.get("criteria", ""), detail.get("criteria", ""),
                service.get("eligible", ""), detail.get("eligible", ""),
            )))
            for change in concepts:
                rule = matched_operating_rule(change["concept"], criteria)
                if not rule:
                    continue
                identity = (event["event_id"], sid, change["concept"])
                if identity in seen:
                    continue
                seen.add(identity)
                edges.append({
                    "event_id": event["event_id"], "service_id": sid,
                    "agency": agency, "agency_code": service.get("agency_code", ""),
                    "agency_type": service.get("agency_type", ""),
                    "service": program, "service_url": service.get("detail_url", ""),
                    "policy_concept": change["concept"],
                    "operating_rule": rule,
                    "source_rule": criteria[:500],
                    "source_updated": service.get("updated", ""),
                    "policy_before": change["before"],
                    "policy_after": change["after"],
                    "policy_article": change["article"],
                    "policy_source_url": change["source_url"],
                    "evidence_status": "service_formula_matched",
                })
                if len(edges) >= max_edges:
                    return edges
            # A separately verified changed-clause citation can link
            # non-monetary eligibility provisions without keyword guesses.
            cited = cited_changed_provision(provisions, service)
            if cited:
                identity = (event["event_id"], sid, cited["law"], cited["article"])
                if identity not in seen:
                    seen.add(identity)
                    criteria_text = " ".join(filter(None, (
                        service.get("criteria", ""), detail.get("criteria", ""),
                        service.get("eligible", ""), detail.get("eligible", ""),
                    )))
                    edges.append({
                        "event_id": event["event_id"], "service_id": sid,
                        "agency": agency, "agency_code": service.get("agency_code", ""),
                        "agency_type": service.get("agency_type", ""),
                        "service": program, "service_url": service.get("detail_url", ""),
                        "policy_concept": cited["article"],
                        "operating_rule": cited["excerpt"],
                        "source_rule": criteria_text[:500],
                        "source_updated": service.get("updated", ""),
                        "policy_before": cited["before"],
                        "policy_after": cited["after"],
                        "policy_article": cited["article"],
                        "policy_source_url": cited["source_url"],
                        "evidence_status": "service_clause_citation_matched",
                    })
                    if len(edges) >= max_edges:
                        return edges
    return edges


def agency_service_action(event: dict, edge: dict) -> dict:
    """Create one program-specific action from two independent official facts.

    Parent change is law.go.kr; operation of the program is Gov24's named
    owner and live published eligibility criterion. No hardcoded agency,
    program, obligation or implementation status is inserted.
    """
    raw_id = "|".join((event["event_id"], edge["service_id"],
                       edge["policy_concept"]))
    uid = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:20]
    parent_current = event.get("presentation_source") == "v4_official_source"
    parent_evidence = source_url(edge.get("policy_source_url"))
    if parent_evidence == "https://www.law.go.kr":
        raise ValueError("Public-service relation has no verified policy citation")
    source_kind = (("service_cited_changed_article_verified"
                    if edge.get("evidence_status") == "service_clause_citation_matched"
                    else "service_formula_dependency_verified") if parent_current
                   else "legacy_service_dependency_pending_recheck")
    # These values are the PARENT base standard, not a claimed pre/post
    # threshold in the agency's own published programme.
    before, after = edge["policy_before"], edge["policy_after"]
    return {
        "id": "svc:" + uid,
        "event_id": event["event_id"],
        "agency": edge["agency"],
        "agency_code": edge["agency_code"],
        "agency_role": "공공서비스 소관기관(정부24 공식 등록)",
        "service_id": edge["service_id"],
        "service": edge["service"],
        "service_url": edge["service_url"],
        "service_evidence_source": "gov24_api",
        "service_evidence_rule": edge["source_rule"],
        "service_criteria": edge["operating_rule"],
        "service_record_updated": edge["source_updated"],
        "work": "공공서비스 선정·지원기준",
        "target_location": edge["service"] + " · " + edge["policy_concept"],
        "what_to_change": edge["policy_concept"] + ": " + before + " → " + after,
        "changes": [{"before": before, "after": after}],
        "required_change": (edge["service"] + " · " + edge["policy_concept"] +
                            " 기준 변경: " + before + " → " + after),
        "article": edge["policy_article"],
        "law_title": event.get("title", ""),
        "effective_date": event.get("effective_date", ""),
        "basis": parent_evidence,
        "impact_link_basis": (
            "행정안전부 공공서비스의 실제 변경 조항 적용 인용"
            if edge.get("evidence_status") == "service_clause_citation_matched"
            else "행정안전부 공공서비스 선정기준의 " +
                 edge["policy_concept"] + " 비율·산식 인용"),
        "status": ("반영 확인 필요" if parent_current
                   else "최신 근거 재확인 필요"),
        "confidence": ("공식 정책 기준값·정부24 사업 선정기준 교차 확인"
                       if parent_current else
                       "이전 공식 기준액·정부24 사업 선정기준 교차 확인"),
        "evidence_scope": source_kind,
        "verification_note": (
            "공식 서비스 선정기준이 변경된 기준변수를 이용하는 관계를 확인. "
            "실제 기관의 공고·업무시스템 반영 여부는 미확인."
        ),
    }
