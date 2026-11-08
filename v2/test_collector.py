import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2 import collector as m

class CollectorTests(unittest.TestCase):
    def entry(self, source="admrul", name="가상 서비스 운영기준", serial="100"):
        return {"source":source,"stable_id":"22","serial":serial,"title":name,
                "published_at":"2026-10-01","effective_date":"2027-01-01",
                "ministry":"가상기관","revision":"일부개정",
                "kind":"고시","number":"제12호","url":"https://www.law.go.kr/example"}

    def test_list_admin_rules_not_enrolled(self):
        root=ET.fromstring("""<AdmrulSearch><admrul><행정규칙명>가상 환경관리 기준</행정규칙명>
        <행정규칙ID>123</행정규칙ID><행정규칙일련번호>456</행정규칙일련번호>
        <발령일자>20261031</발령일자><발령번호>제33호</발령번호><소관부처명>가상부</소관부처명>
        <행정규칙종류>고시</행정규칙종류></admrul></AdmrulSearch>""")
        with patch.object(m, "request", return_value=root):
            found=m.list_source("admrul",100)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["title"],"가상 환경관리 기준")
        self.assertEqual(found[0]["published_at"],"2026-10-31")

    def test_compare_real_versions_from_any_domain(self):
        entry=self.entry()
        changed=m.compare({"제2조":"허가 신청은 30일 이내에 한다."},
                          {"제2조":"허가 신청은 15일 이내에 한다."},entry)
        self.assertEqual(changed[0]["before"],"허가 신청은 30일 이내에 한다.")
        self.assertEqual(changed[0]["after"],"허가 신청은 15일 이내에 한다.")
        self.assertEqual(m.compare({"제2조":"동일"},{"제2조":"동일"},entry),[])
        self.assertEqual(changed[0]["numbers_before"],["30일"])
        self.assertEqual(changed[0]["numbers_after"],["15일"])

    def test_no_previous_no_fake_comparison(self):
        entry=self.entry()
        event=m.make_event(entry,[],"이전 연혁 본문 미확보","2026-11-08")
        self.assertEqual(event["change_count"],0)
        self.assertEqual(m.action_records(event),[])

    def test_general_actions_use_evidence_and_mark_uncertain(self):
        entry=self.entry(name="가상 수출지원법")
        diff=m.compare({"제3조":"교육감은 신청 연령 20세를 심사한다."},
                       {"제3조":"교육감은 신청 연령 18세를 심사한다."},entry)[0]
        event=m.make_event(entry,[diff],"신구 본문 비교 완료","2026-11-08")
        actions=m.action_records(event)
        self.assertTrue(any(x["agency"]=="교육감" for x in actions))
        self.assertTrue(all(x["status"]=="영향 검토 필요" for x in actions))
        self.assertTrue(all(x["target_verified"] is False for x in actions))

    def test_citation_relation_not_shared_keyword(self):
        a=m.make_event(self.entry(name="가상 기준법",serial="101"),[],"신구 본문 비교 완료","t")
        b=m.make_event(self.entry(name="가상 업무규칙",serial="102"),
            [{"after":"「가상 기준법」 제3조를 따른다.","before":"다른 기준", "article":"제1조"}],
            "신구 본문 비교 완료","t")
        c=m.make_event(self.entry(name="가상 제3규칙",serial="103"),
            [{"after":"가상 기준법과 업무가 유사하다.","before":"", "article":"제1조"}],
            "신구 본문 비교 완료","t")
        self.assertEqual(m.link_relations([a,b,c]),1)
        self.assertEqual(len(a["downstream_changes"]),1)
        self.assertEqual(len(c["upstream_changes"]),0)

    def test_reference_search_not_claimed_proven(self):
        e=m.make_event(self.entry(),[{"before":"", "after":"방식", "article":"제1조"}],
                       "신구 본문 비교 완료","t")
        xml=ET.fromstring("""<root><admrul><행정규칙명>가상 지원 업무</행정규칙명>
        <행정규칙ID>999</행정규칙ID><행정규칙일련번호>444</행정규칙일련번호>
        <발령일자>20261010</발령일자></admrul></root>""")
        with patch.object(m,"request",return_value=xml):
            hits,errors=m.add_reference_hits(e,search_quota=1)
        self.assertEqual(errors,[])
        self.assertTrue(hits)
        self.assertIn("미확인",hits[0]["status"])

    def test_parse_admin_detail_as_flat_content(self):
        root=ET.fromstring("""<행정규칙><조문내용>제1조(목적) 허가한다. 제2조(대상) 100원을 지원한다.</조문내용></행정규칙>""")
        with patch.object(m,"request",return_value=root):
            clauses=m.read_clauses(self.entry())
        self.assertEqual(len(clauses),2)
        self.assertIn("100원",clauses["제2조"])

    def test_annual_standard_search_is_generic_not_policy_specific(self):
        new=self.entry(name="2027년도 가상 서비스 기준",serial="500")
        older=ET.fromstring("""<root><admrul><행정규칙명>2026년도 가상 서비스 기준</행정규칙명>
        <행정규칙ID>888</행정규칙ID><행정규칙일련번호>400</행정규칙일련번호>
        <발령일자>20251001</발령일자></admrul></root>""")
        empty=ET.fromstring("<root><totalCnt>0</totalCnt></root>")
        with patch.object(m,"request",side_effect=[empty,older]),patch.object(m,"read_clauses",return_value={"제1조":"100원"}):
            previous=m.historical_predecessor(new)
        self.assertTrue(previous["annual_comparison"])
        self.assertEqual(previous["record"]["title"],"2026년도 가상 서비스 기준")

    def test_scope_two_official_categories(self):
        src = Path(m.__file__).read_text("utf-8")
        self.assertIn('("law", "admrul")',src)
        self.assertNotIn("SOURCE_PROFILES",src)
        self.assertNotIn("주거급여",src)
        self.assertNotIn("교육급여",src)
        self.assertNotIn("중위소득",src)

if __name__=="__main__":
    unittest.main()
