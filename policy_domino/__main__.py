"""One supported production entry point.

    python -m policy_domino --source official  # scheduled official crawl
    python -m policy_domino --source stored    # deterministic republish

Both modes rebuild the same policy-to-agency view and run local contracts.
"""
from __future__ import annotations

import argparse
import json
from typing import Literal


def run(source: Literal["official", "stored"] = "official") -> dict:
    if source == "official":
        from policy_domino.engine.pipeline import run as refresh_evidence
    elif source == "stored":
        from policy_domino.engine.stage_refresh import run as refresh_evidence
    else:
        raise ValueError(f"Unsupported evidence source: {source}")

    from policy_domino.engine.publication import run as publish_agency_impact

    evidence = refresh_evidence()
    if evidence.get("schema") != "policy-domino-v4":
        raise ValueError("Official evidence contract mismatch")
    if source == "official":
        # The public-service directory is an independent, source-backed
        # catalogue. It does not replace the official legal collector.
        from policy_domino.public_services import refresh_from_env
        refresh_from_env()
    published = publish_agency_impact()
    if published.get("schema") != "policy-domino-next-v1":
        raise ValueError("Public agency-impact contract mismatch")
    if not published.get("events"):
        raise ValueError("Refusing to deploy an empty policy feed")
    return {
        "source": source,
        "evidence_schema": evidence["schema"],
        "view_schema": published["schema"],
        "events": len(published["events"]),
        "agency_review_items": len(published.get("actions", [])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Policy Domino production pipeline")
    parser.add_argument("--source", choices=("official", "stored"),
                        default="official",
                        help="official: live API crawl; stored: rebuild from persisted evidence")
    args = parser.parse_args()
    print("POLICY_DOMINO_PIPELINE", json.dumps(run(args.source), ensure_ascii=False))


if __name__ == "__main__":
    main()
