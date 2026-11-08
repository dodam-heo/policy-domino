import unittest
from v3 import impact,evidence_gate

def doc(name,old,new,revision="일부개정",agency="가상 부처",article="제3조"):
    return {
      "id":name,"source":"admrul","stable_id":name,"serial":name+"-2",
      "title":name,"revision":revision,"kind":"행정규칙",
      "ministry":agency,"comparison_status":"신구 본문 비교 완료",
      "url":"https://www.law.go.kr/example",
      "changes":[{"article":article,"type":"개정","before":old,"after":new,
                  "source_url":"https://www.law.go.kr/example"}]}

class UniversalEvidenceGate(unittest.TestCase):
    def analyze(self,*documents):
        return impact.analyze({"events":list(documents),"health":{}})["events"]

    def test_repeal_does_not_create_duties_for_legacy_actors(self):
        e=doc("지역 전산장애 비상대응 규정",
              "장학위원회는 접수기준을 12일로 정한다. 노동부장관은 지급액 120만원을 적용한다.",
              "장학위원회는 접수기준을 13일로 정한다.","폐지")
        r=self.analyze(e)[0]
        self.assertEqual(r["impact_category"],"폐지·효력종료")
        self.assertFalse(r["institution_actions"])
        self.assertFalse(r["agency_candidates"])
        self.assertFalse(r["dependency_actions"])
        self.assertIn("폐지",r["impact_summary"])

    def test_repeal_only_based_on_official_metadata_not_quoted_phrase(self):
        e=doc("전산관리 운영규칙","신청서에는 구 지침 폐지를 명시한다.",
              "신청서에는 새 지침 폐지를 명시한다.")
        r=self.analyze(e)[0]
        self.assertNotEqual(r["impact_category"],"폐지·효력종료")

    def test_repeal_and_reenact_is_not_mistaken_for_plain_repeal(self):
        e=doc("전국 가상기준 운영규칙",
              "가상운영공단은 신청기한을 30일로 정한다.",
              "가상운영공단은 신청기한을 20일로 정한다.",
              revision="폐지제정")
        r=self.analyze(e)[0]
        self.assertNotEqual(r["impact_category"],"폐지·효력종료")
        self.assertGreater(len(r["institution_actions"]),0)

    def test_same_changed_sentence_explicit_actor_and_duty(self):
        e=doc("항공운항 신청 운영규칙",
              "가상항공공단은 신청서 처리기간을 30일로 정한다.",
              "가상항공공단은 신청서 처리기간을 20일로 정한다.")
        r=self.analyze(e)[0]
        self.assertGreater(len(r["institution_actions"]),0)
        self.assertEqual({a["agency"] for a in r["institution_actions"]},{"가상항공공단"})
        self.assertTrue(all(a["article"]=="제3조" for a in r["institution_actions"]))
        self.assertTrue(all(a["evidence_type"]=="변경된 동일 조문 내 업무주체·의무문 확인"
                            for a in r["institution_actions"]))

    def test_no_cross_article_actors_even_when_topics_overlap(self):
        e=doc("정보시스템 운영규정","심사기준을 32일로 한다.",
              "심사기준을 31일로 한다.")
        e["changes"].insert(0,{"article":"제1조","type":"개정",
             "before":"가상위원회는 심사를 담당한다.","after":"가상위원회는 심사를 담당한다."})
        r=self.analyze(e)[0]
        self.assertFalse(r["institution_actions"])

    def test_issuer_is_not_automatically_executing_actor(self):
        e=doc("건축기준 운영규칙","지원액 200만원을 적용한다.",
              "지원액 300만원을 적용한다.",agency="가상건설부")
        r=self.analyze(e)[0]
        self.assertFalse(r["institution_actions"])
        self.assertNotIn("가상건설부",[a["agency"] for a in r["institution_actions"]])

    def test_multiagency_omnibus_requires_separate_changed_duties(self):
        e=doc("전국 시설심사 업무조정령",
              "가상도시공단은 신고서를 30일 이내 처리한다.",
              "가상도시공단은 신고서를 15일 이내 처리한다.")
        e["changes"].append({"article":"제4조","type":"개정",
            "before":"가상안전재단은 검사신청서를 60일 이내 처리한다.",
            "after":"가상안전재단은 검사신청서를 40일 이내 처리한다."})
        r=self.analyze(e)[0]
        self.assertEqual({a["agency"] for a in r["institution_actions"]},
                         {"가상도시공단","가상안전재단"})

    def test_annual_standard_without_executing_actor_stays_discoverable(self):
        e=doc("2027년도 가상산업 지원기준",
              "지원대상 선정기준은 100만원","지원대상 선정기준은 150만원")
        r=self.analyze(e)[0]
        self.assertTrue(r["effects"])
        self.assertFalse(r["institution_actions"])
        self.assertEqual(r["impact_category"],"제도·업무 변경")

    def test_staffing_owner_is_extracted_from_arbitrary_law_title(self):
        e=doc("가상산림청과 그 소속기관 직제",
            "가상산림청 공무원 정원표 총계 41","가상산림청 공무원 정원표 총계 47")
        e["source"]="law"
        r=self.analyze(e)[0]
        self.assertEqual({a["agency"] for a in r["institution_actions"]},{"가상산림청"})
        self.assertTrue(any("41명 → 47명" in a["what_to_change"] for a in r["institution_actions"]))

if __name__=="__main__":unittest.main()
