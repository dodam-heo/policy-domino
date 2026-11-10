"""Regression for one official-source preview after dropping implementation tracking."""
import copy
import unittest
from unittest.mock import patch

from policy_domino.engine import stage_refresh


class SourcePreviewAuditTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "catalog": {"one": {"title": "Sample official source"}},
            "inspected": {"source:1": {"verification": "verified_changed_clauses"}},
        }
        self.data = {
            "featured_events": [{
                "summary": "공식 조문 변경",
                "source_count": 1,
                "dependencies": [{
                    "type": "cited_changed_provision",
                    "affected_verified": True,
                    "source_event": "source:1",
                    "source_article": "제2조",
                    "target_document": "agency:1",
                    "target_article": "제5조",
                }],
            }],
            "other_events": [],
            "collection": {
                "whole_corpus_complete": False,
                "official_catalogue": 1,
                "fresh_official_index": 1,
                "detailed_checked": 1,
                "pending_details": 0,
            },
            "links": {
                "confirmed_provision_or_formula_use": 1,
                "official_delegation_review_candidates": 0,
            },
        }

    def test_refresh_accepts_verified_source_without_implementation_tracking(self):
        with patch.object(stage_refresh.pipeline, "load_json", return_value=self.state), \
             patch.object(stage_refresh.pipeline, "build", return_value=self.data), \
             patch.object(stage_refresh.pipeline, "save_json") as save:
            returned = stage_refresh.run()
        self.assertIs(returned, self.data)
        save.assert_called_once()
        self.assertNotIn("implementation_verified",
                         returned["featured_events"][0]["dependencies"][0])

    def test_legacy_implementation_status_does_not_reenter_public_data(self):
        invalid = copy.deepcopy(self.data)
        invalid["featured_events"][0]["dependencies"][0]["implementation_verified"] = False
        with patch.object(stage_refresh.pipeline, "load_json", return_value=self.state), \
             patch.object(stage_refresh.pipeline, "build", return_value=invalid), \
             patch.object(stage_refresh.pipeline, "save_json") as save:
            with self.assertRaisesRegex(AssertionError, "retired implementation-status"):
                stage_refresh.run()
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
