import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
from v3 import semantic_diff as s,impact
from v2 import collector

def evt(title,old,new,article="제35조"):
    return {"id":title,"title":title,"source":"law","stable_id":title,
            "serial":"1001","ministry":"가상부","revision":"일부개정",
            "kind":"법률","url":"https://law.go.kr/example",
            "comparison_status":"신구 본문 비교 완료",
            "changes":[{"article":article,"type":"개정",
                        "before":old,"after":new,"source_url":"https://law.go.kr/example"}]}

class CompleteSentenceRegression(unittest.TestCase):
    def test_nested_parenthetical_period_does_not_split_sentence(self):
        old="제35조(검사업무) ① 해양시험청장은 검사업무를 수행한다."
        new="제35조(검사업무) ① 해양시험청장은 검사업무(정밀안전진단 등을 포함한다. 이하 이 조에서 같다)를 수행한다."
        p=s.pairs(evt("A",old,new)["changes"][0])
        self.assertEqual(len(p),1,p)
        self.assertIn("이하 이 조에서 같다)를 수행한다",p[0]["after"])
        self.assertIn("해양시험청장",p[0]["before"])
        self.assertIn("해양시험청장",p[0]["after"])

    def test_unrelated_string_frags_not_paired(self):
        before="「가상에너지 특별회계법」 제5조에 따라 예산을 편성한다."
        after="내항화물운송사업자에게 새 서류를 제출하도록 안내한다."
        p=s.pairs(evt("B",before,after)["changes"][0])
        self.assertFalse(any(x["before"] and x["after"] for x in p),p)
        self.assertNotIn(("「가상에너지","내항화물운송사업자에게"),
                         [(x["before"],x["after"]) for x in p])

    def test_two_edits_one_long_clause_do_not_spawn_duplicates(self):
        old=("제41조(검사) ① 해양시험청장은 선박의 검사업무를 수행한다. "
             "② 해양시험청장은 검사결과를 통지하여야 한다.")
        new=("제41조(검사) ① 해양시험청장은 선박의 정기검사업무를 수행한다. "
             "② 해양시험청장은 검사결과를 15일 이내에 통지하여야 한다.")
        e=impact.analyze({"events":[evt("C",old,new,article="제41조")],"health":{}})["events"][0]
        a=e["institution_actions"]
        keys=[(x["agency"],x["article"],x["work"]) for x in a]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertTrue(all(x.get("change_pairs") for x in a))
        for x in a:
            for p in x["change_pairs"]:
                self.assertTrue(p["before"].startswith("제41조") or
                                p["before"].startswith("①") or
                                p["before"].startswith("②"))
                self.assertIn("해양시험청장",p["after"])

    def test_large_unrelated_document_reflow_is_not_a_specific_action(self):
        old="제4조(기준) 가상항공공단은 장비검사를 실시한다."
        new="제4조(기준) 가상교육재단은 장학금 지급기준을 다시 정한다."
        e=impact.analyze({"events":[evt("D",old,new)],"health":{}})["events"][0]
        self.assertFalse(any("장비검사를" in a["what_to_change"] and
                             "장학금" in a["what_to_change"]
                             for a in e["institution_actions"]))

    def test_unrelated_agency_in_unchanged_other_clause_does_not_receive_task(self):
        old=("제3조 ① 가상해양청장은 검사를 한다. "
             "② 가상지원재단은 신청서를 30일 이내 처리한다.")
        new=("제3조 ① 가상해양청장은 검사를 한다. "
             "② 가상지원재단은 신청서를 20일 이내 처리한다.")
        e=impact.analyze({"events":[evt("E",old,new,"제3조")],"health":{}})["events"][0]
        agencies={a["agency"] for a in e["institution_actions"]}
        self.assertNotIn("가상해양청장",agencies)
        self.assertIn("가상지원재단",agencies)

    def test_xml_article_subclauses_are_not_appended_twice(self):
        xml=ET.fromstring("""<법령><조문단위><조문번호>35</조문번호>
          <조문내용>제35조(검사) 해양시험청장은 검사를 한다.</조문내용>
          <항><항내용>① 해양시험청장은 검사업무를 수행한다.</항내용>
            <호><호내용>1. 정기검사의 기준</호내용></호>
          </항></조문단위></법령>""")
        with patch.object(collector,"request",return_value=xml):
            got=collector.read_clauses({"source":"law","serial":"1000"})
        c=got["제35조"]
        self.assertEqual(c.count("① 해양시험청장은"),1,c)
        self.assertEqual(c.count("1. 정기검사의 기준"),1,c)

    def test_duplicate_nested_paragraph_does_not_make_artificial_change(self):
        before=("제35조(검사) ① 해양시험청장은 검사를 한다. "
                "② 해양시험청장은 검사 결과를 기록한다.")
        after=("제35조(검사) ① 해양시험청장은 검사를 한다. "
               "① 해양시험청장은 검사를 한다. "
               "② 해양시험청장은 검사 결과를 기록한다.")
        p=s.pairs(evt("F",before,after)["changes"][0])
        self.assertFalse(p,p)

    def test_real_deadline_still_detected_without_registered_sector(self):
        e=impact.analyze({"events":[evt("항공시설 관리규칙",
          "가상운영공단은 신청서를 30일 이내 처리한다.",
          "가상운영공단은 신청서를 15일 이내 처리한다.")],"health":{}})["events"][0]
        self.assertTrue(e["institution_actions"])
        self.assertTrue(any("30일" in p["before"] and "15일" in p["after"]
                            for a in e["institution_actions"]
                            for p in a["change_pairs"]))

    def test_source_annual_standard_without_actor_remains_searchable(self):
        e=impact.analyze({"events":[evt("2027년도 시험 기준",
          "2026년 산정기준액은 100만원이다.",
          "2027년 산정기준액은 120만원이다.")],"health":{}})["events"][0]
        self.assertEqual(e["institution_actions"],[])
        self.assertTrue(e["effects"])
        self.assertEqual(e["impact_category"],"제도·업무 변경")

if __name__=="__main__":unittest.main()
