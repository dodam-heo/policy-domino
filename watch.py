"""POLICY DOMINO: GitHub Actions cloud-only RSS monitor.
Reads official public RSS; never modifies external websites.
Data is a candidate list, not a legal or compliance determination.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib, html, json, re
import urllib.request
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
STATE=ROOT/"data"/"state.json"
OUT=ROOT/"site"/"data.json"
FEEDS=[
 ("중소벤처기업부 법령공고","https://mss.go.kr/rss/smba/board/126.do"),
 ("중소벤처기업부 훈령·예규","https://mss.go.kr/rss/smba/board/125.do"),
 ("중소벤처기업부 사업공고","https://mss.go.kr/rss/smba/board/310.do"),
 ("중소벤처기업부 보도자료","https://mss.go.kr/rss/smba/board/86.do"),
 ("중소벤처기업부 공지사항","https://mss.go.kr/rss/smba/board/81.do")
]
KEYWORDS=re.compile(r"개정|제정|폐지|개편|변경|공포|시행|고시|신설|확대|축소|완화|강화|선정기준|지원기준|인상|인하|법령|지침|규정")
def now():
 return datetime.now(timezone.utc).isoformat(timespec="seconds")
def text(s):
 return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",s or ""))).strip()
def parse(raw):
 root=ET.fromstring(raw)
 entries=[]
 if root.tag.endswith("rss") or root.find("channel") is not None:
  for node in root.findall(".//item"):
   get=lambda tag: (node.findtext(tag) or "").strip()
   title=text(get("title")); link=get("link") or get("guid")
   if title and link and link.startswith(("https://","http://")):
    entries.append(dict(title=title,url=link,body=text(get("description"))[:600],published=get("pubDate")))
 else:
  ns={"a":"http://www.w3.org/2005/Atom"}
  for node in root.findall("a:entry",ns):
   title=text(node.findtext("a:title","",ns))
   links=node.findall("a:link",ns)
   link=next((e.get("href","") for e in links if e.get("rel","alternate")=="alternate"),"")
   if title and link.startswith(("https://","http://")):
    entries.append(dict(title=title,url=link,body=text(node.findtext("a:summary","",ns))[:600],published=node.findtext("a:updated","",ns)))
 return entries
def read_json(path,default):
 try: return json.loads(path.read_text(encoding="utf-8"))
 except (OSError,ValueError): return default
def main():
 STATE.parent.mkdir(parents=True,exist_ok=True)
 OUT.parent.mkdir(parents=True,exist_ok=True)
 state=read_json(STATE,{"hashes":{},"initialized":false}) if False else read_json(STATE,{"hashes":{},"initialized":False})
 old=state.get("hashes",{})
 hashes=dict(old)
 initial=not state.get("initialized",False)
 sources=[]; events=[]; failures=0; total=0; new_count=0; changed_count=0
 for source,url in FEEDS:
  stamp=now()
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"PolicyDomino-Research/1.0","Accept":"application/rss+xml,application/atom+xml,application/xml,text/xml,*/*"})
   with urllib.request.urlopen(req,timeout=18) as response: raw=response.read(2000000)
   posts=parse(raw); total+=len(posts)
   sources.append(dict(name=source,url=url,status="정상",count=len(posts),last_check=stamp))
   for p in posts:
    key=p["url"]
    signature=hashlib.sha256((p["title"]+"\n"+p["body"]).encode()).hexdigest()
    prev=old.get(key)
    hashes[key]=signature
    status="기존 게시" if prev==signature else "기준선 수집" if initial and prev is None else "수정 감지" if prev else "신규 감지"
    if status=="신규 감지":new_count+=1
    if status=="수정 감지":changed_count+=1
    kind="변경 후보" if KEYWORDS.search(p["title"]+" "+p["body"]) else "일반 게시"
    events.append(dict(**p,source=source,status=status,kind=kind,
                       targets=[],notice="제목과 요약의 표현으로 분류한 후보입니다. 실제 제도 변경 또는 타 기관 게시물 수정 의무는 아직 검증되지 않았습니다."))
  except Exception as exc:
   failures+=1
   sources.append(dict(name=source,url=url,status="수집 실패",error=str(exc)[:250],last_check=stamp))
 events.sort(key=lambda e:(e["status"] in ("수정 감지","신규 감지"),e["kind"]=="변경 후보",e.get("published") or ""),reverse=True)
 payload=dict(generated_at=now(),first_scan=initial,counts={"total":total,"change_count":sum(e["kind"]=="변경 후보" for e in events),"new_count":new_count,"modified_count":changed_count},sources=sources,items=events[:150],interval_hours=1,scope="중소벤처기업부 공식 RSS 5개",source_failures=failures,coverage="현재 시범 수집원. 전국 정책 변경 및 기관별 게시물 전수 탐지는 미구현.")
 OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
 STATE.write_text(json.dumps({"initialized":True,"hashes":hashes},ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({"items":len(events),"sources":len(sources),"failures":failures,"first_scan":initial},ensure_ascii=False))
if __name__=="__main__":main()
