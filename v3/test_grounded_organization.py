import unittest
from v3 import impact, agency_resolver, policy_graph

OLD=("■ 개인정보 보호위원회 직제 [별표 1] 개인정보 보호위원회 공무원 정원표"
     "(제12조제1항 관련) 총계 192 정무직 계 2 위원장(장관급) 1 "
     "부위원장(차관급) 1 일반직 계 189 고위공무원단 6 "
     "3급 또는 4급 이하 181 전문경력관 2")
NEW=OLD.replace("총계 192","총계 197").replace("일반직 계 189","일반직 계 194").replace("4급 이하 181","4급 이하 186")

def rule(title="개인정보 보호위원회 직제",old=OLD,new=NEW):
    return {"id":"org1","source":"law","stable_id":"stable1","serial":"v2",
            "title":title,"ministry":"개인정보보호위원회,행정안전부",
            "kind":"대통령령","revision":"타법개정",
            "promulgated_at":"2026-08-28","effective_date":"2026-08-28",
            "url":"https://www.law.go.kr/법령/직제",
            "comparison_status":"신구 본문 비교 완료",
            "changes":[{"article":"별표 0001","type":"개정",
                "before":old,"after":new,"source_url":"https://www.law.go.kr/법령/직제"}]}

class GroundedOrganizationTests(unittest.TestCase):
    def test_only_owning_agency_receives_count_not_unrelated_ministries(self):
        data=rule()
        parsed=impact.identify(data)
        self.assertEqual(len(parsed["actions"]),1)
        item=parsed["actions"][0]
        self.assertEqual(item["agency"],"개인정보 보호위원회")
        self.assertIn("공무원 정원 총계",item["target_location"])
        self.assertIn("192명 → 197명",item["what_to_change"])
        self.assertIn("+5명",item["what_to_change"])
        self.assertEqual(item["article"],"별표 0001")
        self.assertFalse(item["actual_system_verified"])
        self.assertEqual(parsed["candidate_agencies"],[])

    def test_article_mentions_do_not_trigger_other_agency_cards(self):
        e=rule()
        analyzed=impact.identify(e)
        e.update({"effects":analyzed["effects"],"institution_actions":analyzed["actions"]})
        clauses={
            "제3조":"고용노동부장관은 인사관리업무와 개인정보 보호를 담당한다.",
            "제7조":"구청장은 조직과 정원의 관리 업무를 지원한다.",
            "별표 0001":NEW
        }
        self.assertEqual(agency_resolver.assign(e,clauses),[])

    def test_number_without_field_is_not_an_instruction(self):
        e=rule(old="별표 1 총계 192명",new="별표 1 총계 197명")
        found=impact.identify(e)
        self.assertFalse(found["actions"])

    def test_owner_is_generic_from_law_title_not_programmed_agency(self):
        e=rule(title="가상공공청과 그 소속기관 직제")
        actions=impact.identify(e)["actions"]
        self.assertEqual(len(actions),1)
        self.assertEqual(actions[0]["agency"],"가상공공청")

    def test_unrelated_laws_mentioning_privacy_are_not_a_domino(self):
        a=rule()
        a.update({"effects":impact.effects(a),"impact_category":"조직개편·업무이관",
                  "institution_actions":[],"agency_candidates":[]})
        b=dict(a,id="other",title="가상건강법 시행령",source="law",
               stable_id="other",serial="other",impact_category="제도·업무 변경")
        snap={}
        result=policy_graph.link_documents([a,b],snap)
        self.assertEqual(result["links"],0)
        self.assertEqual(a["policy_links"],[])
        self.assertEqual(a.get("dependency_actions",[]),[])

if __name__=="__main__":
    unittest.main()
