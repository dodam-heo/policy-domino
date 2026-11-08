"""Policy Domino v2: source-wide official legal change collection.
No manually enrolled policy names, values, sectors, examples, or multipliers.
All findings are evidence records; unknown previous text is never invented.
"""
from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "v2_state.json"
OUTPUT = ROOT / "site" / "data.json"
API = "https://www.law.go.kr/DRF/"
HEADERS = {"User-Agent": "PolicyDomino/2.0 (public legal data research)"}
VALID = ("개정", "제정", "폐지", "정정")
MAX_PER_SOURCE = int(os.getenv("PD_LIST_LIMIT", "160"))
MAX_DETAILS = int(os.getenv("PD_DETAIL_LIMIT", "24"))
MAX_REFERENCES = int(os.getenv("PD_REFERENCE_LIMIT", "5"))
DOMAINS = (
    ("금액·산식", ("금액", "산정", "기준액", "요율", "수수료", "급여", "보조금", "단가", "비율", "부담금")),
    ("자격·대상", ("대상자", "자격", "선정기준", "소득", "연령", "요건", "해당하는 사람")),
    ("접수·서류", ("신청", "제출", "첨부", "증빙", "구비", "서식", "별지")),
    ("기한·시행", ("기간", "기한", "이내", "시행일", "유예", "경과조치")),
    ("인허가·심사", ("허가", "신고", "심사", "등록", "승인", "검사")),
    ("의무·제재", ("준수", "의무", "금지", "과태료", "제재", "점검", "감독")),
    ("조직·인력", ("정원", "직제", "직급", "사무분장", "하부조직", "직렬")),
)
ACTORS = (
    "시장·군수·구청장", "시장ㆍ군수ㆍ구청장", "특별자치시장",
    "시·도지사", "시ㆍ도지사", "교육감", "국민건강보험공단",
    "한국장학재단", "근로복지공단", "시장", "군수", "구청장",
)
REFERENCE_RE = re.compile(r"「([^」]{2,100})」")
FIGURE_RE = re.compile(r"(?<!\d)\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:원|만원|퍼센트|%|세|일|개월|년)(?![가-힣])")
PHRASE_RE = re.compile(r"([가-힣][가-힣 ]{2,24}(?:기준|요율|금액|수수료|선정기준|단가))")
RELEVANT_TEXT = re.compile(r"개정|제정|폐지|신설|변경|조정|지급|신청|기준|자격|의무|정원|기한|허가|산정")

def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def uid(*values):
    return hashlib.sha256("|".join(map(str, values)).encode("utf-8")).hexdigest()[:20]

