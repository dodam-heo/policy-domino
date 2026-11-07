"""Evidence-based downstream publication impact discovery.

Input: already-detected public policy changes with authoritative source URLs.
Output: public website/document paths with literal before/after discrepancies,
not generic RSS matching and not an assertion of legal non-compliance.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse
import html, re, urllib.request
import xml.etree.ElementTree as ET

ALLOWED_DOMAINS=(".go.kr", ".or.kr", ".ac.kr", ".co.kr", ".com", ".kr")
UNITS=r"(?:원|만원|천원|%|세|명|개월|년|개|등급)?"
NUM=rf"\d[\d,]*(?:\.\d+)?{UNITS}"
IGNORED=set("일부개정 전부개정 시행령 시행규칙 고시 훈령 예규 지침 개정 제정 법률 신청 내용 지원 기준 변경 사업 공고 안내 자료 검토 개편 정책".split())
LAST_ERRORS=[]

def normalize(value):
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",value or ""))).strip()

def date_year(value):
    m=re.search(r"(20\d{2})",str(value or ""))
    return int(m.group(1)) if m else None

def distinctive(title):
    # Query with the named subject, not boilerplate legal suffixes.
    title=re.sub(r"[「」『』\[\]()]", " ", title or "")
    title=re.sub(r"(일부|전부)?개정(령)?안?|입법예고|행정예고|시행령|시행규칙|공포|확정|제정|법률|고시|공고", " ", title)
    words=[w for w in re.findall(r"[가-힣A-Za-z]{3,}",title) if w not in IGNORED]
    return " ".join(words[:5])

def norm_num(val):
    return re.sub(r"[, ]","",str(val or "")).strip()

def find_explicit_deltas(text):
    """Extract only explicit old-to-new pairs from authority text; no fabricated values."""
    matches=[]
    pat=rf"(?:현행|종전|기존|당초)?\s*({NUM})\s*(?:→|➝|->|에서)\s*(?:인상|인하|변경|확대|축소|조정|개정)?\s*({NUM})"
    for m in re.finditer(pat,text or ""):
        a,b=m.groups()
        if len(norm_num(a))<2 or norm_num(a)==norm_num(b):continue
        key=(norm_num(a),norm_num(b))
        if key not in [(x["old_key"],x["new_key"]) for x in matches]:
            matches.append({"before":a,"after":b,"old_key":key[0],"new_key":key[1],
                            "evidence":normalize(text[max(0,m.start()-85):m.end()+85])})
    return matches[:20]

def year_table_deltas(source_html):
    """Match paired rows of explicit years, only within the same HTML table."""
    try:
        from bs4 import BeautifulSoup
        soup=BeautifulSoup(source_html,"html.parser")
    except Exception:
        return []
    out=[]
    for table in soup.select("table")[:20]:
        rows=[[normalize(cell.get_text(" ",strip=True)) for cell in tr.find_all(["td","th"])]
              for tr in table.select("tr")]
        for i,row in enumerate(rows):
            yrs=[date_year(x) for x in row[:3]]
            yr=next((x for x in yrs if x and x>=2024),None)
            if not yr:continue
            for other in rows[i+1:i+5]:
                old_yr=next((date_year(x) for x in other[:3] if x),None)
                if old_yr!=yr-1 or len(other)!=len(row):continue
                label=normalize(" ".join(rows[i-1][:2])) if i else ""
                for j in range(1,len(row)):
                    new=row[j].strip()
                    old=other[j].strip()
                    if (not re.fullmatch(NUM,new) or not re.fullmatch(NUM,old)
                            or norm_num(new)==norm_num(old)):continue
                    out.append({"before":old,"after":new,"old_key":norm_num(old),
                                "new_key":norm_num(new),
                                "evidence":f"{label} {old_yr}년 {old} → {yr}년 {new}",
                                "effective_year":yr,"measure":label})
    return out[:30]

def is_public_url(url):
    try:
        p=urlparse(url)
        host=(p.hostname or "").lower()
        return p.scheme=="https" and bool(host) and not host.startswith(("localhost","127.","10.","192.168.")) and "." in host and host.endswith(ALLOWED_DOMAINS)
    except Exception:return False

def is_historical_record(title,url,text,policy):
    """Archived past-year instructions should never be labelled 'needs fixing'."""
    effective=date_year(policy.get("effective_date") or policy.get("effective_year"))
    if not effective:return False
    tokens=[str(title or ""),urlparse(url).path]
    tagged=[date_year(t) for t in tokens if date_year(t)]
    return bool(tagged) and max(tagged)<effective

def extract_hit(text,old_key):
    # Numeric display styles vary: 2,078,316원 versus 2078316원.
    cleaned=normalize(text)
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?(?:원|만원|천원|%|세|명|개월|년|개)?",cleaned):
        if norm_num(m.group(0))==old_key:
            a=max(0,m.start()-110);b=min(len(cleaned),m.end()+110)
            return cleaned[a:b]
    return ""

def contains_value(text,key):
    return bool(extract_hit(text,key))

def rss_search(query,timeout=12):
    """Search indexed public pages rather than only already-monitored RSS boards."""
    url="https://www.bing.com/search?"+urlencode({"format":"rss","q":query})
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 PolicyDomino-Research/1.0","Accept":"application/rss+xml, text/xml"})
    with urllib.request.urlopen(req,timeout=timeout) as res:
        raw=res.read(900000)
    root=ET.fromstring(raw)
    found=[]
    for item in root.findall(".//item"):
        title=normalize(item.findtext("title") or "")
        link=(item.findtext("link") or "").strip()
        if is_public_url(link) and link not in [x["url"] for x in found]:
            found.append({"title":title,"url":link,"origin":"외부 공개검색","description":normalize(item.findtext("description") or "")})
    return found[:12]

def inspect_target(url,inspect):
    body,attachments,sections=inspect(url)
    return body,attachments,sections

def evaluate_target(policy,delta,target,inspect):
    url=target.get("url","")
    if not is_public_url(url) or url==policy.get("url"):return None
    body,files,sections=inspect_target(url,inspect)
    title=target.get("title","")
    subject=distinctive(policy.get("title",""))
    if not body:return None
    # Require distinctive subject of law/policy to be visible in the inspected page.
    topic=[w for w in subject.split() if len(w)>2]
    if topic and not any(w in (title+" "+body) for w in topic):return None
    before=delta["old_key"];after=delta["new_key"]
    if not contains_value(body,before) or contains_value(body,after):return None
    record_status=("과거 연도 자료 보존" if is_historical_record(title,url,body,policy)
                   else "기존값 발견·적용 검토")
    location=next((f"본문 {i}번째 블록" for i,t in sections if contains_value(t,before)),"게시글 본문")
    proof=extract_hit(body,before)
    return {
        "policy_title":policy.get("title",""),"policy_url":policy.get("url",""),
        "policy_source":policy.get("source",""),"policy_stage":policy.get("stage",""),
        "target_source":target.get("source") or urlparse(url).hostname,
        "target_title":title,"target_url":url,"location":location,
        "before":delta["before"],"after":delta["after"],"evidence":proof,
        "policy_evidence":delta["evidence"],
        "effective_date":policy.get("effective_date",""),
        "status":record_status,"review_required":record_status!="과거 연도 자료 보존",
        "checked_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note":"공식 변경자료의 종전값과 대상 공개자료의 표시가 일치합니다. 적용시점과 페이지 용도를 확인한 후 수정하세요."
    }

def scan(policies,source_items,inspect,read_raw=None,max_policy=8):
    """Discover downstream links; only report findings supported by before/after evidence."""
    findings=[];inquiries=[];metrics={"policies_examined":0,"source_pages_read":0,
           "search_requests":0,"candidates_found":0,"target_pages_examined":0,
           "attachments_examined":0,"errors":[]}
    cache={}
    def get(url):
        if url not in cache:cache[url]=inspect(url)
        return cache[url]
    feeds=[x for x in source_items if x.get("url") and is_public_url(x["url"])]
    for p in policies[:max_policy]:
        metrics["policies_examined"]+=1
        url=p.get("url") or ""
        if not is_public_url(url):continue
        body,attachments,sections=get(url)
        if body:metrics["source_pages_read"]+=1
        details=find_explicit_deltas((p.get("body","") or "")+" "+body)
        if read_raw is not None:
            try:
                raw=read_raw(url)
                if raw:details.extend(year_table_deltas(raw.decode("utf-8","replace")))
            except Exception:pass
        for f in attachments[:3]:
            if not is_public_url(f.get("url","")):continue
            doc,_,_=get(f["url"])
            metrics["attachments_examined"]+=1
            if doc:details.extend(find_explicit_deltas(doc))
        unique={}
        for d in details:unique[(d["old_key"],d["new_key"])]=d
        details=list(unique.values())[:12]
        p["change_details"]=details
        p["details_checked"]=bool(body)
        if not details:
            inquiries.append({"title":p.get("title",""),"url":url,
                              "status":"변경 전·후 추출 대기","source":p.get("source",""),
                              "reason":"원문에서 대조 가능한 개정 전·후 값 또는 문구를 확인하지 못했습니다."})
            continue
        candidates={}
        for item in feeds:
            if item["url"]==url or item.get("source")==p.get("source"):continue
            candidates[item["url"]]=item
        subject=distinctive(p.get("title",""))
        for d in details[:2]:
            if not subject:break
            query=f'"{subject}" "{d["before"]}" (site:go.kr OR site:or.kr OR site:ac.kr)'
            try:
                result=rss_search(query)
                metrics["search_requests"]+=1
                for item in result:candidates[item["url"]]=item
            except Exception as e:
                metrics["errors"].append("공개검색 연결 오류: "+type(e).__name__)
        metrics["candidates_found"]+=len(candidates)
        matched=0
        # Prefer indexed results, then existing official-board items; avoid fetching every item.
        ranked=sorted(candidates.values(),key=lambda x:(x.get("origin")=="외부 공개검색",
              x.get("source")!=p.get("source"),
              len(set(subject.split())&set(x.get("title","").split()))),reverse=True)[:16]
        for target in ranked:
            if target.get("url") in [x.get("target_url") for x in findings]:continue
            try:
                metrics["target_pages_examined"]+=1
                for d in details[:6]:
                    result=evaluate_target(p,d,target,get)
                    if result:
                        matched+=1
                        findings.append(result)
                        break
            except Exception as e:
                metrics["errors"].append("문서 조회 오류: "+type(e).__name__)
            if len(findings)>=80:break
        if matched==0:
            inquiries.append({"title":p.get("title",""),"url":url,
                              "source":p.get("source",""),"status":"기관별 반영자료 탐색 중",
                              "reason":f"명시적 변경값 {len(details)}쌍 추출. 관련 공개 페이지에서 종전값 표시를 아직 확인하지 못했습니다."})
    findings.sort(key=lambda x:(x["review_required"],x["checked_at"]),reverse=True)
    return findings,inquiries,metrics
