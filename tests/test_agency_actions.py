"""Focused regressions for translating official changed clauses into agency review cards."""
import unittest
from policy_domino.engine.agency_actions import (
    owner, source_url, textual_edits, choose_excerpts, new_action, group_event,
    unique_actions,
)


class AgencyActionTests(unittest.TestCase):
    def setUp(self):
        self.doc = {
            "title": "가상청 직제",
            "verification": "verified_changed_clauses",
            "kind": "대통령령",
            "changed_articles": ["제2조"],
            "excerpts": [{
                "article": "제2조",
                "before": "제2조(정원) 가상청 공무원 정원 총계는 192명이다.",
                "after": "제2조(정원) 가상청 공무원 정원 총계는 197명이다.",
            }],
            "url": "https://www.law.go.kr/가상청",
        }

    def test_organization_title_is_an_explicit_actor_not_ministry_keyword(self):
        self.assertEqual(owner("가상청 직제"), "가상청")
        self.assertEqual(owner("가상청 직제 시행규칙"), "가상청")
        self.assertEqual(owner("가상청 업무 소개"), "")

    def test_unsupported_url_is_not_published_as_official(self):
        self.assertEqual(source_url("javascript:alert(1)"),
                         "https://www.law.go.kr")
        self.assertEqual(source_url("https://untrusted.example/item"),
                         "https://www.law.go.kr")

    def test_pair_extract_requires_field_context(self):
        self.assertEqual(textual_edits("무작위 192", "무작위 197"), [])
        edits = textual_edits("정원 총계 192명", "정원 총계 197명")
        self.assertTrue(edits)
        self.assertEqual(edits[0]["before"], "192")

    def test_no_action_without_verified_agency_identity(self):
        doc = {**self.doc, "title": "일반 개정 법령"}
        self.assertIsNone(new_action(doc, self.doc["excerpts"][0], "v4:1"))

    def test_one_verified_organization_produces_one_review_card(self):
        e, actions = group_event({
            "id": "case", "date": "2026-11-09", "number": "123",
            "source_docs": [self.doc], "source_count": 1,
            "agency_count": 1, "dependencies": []
        })
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["agency"], "가상청")
        self.assertEqual(actions[0]["status"], "반영 확인 필요")
        self.assertEqual(actions[0]["evidence_scope"], "v4_verified_source")
        self.assertIn("정원", actions[0]["work"])
        self.assertEqual(e["presentation_source"], "v4_official_source")

    def test_duplicate_article_work_is_combined(self):
        action = new_action(self.doc, self.doc["excerpts"][0], "v4:1")
        self.assertEqual(len(unique_actions([action, dict(action)])), 1)

    def test_heading_only_excerpt_not_promoted(self):
        self.assertEqual(choose_excerpts({"excerpts":[
            {"article":"제5조", "before":"", "after":"제5조(제목)"}
        ]}), [])


if __name__ == "__main__":
    unittest.main()
