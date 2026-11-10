"""Official National Law Information Center adapter for the active pipeline.

Only source querying, parsing and changed-article comparison live here.
No legacy V2 watcher, output state, policy categories or deployment side effects.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from policy_domino import attachments

API = "https://www.law.go.kr/DRF/"
HEADERS = {"User-Agent": "PolicyDomino/official-source-client"}
FIGURE_RE = re.compile(r"(?<!\d)\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:원|만원|퍼센트|%|세|일|개월|년)(?![가-힣])")


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

def request(target, endpoint="lawSearch.do", **kwargs):
    oc = os.getenv("LAW_OC", "").strip()
    if not oc:
        raise RuntimeError("LAW_OC must be configured for official API collection")
    query = urllib.parse.urlencode({"OC": oc, "target": target, "type": "XML", **kwargs})
    url = API + endpoint + "?" + query
    req = urllib.request.Request(url, headers=HEADERS)
    last = None
    for trial in range(3):
        try:
            with urllib.request.urlopen(req, timeout=22) as response:
                raw = response.read(24_000_001)
            if len(raw) > 24_000_000:
                raise ValueError("공식 API 응답이 24MB를 초과하여 안전하게 처리를 중단했습니다.")
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

class ExtractedClauses(dict):
    """Official clauses plus attachment links that still need verification."""
    def __init__(self, values, unresolved=None):
        super().__init__(values)
        self.unresolved_attachments=unresolved or []


def read_clauses(record):
    opts = {"MST": record["serial"]} if record["source"] in ("law","ordin") else {"ID": record["serial"]}
    root = request(record["source"], endpoint="lawService.do", **opts)
    items = {}
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag in ("조문단위","조문"):
            num = field(node, "조문번호")
            branch = field(node, "조문가지번호")
            label = f"제{num}조" + (f"의{branch}" if branch not in ("", "0") else "")
            if not num:
                continue
            # Collect each XML provision component exactly once. The old
            # implementation added the first 항/호/목 with field() and then
            # added every 항/호/목 again through node.iter(), producing fake
            # reordered or repeated clauses in text diffs.
            parts = []
            tags = {"조문내용","항내용","호내용","목내용"}
            for x in node.iter():
                if x.tag.split("}")[-1] not in tags:
                    continue
                # When a component wraps child provision nodes, its itertext
                # includes their text. Use its own text in that case.
                children = [y for y in x.iter() if y is not x and
                            y.tag.split("}")[-1] in tags]
                value = normalize(x.text if children else "".join(x.itertext()))
                if value and (not parts or parts[-1] != value):
                    parts.append(value)
            txt = normalize(" ".join(parts))
            if txt:
                items[label] = txt[:12000]
        if tag in ("별표", "별표단위"):
            number = field(node, "별표번호") or str(len(items) + 1)
            text = field(node, "별표내용")
            if text:
                items["별표 " + number] = text[:12000]
    # National Law Information's official XML exposes annex PDF/HWP links.
    # Unreadable files stay pending instead of masquerading as compared text.
    unresolved=[]
    seen_links=set()
    for node in root.iter():
        tag=node.tag.split("}")[-1]
        if tag not in ("별표단위","첨부파일"):
            continue
        number=field(node,"별표번호") or str(len(seen_links)+1)
        title=field(node,"별표제목") or field(node,"첨부파일명")
        label=("별표 "+number if tag=="별표단위" else "첨부 "+number)
        link=(field(node,"별표서식PDF파일링크") or
              field(node,"별표서식파일링크") or field(node,"첨부파일링크"))
        url=attachments.official_url(link)
        if not url or url in seen_links:
            continue
        seen_links.add(url)
        if label in items and len(items[label])>=100:
            continue
        extracted=""
        if attachments.enabled() and len(seen_links)<=4:
            try:
                extracted=attachments.extract(url)
            except (OSError,ValueError,RuntimeError,ET.ParseError,zipfile.BadZipFile):
                extracted=""
        if extracted:
            items[label]=normalize(extracted)
        else:
            unresolved.append({"title":title or label,"url":url,"label":label})
    if items:
        return ExtractedClauses(items,unresolved)
    # Several administrative-rule responses expose a flat 조문내용 instead.
    full = " ".join(normalize("".join(x.itertext())) for x in root.iter()
                    if x.tag.split("}")[-1] == "조문내용")
    if not full:
        raise RuntimeError("공식 본문에서 조문을 추출하지 못했습니다.")
    # Split only structural headings. A sentence citing "제6조" is not a new article.
    # Some flat administrative-rule XML concatenates all article titles
    # after numbered list items (not a period). Detect real named headings
    # rather than attributing 제3조 obligations to 제2조.
    matches = list(re.finditer(
        r"(?<![가-힣0-9])제\s*\d+\s*조(?:의\s*\d+)?\s*\([^)\n]{1,75}\)",
        full))
    if matches:
        for i, match in enumerate(matches[:150]):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(full)
            label = re.sub(r"\s+", "", match.group(0).split("(")[0])
            items[label] = full[match.start():end][:12000]
    else:
        items["본문"] = full[:16000]
    return ExtractedClauses(items,unresolved)

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
