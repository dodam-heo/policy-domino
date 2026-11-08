import unittest
from v3 import policy_graph as g
from v2 import collector

def event(i,title,source="admrul",category="제도·업무 변경"):
    return {"id":i,"title":title,"source":source,"stable_id":i,"serial":i+"-v2",
            "effective_date":"2027-01-01","impact_category":category,
            "effects":[{"article":"제2조","old":"이전 기준","new":"새 기준"}],
            "institution_actions":[],"agency_candidates":[],
            "ministry":"가상부","url":"https://www.law.go.kr/test","citations":[]}
def snapshots(events,texts):
    return {collector.uid(e["source"],e["stable_id"]):
            {"serial":e["serial"],"clauses":{"본문":texts[e["id"]]}} for e in events}

class CrossPolicyGraphTests(unittest.TestCase):
    def test_explicit_citation_with_operative_clause_creates_reference_not_action(self):
        a=event("a","기술지원 공통 산정기준")
        b=event("b","지역산업 보조금 관리규정")
        snap=snapshots([a,b],{
            "a":"공통 산정기준을 정한다.",
            "b":"가상지자체는 「기술지원 공통 산정기준」을 적용하여 지원액을 산정한다."})
        info=g.link_documents([a,b],snap)
        self.assertEqual(info["links"],1)
        self.assertEqual(a["policy_links"][0]["target_title"],b["title"])
        self.assertFalse(a["policy_links"][0]["causation_verified"])
        self.assertEqual(a["dependency_actions"],[])

    def test_shared_law_citation_not_enough(self):
        a=event("a","공통 복지지원 산정기준")
        b=event("b","학교 교육지원 선정기준")
        snap=snapshots([a,b],{
            "a":"「가상 기본법」에 따라 지원기준을 산정한다.",
            "b":"「가상 기본법」에 따라 교육지원 선정기준을 정한다."})
        self.assertEqual(g.link_documents([a,b],snap)["links"],0)

    def test_unrelated_rules_sharing_one_topical_word_do_not_link(self):
        a=event("a","시스템 장애 예방규정")
        b=event("b","학교 장애지원 운영규정")
        snap=snapshots([a,b],{
            "a":"장애 대응을 시행한다.",
            "b":"학교 내 장애를 지원하고 관련 시스템을 운영한다."})
        self.assertEqual(g.link_documents([a,b],snap)["links"],0)

    def test_naked_document_name_without_application_does_not_link(self):
        a=event("a","공통 시설지원 평가기준")
        b=event("b","가상 자료소개 규정")
        snap=snapshots([a,b],{
            "a":"시설지원 평가기준을 정한다.",
            "b":"「공통 시설지원 평가기준」의 문서명을 참고자료로 표시한다."})
        self.assertEqual(g.link_documents([a,b],snap)["links"],0)

    def test_repealed_document_never_generates_live_agency_dependency(self):
        a=event("a","시설 비상대응 지침",category="폐지·효력종료")
        b=event("b","시설 안전관리 규정")
        snap=snapshots([a,b],{
            "a":"시설 비상대응 지침을 폐지한다.",
            "b":"「시설 비상대응 지침」을 준용하여 기록한다."})
        self.assertEqual(g.link_documents([a,b],snap)["links"],0)

    def test_absent_official_body_yields_no_assumed_relation(self):
        a=event("a","공통 지원기준")
        b=event("b","가상 지원관리 규정")
        self.assertEqual(g.link_documents([a,b],{})["links"],0)

if __name__=="__main__":unittest.main()
