"""Submission contract: issuer provenance, one publisher, coverage retries."""
import datetime as dt
import unittest
from unittest.mock import patch

from policy_domino.engine import pipeline, publication
from policy_domino.public_services import SCHEMA


class PublicationContract(unittest.TestCase):
    @staticmethod
    def doc(title, ministry):
        return {
            "title": title, "ministry": ministry, "kind": "대통령령",
            "revision": "일부개정", "effective": "2026-12-01",
            "url": "https://www.law.go.kr/법령/가상",
            "verification": "verified_changed_clauses",
            "changed_articles": ["제2조"],
            "excerpts": [{
                "article": "제2조",
                "before": "제2조(정원) 공무원 정원 총계는 192명이다.",
                "after": "제2조(정원) 공무원 정원 총계는 197명이다.",
                "kind": "개정",
                "source_url": "https://www.law.go.kr/법령/가상",
            }]
        }

    def test_change_issuer_is_not_replaced_by_the_affected_agency(self):
        group = {
            "id": "g1", "date": "2026-11-10", "number": "11",
            "effective_at": "2026-12-01",
            "source_docs": [self.doc("가상청 직제", "가상정책부"),
                            self.doc("가상위원회 직제", "가상행정부")],
            "source_count": 2, "agency_count": 2,
            "dependencies": [], "official_common_promulgation": True,
        }
        source = {
            "schema": "policy-domino-v4", "generated_at": "2026-11-10",
            "featured_events": [group], "other_events": [],
            "collection": {"detailed_checked": 2},
        }
        result = publication.build(source, service_catalog={
            "schema": SCHEMA, "services": {},
        })
        self.assertEqual(len(result["events"]), 1)
        event = result["events"][0]
        self.assertEqual(event["issuing_authorities"],
                         ["가상정책부", "가상행정부"])
        self.assertNotIn("직접 변경 대상 기관", event["ministry"])
        self.assertEqual(len(event["source_documents"]), 2)
        self.assertTrue(event["change_summary"])
        self.assertEqual(event["presentation_source"], "v4_official_source")
        self.assertTrue(result["actions"])
        self.assertTrue(all(a["evidence_scope"] == "v4_verified_source"
                            for a in result["actions"]))

    def test_collector_includes_today_and_retries_failed_official_window(self):
        date = dt.date(2026, 11, 10)
        state = {"catalog": {}, "coverage": [{
            "source": "admrul", "first": "2026-08-01", "last": "2026-08-07",
            "complete": False,
        }], "backfill_cursor_days": 14}
        requested_changes = []
        queried = []
        def changes(state_arg, days, max_pages):
            requested_changes.extend(days)
            state_arg["_source_pages_confirmed"]=1
            state_arg["coverage"].append({
                "source":"law_history","first":days[0],"last":days[0],
                "complete":True,"edition":"history",
            })
        def index(state_arg, source, windows, max_pages):
            queried.append((source, list(windows)))
        with patch.dict("os.environ", {"LAW_OC":"test-only"}, clear=False), patch.object(
            pipeline.collect_index, "ingest_changes", changes
        ), patch.object(pipeline.collect_index, "ingest_index", index):
            pipeline.scan_new(state, date)
        self.assertEqual(len(requested_changes), 8)
        self.assertEqual(requested_changes[0], "2026-11-10")
        self.assertIn(("admrul", [("2026-08-01", "2026-08-07")]), queried)
        self.assertEqual(state["backfill_cursor_days"], 182)
        self.assertEqual(state["coverage_plan"], "official_rolling_all_sources_v2")
        self.assertEqual(state["latest_official_scan"], "2026-11-10")
        self.assertEqual(len(state.get("catalog",{})),0)

    def test_missing_secret_uses_configured_official_identifier(self):
        from policy_domino import official_api as api
        with patch.dict("os.environ", {"LAW_OC":"","LAW_0C":""}):
            self.assertEqual(api.official_oc(),"dori")

    def test_recent_all_source_types_are_scanned_and_failed_history_retried(self):
        date=dt.date(2026,11,10)
        state={"catalog":{"prior":{"title":"persisted source"}},
               "coverage":[{"source":"law_history","first":"2026-10-03",
                            "last":"2026-10-03","edition":"history","complete":False}]}
        queried=[]
        def changes(data,days,max_pages):
            queried.append(("law_history",tuple(days)))
            data["_source_pages_confirmed"]=data.get("_source_pages_confirmed",0)+1
        def index(data,source,windows,max_pages):
            queried.append((source,tuple(windows)))
        checkpoints=[]
        with patch.dict("os.environ", {"PD_BACKFILL_WINDOWS_PER_RUN":"1",
                    "PD_HISTORY_DAYS":"365","LAW_OC":""}), patch.object(
               pipeline.collect_index,"ingest_changes",changes), patch.object(
               pipeline.collect_index,"ingest_index",index):
            pipeline.scan_new(state,date,checkpoint=lambda data:checkpoints.append(len(queried)))
        for source in ("law","admrul","ordin"):
            self.assertIn((source,(("2026-11-03","2026-11-10"),)),queried)
        self.assertIn(("law_history",("2026-10-03",)),queried)
        self.assertEqual(len(state["catalog"]),1)
        self.assertGreaterEqual(len(checkpoints),5)


if __name__ == "__main__":
    unittest.main()
