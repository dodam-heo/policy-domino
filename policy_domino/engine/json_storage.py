"""Atomic JSON output for official evidence and public Pages datasets.

Repository-tracked JSON is a transport format, not a place to duplicate or
truncate source records. Compact formatting leaves every field intact and
keeps high-volume public artifacts below GitHub's 100 MB per-file limit.
"""
from __future__ import annotations

import json
from pathlib import Path

PUBLIC_MAX_BYTES = 95_000_000


def atomic_json(path: Path, data: object, *, public: bool = False) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        data, ensure_ascii=False,
        separators=(",", ":") if public else None,
        indent=None if public else 2,
    ).encode("utf-8")
    if public and len(encoded) > PUBLIC_MAX_BYTES:
        raise ValueError(
            f"Public JSON {path.name} is {len(encoded):,} bytes; "
            f"exceeds the {PUBLIC_MAX_BYTES:,}-byte publication safety cap. "
            "Do not truncate official source or overwrite the saved file."
        )
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(encoded)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return len(encoded)
