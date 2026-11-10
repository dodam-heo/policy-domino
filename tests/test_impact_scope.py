"""Regression tests for the documented breadth filter (not social significance)."""
import unittest
from policy_domino.engine.impact_scope import assess_impact_scope


class ImpactScopeTests(unittest.TestCase):
    def setUp(self):
        self.event = {
            "event_id": "case:1",
            "presentation_source": "v4_official_source",
            "downstream_changes": [],
        }

    @staticmethod
    def action(agency, scope="v4_verified_source", event_id="case:1"):
        return {"event_id": event_id, "agency": agency, "evidence_scope": scope}

    @staticmethod
    def link(title, article, evidence="공식 근거"):
        return {"title": title, "article": article, "evidence": evidence,
                "status": "변경 조항 적용 관계 확인"}

    def test_two_verified_institutions_qualify(self):
        scope = assess_impact_scope(self.event, [self.action("가상공사 A"),
                                                 self.action("가상공사 B")])
        self.assertEqual(scope["impact_level"], "high")
        self.assertEqual(scope["impact_scope"]["institutions"], 2)
        self.assertFalse(scope["impact_scope"]["provisional"])

    def test_repeated_actions_for_one_agency_do_not_inflate_scope(self):
        scope = assess_impact_scope(self.event, [self.action("가상공사 A")] * 3)
        self.assertEqual(scope["impact_level"], "not_assessed")
        self.assertEqual(scope["impact_scope"]["institutions"], 1)

    def test_unverified_or_unrelated_actions_cannot_qualify(self):
        actions = [
            self.action("가상공사 A"),
            self.action("가상공사 B", "unverified_candidate"),
            self.action("가상공사 C", event_id="other-case"),
        ]
        self.assertEqual(assess_impact_scope(self.event, actions)["impact_level"],
                         "not_assessed")

    def test_two_distinct_confirmed_dependent_provisions_qualify(self):
        event = {**self.event, "downstream_changes": [
            self.link("가상 시행규정", "제3조"),
            self.link("가상 시행규정", "제4조"),
        ]}
        scope = assess_impact_scope(event, [])
        self.assertEqual(scope["impact_level"], "high")
        self.assertEqual(scope["impact_scope"]["proven_dependent_rules"], 2)

    def test_duplicate_or_unproven_links_do_not_qualify(self):
        one = self.link("가상 시행규정", "제3조")
        event = {**self.event, "downstream_changes": [
            one, one.copy(), self.link("다른 규정", "제2조", evidence="")
        ]}
        scope = assess_impact_scope(event, [])
        self.assertEqual(scope["impact_level"], "not_assessed")
        self.assertEqual(scope["impact_scope"]["proven_dependent_rules"], 1)

    def test_unverified_candidate_is_not_an_affected_institution(self):
        scope=assess_impact_scope(self.event,[self.action("가상공사 A"),
             self.action("가상공사 B","unverified_candidate")])
        self.assertEqual(scope["impact_level"],"not_assessed")
        self.assertFalse(scope["impact_scope"]["provisional"])


if __name__ == "__main__":
    unittest.main()
