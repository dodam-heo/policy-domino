"""POLICY DOMINO — multi-agency public policy watcher and publication auditor.
Scheduled by GitHub Actions. All downloaded content is public, source-linked.
A detected candidate is never automatically treated as an effective legal change.
"""
from __future__ import annotations
import concurrent.futures as futures
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlparse
from io import BytesIO
import hashlib, html, json, re, urllib.request, xml.etree.ElementTree as ET, zipfile
from law_changes import get_law_changes

ROOT=Path(__file__).resolve().parent
STATE=ROOT/"data"/"state.json"
OUT=ROOT/"site"/"data.json"
HEADERS={"User-Agent":"Mozilla/5.0 (compatible; PolicyDomino/2.1; public policy research)","Accept":"application/rss+xml,application/atom+xml,text/html,application/xml,*/*"}
FEEDS=[
("중소벤처기업부","법령공고","https://mss.go.kr/rss/smba/board/126.do"),
("중소벤처기업부","훈령·예규","https://mss.go.kr/rss/smba/board/125.do"),
("중소벤처기업부","사업공고","https://mss.go.kr/rss/smba/board/310.do"),
("중소벤처기업부","보도자료","https://mss.go.kr/rss/smba/board/86.do"),
("중소벤처기업부","공지사항","https://mss.go.kr/rss/smba/board/81.do"),
("보건복지부","훈령·예규·고시·지침","https://www.mohw.go.kr/rss/board.es?mid=a10409020000&update=&cg_code=&bid=0026"),
("보건복지부","보도자료","https://www.mohw.go.kr/rss/board.es?mid=a10503000000&bid=0027&info="),
("보건복지부","공지사항","https://www.mohw.go.kr/rss/board.es?mid=a10501010000&bid=0003&cg_code=C01&info="),
("행정안전부","보도자료","https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1012"),
("행정안전부","알림","https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1001"),
("행정안전부","설명자료","https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1013"),
("과학기술정보통신부","보도자료","https://www.msit.go.kr/user/rss/rss.do?bbsSeqNo=94"),
("과학기술정보통신부","연구개발·인재정책","https://www.msit.go.kr/user/rss/rss.do?bbsSeqNo=65"),
("서울특별시","전체 정책 소식","https://mediahub.seoul.go.kr/news/rss/"),
("서울특별시","복지","https://mediahub.seoul.go.kr/news/rss/07"),
("서울특별시","행정","https://mediahub.seoul.go.kr/news/rss/08"),
("서울특별시","주택","https://mediahub.seoul.go.kr/news/rss/03"),
("경기도","보도자료","https://gnews.gg.go.kr/rss/gnewsRssBodo.do"),
("경기도","복지","https://gnews.gg.go.kr/rss/categoryRssSearch.do?kwd=E002&policyCode=E002"),
("경기도","경제","https://gnews.gg.go.kr/rss/categoryRssSearch.do?kwd=E001&policyCode=E001"),
("경기도","교육","https://gnews.gg.go.kr/rss/categoryRssSearch.do?kwd=E003&policyCode=E003"),
("KOSIS 국가통계포털","공지","https://kosis.kr/rss/notice_rss.jsp"),
("국가데이터처","보도자료","https://mods.go.kr/menu.es?mid=a10301010000&act=rss")
]
CANDIDATE=re.compile(r"개정|제정|폐지|개편|변경|공포|시행|고시|신설|확대|축소|완화|강화|선정기준|지원기준|인상|인하|법률|지침|규정|기준")
CONFIRMED=re.compile(r"(공포|확정|시행|개정 완료|일부개정령\s*공포|개정\s*고시|시행규칙\s*개정)")
PROPOSAL=re.compile(r"(입법예고|행정예고|개정안|제정안|의견수렴|공청회|예고안|국무회의\s*통과)")
STOP=set("대한민국 정부 정책 보도자료 개정 시행 일부 법률 관련 발표 추진 지원 정부부처 사업 기관 공공 국민 적용 안내 내용 등을 위한 기준 결과 올해 이번 새로운 제공 서울 경기 중소기업 시행계획 임용시험 재공고 사업계획 연구개발 내용변경 입법예고 행정예고 지원사업 기준완화 사업공고 공고문 내용안내 정책변화".split())
ALLOWED_SUFFIX={".pdf",".hwp",".hwpx",".docx",".txt"}
FETCH_BUDGET=9
def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
def clean(s):
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",s or ""))).strip()
def read_json(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError,OSError):return default
def date_iso(s):
    s=(s or "").strip()
    if not s:return ""
    try:
        if re.fullmatch(r"\d{14}",s):return datetime.strptime(s,"%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo("Asia/Seoul")).astimezone(timezone.utc).isoformat()
        if re.fullmatch(r"\d{8}",s):return datetime.strptime(s,"%Y%m%d").replace(tzinfo=ZoneInfo("Asia/Seoul")).astimezone(timezone.utc).isoformat()
        if re.fullmatch(r"\d{4}[.-]\d{1,2}[.-]\d{1,2}.?",s):
            return datetime.strptime(re.sub(r"\D","-",s).strip("-"),"%Y-%m-%d").replace(tzinfo=ZoneInfo("Asia/Seoul")).astimezone(timezone.utc).isoformat()
        try:return parsedate_to_datetime(s).astimezone(timezone.utc).isoformat()
        except (TypeError,ValueError,OverflowError):dt=datetime.fromisoformat(s.replace("Z","+00:00")); return (dt.replace(tzinfo=ZoneInfo("Asia/Seoul")) if dt.tzinfo is None else dt).astimezone(timezone.utc).isoformat()
    except (TypeError,ValueError):return ""
def fetch(url,limit=2000000,timeout=14):
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read(limit),r.headers.get("content-type","")
def local(tag):return tag.split("}")[-1].lower()
def field(node,name):
    return next(((x.text or "").strip() for x in node if local(x.tag)==name), "")
def parse(raw,source,category):
    root=ET.fromstring(raw)
    entries=[x for x in root.iter() if local(x.tag) in ("item","entry")]
    result=[]
    for node in entries[:35]:
        title=clean(field(node,"title"))
        url=field(node,"link")
        if not url:
            link=next((x for x in node if local(x.tag)=="link" and x.attrib.get("href")) ,None)
            if link is not None:url=link.attrib.get("href","")
        if not url:url=field(node,"guid")
        if not url.startswith(("https://","http://")) or not title:continue
        body=clean(field(node,"description") or field(node,"summary") or field(node,"content"))[:850]
        date=field(node,"pubdate") or field(node,"published") or field(node,"updated") or field(node,"date")
        date_basis="RSS 게시일"
        if not date:
            # Some official portals encode the article creation timestamp in the URL.
            # Distinguish this from an explicitly published timestamp.
            m=re.search(r"(?:number|article_no|idx)=(20\d{12})",url)
            if m:
                date=m.group(1)
                date_basis="게시번호 생성시각"
        result.append(dict(title=title,url=url,body=body,source=source,category=category,
                           published=date,published_at=date_iso(date),date_basis=date_basis))
    return result
def load_feed(args):
    source,category,url=args
    try:
        raw,ctype=fetch(url)
        posts=parse(raw,source,category)
        if not posts:raise ValueError("피드에서 유효한 게시물 미발견")
        return dict(name=source,category=category,url=url,status="정상",count=len(posts),posts=posts)
    except Exception as e:
        return dict(name=source,category=category,url=url,status="수집 실패",count=0,error=str(e)[:170],posts=[])
def stage(title,cat):
    if PROPOSAL.search(title):return "예고·심의 단계"
    if re.search(r"공포|확정|일부개정|전부개정|개정 고시|규정 개정",title) and not re.search(r"예정|검토|추진",title):return "확정·개정 관련 게시"
    if CANDIDATE.search(title):return "변경 관련 검토"
    return "일반 게시"
def tokens(s):
    words=re.findall(r"[가-힣]{3,}",s or "")
    return {w for w in words if w not in STOP and not CANDIDATE.fullmatch(w) and len(w)<17}
def similarity(a,b):
    a=tokens(a);b=tokens(b)
    if not a or not b:return 0
    inter=a&b
    if len(inter)<2 and not any(len(x)>=6 for x in inter):
        return 0
    return round((len(inter)/max(2,min(len(a),len(b))))*100)
def inspect_page(url):
    try:
        raw,mime=fetch(url,limit=1500000,timeout=12)
        if "pdf" in mime or urlparse(url).path.lower().endswith(".pdf"):
            from pypdf import PdfReader
            pages=PdfReader(BytesIO(raw)).pages
            parts=[(i+1,p.extract_text() or "") for i,p in enumerate(pages[:20])]
            return clean(" ".join(p[1] for p in parts))[:12000],[],parts
        if urlparse(url).path.lower().endswith(".docx") or (raw[:4]==b"PK\x03\x04" and b"word/document.xml" in raw[:150000]):
            from docx import Document
            lines=[p.text for p in Document(BytesIO(raw)).paragraphs]
            return clean(" ".join(lines))[:12000],[],[(i+1,t) for i,t in enumerate(lines)]
        if urlparse(url).path.lower().endswith(".hwpx") or (raw[:4]==b"PK\x03\x04" and b"Contents/section" in raw[:180000]):
            with zipfile.ZipFile(BytesIO(raw)) as z:
                sections=[(n,z.read(n).decode("utf-8","replace")) for n in z.namelist() if n.startswith("Contents/section") and n.endswith(".xml")]
            return clean(" ".join(x[1] for x in sections))[:12000],[],[(i+1,clean(x[1])) for i,x in enumerate(sections)]
        if urlparse(url).path.lower().endswith(".txt"):
            return clean(raw.decode("utf-8","replace"))[:12000],[],[]
        from bs4 import BeautifulSoup
        soup=BeautifulSoup(raw,"html.parser")
        for el in soup(["script","style","nav","footer","header"]):el.decompose()
        links=[]
        for el in soup.select("a[href]"):
            href=urljoin(url,el.get("href",""))
            if urlparse(href).scheme not in ("http","https"):continue
            name=clean(el.get_text(" ",strip=True)) or href.rsplit("/",1)[-1]
            path=urlparse(href).path.lower()
            file_named=any(path.endswith(ext) for ext in ALLOWED_SUFFIX)
            download_named=bool(re.search(r"\.(?:pdf|hwp|hwpx|docx|txt)(?:\b|$)",name,re.I))
            download_endpoint=bool(re.search(r"(?:download|filedown|file_down|fileDown|atchfile|fileSeq|attach)",href,re.I))
            if file_named or (download_named and download_endpoint):
                if urlparse(href).hostname and urlparse(href).hostname.endswith(("go.kr","or.kr","gg.go.kr","seoul.go.kr")):
                    if href not in [x["url"] for x in links]:
                        links.append(dict(url=href,name=name))
        paragraphs=[clean(el.get_text(" ",strip=True)) for el in soup.select("main p, main li, article p, article li, .view_cont p, .view_cont li, .bbs_view p, td") if clean(el.get_text(" ",strip=True))]
        full=clean(soup.get_text(" ",strip=True))
        return full[:18000],links[:12],[(i+1,p) for i,p in enumerate(paragraphs[:80])]
    except Exception:
        return "",[],[]
def excerpt(s,needle,wide=85):
    pos=s.find(needle)
    if pos<0:return ""
    return s[max(0,pos-wide):pos+len(needle)+wide]
def deltas(text):
    # Only explicit before -> after expressions; do not treat unrelated amounts as a change.
    patterns=[
       r"(?:기존|종전|당초|현행)\s*([0-9][0-9,]*(?:원|만원|%|세)?)\s*(?:에서|→|->|에서\s*)\s*(?:변경|개정|인상|인하|조정|확대|축소)?\s*([0-9][0-9,]*(?:원|만원|%|세)?)",
       r"([0-9][0-9,]*(?:원|만원|%|세)?)\s*(?:→|->|에서)\s*([0-9][0-9,]*(?:원|만원|%|세)?)\s*(?:으로|로|까지)?"
    ]
    result=[]
    for pat in patterns:
        for match in re.finditer(pat,text):
            old,new=match.groups()
            if old!=new and len(old)>=2:
                item={"before":old,"after":new,"evidence":text[max(0,match.start()-70):match.end()+70]}
                if (old,new) not in [(x["before"],x["after"]) for x in result]:result.append(item)
            if len(result)>=7:return result
    return result
def audit(items,history):
    # Analyze a bounded set of newest public change publications and corresponding agency pages.
    # Cross-source matches are explicitly *candidates* until old value and authoritative change evidence agree.
    policies=[x for x in items if x["stage"]!="일반 게시" and x.get("published_at")][:14]
    candidates=[]
    page_cache={}
    for p in policies[:FETCH_BUDGET]:
        text,files,lines=inspect_page(p["url"])
        page_cache[p["url"]]=(text,files,lines)
        p["attachments"]=[dict(**f,analysis="수집 대상") for f in files]
        p["details_checked"]=bool(text)
        p["change_details"]=deltas((p["body"]+" "+text)[:15000])
    for p in policies[:8]:
        matches=[]
        for q in items:
            if q["source"]==p["source"] or q["url"]==p["url"]:continue
            score=similarity(p["title"],q["title"])
            if score<55:continue
            matches.append((score,q))
        matches.sort(key=lambda a:a[0],reverse=True)
        for score,q in matches[:3]:
            old_new=p.get("change_details",[])
            evidence=""
            status="연관 게시자료 검토"
            before=after=""
            location="공개 게시글 본문"
            target_url=q["url"]
            if old_new:
                t,f,lines=page_cache.get(q["url"],("",[],[]))
                if not t:
                    t,f,lines=inspect_page(q["url"])
                    page_cache[q["url"]]=(t,f,lines)
                for d in old_new:
                    if d["before"] in t and d["after"] not in t:
                        evidence=excerpt(t,d["before"])
                        before,after=d["before"],d["after"]
                        status="종전 수치 확인·적용시점 검토"
                        where=next((n for n,line in lines if before in line),None)
                        location=("게시글 본문 블록 "+str(where)) if where else "공개 게시글 본문"
                        break
                if not before and f:
                    for attachment in f[:2]:
                        doc,_,sections=inspect_page(attachment["url"])
                        for d in old_new:
                            if d["before"] in doc and d["after"] not in doc:
                                before,after=d["before"],d["after"]
                                evidence=excerpt(doc,before)
                                target_url=attachment["url"]
                                section=next((n for n,part in sections if before in part),None)
                                ext=urlparse(target_url).path.lower()
                                partname="PDF 페이지" if ext.endswith(".pdf") else "첨부 문서 단락·섹션"
                                location=attachment["name"]+" · "+partname+((" "+str(section)) if section else "")
                                status="첨부자료 종전 수치 확인·적용시점 검토"
                                break
                        if before:break
            candidates.append(dict(policy_title=p["title"],policy_url=p["url"],policy_source=p["source"],
                        target_source=q["source"],target_title=q["title"],target_url=target_url,
                        location=location,
                        before=before,after=after,evidence=evidence,similarity=score,status=status,
                        policy_stage=p["stage"],checked_at=stamp(),published_at=q.get("published_at",""),
                        notice="연관성·문구를 검출한 조사 대상이며, 수정 의무 또는 오류 판정은 아닙니다."))
    # Inspect attachments on up to 4 newest policy pages, and report that text has been analyzed.
    for p in policies[:5]:
        for f in p.get("attachments",[])[:3]:
            url=f["url"]
            if urlparse(url).path.lower().endswith(".hwp"):
                f["analysis"]="파일 탐지 (HWP 본문은 미분석)"
            else:
                content,_,_=inspect_page(url)
                f["analysis"]="본문 추출" if content else "첨부 탐지·본문 접근 불가"
                f["preview"]=content[:180]
    return candidates[:60]
def main():
    STATE.parent.mkdir(parents=True,exist_ok=True)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    state=read_json(STATE,{"initialized":False,"hashes":{},"first_seen":{}})
    prev=state.get("hashes",{})
    hashes=dict(prev); first_seen=dict(state.get("first_seen",{}))
    initial=not state.get("initialized",False)
    sources=[];items=[];now=stamp()
    with futures.ThreadPoolExecutor(max_workers=9) as pool:
        results=list(pool.map(load_feed,FEEDS))
    for r in results:
        sources.append({k:r[k] for k in ("name","category","url","status","count")}|({"error":r["error"]} if "error" in r else {})|{"last_check":now})
        for post in r["posts"]:
            url=post["url"]
            signature=hashlib.sha256((post["title"]+"\n"+post["body"]).encode()).hexdigest()
            original=prev.get(url)
            if url not in first_seen:first_seen[url]=now
            detected="기존" if original==signature else "기준선" if initial and original is None else "수정 감지" if original else "신규 감지"
            hashes[url]=signature
            post.update(detected=detected,detected_at=now if detected in ("신규 감지","수정 감지") else first_seen[url],
                        stage=stage(post["title"],post["category"]),first_seen_at=first_seen[url])
            items.append(post)
    # Some RSS channels repeat the same post: retain the latest source occurrence, one URL per item.
    unique={}
    for p in items:
        if p["url"] not in unique or p.get("published_at","")>unique[p["url"]].get("published_at",""):unique[p["url"]]=p
    items=list(unique.values())
    items.sort(key=lambda p:(p.get("published_at") or p.get("first_seen_at") or "",p.get("title","")),reverse=True)
    impacts=audit(items,state)
    law_changes,law_seen,law_source=get_law_changes(items,state.get("law_seen",{}))
    cutoff=datetime.fromisoformat(now).timestamp()-7*86400
    recent_laws=sum(bool(law.get("promulgated_at") or law.get("published_at")) and datetime.fromisoformat(law.get("promulgated_at") or law.get("published_at")).timestamp()>=cutoff for law in law_changes)
    counts={"total":len(items),"law_total":len(law_changes),"law_recent_7d":recent_laws,
            "recent":sum(p["detected"] in ("신규 감지","수정 감지") for p in items),
            "modified":sum(p["detected"]=="수정 감지" for p in items),
            "candidate":sum(p["stage"]!="일반 게시" for p in items),"targets":len(impacts)}
    data={"generated_at":now,"first_scan":initial,"counts":counts,"sources":sources,
          "law_changes":law_changes,"law_source":law_source,
          "items":items[:280],"impacts":impacts,"source_count":len(FEEDS),
          "success_count":sum(s["status"]=="정상" for s in sources),
          "scope":"중앙행정기관·지방자치단체·공공통계 공식 RSS",
          "method":"실시간 공개 게시물 · 첨부자료 일부 원문 검사 · 기관 간 연관 게시물 탐색"}
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    STATE.write_text(json.dumps({"initialized":True,"hashes":hashes,"first_seen":first_seen,"law_seen":law_seen},ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"posts":len(items),"sources_ok":data["success_count"],"sources_all":len(sources),"impact_candidates":len(impacts),"enacted_changes":len(law_changes),"law_api":law_source["api_connected"]},ensure_ascii=False))
if __name__=="__main__":main()
