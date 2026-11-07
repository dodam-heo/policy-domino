import unittest
from unittest import mock
from impact_scanner import find_explicit_deltas, find_text_deltas, evaluate_target, is_historical_record, scan, distinctive

class EvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.policy={"title":"2027년 기준 중위소득 및 생계급여 기준 변경",
                     "url":"https://www.mohw.go.kr/change",
                     "source":"보건복지부",
                     "effective_date":"20270101",
                     "body":"종전 2,078,316원 → 2,217,563원"}
        self.delta=find_explicit_deltas(self.policy["body"])[0]

    def test_explicit_delta_is_not_guessed(self):
        d=find_explicit_deltas("종전 2,078,316원 → 2,217,563원")
        self.assertEqual((d[0]["before"],d[0]["after"]),("2,078,316원","2,217,563원"))
        self.assertEqual(find_explicit_deltas("2027년 생계급여가 확대됩니다"),[])

    def test_stale_current_year_page_is_flagged_for_review(self):
        target={"title":"2027년 생계급여 4인 기준 안내",
                "url":"https://www.example.go.kr/welfare/2027",
                "source":"시청"}
        def inspect(url):
            return "2027년 생계급여와 기준 중위소득 4인 가구 2,078,316원",[],[(1,"2027년 생계급여 2,078,316원")]
        found=evaluate_target(self.policy,self.delta,target,inspect)
        self.assertEqual(found["before"],"2,078,316원")
        self.assertEqual(found["after"],"2,217,563원")
        self.assertEqual(found["location"],"본문 1번째 블록")
        self.assertTrue(found["review_required"])

    def test_explicit_wording_change(self):
        changes=find_text_deltas("종전 ‘가구당 20일’에서 ‘가구당 30일’로 개정")
        self.assertEqual(len(changes),1)
        self.assertEqual((changes[0]["before"],changes[0]["after"]),("가구당 20일","가구당 30일"))

    def test_2026_archive_is_not_mislabeled(self):
        target={"title":"2026년 생계급여 안내",
                "url":"https://www.example.go.kr/welfare/2026"}
        def inspect(url):return "2026년 기준 중위소득 생계급여 2,078,316원",[],[]
        found=evaluate_target(self.policy,self.delta,target,inspect)
        self.assertEqual(found["status"],"과거 연도 자료 보존")
        self.assertFalse(found["review_required"])

    def test_current_new_value_is_not_stale(self):
        target={"title":"2027년 생계급여 안내","url":"https://www.example.go.kr/2027"}
        def inspect(url):return "2027년 기준 중위소득 생계급여 2,217,563원",[],[]
        self.assertIsNone(evaluate_target(self.policy,self.delta,target,inspect))

    def test_only_search_results_with_old_value_become_findings(self):
        target={"title":"2027년 생계급여","url":"https://www.example.go.kr/welfare/2027","source":"서울"}
        def inspect(url):
            if url==self.policy["url"]:
                return self.policy["body"]+" 기준 중위소득",[],[]
            return "2027년 기준 중위소득 생계급여 2,078,316원",[],[(1,"2,078,316원")]
        # Feed-derived candidate is used without a search service.
        with mock.patch("impact_scanner.rss_search",return_value=[]):
            findings,queue,metrics=scan([self.policy],[target],inspect,max_policy=1)
        self.assertEqual(len(findings),1)
        self.assertEqual(metrics["policies_examined"],1)

if __name__=="__main__":unittest.main()
