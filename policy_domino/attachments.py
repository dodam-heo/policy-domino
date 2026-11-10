"""Optional extraction of source annexes from the official law.go.kr download API.

A readable PDF/HWPX annex becomes source evidence. Unsupported or scanned
attachments remain explicitly unresolved; text is never invented.
"""
from __future__ import annotations
from io import BytesIO
from urllib.parse import urljoin,urlsplit
from urllib.request import Request,urlopen
import os
import zipfile
import xml.etree.ElementTree as ET

BASE="https://www.law.go.kr"
MAX_BYTES=8_000_000
MAX_TEXT=11_000

def official_url(raw: str) -> str:
    value=str(raw or "").strip()
    if not value:
        return ""
    url=urljoin(BASE+"/",value)
    parts=urlsplit(url)
    if (parts.scheme!="https" or parts.hostname not in
        ("law.go.kr","www.law.go.kr") or
        not parts.path.startswith(("/LSW/","/DRF/")) or
        parts.username or parts.password):
        return ""
    return url

def read_hwpx(payload: bytes) -> str:
    """Extract text nodes from HWPX's XML sections without executing macros."""
    pieces=[]
    total=0
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        names=sorted(n for n in archive.namelist()
                     if n.startswith("Contents/section") and n.endswith(".xml"))
        for name in names[:25]:
            info=archive.getinfo(name)
            if info.file_size>2_000_000 or total+info.file_size>10_000_000:
                break
            total+=info.file_size
            root=ET.fromstring(archive.read(name))
            for element in root.iter():
                if element.tag.split("}")[-1] in ("t","text"):
                    value="".join(element.itertext()).strip()
                    if value:
                        pieces.append(value)
                        if sum(len(x) for x in pieces)>MAX_TEXT:
                            return " ".join(pieces)[:MAX_TEXT]
    return " ".join(pieces)[:MAX_TEXT]

def extract(raw_url: str, opener=urlopen) -> str:
    url=official_url(raw_url)
    if not url:
        return ""
    req=Request(url,headers={"User-Agent":"PolicyDomino/official-annex-reader"})
    with opener(req,timeout=14) as response:
        final=urlsplit(response.geturl())
        if final.scheme!="https" or final.hostname not in ("law.go.kr","www.law.go.kr"):
            return ""
        payload=response.read(MAX_BYTES+1)
    if len(payload)>MAX_BYTES:
        return ""
    if payload.startswith(b"%PDF-"):
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""
        reader=PdfReader(BytesIO(payload),strict=False)
        parts=[p.extract_text() or "" for p in reader.pages[:25]]
        return " ".join(parts)[:MAX_TEXT].strip()
    if zipfile.is_zipfile(BytesIO(payload)):
        return read_hwpx(payload).strip()
    # Binary HWP, image-only scans and invalid downloads cannot be declared
    # verified text without a separate trusted extractor.
    return ""

def enabled() -> bool:
    return os.getenv("PD_FETCH_OFFICIAL_ATTACHMENTS","false").lower()=="true"
