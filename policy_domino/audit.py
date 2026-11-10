"""Static audit: exactly one automated production pipeline and one Pages deploy.

Runs in CI before publication. Historical scripts may be stored on an
archive branch; they cannot be executable workflows in main.
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = "policy-domino.yml"


def audit() -> list[str]:
    errors = []
    workflows = list((ROOT / ".github" / "workflows").glob("*.yml"))
    deployers = [p.name for p in workflows
                 if "actions/deploy-pages@" in p.read_text("utf-8")]
    if deployers != [EXPECTED]:
        errors.append(f"Expected one Pages deploy workflow ({EXPECTED}); found {deployers}")
    scheduled = [p.name for p in workflows
                 if "\n  schedule:" in p.read_text("utf-8")]
    if scheduled != [EXPECTED]:
        errors.append(f"Expected one scheduled production pipeline; found {scheduled}")
    for retired in ("v2", "v3", "v4", "next"):
        if (ROOT / retired).exists():
            errors.append(f"Retired version directory still in production root: {retired}")
    for stale in ("watch.py", "impact_scanner.py", "law_changes.py"):
        if (ROOT / stale).exists():
            errors.append(f"Obsolete root watcher not archived: {stale}")
    for forbidden in (
        "policy_domino/engine/classic_bridge.py",
        "policy_domino/engine/legacy_recheck.py",
        "site/classic/legacy_source.json",
        "data/v2_state.json",
    ):
        if (ROOT / forbidden).exists():
            errors.append(f"Retired source artifact still present: {forbidden}")
    for module in (ROOT / "policy_domino" / "engine").glob("*.py"):
        if module.name.startswith("test_"):
            continue
        src = module.read_text("utf-8")
        if any(x in src for x in ("from v2 import", "from v3 import", "from v4", "import v4")):
            errors.append(f"Production has legacy runtime import: {module.name}")
    return errors


def main() -> None:
    failures = audit()
    if failures:
        raise SystemExit("\n".join(failures))
    print("PIPELINE_AUDIT_PASS: one scheduled data writer and one Pages publisher")


if __name__ == "__main__":
    main()
