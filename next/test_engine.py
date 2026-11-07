import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from next import engine

class ChangeDetection(unittest.TestCase):
    def setUp(self):
        self.law={"id":"004200","mst":"308100","title":"가상 지원 기준법","promulgated_at":"2026-11-06","promulgation_number":"12345","effective_date":"2027-01-01","revision":"일부개정","ministry":"가상 담당부처","law_type":"법률","url":"https://www.law.go.kr/법령/example"}
    def test_structured_official_record(self):
        import xml.etree.ElementTree as ET
        raw=ET.fromstring("<law><법령명한글>가상 지원 기준법</법령명한글><법령ID>004200</법령ID><법령일련번호>308100</법령일련번호><공포일자>20261106</공포일자><제개정구분명>일부개정</제개정구분명><소관부처명>가상 담당부처</소관부처명></law>")
        row=engine.record_from_law(raw)
        self.assertEqual(row["promulgated_at"],"2026-11-06")
        self.assertEqual(row["revision"],"일부개정")
    def test_detect_article_changes_not_new_posts(self):
        old={"제5조":{"heading":"신청자격","text":"시장이 20세 이상인 사람을 심사한다."}}
        new={"제5조":{"heading":"신청자격","text":"시장이 18세 이상인 사람을 심사한다."}}
        differences=engine.classify_differences(old,new,self.law)
        self.assertEqual(len(differences),1)
        self.assertEqual(differences[0]["before"],old["제5조"]["text"])
        self.assertEqual(differences[0]["after"],new["제5조"]["text"])
        self.assertEqual(engine.classify_differences(old,old,self.law),[])
    def test_infer_operational_tasks_and_local_government_role(self):
        diff={"id":"d1","article":"제5조","before":"시장은 신청자격 20세 이상인 사람을 심사한다.","after":"시장·군수·구청장은 신청자격 18세 이상인 사람을 심사한다.","type":"변경"}
        actions=engine.actions_from_diff(self.law,[diff])
        self.assertGreater(len(actions),0)
        self.assertTrue(any(t["agency"]=="시장·군수·구청장" for t in actions))
        self.assertTrue(all(t["status"]=="시행 예정" for t in actions))
        self.assertTrue(all(t["basis"].startswith("https://") for t in actions))
    def test_no_evidence_means_no_fabricated_task(self):
        changes=[{"id":"d1","article":"제2조","before":"가.","after":"나.","type":"변경"}]
        self.assertEqual(engine.actions_from_diff(self.law,changes),[])
    def test_public_law_date_and_deep_link(self):
        from unittest.mock import patch
        page="""<table><tr><td>1</td><td><a href="lsInfoP.do?lsiSeq=291687&amp;viewCls=lsRvsDocInfoR" title="행정안전부와 그 소속기관 직제 시행규칙 팝업으로 이동">행정안전부와 그 ...</a></td><td>행정안전부</td><td>일부개정</td><td>행정안전부령</td><td>제655호</td><td>2026. 11. 6.</td><td>2026. 11. 6.</td></tr></table>"""
        with patch.object(engine,"download",return_value=page.encode("utf-8")):
            laws=engine.public_law_list()
        self.assertEqual(len(laws),1)
        self.assertEqual(laws[0]["promulgated_at"],"2026-11-06")
        self.assertEqual(laws[0]["title"],"행정안전부와 그 소속기관 직제 시행규칙")
        self.assertIn("lsiSeq=291687",laws[0]["url"])

    def test_public_amendment_produces_source_backed_org_action(self):
        from unittest.mock import patch
        law={**self.law,"url":"https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=291687","title":"가상기관 직제 시행규칙"}
        text="""<html><body>【제정·개정이유】정원 13명을 일반직에서 전문직으로 전환한다.【제정·개정문】
        가상기관 직제 시행규칙을 다음과 같이 개정한다. 제54조 중 "정원 10명"을 "정원 13명"으로 한다.
        부칙 제1조 이 규칙은 공포한 날부터 시행한다.</body></html>"""
        with patch.object(engine,"download",return_value=text.encode("utf-8")):
            material=engine.public_amendment(law)
        diffs=engine.public_amendment_diffs(law,material)
        self.assertTrue(diffs)
        self.assertEqual(diffs[0]["before"],"정원 10명")
        self.assertEqual(diffs[0]["after"],"정원 13명")
        tasks=engine.actions_from_diff(law,diffs)
        self.assertTrue(any(t["work"]=="조직·정원·직무 배정" for t in tasks))
        self.assertTrue(all(t["basis"].endswith("chrClsCd=010202") for t in tasks))

    def test_no_unrelated_licensing_or_public_agency_from_org_chart(self):
        law={**self.law,"title":"가상기관 직제 시행규칙"}
        diff={"id":"org-1","article":"별표 4","before":"정원 30","after":"별표 중 항공사무관 30을 20으로, 재산심사과장을 신설한다.","type":"개정","context":"전문직공무원 정원 조정"}
        tasks=engine.actions_from_diff(law,[diff])
        self.assertTrue(tasks)
        self.assertTrue(all(task["work"]=="조직·정원·직무 배정" for task in tasks))
        self.assertFalse(any(task["agency"]=="공공기관" for task in tasks))

    def test_unique_per_action_role(self):
        changed={"id":"d1","article":"제5조","before":"신청자격 20세","after":"신청자격 18세","type":"변경"}
        ids=[r["id"] for r in engine.actions_from_diff(self.law,[changed])]
        self.assertEqual(len(ids),len(set(ids)))

if __name__=="__main__":unittest.main()
