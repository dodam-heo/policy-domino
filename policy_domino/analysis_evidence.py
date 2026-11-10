"""Pure evidence identity shared by the source-backed agency view and AI cache.

An AI finding is reusable only while its exact verified policy-action evidence
is unchanged. Generated-at timestamps are intentionally excluded.
"""
from __future__ import annotations

import hashlib
import json


def has_verified_action(action: dict) -> bool:
    return (
        action.get("evidence_scope") == "v4_verified_source"
        and all(action.get(key) for key in ("id", "event_id", "agency", "article",
                                            "law_title", "work", "changes"))
        and str(action.get("basis", "")).startswith(
            ("https://www.law.go.kr/", "https://law.go.kr/")
        )
        and isinstance(action["changes"], list)
        and any(isinstance(change, dict) and
                (str(change.get("before", "")).strip() or
                 str(change.get("after", "")).strip())
                for change in action["changes"])
    )


def evidence_identity(event: dict, action: dict) -> str:
    """Stable fingerprint of the actual policy + legal action, not collection time."""
    if event.get("event_id") != action.get("event_id") or not has_verified_action(action):
        raise ValueError("Only a current, source-verified policy action can be fingerprinted")
    facts = {
        "policy": {key: event.get(key, "") for key in (
            "event_id", "title", "promulgated_at", "effective_date",
            "revision", "amendment_reason")},
        "action": {key: action.get(key, "") for key in (
            "id", "agency", "agency_role", "law_title", "article",
            "work", "target_location", "basis", "impact_link_basis")},
        "changes": [
            {"before": str(c.get("before", "")), "after": str(c.get("after", ""))}
            for c in action["changes"] if isinstance(c, dict)
        ],
    }
    payload = json.dumps(facts, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
