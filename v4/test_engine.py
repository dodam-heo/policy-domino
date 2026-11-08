import unittest
import xml.etree.ElementTree as ET
from v4 import collect_index as index,events as event,relationships as relations

def row(i,day="20261107",source="law",number="101"):
    if source=="law":
        return (f"<law><법령명한글>가상정책법{i}</법령명한글><법령ID>{1000+i}</법령ID>"
            f"<법령일련번호>{9000+i}</법령일련번호><공포일자>{day}</공포일자>"
            f"<공포번호>{number}</공포번호><제개정구분명>일부개정</제개정구분명>"
            f"<법령구분명>법률</법령구분명></law>")
    return (f"<admrul><행정규칙명>가상산업지원{i} 기준</행정규칙명>"
            f"<행정규칙ID>{1000+i}</행정규칙ID><행정규칙일련번호>{9000+i}</행정규칙일련번호>"
            f"<발령일자>{day}</발령일자><발령번호>{number}</발령번호>"
            f"<제개정구분명>일부개정</제개정구분명></admrul>")

def rec(i,title="가상정책법",serial=None,day="2026-11-07",source="law",number="101"):
    return {"source":source,"title":title,"stable_id":str(1200+i),
            "serial":str(serial or (10000+i)),"published_at":day,
            "effective_date":"2027-01-01","revision":"일부개정",
            "kind":"법률" if source=="law" else "고시",
            "number":number,"ministry":"가상부","url":"https://www.law.go.kr/example"}

def ev(r,article="제35조",before="검사기준은 30일이다.",after="검사기준은 20일이다."):
    e=dict(r,id=event.key(r),promulgated_at=r["published_at"],
           promulgation_number=r["number"],changes=[{
           "article":article,"type":"개정","before":before,"after":after}],
           verification="verified_changed_clauses")
    return e

class OfficialCollection(unittest.TestCase):
    def test_paginates_to_official_total_not_first_500(self):
        pages=[]
        def fetch(target,**kw):
            self.assertEqual(target,"law")
            page=kw["page"];pages.append(page)
            start=(page-1)*100
            vals=[row(i) for i in range(start,min(start+100,230))]
            return ET.fromstring("<root><totalCnt>230</totalCnt>"+''.join(vals)+"</root>")
        got,stat=index.scan_window("law","2026-11-07","2026-11-07",fetch,max_pages=6)
        self.assertEqual(len(got),230)
        self.assertTrue(stat.complete)
        self.assertEqual(pages,[1,2,3])
        self.assertEqual(stat.reported,230)

    def test_page_cap_is_a_failure_not_an_all_collected_message(self):
        def fetch(target,**kw):
            return ET.fromstring("<root><totalCnt>900</totalCnt>"+
                                 ''.join(row(i) for i in range(100))+"</root>")
        got,stat=index.scan_window("law","2026-11-07","2026-11-07",fetch,max_pages=1)
        self.assertEqual(len(got),100)
        self.assertFalse(stat.complete)
        self.assertIn("Page limit",stat.error)

    def test_source_index_not_filtered_by_sector_or_year(self):
        def fetch(target,**kw):
            self.assertEqual(kw["prmlYd"],"20261001~20261001")
            return ET.fromstring("<root><totalCnt>1</totalCnt>"+row(7,day="20261001",source="admrul")+"</root>")
        state={}
        done=index.ingest_index(state,"admrul",[("2026-10-01","2026-10-01")],fetch)
        self.assertEqual(done["new_versions"],1)
        self.assertEqual(len(state["catalog"]),1)
        self.assertEqual(done["incomplete_windows"],[])

    def test_repealed_administrative_rules_appear_from_history_index(self):
        modes=[]
        def fetch(target,**kw):
            modes.append(kw.get("nw"))
            return ET.fromstring("<root><totalCnt>1</totalCnt>"+
                row(9,day="20261001",source="admrul")+"</root>")
        state={}
        index.ingest_index(state,"admrul",[("2026-10-01","2026-10-01")],fetch)
        self.assertEqual(modes,["1","2"])
        self.assertEqual(len(state["catalog"]),1)
        self.assertEqual(len(state["coverage"]),2)
        self.assertEqual({x["edition"] for x in state["coverage"]},{"current","history"})

    def test_ordinance_xml_uses_korean_row_tags_not_ordin(self):
        sample=ET.fromstring("""<자치법규목록><totalCnt>1</totalCnt>
            <자치법규><자치법규명>가상시 복지 조례</자치법규명>
              <자치법규ID>101</자치법규ID>
              <자치법규일련번호>1111</자치법규일련번호>
              <공포일자>20261107</공포일자>
              <제개정구분명>일부개정</제개정구분명>
            </자치법규></자치법규목록>""")
        items,health=index.scan_window("ordin","2026-11-07","2026-11-07",
            fetch=lambda source,**kw:sample)
        self.assertTrue(health.complete)
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]["title"],"가상시 복지 조례")

    def test_official_history_is_not_current_index(self):
        def fetch(target,**kw):
            self.assertEqual(target,"lsHstInf")
            self.assertEqual(kw["regDt"],"20261107")
            return ET.fromstring("<root><totalCnt>2</totalCnt>"+row(1)+row(2)+"</root>")
        rows,health=index.scan_official_change_day("2026-11-07",fetch)
        self.assertTrue(health.complete)
        self.assertEqual(len(rows),2)
        self.assertTrue(all(x["discovery_kind"]=="official_law_change_history" for x in rows))

    def test_history_status_is_incomplete_if_rows_missing(self):
        def fetch(target,**kw):
            return ET.fromstring("<root><totalCnt>8</totalCnt>"+row(1)+"</root>")
        found,health=index.scan_official_change_day("2026-11-07",fetch)
        self.assertEqual(len(found),1)
        self.assertFalse(health.complete)

