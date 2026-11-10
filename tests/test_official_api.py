"""Contract tests for the only active official source adapter."""
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from policy_domino import official_api as api


class OfficialApiTests(unittest.TestCase):
    def test_never_fall_back_to_embedded_api_credentials(self):
        with patch.dict("os.environ", {"LAW_OC": ""}):
            with self.assertRaisesRegex(RuntimeError, "LAW_OC"):
                api.request("law")

    def test_official_law_index_record(self):
        node = ET.fromstring("""
          <law><법령명한글>가상 지원법</법령명한글>
          <법령ID>123</법령ID><법령일련번호>456</법령일련번호>
          <공포일자>20261109</공포일자><공포번호>19</공포번호>
          <제개정구분명>일부개정</제개정구분명><법령구분명>법률</법령구분명>
          </law>""")
        record = api.row_of(node, "law")
        self.assertEqual(record["stable_id"], "123")
        self.assertEqual(record["published_at"], "2026-11-09")

    def test_cannot_treat_missing_official_id_as_source_event(self):
        node = ET.fromstring("<law><법령명한글>제목</법령명한글><공포일자>20261109</공포일자></law>")
        self.assertIsNone(api.row_of(node, "law"))

    def test_change_pairs_are_source_sourced(self):
        record={"source":"law","stable_id":"123","serial":"456",
                "url":"https://www.law.go.kr/법령/가상"}
        diffs=api.compare({"제5조":"지급액 100만원"},
                          {"제5조":"지급액 200만원"},record)
        self.assertEqual(len(diffs),1)
        self.assertEqual(diffs[0]["before"],"지급액 100만원")
        self.assertEqual(diffs[0]["after"],"지급액 200만원")
        self.assertTrue(diffs[0]["verified"])

    def test_nested_provision_is_not_duplicated(self):
        xml=ET.fromstring("""
        <root><조문단위>
          <조문번호>5</조문번호>
          <조문내용>제5조(지원) <항내용>① 기관은 접수한다.</항내용></조문내용>
        </조문단위></root>""")
        with patch.object(api,"request",return_value=xml):
            result=api.read_clauses({"source":"law","serial":"456"})
        self.assertIn("제5조",result)
        self.assertEqual(result["제5조"].count("기관은 접수한다."),1)


if __name__=="__main__":
    unittest.main()
