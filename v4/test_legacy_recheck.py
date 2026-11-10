"""Legacy source is separately labelled and never upgraded on weak evidence."""
import unittest
from v4.legacy_recheck import legacy_action_ok, legacy_fallback


class LegacyRecheckTests(unittest.TestCase):
    def setUp(self):
        self.event = {
            "event_id": "legacy-source-id",
            "title": "가상 연도별 지원 기준",
            "law_type": "고시·행정규칙",
            "article_differences": [{
                "article": "제2조",
                "directive": "제2조의 \"100만원\"을 \"200만원\"으로 한다.",
                "source_url": "https://www.law.go.kr/가상",
            }],
        }
        self.action = {
            "id": "action",
            "event_id": self.event["event_id"],
            "agency": "가상공공기관",
            "service": "지원금 산정",
            "article": "제2조",
            "changes": [{"before": "100만원", "after": "200만원"}],
            "basis": "https://www.law.go.kr/가상",
        }

    def test_matching_official_literal_is_required(self):
        self.assertTrue(legacy_action_ok(self.action, self.event))
        wrong = {**self.action,
                 "changes": [{"before": "600만원", "after": "900만원"}]}
        self.assertFalse(legacy_action_ok(wrong, self.event))

    def test_missing_or_external_source_cannot_upgrade(self):
        invalid = {**self.event, "article_differences": [{
            **self.event["article_differences"][0],
            "source_url": "https://other.example/가상",
        }]}
        events, actions = legacy_fallback(
            {"events": [invalid], "actions": [self.action]}, set())
        self.assertEqual((events, actions), ([], []))

    def test_legacy_actions_always_retain_provisional_state(self):
        events, actions = legacy_fallback(
            {"events": [self.event], "actions": [self.action]}, set())
        self.assertEqual(len(events), 1)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["status"], "최신 근거 재확인 필요")
        self.assertEqual(events[0]["presentation_source"],
                         "legacy_official_directive_awaiting_recheck")
        self.assertIn("반영", actions[0]["required_change"])
        self.assertNotIn("조치 완료", actions[0]["status"])


if __name__ == "__main__":
    unittest.main()
