import unittest
from v3 import policy_graph as g
from v2 import collector

def event(i,title,acts,source="admrul",year=2027,category="제도·업무 변경"):
    return {"id":i,"title":title,"source":source,"stable_id":i,
            "serial":i+"-v2","effective_date":f"{year}-01-01",
            "impact_category":category,"effects":[{"article":"제2조","old":"이전 기준","new":"새 기준"}],
            "institution_actions":acts,"agency_candidates":[],"ministry":"가상부",
            "url":"https://www.law.go.kr/행정규칙/"+i,"citations":[]}
def snapshots(events,texts):
    return {collector.uid(e["source"],e["stable_id"]):
            {"serial":e["serial"],"clauses":{"본문":texts[e["id"]]}} for e in events}

class CrossPolicyGraphTests(unittest.TestCase):
    def test_direct_standard_use_crosses_ministries_without_enrolled_policy_names(self):
        parent=event("baseline","기술지원 공통 산정기준",[])
        child=event("child","지역산업 보조금 산정기준",
            [{"agency":"가상시","work":"금액·산식 적용",
              "target_location":"지역 지원액 산정 기준표"}])
        snap=snapshots([parent,child],{
            "baseline":"「가상 지원법」에 따라 공통 산정기준을 정한다.",
            "child":"가상시는 기술지원 공통 산정기준을 적용하여 보조금을 산정한다."})
        outcome=g.link_documents([parent,child],snap)
        self.assertEqual(outcome["explicit_standard_uses"],1)
        self.assertEqual(parent["policy_links"][0]["target_title"],child["title"])
        self.assertEqual(parent["dependency_actions"][0]["agency"],"가상시")
        self.assertFalse(parent["dependency_actions"][0]["actual_system_verified"])

    def test_shared_law_is_not_proven_dependency(self):
        parent=event("baseline","기초지원 선정기준",[])
        child=event("child","교육지원 선정기준",[])
        snap=snapshots([parent,child],{
            "baseline":"「가상 보장법」에서 선정기준을 정한다.",
            "child":"「가상 보장법」에 따라 교육지원 선정기준을 정한다."})
        answer=g.link_documents([parent,child],snap)
        self.assertEqual(answer["shared_statutory_basis_candidates"],1)
        self.assertFalse(parent["policy_links"][0]["verified_reference"])
        self.assertFalse(parent["policy_links"][0]["causation_verified"])

    def test_one_annual_basis_can_link_two_other_ministries_with_evidence_levels(self):
        origin=event("common","공통 소득산정 기준과 선정기준",[])
        x=event("housing","지역 주거지원 선정기준",[])
        y=event("education","학교 교육지원 선정기준",[])
        origin["ministry"]="가상보건부"
        x["ministry"]="가상국토부";y["ministry"]="가상교육부"
        snaps=snapshots([origin,x,y],{
            "common":"「국민복지 기본법」에 따라 공통 소득산정 기준을 공표한다.",
            "housing":"임대지원 금액은 공통 소득산정 기준의 48% 이하를 적용한다.",
            "education":"「국민복지 기본법」에 따른 교육지원 선정기준을 정한다."
        })
        stats=g.link_documents([origin,x,y],snaps)
        names={a["target_title"]:a["verified_reference"] for a in origin["policy_links"]}
        self.assertEqual(stats["links"],2)
        self.assertTrue(names[x["title"]])
        self.assertFalse(names[y["title"]])
        self.assertTrue(any(t["agency"]=="가상국토부" for t in origin["dependency_actions"]))
        self.assertTrue(any(t["agency"]=="가상교육부" for t in origin["dependency_actions"]))

    def test_different_year_not_linked(self):
        parent=event("base","지원 공통 선정기준",[])
        child=event("other","지역 보조금 선정기준",[],year=2029)
        snap=snapshots([parent,child],{"base":"지원 공통 선정기준",
                    "other":"지원 공통 선정기준을 적용하여 산정한다."})
        self.assertEqual(g.link_documents([parent,child],snap)["links"],0)

    def test_no_causal_claim_just_matching_titles(self):
        parent=event("a","가상산업 보장기준",[])
        child=event("b","가상산업 보장기준 안내",[])
        snap=snapshots([parent,child],{"a":"가상산업",
                                          "b":"가상산업 보장기준은 문서명이다."})
        self.assertEqual(g.link_documents([parent,child],snap)["links"],0)

if __name__=="__main__":unittest.main()
