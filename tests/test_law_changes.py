import unittest
from unittest.mock import patch, Mock
from law_changes import parse_law_api, from_agency_postings, from_public_law_table, get_law_changes

class LawChangesTests(unittest.TestCase):
    def test_official_api_order_and_change_type(self):
        xml="""<LawSearch><law><법령명한글>가상의 법률</법령명한글><공포일자>20261106</공포일자><제개정구분명>일부개정</제개정구분명><법령구분명>법률</법령구분명><소관부처명>국토교통부</소관부처명><공포번호>22001</공포번호></law></LawSearch>"""
        laws=parse_law_api(xml.encode())
        self.assertEqual(laws[0]["promulgation_date"],"20261106")
        self.assertEqual(laws[0]["change_type"],"일부개정")

    def test_exclude_advance_notice(self):
        rows=[
            dict(title="여성기업지원에 관한 법률 시행령 일부개정령안 입법예고",
                 category="법령공고",published_at="2026-11-05T01:00:00+00:00",url="https://mss.go.kr/test1",source="중소벤처기업부"),
            dict(title="보건복지부 인사관리규정 일부개정",
                 category="훈령·예규·고시·지침",published_at="2026-11-06T01:00:00+00:00",url="https://mohw.go.kr/test2",source="보건복지부"),
            dict(title="부산 불꽃축제 교통 안전관리",category="보도자료",published_at="2026-11-07T01:00:00+00:00",
                 url="https://mois.go.kr/test3",source="행정안전부")
        ]
        found=from_agency_postings(rows)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["title"],"보건복지부 인사관리규정 일부개정")

    def test_official_public_table(self):
        table=b"""<html><body><table><tbody>
        <tr><td>1</td><td>가상의 법률</td><td>보건복지부</td><td>일부개정</td><td>법률</td><td>제22222호</td><td>2026. 11. 6.</td><td>2026. 12. 1.</td></tr>
        <tr><td>2</td><td>다른 법률</td><td>교육부</td><td>제정</td><td>법률</td><td>제22221호</td><td>2026. 11. 3.</td><td>2027. 1. 1.</td></tr>
        </tbody></table></body></html>"""
        response=Mock()
        response.read.return_value=table
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        with patch("urllib.request.urlopen",return_value=response):
            result=from_public_law_table()
        self.assertEqual(result[0]["promulgation_date"],"20261106")
        self.assertEqual(result[0]["title"],"가상의 법률")
        self.assertEqual(result[1]["effective_date"],"20270101")

if __name__=="__main__":unittest.main()
