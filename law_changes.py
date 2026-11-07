"""Enacted and promulgated law feed separate from generic RSS events.

Uses the official MOLEG open-data API when authorized via LAW_OC.
In its absence, displays only official agency legal-regulation postings
that explicitly state a completed enactment/amendment; proposal and news
items never enter the main new/modified law tab.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode, urljoin, quote
import os, re, urllib.request, xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

EXCLUDE=re.compile(r"입법예고|행정예고|의견수렴|개정안|제정안|공청회|개정\(안\)|제정\(안\)|예고안|재공고|국무회의\s*통과|개정\s*추진|제정\s*추진|개정\s*예정|검토중")
COMPLETED=re.compile(r"일부개정|전부개정|개정고시|개정\s*고시|개정\s*공고|일부\s*개정|전부\s*개정|일괄개정|제정\b|폐지\b|규정\s*개정")
REGULATION_CATS=("훈령","예규","고시","지침","법령공고")
VALID_CHANGE=("제정","일부개정","전부개정","일괄개정","폐지","폐지제정","타법개정")
MAX_ITEMS=100

def parse_law_api(raw):
    root=ET.fromstring(raw)
    def val(node,name):
        child=next((x for x in node if x.tag.split("}")[-1]==name),None)
        return ((child.text or "").strip() if child is not None else "")
    law_nodes=[n for n in root.iter() if n.tag.split("}")[-1]=="law"]
    output=[]
    for law in law_nodes:
        name=val(law,"법령명한글")
        day=val(law,"공포일자")
        typ=val(law,"제개정구분명")
        if not name or not re.fullmatch(r"\d{8}",day) or not any(t in typ for t in VALID_CHANGE):
            continue
        doc_id=val(law,"법령일련번호")
        detail=val(law,"법령상세링크")
        url=urljoin("https://www.law.go.kr",detail) if detail else "https://www.law.go.kr/법령/"+quote(name)
        date=datetime.strptime(day,"%Y%m%d").replace(tzinfo=timezone.utc).isoformat()
        eff=val(law,"시행일자")
        output.append(dict(title=name,url=url,source=val(law,"소관부처명") or "법제처 국가법령정보센터",
                    category=val(law,"법령구분명") or "법령",law_type=val(law,"법령구분명") or "법령",
                    change_type=typ,stage="공포 법령",published_at=date,promulgated_at=date,
                    promulgation_date=day,effective_date=eff,promulgation_number=val(law,"공포번호"),
                    law_id=val(law,"법령ID"),document_number=doc_id,
                    date_basis="법제처 공포일",body="",attachments=[]))
    return sorted(output,key=lambda item:(item["promulgation_date"],item["promulgation_number"]),reverse=True)[:MAX_ITEMS]

def from_public_law_table():
    """Official public Recent Promulgated Laws page; no API key needed.
    Only accept rows containing a law kind, promulgation number and date.
    """
    source_url="https://www.law.go.kr/nwRvsLsPop.do?chrIdx=0&cptOfi=&lsKndCd=&lsNm=&p_epubdt=&p_spubdt=&searchType=&sortIdx=0&pg=1"
    request=urllib.request.Request(source_url,headers={
        "User-Agent":"Mozilla/5.0 (compatible; PolicyDomino/3.1)",
        "Accept":"text/html,application/xhtml+xml",
        "Referer":"https://www.law.go.kr/"})
    with urllib.request.urlopen(request,timeout=25) as response:
        raw=response.read(2700000)
    soup=BeautifulSoup(raw,"html.parser")
    output=[]
    for tr in soup.select("tr"):
        tds=tr.find_all("td",recursive=False)
        if len(tds)<7:continue
        vals=[re.sub(r"\s+"," ",td.get_text(" ",strip=True)).strip() for td in tds]
        # Some pages add a checkbox/no. column. Detect date and revise metadata from right edge.
        for idx in range(max(0,len(vals)-3),len(vals)-1):
            if re.fullmatch(r"\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?",vals[idx]):
                promulgated=vals[idx]
                prefix=vals[:idx]
                if len(prefix)<5:continue
                # Common table columns: number, title, ministry, change kind, law type, promulgation number
                law_name,agency,ctype,ltype,number=prefix[-5:]
                if not re.search(r"제정|개정|폐지",ctype):continue
                if not re.search(r"법률|령|규칙|헌법|부령",ltype):continue
                day=re.sub(r"\D","",promulgated)
                if len(day)!=8:continue
                eff=vals[idx+1] if idx+1<len(vals) else ""
                stamp=datetime.strptime(day,"%Y%m%d").replace(tzinfo=timezone.utc).isoformat()
                output.append(dict(title=law_name,source=agency or "법제처 국가법령정보센터",
                    url="https://www.law.go.kr/법령/"+quote(law_name),body="",category=ltype,
                    law_type=ltype,change_type=ctype,stage="공포 법령",
                    promulgation_date=day,promulgated_at=stamp,published_at=stamp,
                    promulgation_number=number,effective_date=re.sub(r"\D","",eff),
                    date_basis="법제처 최근공포법령 공포일",attachments=[]))
                break
    dedup={}
    for law in output:
        dedup[(law["title"],law["promulgation_date"],law["promulgation_number"])]=law
    return sorted(dedup.values(),key=lambda v:(v["promulgation_date"],v["promulgation_number"]),reverse=True)[:MAX_ITEMS]


def from_agency_postings(items):
    """Fallback only for explicit completed formal administrative-rule notices."""
    candidates=[]
    for item in items:
        title=item.get("title","")
        category=item.get("category","")
        if not any(c in category for c in REGULATION_CATS):
            continue
        if EXCLUDE.search(title) or not COMPLETED.search(title):
            continue
        if re.search(r"공고|보도자료|뉴스",category) and not re.search(r"일부개정\s*고시|전부개정\s*고시|개정\s*고시|규정\s*개정\s*공고",title):
            continue
        typ="폐지" if "폐지" in title else "제정" if "제정" in title else "전부개정" if "전부개정" in title else "일부개정"
        p={**item,
           "law_type":"행정규칙·고시" if re.search("고시|훈령|예규",category) else "기관 규정",
           "change_type":typ,
           "date_basis":"소관기관 공식 게시일",
           "stage":"기관 공식 개정·제정 게시",
           "promulgated_at":None}
        p.pop("detected_at",None)
        candidates.append(p)
    candidates.sort(key=lambda x:x.get("published_at") or "",reverse=True)
    return candidates[:MAX_ITEMS]

def get_law_changes(items,seen=None):
    seen=seen or {}
    key=os.getenv("LAW_OC","").strip()
    failure=None
    verified=[]
    if key:
        query=urlencode({"OC":key,"target":"law","type":"XML","sort":"ddes","display":100})
        url="https://www.law.go.kr/DRF/lawSearch.do?"+query
        req=urllib.request.Request(url,headers={"User-Agent":"PolicyDomino/3.0 (public legal records)"})
        try:
            with urllib.request.urlopen(req,timeout=25) as response:
                raw=response.read(2500000)
            verified=parse_law_api(raw)
            if not verified:failure="법제처 인증·응답을 확인할 수 없거나 최신 공포 내역이 비어 있습니다."
        except Exception as e:
            failure="국가법령정보 API 조회 실패: "+type(e).__name__
    else:
        failure="법제처 Open API 인증 미설정 — 공포 법령 목록 대신 공식 기관 개정 고시를 표시합니다."
    if not verified:
        try:
            verified=from_public_law_table()
            if verified:failure=None
        except Exception as e:
            failure=(failure or "")+" | 공개 최근공포법령 목록 수집 실패: "+type(e).__name__
    fallback=from_agency_postings(items)
    records=verified+fallback
    # Ensure the same agency posting is not listed twice.
    unique={}
    for item in records:
        unique.setdefault(item["url"],item)
    records=list(unique.values())
    records.sort(key=lambda x:(x.get("promulgated_at") or x.get("published_at") or "",x.get("title") or ""),reverse=True)
    latest={}
    baseline=not bool(seen)
    for entry in records:
        k=entry["url"]
        signature=(entry.get("promulgation_number") or "")+"|"+(entry.get("change_type") or "")+"|"+(entry.get("published_at") or "")
        entry["change_detected"]=("기준선" if baseline and k not in seen else "신규 감지" if k not in seen else "수정 감지" if seen[k]!=signature else "기존")
        latest[k]=signature
    return records[:MAX_ITEMS],latest,{"authority":("법제처 최근공포법령" if verified else "공식 부처 행정규칙·고시 게시"),"api_connected":bool(verified),"api_note":failure,"law_count":len(verified),"agency_count":len(fallback)}
