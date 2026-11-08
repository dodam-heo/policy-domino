import unittest
from v3 import agency_resolver as a

class OfficialActorTests(unittest.TestCase):
    def policy(self):
        return {"effects":[{"article":"제3조","old":"제출서류 1부","new":"제출서류 2부",
            "operations":["신청·접수 처리"]}],"institution_actions":[]}

    def test_identify_agency_from_full_unchanged_implementation_clause(self):
        e=self.policy()
        clauses={"제2조":"가상지원공단은 지원신청서를 접수하고 심사하여야 한다.",
                 "제3조":"제출서류는 2부로 한다."}
        out=a.assign(e,clauses)
        self.assertTrue(out)
        self.assertEqual(out[0]["agency"],"가상지원공단")
        self.assertEqual(out[0]["basis_article"],"제2조")
        self.assertIn("2부",out[0]["what_to_change"])
        self.assertFalse(out[0]["actual_system_verified"])

    def test_no_unrelated_organization_without_matching_operation(self):
        e=self.policy()
        out=a.assign(e,{"제1조":"가상교육청은 조직의 정원 배치를 담당한다."})
        self.assertEqual(out,[])

    def test_do_not_repeat_direct_clause_agency(self):
        e=self.policy()
        e["institution_actions"]=[{"agency":"가상지원공단","work":"신청·접수 처리"}]
        out=a.assign(e,{"제2조":"가상지원공단은 지원신청서를 접수한다."})
        self.assertEqual(out,[])

    def test_no_claim_without_change_evidence(self):
        e=self.policy();e["effects"]=[]
        self.assertEqual(a.assign(e,{"제2조":"가상지원공단은 지원신청서를 접수한다."}),[])
if __name__=="__main__":
    unittest.main()
