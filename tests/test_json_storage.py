"""Public dataset writes remain complete, atomic, and GitHub-size-safe."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from policy_domino.engine.json_storage import atomic_json


class AtomicJsonPublicationTests(unittest.TestCase):
    def test_public_compaction_preserves_every_source_record(self):
        document={
            "events":[{"id":str(i),"official_text":"조문과 근거는 생략할 수 없습니다.","changes":[{"before":"변경 전","after":"변경 후"}]}
                      for i in range(65)],
            "metadata":{"verified":True,"null":None,"numbers":[1,2,3]},
        }
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/"data.json"
            size=atomic_json(target,document,public=True)
            raw=target.read_bytes()
            self.assertEqual(size,len(raw))
            self.assertEqual(json.loads(raw),document)
            self.assertNotIn(b"\n",raw)
            pretty=len(json.dumps(document,ensure_ascii=False,indent=2).encode("utf-8"))
            self.assertLess(size,pretty)
            self.assertFalse(target.with_name("data.json.tmp").exists())

    def test_oversized_published_file_is_rejected_without_destroying_prior_data(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/"data.json"
            target.write_text('{"safe":true}',encoding="utf-8")
            with patch("policy_domino.engine.json_storage.PUBLIC_MAX_BYTES",60):
                with self.assertRaisesRegex(ValueError,"exceeds"):
                    atomic_json(target,{"text":"가나다"*100},public=True)
            self.assertEqual(target.read_text(encoding="utf-8"),'{"safe":true}')
            self.assertFalse(target.with_name("data.json.tmp").exists())

    def test_source_state_remains_complete_even_when_public_blob_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            original={"catalog":{"law:1":{"title":"행정규칙","body":"고시 원문"}}}
            target=Path(temp)/"state.json"
            atomic_json(target,original,public=False)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")),original)
            self.assertIn("\n",target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
