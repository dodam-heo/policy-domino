"""Official annex extraction is bounded and never manufactures missing text."""
import io
import os
import unittest
import zipfile
import xml.etree.ElementTree as ET
from unittest.mock import patch
from policy_domino import attachments,official_api


class OfficialAnnexContract(unittest.TestCase):
    def test_rejects_untrusted_links_and_accepts_legal_download(self):
        self.assertEqual(attachments.official_url("https://evil.example/LSW/flDownload.do"),"")
        self.assertEqual(attachments.official_url("javascript:alert(1)"),"")
        self.assertEqual(attachments.official_url("/LSW/flDownload.do?flSeq=123"),
                         "https://www.law.go.kr/LSW/flDownload.do?flSeq=123")

    def test_reads_hwpx_xml_without_binary_or_name_shortcuts(self):
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,"w") as archive:
            archive.writestr("Contents/section0.xml",
                '<hp:section xmlns:hp="urn:sample"><hp:t>임의의 적용기준 250만원</hp:t></hp:section>')
        self.assertIn("250만원",attachments.read_hwpx(raw.getvalue()))

    def test_official_annex_link_persists_when_content_is_unreadable(self):
        root=ET.fromstring("""<행정규칙>
            <조문단위><조문번호>1</조문번호><조문내용>기준은 별표에 따른다.</조문내용></조문단위>
            <별표단위><별표번호>2</별표번호><별표제목>기준표</별표제목>
            <별표서식PDF파일링크>/LSW/flDownload.do?flSeq=123</별표서식PDF파일링크>
            </별표단위></행정규칙>""")
        with patch.object(official_api,"request",return_value=root),patch.dict(
             os.environ,{"PD_FETCH_OFFICIAL_ATTACHMENTS":"false"}):
            result=official_api.read_clauses({"source":"admrul","serial":"100"})
        self.assertIn("제1조",result)
        self.assertEqual(len(result.unresolved_attachments),1)
        self.assertEqual(result.unresolved_attachments[0]["label"],"별표 2")
        self.assertIn("law.go.kr",result.unresolved_attachments[0]["url"])

if __name__=="__main__":
    unittest.main()
