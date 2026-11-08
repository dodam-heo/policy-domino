import unittest
import xml.etree.ElementTree as ET
from v4 import official_links as o

class DelegatedProvisionEvidence(unittest.TestCase):
    def test_an_actual_changed_article_returns_only_its_official_targets(self):
        xml=ET.fromstring("""<root>
          <위임><조문번호>003500</조문번호><위임구분>위임행정규칙</위임구분>
            <위임행정규칙일련번호>56008</위임행정규칙일련번호>
            <위임행정규칙제목>가상 해상기준 고시</위임행정규칙제목>
            <라인텍스트>제35조제1항에 따른 세부기준</라인텍스트>
          </위임>
          <위임><조문번호>003600</조문번호><위임구분>위임법령</위임구분>
            <위임법령일련번호>1132</위임법령일련번호>
            <위임법령제목>가상 법령 시행령</위임법령제목>
          </위임>
        </root>""")
        law={"source":"law","title":"가상 지원법","stable_id":"1122"}
        res=o.delegated_changed_articles(law,["제35조"],
             request=lambda target,**kwargs:xml)
        self.assertEqual(len(res["links"]),1)
        link=res["links"][0]
        self.assertEqual(link["title"],"가상 해상기준 고시")
        self.assertEqual(link["source_article"],"제35조")
        self.assertFalse(link["requires_amendment_verified"])
        self.assertFalse(link["implementation_verified"])

    def test_no_title_keyword_is_ever_used_to_infer_delegation(self):
        xml=ET.fromstring("""<root><위임>
           <조문번호>003600</조문번호>
           <위임행정규칙일련번호>203</위임행정규칙일련번호>
           <위임행정규칙제목>가상 지원법과 관련된 고시</위임행정규칙제목>
           </위임></root>""")
        law={"source":"law","title":"가상 지원법","stable_id":"1222"}
        got=o.delegated_changed_articles(law,["제35조"],
                  request=lambda target,**kwargs:xml)
        self.assertEqual(got["links"],[])

    def test_supports_legislation_local_rules_and_public_body_standards(self):
        xml=ET.fromstring("""<root><위임><조문번호>000800</조문번호>
           <위임법령일련번호>11</위임법령일련번호>
           <위임법령제목>가상 시행령</위임법령제목>
           <위임자치법규일련번호>22</위임자치법규일련번호>
           <위임자치법규제목>가상시 시행조례</위임자치법규제목>
           <위임규정일련번호>33</위임규정일련번호>
           <위임규정제목>가상 공공기관 운영규정</위임규정제목>
           </위임></root>""")
        law={"source":"law","title":"가상 지원법","stable_id":"1222"}
        got=o.delegated_changed_articles(law,["제8조"],
                  request=lambda target,**kwargs:xml)
        self.assertEqual(len(got["links"]),3)
        self.assertEqual({x["source"] for x in got["links"]},
                         {"law","ordin","public_rule"})
        self.assertTrue(all(x["requires_amendment_verified"] is False
                            for x in got["links"]))

if __name__=="__main__":unittest.main()
