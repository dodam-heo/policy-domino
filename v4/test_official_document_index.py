import unittest
from v4 import classic_bridge as bridge

class SourceDocumentIndex(unittest.TestCase):
    def test_law_source_agencies_survive_even_when_no_action_is_proven(self):
        docs=[
          {"title":"가상건설위원회 직제", "ministry":"가상부처",
           "url":"https://www.law.go.kr/법령/test1",
           "verification":"verified_repeal_notice"},
          {"title":"가상지역공사 직제", "ministry":"가상부처",
           "url":"https://www.law.go.kr/법령/test2",
           "verification":"verified_repeal_notice"}
        ]
        event,actions=bridge.group_event({
           "id":"event","source_docs":docs,"source_count":2,
           "date":"2026-11-03","effective_at":"2026-11-03",
           "number":"1","agency_count":2})
        self.assertEqual(actions,[])
        self.assertEqual(len(event["official_change_documents"]),2)
        self.assertEqual({x["agency"] for x in event["official_change_documents"]},
                         {"가상건설위원회","가상지역공사"})
        self.assertFalse(any(x["actual_implementation_verified"]
                             for x in event["official_change_documents"]))

    def test_publisher_does_not_become_proven_program_operator(self):
        rows=bridge.official_document_index([{
          "title":"가상 지원법","ministry":"가상부처",
          "url":"https://www.law.go.kr/법령/fake"}])
        self.assertEqual(len(rows),1)
        self.assertIn("집행기관 미확인",rows[0]["agency_role"])
        self.assertFalse(rows[0]["actual_implementation_verified"])

    def test_no_unofficial_links_or_false_data(self):
        rows=bridge.official_document_index([{
          "title":"가상공사 직제","ministry":"가상부처",
          "url":"https://random.example.com/policy"},
          {"title":"가상공사 직제","ministry":"가상부처",
           "url":"https://www.law.go.kr/법령/fake"}])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["agency"],"가상공사")
        self.assertNotIn("required_change",rows[0])

if __name__=="__main__":unittest.main()
