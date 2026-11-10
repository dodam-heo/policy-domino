import unittest
import xml.etree.ElementTree as ET
from policy_domino.engine import dependents,events

def changed():
    record={"source":"law","stable_id":"101","serial":"1001",
      "title":"가상운영법","published_at":"2026-11-01",
      "effective_date":"2027-01-01","revision":"일부개정",
      "kind":"법률","ministry":"가상부","number":"1",
      "url":"https://www.law.go.kr/example"}
    e={**record,"id":events.key(record),"verification":"verified_changed_clauses",
      "promulgated_at":record["published_at"],
      "changes":[{"article":"제35조","before":"신청은 30일 안에 한다.",
                  "after":"신청은 15일 안에 한다.","type":"개정"}],
      "changed_articles":["제35조"]}
    return e

def target(serial="2001",name="가상운영안내"):
    return {"source":"admrul","stable_id":serial,
            "serial":serial,"title":name,
            "ministry":"가상시청","url":"https://www.law.go.kr/example"}

class EvidenceSearchQueue(unittest.TestCase):
    def test_keyword_hit_is_not_a_confirmed_downstream_rule(self):
        source=changed()
        dependent=target()
        state={"inspected":{source["id"]:source},"dependent_queue":{},
               "dependent_checked":{},"confirmed_dependencies":{}}
        dependents.enqueue(state,source,[dependent])
        result=dependents.process(state,read_source=lambda r:
            {"제3조":"「가상운영법」과 관련한 기타 행정사항을 정한다."})
        self.assertEqual(result["attempted"],1)
        self.assertEqual(result["confirmed_total"],0)
        self.assertFalse(state["confirmed_dependencies"])
        self.assertEqual(len(state["dependent_checked"]),1)

    def test_changed_exact_clause_with_actual_application_passes(self):
        source=changed()
        dependent=target()
        state={"inspected":{source["id"]:source},"dependent_queue":{},
               "dependent_checked":{},"confirmed_dependencies":{}}
        dependents.enqueue(state,source,[dependent])
        result=dependents.process(state,read_source=lambda r:
            {"제3조":"가상시청은 「가상운영법」 제35조에 따라 신청서를 처리한다."})
        self.assertEqual(result["confirmed_total"],1)
        link=next(iter(state["confirmed_dependencies"].values()))
        self.assertTrue(link["affected_verified"])
        self.assertFalse(link["implementation_verified"])
        self.assertEqual(link["source_article"],"제35조")

    def test_mismatched_clause_never_passes(self):
        source=changed()
        state={"inspected":{source["id"]:source}}
        dependents.enqueue(state,source,[target()])
        result=dependents.process(state,read_source=lambda r:
            {"제4조":"「가상운영법」 제36조에 따라 신청서를 처리한다."})
        self.assertEqual(result["confirmed_total"],0)

    def test_citation_only_and_confirmed_are_never_combined(self):
        source=changed()
        state={"inspected":{source["id"]:source}}
        dependents.enqueue(state,source,[target("20"),target("21")])
        def read(r):
            return {"제1조":"「가상운영법」 제35조에 따라 해당 업무를 정한다."} if r["serial"]=="20" else {
                "제1조":"「가상운영법」의 목적을 설명한다."}
        result=dependents.process(state,read_source=read,limit=10)
        self.assertEqual(result["confirmed_total"],1)
        self.assertEqual(len(state["dependent_checked"]),2)

if __name__=="__main__":unittest.main()
