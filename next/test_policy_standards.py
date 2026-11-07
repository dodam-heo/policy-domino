import unittest
from unittest.mock import patch
from next import policy_standards as p

def html_doc(text):
    return ("<html><body>"+text+"</body></html>").encode("utf-8")

class AnnualStandardsTests(unittest.TestCase):
    def test_ministry_median_and_livelihood_two_way_comparison(self):
        current=p.parse_html(html_doc(
          '2027년도 기준 중위소득 생계급여 선정기준 ’26년 1인82만 556원, '
          '4인207만 8,316원→ ’27년 1인87만 5,533원, 4인221만 7,563원 '
          '4인 가구 기준으로 올해 649만 4,738원에서 6.70% 인상된 692만 9,885원으로 결정했다.'
        ))
        values=p.median_amounts(current)
        self.assertEqual(values['중위소득:4인'],(6494738,6929885))
        self.assertEqual(values['생계급여:4인'],(2078316,2217563))

    def test_housing_tables_not_news_titles(self):
        page=p.parse_html(html_doc('<table><tr><td>금액(원/월)</td><td>1,230,834</td><td>2,015,660</td>'
            '<td>2,572,337</td><td>3,117,474</td><td>3,627,225</td><td>4,106,857</td><td>4,567,272</td></tr></table>'))
        self.assertEqual(p.housing_numbers(page)[3],3117474)

    def test_2027_policy_requires_authoritative_enacted_notice(self):
        prof=p.SOURCE_PROFILES["welfare"]
        with self.assertRaises(ValueError):
            p.valid_notices(prof,'2027년도 기준 중위소득 입법예고 중')
        self.assertTrue(p.valid_notices(prof,'[시행 2027. 1. 1.] [보건복지부고시 제2026-157호, 2026. 7. 29.]'))

    def test_effect_on_actual_income_eligibility_work(self):
        prof=p.SOURCE_PROFILES["welfare"]
        actions=p.evidence_actions(prof,'policy-example','생계급여:4인',2078316,2217563)
        self.assertEqual(len(actions),2)
        self.assertTrue(all(a['status']=='시행 예정' for a in actions))
        self.assertTrue(all(a['target_location'] for a in actions))
        self.assertEqual(actions[0]['changes'][0]['after'],'2,217,563원')

    def test_announcements_do_not_create_invented_changes(self):
        docs={"notice":p.parse_html(html_doc('2027 시행 제2026-157호')),
              "current":p.parse_html(html_doc('기준 중위소득 변경 보도')),
              "baseline":p.parse_html(html_doc('2026년 기준 중위소득 6,494,738'))}
        def fake(url,timeout=16,max_bytes=900000):
            prof=p.SOURCE_PROFILES["welfare"]
            return html_doc({"notice":'2027년 시행 보건복지부고시 제2026-157호',
               "current":'2027년 기준 중위소득 변경',
               "baseline":'2026년 기준 중위소득 6,494,738'}[next(k for k,v in prof.items() if k in ('notice','current','baseline') and v==url)])
        with patch.dict(p.SOURCE_PROFILES,{"housing":{},"education":{}}):
            events,actions,health=p.scan_policy_standards(fake,{}, {})
        self.assertFalse(events)
        self.assertFalse(actions)
        self.assertEqual(health["confirmed"],0)

if __name__=="__main__":unittest.main()