def normalize(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()

def ymd(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 8:
        return ""
    try:
        return dt.datetime.strptime(digits, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""

def field(node, name):
    item = next((x for x in node.iter() if x.tag.split("}")[-1] == name), None)
    return normalize("".join(item.itertext())) if item is not None else ""

def read_state():
    try:
        return json.loads(STATE.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"events": {}, "snapshots": {}, "cursor": {"law": 0, "admrul": 0}}

def request(target, endpoint="lawSearch.do", **kwargs):
    oc = os.getenv("LAW_OC", "").strip() or "dori"
    query = urllib.parse.urlencode({"OC": oc, "target": target, "type": "XML", **kwargs})
    url = API + endpoint + "?" + query
    req = urllib.request.Request(url, headers=HEADERS)
    last = None
    for trial in range(3):
        try:
            with urllib.request.urlopen(req, timeout=22) as response:
                raw = response.read(4_000_000)
            root = ET.fromstring(raw)
            if root.tag.lower() in ("html", "error") or "오류" in root.tag:
                raise ValueError("공식 API 응답 오류")
            return root
        except (OSError, ET.ParseError, ValueError) as exc:
            last = exc
            if trial < 2:
                time.sleep(trial + 1)
    raise RuntimeError(f"{target} 공식 API 조회 실패: {type(last).__name__}: {str(last)[:110]}")

def row_of(node, target):
    if target == "law":
        title = field(node, "법령명한글")
        stable = field(node, "법령ID")
        serial = field(node, "법령일련번호")
        published = field(node, "공포일자")
        number = field(node, "공포번호")
        kind = field(node, "법령구분명") or "법령"
    else:
        title = field(node, "행정규칙명")
        stable = field(node, "행정규칙ID")
        serial = field(node, "행정규칙일련번호")
        published = field(node, "발령일자")
        number = field(node, "발령번호")
        kind = field(node, "행정규칙종류") or "행정규칙"
    if not (title and stable and serial and ymd(published)):
        return None
    revision = field(node, "제개정구분명")
    return {
        "source": target, "stable_id": stable, "serial": serial, "title": title,
        "published_at": ymd(published), "effective_date": ymd(field(node, "시행일자")),
        "number": number, "revision": revision, "kind": kind,
        "ministry": field(node, "소관부처명"),
        "url": ("https://www.law.go.kr/법령/" if target == "law"
                else "https://www.law.go.kr/행정규칙/") + urllib.parse.quote(title),
    }

def list_source(target, limit=MAX_PER_SOURCE, date_window=None, title_query=None):
    """Collect across sectors by official issue-date windows, not topic names.
    The newest window is checked on every run. Older windows are backfilled
    incrementally and unprocessed entries remain in the persistent queue.
    """
    collected = []
    modes = [{}] if target == "law" else [{"nw": "1"}, {"nw": "2"}]
    pages = max(1, (limit + 99) // 100)
    date_filter = {}
    if title_query:
        date_filter["query"] = str(title_query)
    if date_window:
        start, end = date_window
        key = "ancYd" if target == "law" else "prmlYd"
        date_filter[key] = start.strftime("%Y%m%d") + "~" + end.strftime("%Y%m%d")
    for mode in modes:
        for page in range(1, pages + 1):
            root = request(target, sort="ddes", display=100, page=page, **mode, **date_filter)
            nodes = [node for node in root.iter() if node.tag.split("}")[-1].lower() == target]
            if not nodes:
                if page == 1 and field(root, "totalCnt") not in ("0", ""):
                    raise RuntimeError(f"{target} 조회 레코드가 응답 건수와 다릅니다.")
                if page == 1 and field(root, "totalCnt") == "":
                    raise RuntimeError(f"{target} 원천에서 유효한 목록 응답을 받지 못했습니다.")
                break
            collected.extend(x for node in nodes if (x := row_of(node, target)))
            if len(nodes) < 100:
                break
    distinct = {}
    for entry in collected:
        distinct.setdefault((entry["stable_id"], entry["serial"]), entry)
    return sorted(distinct.values(), key=lambda x: (x["published_at"], x["serial"]), reverse=True)[:limit]

def historical_predecessor(record, cached=None):
    if cached and cached.get("serial") != record["serial"]:
        if cached.get("published_at", "") <= record["published_at"] and cached.get("clauses"):
            return {"record": cached, "clauses": cached["clauses"]}
    if record["source"] == "law":
        root = request("eflaw", LID=record["stable_id"], nw="1,2,3", sort="ddes", display=100)
    else:
        root = request("admrul", query=record["title"], nw="2", sort="ddes", display=100)
    target = record["source"]
    candidates = [row_of(x, target) for x in root.iter()
                  if x.tag.split("}")[-1].lower() == target]
    matches = [x for x in candidates if x and x["stable_id"] == record["stable_id"]
               and x["serial"] != record["serial"]
               and x["published_at"] <= record["published_at"]]
    matches.sort(key=lambda x: (x["published_at"], x["serial"]), reverse=True)
    if matches:
        return {"record": matches[0], "clauses": read_clauses(matches[0])}
    # Annual rules can be a *new* administrative-rule ID each year.
    # Find previous year's matching official title without hardcoded policy names.
    year_pattern = re.compile(r"(20\d{2})(\s*년(?:도)?)")
    match = year_pattern.search(record["title"])
    if not match or target != "admrul":
        return None
    previous_year = str(int(match.group(1)) - 1)
    expected = record["title"][:match.start(1)] + previous_year + record["title"][match.end(1):]
    prior_root = request("admrul", query=expected, nw="1", sort="ddes", display=100)
    prior_nodes = [row_of(x, "admrul") for x in prior_root.iter()
                   if x.tag.split("}")[-1].lower() == "admrul"]
    exact = [x for x in prior_nodes if x and normalize(x["title"]) == normalize(expected)
             and x["published_at"] < record["published_at"]]
    if not exact:
        # The older annual document can also be in the historical index.
        prior_root = request("admrul", query=expected, nw="2", sort="ddes", display=100)
        prior_nodes = [row_of(x, "admrul") for x in prior_root.iter()
                       if x.tag.split("}")[-1].lower() == "admrul"]
        exact = [x for x in prior_nodes if x and normalize(x["title"]) == normalize(expected)
                 and x["published_at"] < record["published_at"]]
    exact.sort(key=lambda x: x["published_at"], reverse=True)
    if not exact:
        return None
    # Preserve the separate legal identity; this is an annual STANDARD comparison,
    # not a claim that the new rule amended the prior rule's legal text.
    prior = exact[0]
    return {"record": prior, "clauses": read_clauses(prior), "annual_comparison": True}

def read_clauses(record):
    opts = {"MST": record["serial"]} if record["source"] == "law" else {"ID": record["serial"]}
    root = request(record["source"], endpoint="lawService.do", **opts)
    items = {}
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag == "조문단위":
            num = field(node, "조문번호")
            branch = field(node, "조문가지번호")
            label = f"제{num}조" + (f"의{branch}" if branch not in ("", "0") else "")
            if not num:
                continue
            pieces = [field(node, name) for name in ("조문내용", "항내용", "호내용", "목내용")]
            pieces += [normalize("".join(x.itertext())) for x in node.iter()
                       if x.tag.split("}")[-1] in ("항내용", "호내용", "목내용")]
            txt = normalize(" ".join(x for x in pieces if x))
            if txt:
                items[label] = txt[:12000]
        if tag in ("별표", "별표단위"):
            number = field(node, "별표번호") or str(len(items) + 1)
            text = field(node, "별표내용")
            if text:
                items["별표 " + number] = text[:12000]
    if items:
        return items
    # Several administrative-rule responses expose a flat 조문내용 instead.
    full = " ".join(normalize("".join(x.itertext())) for x in root.iter()
                    if x.tag.split("}")[-1] == "조문내용")
    if not full:
        raise RuntimeError("공식 본문에서 조문을 추출하지 못했습니다.")
    matches = list(re.finditer(r"제\s*\d+\s*조(?:의\s*\d+)?(?:\([^)]*\))?", full))
    if matches:
        for i, match in enumerate(matches[:150]):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(full)
            label = re.sub(r"\s+", "", match.group(0).split("(")[0])
            items[label] = full[match.start():end][:12000]
    else:
        items["본문"] = full[:16000]
    return items

def compare(old, new, record):
    changes = []
    for label in sorted(set(old) | set(new)):
        a, b = old.get(label, ""), new.get(label, "")
        if a == b:
            continue
        kind = "신설" if not a else "삭제" if not b else "개정"
        changes.append({
            "id": uid(record["source"], record["stable_id"], record["serial"], label),
            "article": label, "type": kind, "before": a, "after": b,
            "source_url": record["url"], "verified": True,
            "numbers_before": FIGURE_RE.findall(a)[:20], "numbers_after": FIGURE_RE.findall(b)[:20],
        })
    return changes[:70]

def changed_domains(change):
    delta = change["after"] + " " + change["before"]
    return [label for label, keys in DOMAINS if any(word in delta for word in keys)]

def actors(text):
    names = []
    for actor in ACTORS:
        if actor in text and not any(actor in other for other in names):
            names.append(actor)
    return names[:6]

def action_records(event):
    output = []
    for diff in event["changes"]:
        domains = changed_domains(diff)
        if not domains:
            continue
        before, after = diff["before"], diff["after"]
        # Named actor from actual changed legal text is stronger than the promulgating ministry.
        named = actors(after + " " + before)
        agency_names = named if named else [event["ministry"]] if event["ministry"] else []
        for agency in agency_names:
            for domain in domains[:3]:
                output.append({
                    "id": uid(event["id"], diff["article"], agency, domain),
                    "event_id": event["id"], "agency": agency,
                    "agency_role": "변경 조문에 명시된 업무주체" if named else "소관부처(집행기관 추가 확인)",
                    "work": domain, "article": diff["article"], "status": "영향 검토 필요",
                    "required_change": f"{diff['article']}의 {domain} 변경사항이 해당 기관의 실제 업무기준에 적용되는지 대조·확인",
                    "before": before[:1600], "after": after[:1600],
                    "basis": diff["source_url"], "target_verified": False,
                    "verification_note": "기관 내부 시스템이나 조치 완료 여부를 확인한 결과가 아닙니다.",
                })
    return output[:160]

def reference_names(text):
    return sorted(set(normalize(x) for x in REFERENCE_RE.findall(text) if len(x) <= 80))

def potential_terms(event):
    terms = [event["title"]]
    title = re.sub(r"(?:19|20)\d{2}\s*(?:년도|년)?", "", event["title"]).strip(" ·-")
    if len(title) > 5 and title != event["title"]:
        terms.append(title)
    for change in event["changes"][:5]:
        txt = change["after"]
        terms.extend(x.strip() for x in PHRASE_RE.findall(txt) if 5 <= len(x.strip()) <= 28)
    unique = []
    for t in terms:
        if t not in unique and 4 <= len(t) <= 80:
            unique.append(t)
    return unique[:3]

def link_relations(events):
    by_title = {e["title"]: e for e in events if e.get("title")}
    for e in events:
        e["upstream_changes"] = []
        e["downstream_changes"] = []
    edges = set()
    # An actual official citation is required. Similarity, shared dates, and numbers alone do not prove causation.
    for child in events:
        names = child.get("citations") or reference_names(" ".join(c["after"] for c in child.get("changes", [])))
        for name in names:
            parent = by_title.get(name)
            if parent is None or parent["id"] == child["id"]:
                continue
            relation = (parent["id"], child["id"])
            if relation in edges:
                continue
            edges.add(relation)
            basis = f"공식 본문에서 「{name}」을 명시적으로 인용 (변경의 원인 여부는 별도 검토)"
            parent["downstream_changes"].append({"event_id": child["id"], "title": child["title"], "evidence": basis})
            child["upstream_changes"].append({"event_id": parent["id"], "title": parent["title"], "evidence": basis})
    return len(edges)

def add_reference_hits(event, search_quota=MAX_REFERENCES):
    """Search across the *entire* official administrative-rule corpus for possible users
    of a changed standard, not just documents pre-enrolled in configuration.
    Every hit is a candidate until its actual text is verified.
    """
    hits = []
    errors = []
    queries = potential_terms(event)
    for term in queries[:search_quota]:
        for kind in ("admrul", "law"):
            try:
                root = request(kind, search=2, query=term, display=30, page=1)
                nodes = [n for n in root.iter() if n.tag.split("}")[-1].lower() == kind]
                for node in nodes:
                    item = row_of(node, kind)
                    if not item or (item["source"] == event["source"] and item["stable_id"] == event["stable_id"]):
                        continue
                    identifier = uid(item["source"], item["stable_id"])
                    if identifier in {x["id"] for x in hits}:
                        continue
                    hits.append({"id": identifier, "title": item["title"], "source": kind,
                                 "stable_id": item["stable_id"], "serial": item["serial"],
                                 "ministry": item["ministry"], "url": item["url"],
                                 "matched_term": term,
                                 "status": "공식 본문 검색 후보 · 인용/산식 미확인"})
            except Exception as exc:
                errors.append({"source": kind, "term": term, "error": str(exc)[:100]})
    return hits[:65], errors

def make_event(record, changes, comparison, checked_at, citations=None):
    return {
        "id": uid(record["source"], record["stable_id"], record["serial"]),
        "source": record["source"], "stable_id": record["stable_id"], "serial": record["serial"],
        "title": record["title"], "ministry": record["ministry"], "kind": record["kind"],
        "revision": record["revision"], "number": record["number"],
        "promulgated_at": record["published_at"], "effective_date": record["effective_date"],
        "url": record["url"], "comparison_status": comparison,
        "changes": changes, "change_count": len(changes), "verified_at": checked_at,
        "reference_candidates": [], "citations": citations or [], "upstream_changes": [], "downstream_changes": [],
    }

def run():
    stamp_now = stamp()
    state = read_state()
    cache = state.get("snapshots", {})
    records = state.get("events", {})
    cursor = state.get("cursor", {"law": 0, "admrul": 0})
    health = {"sources": {}, "partial": False, "errors": [], "verified_compared": 0,
              "not_compared": 0, "candidate_relations": 0, "confirmed_relations": 0,
              "collect_at": stamp_now, "scope": "법제처 법령+행정규칙 발령 목록; 실행별 처리 한도 있음"}
    # Scan the newest 14 days on every run and steadily backfill earlier windows.
    # Queue prevents high-volume windows from being lost to per-run detail limits.
    all_list = {}
    pending = {uid(x["source"], x["stable_id"], x["serial"]): x
               for x in state.get("pending", []) if x.get("serial")}
    today = dt.date.today()
    backfill_days = max(14, int(state.get("backfill_days", 14)))
    windows = [
        ("최근", today - dt.timedelta(days=14), today),
        ("과거 이력", today - dt.timedelta(days=backfill_days + 14),
         today - dt.timedelta(days=backfill_days))
    ]
    succeeded = 0
    for target in ("law", "admrul"):
        gathered = {}
        successful_windows = 0
        for label, window_start, window_end in windows:
            try:
                found = list_source(target, date_window=(window_start, window_end))
                successful_windows += 1
                succeeded += 1
                for record in found:
                    gathered[uid(target, record["stable_id"], record["serial"])] = record
                if len(found) >= MAX_PER_SOURCE:
                    health["partial"] = True
                health["sources"][target + ":" + label] = {
                    "status": "정상", "listed": len(found),
                    "range": window_start.isoformat() + "~" + window_end.isoformat()
                }
            except Exception as exc:
                error = {"source": target, "range": label, "error": str(exc)[:200]}
                health["errors"].append(error)
                health["sources"][target + ":" + label] = {"status": "실패", "listed": 0,
                                                             "error": str(exc)[:200]}
        # Future-effective policies can be adopted months before their start.
        # Discover next-year titles across ALL sectors, without enrolling policy names.
        try:
            upcoming=list_source(target, limit=MAX_PER_SOURCE,
                                 title_query=str(today.year+1))
            for record in upcoming:
                gathered[uid(target, record["stable_id"], record["serial"])] = record
            health["sources"][target+":연도별 선제 탐색"]={"status":"정상",
                "listed":len(upcoming),"year":today.year+1}
            if len(upcoming)>=MAX_PER_SOURCE:health["partial"]=True
        except Exception as exc:
            health["sources"][target+":연도별 선제 탐색"]={"status":"실패","listed":0,
                "error":str(exc)[:150]}
            health["errors"].append({"source":target,"range":"연도별 선제 탐색","error":str(exc)[:170]})
        all_list[target] = list(gathered.values())
        health["sources"][target] = {"status": "정상" if successful_windows == len(windows) else
                                    "부분" if successful_windows else "실패",
                                    "listed": len(gathered)}
    if not succeeded and not records:
        raise RuntimeError("공식 법령·행정규칙 원천 조회에 모두 실패했습니다.")
    backfill_days = 14 if backfill_days >= 364 else backfill_days + 14
    for target, listed in all_list.items():
        for record in sorted(listed, key=lambda x: x["published_at"], reverse=True):
            identifier = uid(target, record["stable_id"], record["serial"])
            if identifier not in records and identifier not in pending:
                pending[identifier] = record
    examined = []
    quota_each = max(1, MAX_DETAILS // 2)
    for target in ("law", "admrul"):
        matching = [(eid, record) for eid, record in pending.items() if record["source"] == target]
        priority = [(eid, record) for eid, record in matching
                    if (str(today.year+1) in record["title"]
                        or record.get("effective_date","") > today.isoformat())]
        # Reserve half the detail capacity for future-starting policy revisions,
        # while still inspecting contemporary official changes.
        chosen = priority[:max(1,quota_each//2)]
        chosen_ids={x[0] for x in chosen}
        chosen += [(eid,record) for eid,record in matching if eid not in chosen_ids][:quota_each-len(chosen)]
        for eid, record in chosen:
            examined.append({"id": eid, "record": record})
    new_count = 0
    for item in examined:
        record = item["record"]
        eid = item["id"]
        stable = uid(record["source"], record["stable_id"])
        if eid in records and records[eid].get("comparison_status") in ("신구 본문 비교 완료", "연도별 기준 비교 완료"):
            continue
        try:
            latest = read_clauses(record)
            cached = cache.get(stable)
            history = historical_predecessor(record, cached)
            if history:
                changes = compare(history["clauses"], latest, record)
                status = "연도별 기준 비교 완료" if history.get("annual_comparison") else "신구 본문 비교 완료"
                health["verified_compared"] += 1
            else:
                changes, status = [], "이전 연혁 본문 미확보"
                health["not_compared"] += 1
            e = make_event(record, changes, status, stamp_now,
                           citations=reference_names(" ".join(latest.values())))
            records[eid] = e
            cache[stable] = {"serial": record["serial"], "published_at": record["published_at"],
                             "clauses": latest, "verified_at": stamp_now}
            new_count += 1
            pending.pop(eid, None)
        except Exception as exc:
            health["errors"].append({"source": record["source"], "title": record["title"], "error": str(exc)[:160]})
            pending[eid]["failures"] = pending[eid].get("failures", 0) + 1
    events = sorted(records.values(), key=lambda e: (e.get("promulgated_at", ""), e["id"]), reverse=True)[:500]
    health["confirmed_relations"] = link_relations(events)
    # A bounded reverse look-up adds candidate matches without incorrectly declaring a domino.
    for event in (e for e in events if e.get("verified_at") == stamp_now and e.get("changes")):
        if health["candidate_relations"] >= 40:
            break
        matches, errors = add_reference_hits(event, search_quota=1)
        event["reference_candidates"] = matches
        health["candidate_relations"] += len(matches)
        health["errors"].extend(errors)
        if health["candidate_relations"] >= 40:
            health["partial"] = True
    health["pending_details"] = len(pending)
    if pending:
        health["partial"] = True
    # The event is a verified document revision only if a real before/after comparison succeeded.
    actions = [a for e in events if e.get("comparison_status") in ("신구 본문 비교 완료", "연도별 기준 비교 완료")
               for a in action_records(e)]
    data = {
        "schema": "policy-domino-v2", "generated_at": stamp_now,
        "health": {**health, "newly_examined": new_count, "events": len(events),
                   "actions": len(actions),
                   "status": "부분 수집" if health["errors"] or health["partial"] else "정상"},
        "events": events, "actions": actions,
        "method": "모든 변경과 공식 인용을 탐색하되 검증되지 않은 연관·기관 시스템을 사실로 표시하지 않음",
    }
    STATE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"events": {e["id"]: e for e in events}, "snapshots": cache,
                                 "pending": list(pending.values()),
                                 "backfill_days": backfill_days}, ensure_ascii=False, indent=2), "utf-8")
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"newly_examined": new_count, "sources": health["sources"],
                      "compared": health["verified_compared"], "errors": len(health["errors"])}, ensure_ascii=False))
    return data

if __name__ == "__main__":
    run()
