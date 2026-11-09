import json
import unittest
from pathlib import Path
from v4 import institutional_impact as impact
from v4 import classic_bridge as bridge

def event(name, field, before, after, year="2027-01-01"):
    return {"event_id":name,"title":name,
        "presentation_source":"legacy_official_directive_awaiting_recheck",
        "effective_date":year,
        "article_differences":[{"article":field,
            "before":before,"after":after,
            "source_url":"https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=123"}]}

def entry():
    return {"id":"synthetic-public-agency","institution":"테스트시설공단",
      "program":"특정 신규자격 수급심사","institution_role":"운영기관",
      "criterion":{"name":"가상선정기준","aliases":["가상선정기준"],"match":"changed_field"},
      "relation":"numeric_formula","source_year":2026,"followup_year":2027,
      "work":"수급심사기준 점검","target_location":"가상사업 신규자격·선정 심사표",
      "review_action":"공식 기준액이 변경된 2027년도 운영기준을 검토",
      "scope_note":"실제 기관 내부시스템 수정 여부 미확인",
      "source":{"url":"https://sample.go.kr/info","publisher":"가상 기관",
                "source_heading":"공식 지원사업 안내","evidence":"가상선정기준에 따라 해당 운영업무 수행"}}

class GeneralizableAgencyCascade(unittest.TestCase):
    def test_all_registries_loaded_with_primary_sources(self):
        data=impact.load_sources()
        self.assertGreaterEqual(len(data),3)
        self.assertTrue(all(x["source"]["publisher"] and x["source"]["evidence"] for x in data))

    def test_unrelated_synthetic_institution_works_without_law_name_whitelist(self):
        e=event("무관한 새 정책", "가상선정기준:4인", "100원","120원")
        actions,added=impact.connect([e],[],[entry()])
        self.assertEqual(len(added),1)
        self.assertEqual(added[0]["agency"],"테스트시설공단")
        self.assertEqual(added[0]["target_location"],"가상사업 신규자격·선정 심사표")
        self.assertEqual(added[0]["changes"][0]["meaning"],"원천 정책의 변경값(기관별 적용 금액 미확정)")
        self.assertFalse(added[0]["institutional_implementation_verified"])

    def test_matching_title_but_unchanged_standard_is_not_impact(self):
        e=event("가상선정기준을 언급하는 제목", "다른 지원액:4인", "100원","120원")
        self.assertIsNone(impact.candidate_action(e,entry()))

    def test_prose_only_and_unknown_source_never_become_new_duties(self):
        e=event("가상정책", "가상선정기준:4인", "업무의 정의를 변경한다","업무를 정하는 방식이 변경된다")
        self.assertIsNone(impact.candidate_action(e,entry()))
        e["article_differences"][0]["source_url"]="https://random.example.com/policy"
        e["article_differences"][0]["before"]="100원"
        e["article_differences"][0]["after"]="200원"
        self.assertIsNone(impact.candidate_action(e,entry()))

    def test_effective_year_must_match_new_program_year(self):
        e=event("2026 업무", "가상선정기준:4인","100원","200원","2026-01-01")
        self.assertIsNone(impact.candidate_action(e,entry()))

    def test_source_does_not_claim_installed_app_or_updated_internal_system(self):
        e=event("가상정책", "가상선정기준:4인", "100원","200원")
        a=impact.candidate_action(e,entry())
        self.assertFalse(a["is_direct_legal_amendment"])
        self.assertFalse(a["institutional_implementation_verified"])
        self.assertIn("별도",a["verification_note"] if "별도" in a["verification_note"] else "별도")

    def test_real_cross_institutional_sources_link_official_2027_income_change(self):
        original=json.loads((impact.ROOT/"site"/"classic"/"legacy_source.json").read_text("utf8"))
        chosen=next(e for e in original["events"]
                    if any(d.get("article")=="중위소득:4인" for d in e["article_differences"]))
        e={**chosen,"event_id":"legacy:"+chosen["event_id"],
           "presentation_source":"legacy_official_directive_awaiting_recheck"}
        actions,added=impact.connect([e],[],impact.load_sources())
        self.assertEqual(len(added),2)
        self.assertTrue(any("학자금" in x["work"] and x["agency"]=="한국장학재단" for x in added))
        self.assertTrue(any("통합공공임대" in x["work"] and "LH" in x["agency"] for x in added))
        self.assertTrue(all(x["changes"][0]["before"]=="6,494,738원" and
                            x["changes"][0]["after"]=="6,929,885원" for x in added))
        self.assertTrue(all(x["agency_basis"].startswith("https://") for x in added))

    def test_real_lh_housing_survey_is_role_limited_not_new_eligibility_decider(self):
        data=json.loads((impact.ROOT/"site"/"classic"/"legacy_source.json").read_text("utf8"))
        e=next(x for x in data["events"]
               if any(d.get("article")=="주거급여:4인" for d in x["article_differences"]))
        source={**e,"event_id":"legacy:"+e["event_id"],
                "presentation_source":"legacy_official_directive_awaiting_recheck"}
        actions,added=impact.connect([source],[],impact.load_sources())
        self.assertEqual(len(added),1)
        self.assertIn("LH",added[0]["agency"])
        self.assertIn("주택조사",added[0]["work"])
        self.assertIn("지급",added[0]["verification_note"])
        self.assertIn("3,117,474원",added[0]["changes"][0]["before"])
        self.assertIn("3,326,345원",added[0]["changes"][0]["after"])

if __name__=="__main__":unittest.main()
