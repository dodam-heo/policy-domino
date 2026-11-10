"""Source-backed, presentation-only facts about amended provisions.

This module does not determine policy impact or infer agency duties. It turns
official before/after clauses into inspectable, bounded source excerpts.
"""
from __future__ import annotations

import difflib
import hashlib
import json
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


def _numeric_changes(before: str, after: str) -> list[tuple[str, str]]:
    """Align complete numeric tokens, never character fragments such as 2→7."""
    pattern = re.compile(r"(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:만원|원|명|일|개월|년|세|%)?")
    left = [x.strip() for x in pattern.findall(before)]
    right = [x.strip() for x in pattern.findall(after)]
    matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
    changes = []
    for mode, a, b, c, d in matcher.get_opcodes():
        if mode == "replace" and b - a == d - c == 1:
            if left[a] != right[c]:
                changes.append((left[a], right[c]))
    return changes


def _source_heading(row: dict) -> str:
    old, after = norm(row.get("before")), norm(row.get("after"))
    match = TITLE.search(after or old)
    article = norm(row.get("article")) or "변경 조항"
    if match:
        heading = norm(match.group(1))
        if heading and heading not in article:
            return heading + " (" + article + ")"
    return article


def concise_summary(comparisons: list[dict], count: int, *,
                    title: str = "", revision: str = "",
                    source_count: int = 1) -> str:
    """Deterministic Korean narrative for every event, without LLM availability.

    Express documented changes when full old/new official text exists.
    Otherwise state the *known issuance* and explicitly distinguish the still
    missing detail. Never turn a discovery row into a fabricated clause change.
    """
    title = norm(title)
    revision = norm(revision)
    multi = int(source_count or 1) > 1
    label = (f"{int(source_count)}개 법령" if multi else
             f"「{title}」" if title else "해당 정책")
    if not comparisons:
        if "폐지" in revision:
            return f"{label}의 폐지 사실이 공표됐습니다. 폐지에 따른 후속 업무 영향은 확인된 공식 근거를 바탕으로 구분합니다."
        if "제정" in revision or "신규" in revision:
            return f"{label}이 새로 제정됐습니다. 원문 확보 전에는 구체적인 요건이나 변경 금액을 추정하지 않습니다."
        return (f"{label}의 변경이 공식 목록에 등록됐습니다. "
                "변경 조문 원문이 아직 확인되지 않아 세부 사항은 비교하지 않았습니다.")

    changes = [x for x in comparisons if x.get("before") != x.get("after")]
    if not changes:
        return f"{label}에서 공식 변경 문구를 확인했습니다. 실질적인 변경 범위는 조문별 원문에서 확인할 수 있습니다."
    num = max(int(count or 0), len(changes))
    # Prefer a representative substantive change, not a punctuation edit
    # or the first arbitrary administrative-rule annex.
    ranked=sorted(changes,key=lambda row:(
        row.get("type")!="표기 정비",
        bool(_numeric_changes(norm(row.get("before")),norm(row.get("after")))),
        len(norm(row.get("before")))+len(norm(row.get("after"))),
    ),reverse=True)
    first = ranked[0]
    heading = _source_heading(first)
    kind = first.get("type") or category(str(first.get("before","")),str(first.get("after","")))
    old, new = norm(first.get("before")), norm(first.get("after"))
    numeric = _numeric_changes(old,new) if kind == "내용 개정" else []
    # Describe a uniquely aligned numeric standard without guessing what an
    # individual programme should implement or what a bare year refers to.
    values = [(a,b) for a,b in numeric if
              re.search(r"\d",a) and re.search(r"\d",b) and a != b]
    if len(values) == 1 and re.search(r"정원|총계|기준|금액|급여|기간|인원|수수료|지원|선정", old+" "+new):
        a,b=values[0]
        subject = "정원·인원" if re.search(r"정원|인원|총계",old+" "+new) else "해당 기준값"
        detail = f"{heading}에서 {subject}을 종전 {a}에서 {b}로 변경했습니다."
    elif kind == "조문 신설":
        detail = f"{heading}에 관한 규정을 새로 마련했습니다."
    elif kind == "조문 삭제":
        detail = f"{heading}에 관한 기존 규정을 삭제했습니다."
    elif kind == "표기 정비":
        detail = f"{heading}의 문구와 표기 방식을 정비했습니다."
    else:
        detail = f"{heading}에 관한 규정을 개정했습니다."
        # When there is no numeric formula to describe, preserve the exact
        # old/new wording rather than claiming an invented policy effect.
        # A concise side-by-side citation is more useful than 'content amended'.
        if old and new:
            # Only quote comparable context around the actual changed clause,
            # not the first 105 characters of identical legal boilerplate.
            opcodes=[(a,b,c,d) for tag,a,b,c,d in
                     difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes()
                     if tag!="equal"]
            if opcodes:
                a,b,c,d=max(opcodes,key=lambda op:(
                    bool(re.search(r"\\d",old[op[0]:op[1]]+new[op[2]:op[3]])),
                    min(30,(op[1]-op[0])+(op[3]-op[2]))))
                def excerpt(text: str, beginning: int, ending: int) -> str:
                    start=max(0,beginning-38)
                    stop=min(len(text),max(ending,beginning+1)+45)
                    return ("…" if start else "")+text[start:stop]+(
                        "…" if stop<len(text) else "")
                old_quote,new_quote=excerpt(old,a,b),excerpt(new,c,d)
                if old_quote != new_quote:
                    detail += f" 종전 ‘{old_quote}’에서 개정 후 ‘{new_quote}’로 문구가 바뀌었습니다."
    remaining = num - 1
    if remaining > 0:
        headings = []
        for row in changes[1:]:
            name = _source_heading(row)
            if name != heading and name not in headings:
                headings.append(name)
            if len(headings) == 2:
                break
        follow = " · ".join(headings)
        detail += (f" 함께 변경된 조문은 {remaining}개이며, "
                   + (f"{follow} 등의 변경이 포함됩니다." if follow else
                      "전체 신구 비교에서 확인할 수 있습니다."))
    prefix=(f"{label}의 {num}개 변경 조문 중 " if multi else
            f"{label}의 " if title else "")
    return prefix + detail


def fingerprint(event: dict) -> str:
    """Stable binding between a published policy change and its AI explanation."""
    pairs = [
        (row.get("article",""), row.get("before",""), row.get("after",""))
        for row in event.get("article_differences",[])
        if row.get("before","") != row.get("after","")
    ]
    if not pairs or event.get("source_verification") not in (
        "verified_changed_clauses","verified_other"):
        return ""
    payload = (event.get("event_id",""),event.get("title",""),
               event.get("promulgated_at",""),pairs)
    return hashlib.sha256(
        json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode("utf-8")
    ).hexdigest()[:24]
