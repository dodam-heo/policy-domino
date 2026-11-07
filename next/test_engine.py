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
    def test_unique_per_action_role(self):
        changed={"id":"d1","article":"제5조","before":"신청자격 20세","after":"신청자격 18세","type":"변경"}
        ids=[r["id"] for r in engine.actions_from_diff(self.law,[changed])]
        self.assertEqual(len(ids),len(set(ids)))

if __name__=="__main__":unittest.main()
