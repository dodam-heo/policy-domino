import unittest
from v3 import impact

def event(title, before, after, agency="가상부처", category="법령", parent=None):
    item={"id":title,"title":title,"ministry":agency,"kind":category,
          "promulgated_at":"2026-11-08","comparison_status":"신구 본문 비교 완료",
          "number":"제101호","url":"https://www.law.go.kr/test",
          "changes":[{"article":"제3조","type":"개정","before":before,
                      "after":after,"source_url":"https://www.law.go.kr/test"}],
          "upstream_changes":[]}
    if parent:item["upstream_changes"]=[{"event_id":parent}]
    return item

class ImpactTests(unittest.TestCase):
    def test_unregistered_policy_monetary_impact(self):
        e=event("기술지원 평가규정",
                "시장·군수·구청장은 지원금 상한액 100만원을 적용한다.",
                "시장·군수·구청장은 지원금 상한액 150만원을 적용한다.")
        found=impact.identify(e)
        self.assertTrue(found["effects"])
        self.assertTrue(found["actions"])
        self.assertEqual(found["actions"][0]["agency"],"시장·군수·구청장")
        self.assertTrue(any("금액·산식" in a["work"] for a in found["actions"]))
        self.assertTrue(any("100" in a["what_to_change"] and "150" in a["what_to_change"] for a in found["actions"]))
    def test_any_application_or_deadline_change(self):
        e=event("환경배출시설 신청규칙",
                "교육감은 신청서를 30일 이내 심사한다.",
                "교육감은 신청서를 15일 이내 심사한다.")
        found=impact.identify(e)
        self.assertTrue(found["actions"])
        self.assertTrue(any(x["work"]=="처리기한·시행" for x in found["actions"]))
    def test_not_every_citation_is_causal_policy_domino(self):
        a=event("가상 기준법","100원","150원")
        b=event("가상 시행규칙","「가상 기준법」을 따른다.","「가상 기준법」을 따른다.")
        b["upstream_changes"]=[{"event_id":a["id"]}]
        self.assertFalse(impact.strong_cause(a,b))
        self.assertEqual(len(impact.group_events([a,b])),2)
    def test_proven_causation_from_amendment_reason_can_group(self):
        a=event("가상 기준법","100원","150원")
        b=event("가상 시행규칙","기준 A","기준 B",parent=a["id"])
        b["amendment_reason"]="가상 기준법 제101호가 개정됨에 따라 이 규정을 정비함"
        self.assertTrue(impact.strong_cause(a,b))
        group=impact.group_events([a,b])
        self.assertEqual(len(group),1)
        self.assertEqual(len(group[0]["linked"]),1)
    def test_org_is_not_mistaken_for_primary_public_benefit(self):
        x=event("가상청 직제 시행규칙","가상청 정원 15명","가상청 정원 20명")
        y=event("가상사업 운영규칙","지원금 상한액 100만원","지원금 상한액 150만원")
        self.assertLess(impact.identify(x)["priority"],impact.identify(y)["priority"])
        self.assertEqual(impact.identify(x)["category"],"조직·인사")
    def test_uncompared_record_has_no_invented_action(self):
        x=event("가상 정책","10원","20원")
        x["comparison_status"]="이전 연혁 본문 미확보"
        self.assertFalse(impact.identify(x)["actions"])
    def test_ministry_not_misrepresented_as_verified_operating_agency(self):
        x=event("가상 지원규칙","지원금 상한액 100만원","지원금 상한액 150만원")
        identified=impact.identify(x)
        self.assertEqual(identified["actions"],[])
        self.assertTrue(identified["candidate_agencies"])
        self.assertEqual(identified["candidate_agencies"][0]["status"],"집행기관 추가 조사 필요")
    def test_normalized_cause_only_not_general_keywords(self):
        parent=event("가상 소득기준 고시","100원","120원")
        child=event("가상 주거지원 시행규칙","100원","120원",parent=parent["id"])
        child["amendment_reason"]="「가상 소득기준 고시」를 참고하여 제도를 소개한다"
        self.assertFalse(impact.strong_cause(parent,child))
    def test_output_is_policy_evidence_not_prebaked_sector(self):
        x=event("항공시설 관리규칙","교육감은 검사 기한 20일을 적용한다.","교육감은 검사 기한 10일을 적용한다.")
        data=impact.analyze({"generated_at":"2026-11-08","events":[x],"health":{}})
        self.assertEqual(data["schema"],"policy-domino-impact-v3")
        self.assertGreater(data["impact_health"]["direct_actor_actions"],0)
        self.assertEqual(data["impact_health"]["verified_documents"],1)

if __name__=="__main__":
    unittest.main()
