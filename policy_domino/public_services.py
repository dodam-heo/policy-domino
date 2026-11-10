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
NUMBER = re.compile(r"(?<![\\d])\\d[\\d,]*(?:\\.\\d+)?\\s*(?:원|만원|%)")
RATIO = re.compile(r"(?:\\d{1,3}(?:\\.\\d+)?\\s*(?:%|퍼센트)|\\d(?:\\.\\d+)?\\s*배)")
# Generic *concept types*, never institution/program names. Require an actual
# named standard; standalone vague words such as '지원', '급여' cannot link.
STANDARD = re.compile(
    r"[가-힣]{2,22}?(?:중위소득|최저보장수준|산정기준|선정기준|기준소득|"
    r"소득인정액|지급기준|소득기준)")
LAW_TITLE = re.compile(r"「([^」]{3,110})」")
ARTICLE = re.compile(r"제\\s*\\d+\\s*조(?:의\\s*\\d+)?")
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
    text = normalize_text(text)
    terms = {m.group() for m in STANDARD.finditer(text)}
    # Avoid matching a long arbitrary title prefix instead of the named
    # variable. Suffix-similarity alone is not enough for a proof.
    return {v for v in terms if len(v) >= 4}


def changed_concepts(event: dict) -> list[dict]:
    """Only a real before/after numeric change creates an operative variable."""
    result = []
    for change in event.get("article_differences") or []:
        before, after = normalize_text(change.get("before")), normalize_text(change.get("after"))
        if not (before and after and before != after and
                (NUMBER.search(before) or NUMBER.search(after))):
            continue
        candidates = named_standard(
            normalize_text(change.get("article")) + " " +
            normalize_text(change.get("title")) + " " +
            normalize_text(event.get("title")))
        for concept in candidates:
            result.append({"concept": concept, "before": before[:300],
                           "after": after[:300], "article": change.get("article", ""),
                           "source_url": change.get("source_url", "")})
    return result


def matched_operating_rule(concept: str, text: str) -> str:
    """A named standard must participate in an actual threshold formula."""
    normalized = normalize_text(text)
    needle = re.sub(r"\\s+", "", concept)
    compact = re.sub(r"\\s+", "", normalized)
    if len(needle) < 4:
        return ""
    pos = compact.find(needle)
    if pos < 0:
        return ""
    neighborhood = compact[max(0, pos - 35): pos + len(needle) + 75]
    if not RATIO.search(neighborhood):
        return ""
    return neighborhood[:160]


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
        if not concepts:
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
    return edges
