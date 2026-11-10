"""Only one production build sequence may publish the agency view."""
import unittest
from unittest.mock import patch

from policy_domino.__main__ import run


class PipelineEntryTests(unittest.TestCase):
    def test_official_mode_follows_collection_then_agency_view(self):
        calls = []
        def source():
            calls.append("official")
            return {"schema": "policy-domino-v4"}
        def view():
            calls.append("view")
            return {"schema": "policy-domino-next-v1",
                    "events": [{"event_id":"example"}], "actions": []}
        with patch("policy_domino.engine.pipeline.run", source), patch("policy_domino.engine.classic_bridge.run", view):
            out = run("official")
        self.assertEqual(calls, ["official", "view"])
        self.assertEqual(out["events"], 1)

    def test_stored_mode_does_not_call_official_api(self):
        with patch("policy_domino.engine.stage_refresh.run",
                   return_value={"schema": "policy-domino-v4"}), patch(
                    "policy_domino.engine.classic_bridge.run",
                    return_value={"schema": "policy-domino-next-v1", "events":[{}]}):
            out = run("stored")
        self.assertEqual(out["source"], "stored")

    def test_contract_mismatch_blocks_publication(self):
        with patch("policy_domino.engine.stage_refresh.run", return_value={"schema": "broken"}), patch(
                "policy_domino.engine.classic_bridge.run") as publish:
            with self.assertRaises(ValueError):
                run("stored")
            publish.assert_not_called()

    def test_empty_feed_blocks_deploy(self):
        with patch("policy_domino.engine.stage_refresh.run",
                   return_value={"schema": "policy-domino-v4"}), patch(
                    "policy_domino.engine.classic_bridge.run",
                    return_value={"schema":"policy-domino-next-v1","events":[]}):
            with self.assertRaisesRegex(ValueError,"empty"):
                run("stored")

    def test_unknown_mode_refused(self):
        with self.assertRaises(ValueError):
            run("historical")


if __name__ == "__main__":
    unittest.main()
