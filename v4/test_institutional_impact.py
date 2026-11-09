import unittest
from v4 import institutional_impact as d
from v4 import classic_bridge as bridge

def change(field="가상소득기준",before="1,234,567원",after="1,345,678원"):
    return {"event_id":"event-x","title":"새 기준 개정","effective_date":"2027-01-01",
        "presentation_source":"v4_official_source","impact_priority":1,
        "article_differences":[{"article":field,"before":before,"after":after,
          "source_url":"https://www.law.go.kr/rule123"}]}

PAGE='''<html><head><title>가상지원사업 신청 및 자격 안내 | 가상문화재단</title>
<meta property="og:site_name" content="가상문화재단"></head>
<body><h1>가상지원사업 신청 및 자격 안내</h1>
<p>2026년 신청 대상자 선정시 가상소득기준 1,234,567원 기준표를 적용하여 자격을 심사합니다.</p></body></html>'''

class Discovery(unittest.TestCase):
    def test_search_url_parser_handles_web_engine_redirects(self):
        h='<a href="/url?q=https%3A%2F%2Fagency.example.go.kr%2Fpage&amp;sa=U">page</a>'
        self.assertEqual(d._search_leads(h),["https://agency.example.go.kr/page"])

    def test_broad_discovery_checks_page_not_search_words(self):
        q=[]
        def search(query):
            q.append(query)
            return [] if "1,234,567" in query else ["https://open.example.go.kr/program"]
        hits,health=d.discover([change()],search=search,fetch=lambda u:PAGE)
        self.assertEqual(len(q),2)
        self.assertEqual(len(hits),1)
        self.assertEqual(health["matched"],1)

    def test_new_agency_from_discovered_page_not_registry(self):
        e=change()
        hits,health=d.discover([e],search=lambda q:["https://open.example.go.kr/a"],
          fetch=lambda url:PAGE)
        self.assertEqual(health["matched"],1)
        self.assertEqual(hits[0]["agency"],"가상문화재단")
        self.assertIn("가상지원사업",hits[0]["service"])
        self.assertEqual(hits[0]["discovery_method"],"live_public_search_and_page_validation")
        self.assertFalse(hits[0]["institutional_implementation_verified"])
        actions,added=d.connect([e],[],hits)
        self.assertEqual(len(added),1)

    def test_private_site_address_is_not_public_agency_evidence(self):
        html=PAGE.replace('content="가상문화재단"','content="가상사업포털"').replace(
          '<title>가상지원사업 신청 및 자격 안내 | 가상문화재단</title>',
          '<title>가상지원사업 신청 및 자격 안내 | 가상사업포털</title>')
        html=html.replace('</body>','<footer>가상특별시 가상구 새길 12 대표전화 120 © Corp</footer></body>')
        found,_=d.discover([change()],search=lambda q:["https://private.example.or.kr/article"],
                            fetch=lambda u:html)
        self.assertFalse(found)

    def test_municipal_official_footer_attribution(self):
        html=PAGE.replace('content="가상문화재단"','content="가상서비스포털"').replace(
          '<title>가상지원사업 신청 및 자격 안내 | 가상문화재단</title>',
          '<title>가상지원사업 신청 및 자격 안내 | 가상서비스포털</title>')
        html=html.replace('</body>', '<footer>가상특별시 가상구 새길 12 대표전화: 120 © Metropolitan Government</footer></body>')
        found,_=d.discover([change()],search=lambda q:["https://portal.example.go.kr/service"],
                           fetch=lambda u:html)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["agency"],"가상특별시")

    def test_law_change_yields_source_only_work_review_not_fabricated_agency(self):
        e=change(field="제7조",before="제7조(지원 범위) 검사 비용을 지원한다.",
                after="제7조(지원 범위) 검사 및 치료 비용을 지원한다.")
        reviews=bridge.source_review_candidates(e)
        self.assertEqual(len(reviews),1)
        self.assertEqual(reviews[0]["work_type"],"지원·지급 범위")
        self.assertFalse(reviews[0]["institution_verified"])
        self.assertNotIn("agency",reviews[0])
        e["presentation_source"]="official_index_pending"
        self.assertEqual(bridge.source_review_candidates(e),[])

    def test_registry_style_manual_item_never_enters(self):
        e=change();manual={"event_id":"event-x","agency":"가상재단","work":"가상 업무",
                               "article":"가상소득기준","agency_basis":"https://sample.go.kr"}
        self.assertEqual(d.connect([e],[],[manual]),([],[]))

    def test_source_and_old_amount_required(self):
        e=change()
        for p in (PAGE.replace("1,234,567","1,333,333"),
                  PAGE.replace("가상소득기준","전혀다른기준"),
                  PAGE.replace("2026","2025"),
                  PAGE.replace("가상문화재단","가상장난감회사"),
                  PAGE.replace("가상지원사업 신청 및 자격 안내","정부 정책 보도자료")):
            found,_=d.discover([e],search=lambda q:["https://example.go.kr/a"],
                                fetch=lambda u:p)
            self.assertEqual(found,[])
    def test_search_lead_alone_not_evidence(self):
        e=change()
        found,health=d.discover([e],search=lambda q:["https://example.go.kr/a"],
                                fetch=lambda u: (_ for _ in ()).throw(OSError("blocked")))
        self.assertFalse(found)
        self.assertEqual(health["errors"],1)
    def test_non_official_result_not_accepted(self):
        found,_=d.discover([change()],search=lambda q:["https://commercial.com/a"],
                           fetch=lambda u:PAGE)
        self.assertEqual(found,[])
    def test_no_exact_amount_no_fallback_to_keywords(self):
        self.assertFalse(d.changed_fields(change(before="설명 문구",after="수정된 설명")))
        self.assertFalse(d.changed_fields(change(field="가상정책",before="100원",after="200원")))
    def test_no_live_search_on_non_numeric_event(self):
        calls=[]
        found,health=d.discover([change(before="서식 변경",after="양식 개편")],
                    search=lambda q:calls.append(q),fetch=lambda u:PAGE)
        self.assertFalse(found);self.assertFalse(calls)
        self.assertEqual(health["attempted"],0)

if __name__=="__main__":unittest.main()
