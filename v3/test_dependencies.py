import unittest
from unittest.mock import patch
from v3 import dependencies as d

def policy():
    return {"id":"p1","title":"가상시설 기준고시","ministry":"가상부",
            "url":"https://www.law.go.kr/test","promulgated_at":"2026-11-08",
            "priority":100,
            "effects":[{"article":"제1조","old":"100원","new":"120원","context":"가상시설 지원기준액 120원"}],
            "reference_candidates":[{"source":"admrul","serial":"12","title":"가상시청 지원규칙",
                                     "ministry":"가상시청","url":"https://www.law.go.kr/rule"}]}

class DependencyTests(unittest.TestCase):
    def test_explicit_provision_reference(self):
        p=policy(); c=p["reference_candidates"][0]
        actual="제3조(적용) 가상시청은 「가상시설 기준고시」의 요율을 준용하여 지원액을 산정한다."
        finding=d.evidence(p,c,actual)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["relation_level"],"직접 인용·적용 문구 확인")
        self.assertFalse(finding["cause_verified"])
    def test_no_dependency_without_official_reference(self):
        p=policy(); c=p["reference_candidates"][0]
        self.assertIsNone(d.evidence(p,c,"가상시설에 관한 설명만 포함한 자료이다."))
    def test_naked_name_not_causal(self):
        p=policy(); c=p["reference_candidates"][0]
        self.assertIsNone(d.evidence(p,c,"제3조 「가상시설 기준고시」의 이름을 소개한다."))
    def test_remote_content_checked_before_institution_result(self):
        p=policy();c=p["reference_candidates"][0]
        with patch.object(d,"read_clauses",return_value={"제2조":"가상시청은 「가상시설 기준고시」를 적용한다."}):
            cache,stats=d.discover([p],maximum=2)
        self.assertEqual(stats["checked"],1)
        self.assertEqual(stats["verified_dependents"],1)
        d.add_dependency_agencies([p])
        self.assertEqual(p["dependency_actions"][0]["agency"],"가상시청")
        self.assertFalse(p["dependency_actions"][0]["actual_system_verified"])

if __name__=="__main__":
    unittest.main()