class CausalRelationship(unittest.TestCase):
    def test_law_name_alone_is_not_a_domino(self):
        parent=ev(rec(1,title="해운법"))
        child=ev(rec(2,title="해운안전 업무규정"))
        x=relations.evaluate(parent,child,{"제4조":"「해운법」에 따라 사업자 등록을 처리한다."})
        self.assertEqual(x["type"],"citation_only")
        self.assertFalse(x["affected_verified"])

    def test_wrong_cited_article_is_not_changed_impact(self):
        parent=ev(rec(1,title="가상지원법"))
        child=ev(rec(2,title="가상재단 운영규정"))
        x=relations.evaluate(parent,child,{"제9조":"「가상지원법」 제34조에 따라 지급기준을 정한다."})
        self.assertEqual(x["type"],"citation_only")

    def test_actual_changed_provision_and_operational_use(self):
        parent=ev(rec(1,title="가상지원법"))
        child=ev(rec(2,title="지급업무 관리규정"))
        x=relations.evaluate(parent,child,{"제9조":"지급 대상은 「가상지원법」 제35조에 따라 선정한다."})
        self.assertEqual(x["type"],"cited_changed_provision")
        self.assertTrue(x["affected_verified"])
        self.assertEqual(x["source_article"],"제35조")
        self.assertFalse(x["implementation_verified"])

    def test_formula_derived_from_changed_named_standard(self):
        parent=ev(rec(1,title="2027년도 기준 중위소득 고시",source="admrul"),
                  article="별표 1",before="기준 중위소득 6,000,000원",after="기준 중위소득 6,900,000원")
        child=ev(rec(2,title="가상지급기준",source="admrul"))
        x=relations.evaluate(parent,child,{"본문":"신청자의 소득이 기준 중위소득의 48% 이하인 경우 적용한다."})
        self.assertIsNotNone(x)
        self.assertEqual(x["type"],"formula_dependency")
        self.assertTrue(x["affected_verified"])

    def test_mention_without_operating_formula_is_not_dependent(self):
        parent=ev(rec(1,title="2027년도 기준 중위소득 고시",source="admrul"),
                  article="별표 1",before="기준 중위소득 6,000,000원",after="기준 중위소득 6,900,000원")
        child=ev(rec(2,title="가상업무 안내"))
        x=relations.evaluate(parent,child,{"본문":"이 문서는 기준 중위소득을 설명한다."})
        self.assertIsNone(x)

    def test_different_unrelated_documents_never_link_by_keyword(self):
        p=ev(rec(1,title="시설관리 기준"))
        c=ev(rec(2,title="시설관리 신청규정"))
        g=relations.build_graph([p],[c],{("law",c["stable_id"],c["serial"]):
              {"제1조":"시설을 관리하고 시설 업무를 정한다."}})
        self.assertEqual(g["statistics"]["actual_dependencies"],0)

class VerifiedEvents(unittest.TestCase):
    def test_amendment_is_same_official_stable_id_and_prior_serial(self):
        current=rec(1,serial="19")
        prior=rec(1,serial="17",day="2026-09-07")
        def load(r):
            return {"제3조":"가상항공공단은 신청서를 "+("10" if r["serial"]=="19" else "30")+"일 이내 처리한다."}
        e,clauses=event.inspect(current,[prior],load=load,history=lambda r,rr:prior)
        self.assertEqual(e["verification"],"verified_changed_clauses")
        self.assertTrue(e["comparison"]["same_stable_id"])
        self.assertEqual(e["comparison"]["before_serial"],"17")
        self.assertTrue(e["excerpts"])
        self.assertEqual(e["actors"][0]["agency"],"가상항공공단")

    def test_no_previous_version_is_not_fake_changed_amount(self):
        current=rec(1)
        e,clauses=event.inspect(current,[],load=lambda r:{"제1조":"지원금은 120만원이다."},
            history=lambda r,rr:None,annual=lambda r:None)
        self.assertEqual(e["verification"],"official_record_only")
        self.assertEqual(e["excerpts"],[])
        self.assertEqual(e["actors"],[])

    def test_official_pure_repeal_is_not_a_live_duty(self):
        r=rec(1);r["revision"]="폐지"
        e,clauses=event.inspect(r,load=lambda r:{"제1조":"가상청장은 업무를 수행한다."})
        self.assertEqual(e["verification"],"verified_repeal_notice")
        self.assertEqual(e["actors"],[])
        self.assertEqual(clauses,{})

    def test_same_promulgation_groups_many_target_laws(self):
        one=ev(rec(1,title="가상위원회 직제",number="655"))
        two=ev(rec(2,title="가상소속청 직제",number="655"))
        other=ev(rec(3,title="가상지원법",number="908"))
        for x in (one,two,other):
            x["verification"]="verified_changed_clauses"
            x["actors"]=[]
        groups=event.cluster_promulgations([one,two,other])
        self.assertEqual(len(groups),2)
        self.assertEqual([x["source_count"] for x in groups],[2,1])
        self.assertTrue(groups[0]["official_common_promulgation"])

if __name__=="__main__":unittest.main()
