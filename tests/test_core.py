import unittest
import watch

class PolicyDominoTests(unittest.TestCase):
    def test_korean_feed_timestamp(self):
        self.assertEqual(watch.date_iso("20261106153120"),"2026-11-06T06:31:20+00:00")
    def test_naive_local_timestamp(self):
        self.assertEqual(watch.date_iso("2026-11-06T11:06:56"),"2026-11-06T02:06:56+00:00")
    def test_rss_publication_date_and_link(self):
        raw=b'<rss><channel><item><title>Title A</title><link>https://www.mss.go.kr/article</link><pubDate>20261106153120</pubDate></item></channel></rss>'
        posts=watch.parse(raw,"기관","보도")
        self.assertEqual(posts[0]["published_at"],"2026-11-06T06:31:20+00:00")
    def test_proposal_not_confirmed(self):
        self.assertEqual(watch.stage("시행령 일부개정령안 입법예고","법령"),"예고·심의 단계")
    def test_unrelated_same_word_not_linked(self):
        s=watch.similarity("청주시 임용시험 시행계획 공고","위성정보활용 시행계획")
        self.assertEqual(s,0)
    def test_qualifying_numeric_delta(self):
        changes=watch.deltas("현행 2,078,316원에서 2,217,563원으로 변경")
        self.assertTrue(any(x["before"]=="2,078,316원" and x["after"]=="2,217,563원" for x in changes))

if __name__=="__main__":
    unittest.main()
