"""Source-backed, presentation-only facts about amended provisions.

This module does not determine policy impact or infer agency duties. It turns
official before/after clauses into inspectable, bounded source excerpts.
"""
from __future__ import annotations

import difflib
import re

from policy_domino import semantic_diff

TITLE = re.compile(r"제\s*\d+조(?:의\s*\d+)?\s*\(([^)\n]{2,90})\)")
TOKENS = re.compile(r"\s+|[^\s]+")
NUMERIC = re.compile(
    r"(?<!\d)\d[\d,]*(?:\.\d+)?\s*(?:만원|원|명|일|개월|년|세|%)"
)


def norm(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def category(old: str, new: str) -> str:
    if not old:
        return "조문 신설"
    if not new:
        return "조문 삭제"
    if semantic_diff.fingerprint(old) == semantic_diff.fingerprint(new):
        return "표기 정비"
    return "내용 개정"


def highlight(old: str, new: str, max_changed: int = 240) -> dict:
    """Token-level difference with short unchanged context, never loose words.

    The preview is an annotated *quotation*, not a generated explanation.
    Original source sentences remain available in the detail disclosure.
    """
    a = TOKENS.findall(str(old or ""))
    b = TOKENS.findall(str(new or ""))
    operations = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    first = next((i for i, op in enumerate(operations) if op[0] != "equal"), -1)
    last = next((i for i in range(len(operations)-1, -1, -1)
                 if operations[i][0] != "equal"), -1)

    def render(side: int) -> list[dict]:
        result = []
        for i, (op, a0, a1, b0, b1) in enumerate(operations):
            lo, hi = (a0, a1) if side == 0 else (b0, b1)
            part = "".join((a if side == 0 else b)[lo:hi])
            if not part:
                continue
            changed = op != "equal"
            if changed:
                if len(part) > max_changed:
                    part = part[:max_changed].rstrip() + "…"
            else:
                if first == -1:
                    part = part[:100] + ("…" if len(part) > 100 else "")
                elif i < first:
                    part = ("…" if len(part) > 65 else "") + part[-65:]
                elif i > last:
                    part = part[:65] + ("…" if len(part) > 65 else "")
                elif len(part) > 80:
                    part = part[:35] + " … " + part[-35:]
            if part:
                result.append({"text": part, "changed": changed})
        return result

    return {"before": render(0), "after": render(1)}


def source_pairs(changes: list[dict], limit: int = 70) -> list[dict]:
    """One useful, source-identified comparison per changed article.

    The full article count is retained separately. If sentence matching
    cannot safely align a source, use labelled article excerpts instead of
    claiming an independently verified sentence-to-sentence correspondence.
    """
    result = []
    seen = set()
    for change in changes:
        article = norm(change.get("article"))
        old, new = str(change.get("before") or ""), str(change.get("after") or "")
        if old == new or (not old and not new):
            continue
        pairs = semantic_diff.pairs(change, limit=4)
        matched = next((p for p in pairs if p["before"] and p["after"]), None)
        if matched:
            old, new = matched["before"], matched["after"]
            basis = "동일 조항의 변경 문장 대조"
        else:
            old, new = old[:900], new[:900]
            basis = "동일 조항의 종전·개정 원문 대조"
        identity = (article, norm(old), norm(new))
        if identity in seen:
            continue
        seen.add(identity)
        result.append({
            "article": article,
            "type": category(old, new),
            "before": old, "after": new,
            "source_url": change.get("source_url", ""),
            "comparison_basis": basis,
            "preview": highlight(old, new),
        })
        if len(result) >= limit:
            break
    return result


def concise_summary(comparisons: list[dict], count: int) -> str:
    """Fact-only fallback; never paste cut-out grammatical fragments."""
    if not comparisons:
        return "공식 변경 조문의 내용 비교가 진행 중입니다."
    phrases = []
    for row in comparisons[:3]:
        before = norm(row.get("before"))
        after = norm(row.get("after"))
        heading_match = TITLE.search(after or before)
        subject = norm(heading_match.group(1)) if heading_match else ""
        article = norm(row.get("article")) or "변경 조문"
        label = (f"{subject}({article})" if subject and " · " not in article
                 else article)
        kind = row.get("type") or category(before, after)
        old_nums = NUMERIC.findall(before)
        new_nums = NUMERIC.findall(after)
        if kind == "내용 개정" and len(old_nums) == len(new_nums) == 1 and old_nums != new_nums:
            phrases.append(f"{label} 기준 {old_nums[0].strip()} → {new_nums[0].strip()}")
        elif kind == "조문 신설":
            phrases.append(f"{label} 규정 신설")
        elif kind == "조문 삭제":
            phrases.append(f"{label} 규정 삭제")
        elif kind == "표기 정비":
            phrases.append(f"{label} 표기 정비")
        else:
            phrases.append(f"{label} 규정 내용 개정")
    extra = max(0, int(count or 0) - len(comparisons[:3]))
    return " · ".join(phrases) + (f" · 그 밖의 {extra}개 조문 변경" if extra else "")
