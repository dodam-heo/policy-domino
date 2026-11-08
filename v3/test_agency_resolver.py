import unittest
from v3 import agency_resolver as a

class SourceScopedActorTests(unittest.TestCase):
    def policy(self):
        return {
           "id":"p","title":"기관별 지급신청 규칙","revision":"개정",
           "source":"admrul",
           "effects":[{"article":"제3조","old":"1부","new":"2부",
                       "operations":["신청·접수 처리"]}],
           "changes":[{"article":"제3조",
                       "before":"가상지원공단은 지원신청서를 1부 접수한다.",
                       "after":"가상지원공단은 지원신청서를 2부 접수한다."}],
           "institution_actions":[]}

    def test_same_changed_clause_may_identify_explicit_duty(self):
        e=self.policy()
        out=a.assign(e,{"제3조":e["changes"][0]["after"]})
        self.assertEqual({x["agency"] for x in out},{"가상지원공단"})

    def test_different_unchanged_article_is_not_a_new_duty(self):
        e=self.policy()
        e["changes"][0]["before"]="지원신청서 1부"
        e["changes"][0]["after"]="지원신청서 2부"
        out=a.assign(e,{"제2조":"가상지원공단은 지급신청서를 접수한다.",
                        "제3조":"지원신청서 2부"})
        self.assertEqual(out,[])

    def test_source_clause_must_match_exact_changed_clause(self):
        e=self.policy()
        self.assertEqual(a.assign(e,{"제3조":"대조되지 않은 다른 조문"}),[])

    def test_repealed_rule_has_no_operational_action(self):
        e=self.policy()
        e["revision"]="폐지"
        self.assertEqual(a.assign(e,{"제3조":e["changes"][0]["after"]}),[])

    def test_do_not_duplicate_evidenced_action(self):
        e=self.policy()
        e["institution_actions"]=[{"agency":"가상지원공단",
                                   "article":"제3조","work":"신청·접수 처리"}]
        self.assertEqual(a.assign(e,{"제3조":e["changes"][0]["after"]}),[])

if __name__=="__main__":unittest.main()
