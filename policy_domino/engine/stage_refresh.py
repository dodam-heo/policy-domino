"""Rebuild the preview only from persisted V4 official evidence.

No network, no V2-derived agency actions. Recompute every graph edge with
the CURRENT tested provision/subsection rules before preview publication.
"""
import datetime as dt,json
from pathlib import Path
from policy_domino.engine import pipeline,relationships

ROOT=Path(__file__).resolve().parents[2]

def run():
    state=pipeline.load_json(pipeline.STATE,{})
    if not state.get("inspected") or not state.get("catalog"):
        raise RuntimeError("No verified V4 official source records to publish")
    data=pipeline.build(state,dt.date.today())
    seen=set()
    for group in data["featured_events"]+data["other_events"]:
        for edge in group.get("dependencies",[]):
            assert edge["affected_verified"] is True
            assert edge["type"] in ("cited_changed_provision","formula_dependency")
            assert "implementation_verified" not in edge, "retired implementation-status field in impact evidence"
            if edge["type"]=="cited_changed_provision" and edge.get("source_paragraph"):
                src=state["inspected"][edge["source_event"]]
                actual=relationships.changed_paragraphs(src,edge["source_article"])
                assert actual is not None and edge["source_paragraph"] in actual
            pair=(edge["source_event"],edge["target_document"],
                  edge.get("source_article"),edge.get("target_article"))
            assert pair not in seen,"duplicate policy consequence"
            seen.add(pair)
    assert data["collection"]["whole_corpus_complete"] is False
    pipeline.save_json(pipeline.OUTPUT,data)
    print("V4_FRESH_PREVIEW_AUDIT",json.dumps({
        "source_index":data["collection"]["official_catalogue"],
        "fresh_index":data["collection"].get("fresh_official_index",0),
        "details_verified":data["collection"]["detailed_checked"],
        "pending":data["collection"]["pending_details"],
        "featured":len(data["featured_events"]),
        "impacts":data["links"]["confirmed_provision_or_formula_use"],
        "official_delegation_candidates":data["links"]["official_delegation_review_candidates"],
        "first_events":[{"title":g["summary"],"sources":g["source_count"],
                          "proven_links":len(g["dependencies"])}
                         for g in data["featured_events"][:8]]
    },ensure_ascii=False)[:7000])
    return data

if __name__=="__main__":run()
