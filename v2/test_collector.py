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

    def test_admin_rule_annex_only_has_actual_body(self):
        root=ET.fromstring("""<AdmRulService><별표><별표단위>
          <별표번호>1</별표번호><별표제목>지원 기준표</별표제목>
          <별표내용>가구별 지원금액 120만원</별표내용>
          </별표단위></별표></AdmRulService>""")
        with patch.object(m,"request",return_value=root):
            clauses=m.read_clauses(self.entry())
        self.assertEqual(len(clauses),1)
        self.assertIn("지원금액 120만원",next(iter(clauses.values())))

    def test_flat_escaped_html_is_text_not_markup(self):
        root=ET.fromstring("""<AdmRulService><조문내용>
        &lt;p&gt;제1조(지급)&lt;/p&gt; 100만원을 지급한다.
        &lt;p&gt;제2조(선정)&lt;/p&gt; 20세 이상에 적용한다.
        </조문내용></AdmRulService>""")
        with patch.object(m,"request",return_value=root):
            clauses=m.read_clauses(self.entry())
        self.assertEqual(len(clauses),2)
        self.assertNotIn("<p>",str(clauses))
        self.assertIn("20세",clauses["제2조"])

    def test_unchanged_numbered_clause_and_changed_annex_preserved(self):
        root=ET.fromstring("""<AdmRulService><조문단위>
          <조문번호>3</조문번호><조문내용>제3조(신청) 신청한다.</조문내용>
          </조문단위><별표단위><별표번호>2</별표번호>
          <별표내용>심사 기준 40만원</별표내용>
          </별표단위></AdmRulService>""")
        with patch.object(m,"request",return_value=root):
            clauses=m.read_clauses(self.entry())
        self.assertIn("제3조",clauses)
        self.assertTrue(any(k.startswith("별표 2") for k in clauses))

    def test_supplement_actual_text_is_parsed(self):
        root=ET.fromstring("""<AdmRulService><부칙><부칙공포번호>3</부칙공포번호>
          <부칙공포일자>20261109</부칙공포일자>
          <부칙내용>이 규칙은 2027년 1월 1일부터 시행한다.</부칙내용>
          </부칙></AdmRulService>""")
        with patch.object(m,"request",return_value=root):
            clauses=m.read_clauses(self.entry())
        self.assertTrue(any(k.startswith("부칙") for k in clauses))
        self.assertIn("2027년",next(iter(clauses.values())))

    def test_attachment_link_alone_never_becomes_changed_text(self):
        root=ET.fromstring("""<AdmRulService><별표><별표단위>
          <별표번호>1</별표번호>
          <별표제목>연도별 선정표</별표제목>
          <별표서식파일링크>https://www.law.go.kr/doc/download</별표서식파일링크>
          </별표단위></별표></AdmRulService>""")
        with patch.object(m,"request",return_value=root):
            with self.assertRaisesRegex(RuntimeError,"첨부파일 참조만 확인"):
                m.read_clauses(self.entry())

    def test_ordinance_detail_uses_official_master_serial(self):
        rec=self.entry(source="ordin")
        root=ET.fromstring("""<LawService><조항>
          <조문번호>7</조문번호><조문여부>Y</조문여부>
          <조제목>지원기준</조제목><조내용>신청자에게 25만원을 지급한다.</조내용>
          </조항></LawService>""")
        with patch.object(m,"request",return_value=root) as req:
            clauses=m.read_clauses(rec)
        self.assertEqual(req.call_args.kwargs["MST"],"100")
        self.assertNotIn("ID",req.call_args.kwargs)
        self.assertIn("제7조",clauses)
        self.assertIn("25만원",clauses["제7조"])

    def test_ordinance_section_heading_not_treated_as_modified_article(self):
        rec=self.entry(source="ordin")
        root=ET.fromstring("""<LawService><조항>
          <조문번호>1</조문번호><조문여부>N</조문여부>
          <조제목>제1장 총칙</조제목><조내용>제1장 총칙</조내용>
          </조항><조항><조문번호>2</조문번호>
          <조내용>의무 신청 기준을 정한다.</조내용></조항></LawService>""")
        with patch.object(m,"request",return_value=root):
            clauses=m.read_clauses(rec)
        self.assertEqual(list(clauses),["제2조"])

    def test_flat_text_split_preserves_unheaded_annex_and_unrelated_citation(self):
        root=ET.fromstring("""<AdmRulService><조문내용>「가상급여규정」 제15조를
          준용한다. 선정 금액은 20만원이다.</조문내용></AdmRulService>""")
        with patch.object(m,"request",return_value=root):
            clauses=m.read_clauses(self.entry())
        self.assertEqual(list(clauses),["본문"])
        self.assertIn("제15조",clauses["본문"])

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

    def test_queue_selects_major_annual_standards_before_oneoff_future_records(self):
        import datetime as dt
        entries=[
          self.entry(name="통계작성의 변경승인(가상통계)",serial="1"),
          self.entry(name="2027년 가상 주거지원 선정기준",serial="2"),
          self.entry(name="2027년 가상 교육지원 선정기준",serial="3"),
          self.entry(name="기준 소득 및 수급자 선정기준",serial="4"),
          self.entry(name="가상업무 공무원 인사규정",serial="5")
        ]
        entries[3]["effective_date"]="2027-01-01"
        result=m.select_pending({str(i):x for i,x in enumerate(entries)},
                   "admrul",capacity=3,today=dt.date(2026,11,8))
        titles=[x["title"] for _,x in result]
        self.assertIn("2027년 가상 주거지원 선정기준",titles)
        self.assertIn("2027년 가상 교육지원 선정기준",titles)
        self.assertIn("기준 소득 및 수급자 선정기준",titles)
        self.assertNotIn("통계작성의 변경승인(가상통계)",titles)

    def test_fulltext_future_year_search_reaches_yearless_titles(self):
        import datetime as dt
        root=ET.fromstring("""<root><admrul>
          <행정규칙명>기준 소득 및 선정기준</행정규칙명>
          <행정규칙ID>123</행정규칙ID><행정규칙일련번호>456</행정규칙일련번호>
          <발령일자>20260729</발령일자><시행일자>20270101</시행일자>
          </admrul></root>""")
        with patch.object(m,"request",return_value=root) as call:
            found=m.list_source("admrul",title_query="2027",fulltext=True,
                  date_window=(dt.date(2026,5,1),dt.date(2026,11,8)),limit=70)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["title"],"기준 소득 및 선정기준")
        kwargs=call.call_args.kwargs
        self.assertEqual(kwargs["search"],2)
        self.assertEqual(kwargs["prmlYd"],"20260501~20261108")

    def test_annual_official_notice_replacement_is_not_fake_amount(self):
        current=self.entry(name="2027년 가상기준 고시",serial="200")
        before=self.entry(name="2026년 가상기준 고시",serial="100")
        change=m.annual_switch_change(current,before)[0]
        self.assertFalse(change["numeric_values_verified"])
        self.assertIn("2026년",change["before"])
        self.assertIn("2027년",change["after"])
        self.assertEqual(change["numbers_after"],[])

    def test_predecessor_marks_annual_even_with_same_stable_id(self):
        new=self.entry(name="2027년 가상기준 고시",serial="500")
        old=ET.fromstring("""<root><admrul><행정규칙명>2026년 가상기준 고시</행정규칙명>
          <행정규칙ID>22</행정규칙ID><행정규칙일련번호>450</행정규칙일련번호>
          <발령일자>20251031</발령일자></admrul></root>""")
        with patch.object(m,"request",return_value=old),patch.object(m,"read_clauses",return_value={"본문":"동일"}):
            prior=m.historical_predecessor(new)
        self.assertTrue(prior["annual_comparison"])

    def test_cited_article_not_treated_as_heading_in_flat_rule(self):
        root=ET.fromstring("""<행정규칙><조문내용>「가상지원법」 제6조 및 제12조를 준용한다. 지원금은 50만원이다.</조문내용></행정규칙>""")
        with patch.object(m,"request",return_value=root):
            clauses=m.read_clauses(self.entry())
        self.assertEqual(list(clauses),["본문"])
        self.assertIn("제12조",clauses["본문"])

    def test_scope_two_official_categories(self):
        src = Path(m.__file__).read_text("utf-8")
        self.assertIn('("law", "admrul")',src)
        self.assertNotIn("SOURCE_PROFILES",src)
        self.assertNotIn("주거급여",src)
        self.assertNotIn("교육급여",src)
        self.assertNotIn("중위소득",src)

if __name__=="__main__":
    unittest.main()
