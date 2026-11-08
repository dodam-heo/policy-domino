import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
from v3 import dependencies as d

def policy(source="admrul"):
    return {"id":"p1","title":"가상시설 기준고시","ministry":"가상부",
            "source":source,"stable_id":"999", "url":"https://www.law.go.kr/test",
            "promulgated_at":"2026-11-08","priority":100,"impact_category":"제도·업무 변경",
            "effects":[{"article":"제1조","old":"100원","new":"120원","context":"가상시설 지원기준액 120원"}],
            "reference_candidates":[{"source":"admrul","serial":"12","title":"가상시청 지원규칙",
                                     "ministry":"가상시청","url":"https://www.law.go.kr/rule"}]}

class DependencyTests(unittest.TestCase):
    def test_explicit_provision_reference(self):
        p=policy();c=p["reference_candidates"][0]
        x=d.evidence(p,c,"가상시청은 「가상시설 기준고시」의 요율을 준용하여 지원액을 산정한다.")
        self.assertIsNotNone(x)
        self.assertEqual(x["relation_level"],"명시적 인용·적용 확인")
        self.assertFalse(x["cause_verified"])

    def test_naked_name_not_causal(self):
        p=policy();c=p["reference_candidates"][0]
        self.assertIsNone(d.evidence(p,c,"「가상시설 기준고시」는 우리나라에서 제정된 문서이다."))

    def test_no_source_text_no_claim(self):
        self.assertIsNone(d.evidence(policy(),{}, "",official_link=True))

    def test_linked_law_ordinance_results_parse(self):
        xml=ET.fromstring("""<root><item><자치법규명>가상시 조례</자치법규명>
          <자치법규일련번호>500</자치법규일련번호><자치법규ID>600</자치법규ID>
          <지자체기관명>가상시</지자체기관명></item></root>""")
        p=policy("law")
        with patch.object(d,"request",return_value=xml) as call:
            rows=d.linked_ordinances(p)
        self.assertEqual(rows[0]["ministry"],"가상시")
        self.assertEqual(rows[0]["serial"],"500")
        self.assertEqual(call.call_args.kwargs["knd"],"999")

    def test_ordinance_detail_uses_mst_not_id(self):
        xml=ET.fromstring("""<root><지자체기관명>가상시</지자체기관명>
          <담당부서명>복지과</담당부서명>
          <조내용>가상시설 기준고시를 준용한다</조내용></root>""")
        with patch.object(d,"request",return_value=xml) as call:
            text,agency,dept=d.local_clauses({"serial":"500","stable_id":"600"})
        self.assertEqual(call.call_args.kwargs["MST"],"500")
        self.assertEqual((agency,dept),("가상시","복지과"))
        self.assertIn("준용",text)

    def test_source_verification_precedes_agency_report(self):
        p=policy();c=p["reference_candidates"][0]
        with patch.object(d,"search_users",return_value=[c]),patch.object(
                d,"generic_clauses",return_value=(
                 "가상시청은 「가상시설 기준고시」를 적용한다.","가상시청","지원과")):
            cache,stats=d.discover([p],maximum=2)
        self.assertEqual(stats["checked"],1)
        self.assertEqual(stats["verified_dependents"],1)
        n=d.add_dependency_agencies([p])
        self.assertEqual(n,1)
        self.assertFalse(p.get("dependency_actions",[]))
        self.assertEqual(p["dependency_review_candidates"][0]["ministry"],"가상시청")

    def test_official_link_is_relation_not_system_status(self):
        p=policy("law")
        x=d.evidence(p,{"title":"가상시 조례","ministry":"가상시"},
                     "「가상시설 기준고시」를 준용한다",official_link=True)
        self.assertTrue(x["verified_reference"])
        self.assertEqual(x["real_system_status"],"미확인")

if __name__=="__main__":
    unittest.main()
