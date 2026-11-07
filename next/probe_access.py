"""Diagnose public legal endpoints without exposing any user OC credential."""
import concurrent.futures
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import ssl
targets = {
"law_api_sample_open":"https://open.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=XML&sort=ddes&display=3",
"law_api_sample_open_http":"http://open.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=XML&sort=ddes&display=3",
"law_api_sample_https":"https://www.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=XML&sort=ddes&display=3",
"law_api_sample_http":"http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=XML&sort=ddes&display=3",
"law_api_sample_base":"https://law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=XML&sort=ddes&display=3",
"law_public_index":"https://www.law.go.kr/LSW/nwRvsLsPop.do",
"law_revision_direct":"https://www.law.go.kr/LSW/lsRvsDocInfoR.do?lsiSeq=291687&chrClsCd=010202",
"law_open_guides":"https://open.law.go.kr/LSO/information/guide.do",
"moleg_public":"https://www.moleg.go.kr/",
}
def probe(args):
    name,url=args
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (PolicyDomino public endpoint connectivity test)","Accept":"*/*"})
        with urllib.request.urlopen(req,timeout=7) as r:
            chunk=r.read(140000)
            status=r.status
            final_host=r.url.split("/")[2]
            mime=r.headers.get("Content-Type","")
        try: root=ET.fromstring(chunk);root_name=root.tag
        except Exception:root_name="not-XML"
        return {"endpoint":name,"status":status,"bytes":len(chunk),"mime":mime[:60],"root":root_name,"host":final_host}
    except Exception as exc:
        return {"endpoint":name,"error":type(exc).__name__,"reason":str(exc)[:140]}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    for result in pool.map(probe,targets.items()):
        print(result,flush=True)

# Inspect the shape of official PUBLIC promulgation records.
from html.parser import HTMLParser
class TableRows(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=="tr":self.row=[]
        if self.row is not None and tag in ("td","th"):self.cell=[]
    def handle_data(self,txt):
        if self.cell is not None:self.cell.append(txt)
    def handle_endtag(self,tag):
        if tag in ("td","th") and self.row is not None and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()));self.cell=None
        if tag=="tr" and self.row is not None:
            self.rows.append(self.row);self.row=None
for key in ("law_api_sample_https","law_public_index"):
    try:
        req=urllib.request.Request(targets[key],headers={"User-Agent":"Mozilla/5.0","Accept":"*/*"})
        with urllib.request.urlopen(req,timeout=12) as res:raw=res.read(200000)
        if key=="law_api_sample_https":
            root=ET.fromstring(raw)
            print("PUBLIC SAMPLE API RESPONSE:",ET.tostring(root,encoding="unicode")[:1000],flush=True)
        else:
            parser=TableRows();parser.feed(raw.decode("utf-8","replace"))
            rows=[r for r in parser.rows if len(r)>=6]
            print("PUBLIC LAW INDEX ROWS:",len(rows),flush=True)
            for row in rows[:4]:print("PUBLIC LAW TABLE:",row[:10],flush=True)
    except Exception as exc:
        print("PUBLIC SOURCE PARSE DIAGNOSTIC:",key,type(exc).__name__,str(exc)[:120],flush=True)

# Public recent-law anchors: determine the exact revision link from the official page.
try:
    raw=urllib.request.urlopen(urllib.request.Request(targets["law_public_index"],headers={"User-Agent":"Mozilla/5.0"}),timeout=10).read(150000).decode("utf-8","replace")
    import re
    needle="행정안전부와 그 소속기관 직제 시행규칙"
    i=raw.find(needle)
    if i>=0:print("PUBLIC FIRST LAW HTML:",re.sub(r"\s+"," ",raw[max(0,i-850):i+450])[:1100],flush=True)
    else:print("PUBLIC FIRST LAW HTML: missing",flush=True)
except Exception as e:print("PUBLIC ANCHOR CHECK:",type(e).__name__,str(e)[:100],flush=True)

# Inspect one exact, official published amending-law document for article-level public extraction.
try:
    uri="https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=291687&viewCls=lsRvsDocInfoR"
    req=urllib.request.Request(uri,headers={"User-Agent":"Mozilla/5.0","Accept":"text/html"})
    with urllib.request.urlopen(req,timeout=10) as res:raw=res.read(300000).decode("utf-8","replace")
    from html.parser import HTMLParser
    class Txt(HTMLParser):
        def __init__(self):super().__init__();self.data=[]
        def handle_data(self,t):self.data.append(t)
    p=Txt();p.feed(raw)
    whole=" ".join(" ".join(p.data).split())
    print("PUBLIC REVISION PAGE:",len(raw),"characters, visible text",len(whole),"chars",flush=True)
    for word in ("개정문","제1조","개정이유","부칙"):
        pos=whole.find(word);print("PUBLIC REVISION SAMPLE",word,whole[max(0,pos-65):pos+270] if pos>=0 else "not in SSR text",flush=True)
    for word in ("lsRvsDocInfoR","lsRvsRsn","lawContent","lsiSeq"):
        pos=raw.find(word);print("PUBLIC REVISION HTML",word,raw[max(0,pos-120):pos+210] if pos>=0 else "not present",flush=True)
except Exception as e:print("PUBLIC REVISION ERROR:",type(e).__name__,str(e)[:150],flush=True)

try:
    uri=targets["law_revision_direct"]
    req=urllib.request.Request(uri,headers={"User-Agent":"Mozilla/5.0 (PolicyDomino public law research)","Accept":"text/html"})
    with urllib.request.urlopen(req,timeout=12) as res: raw=res.read(220000).decode("utf-8","replace")
    from html.parser import HTMLParser
    class PlainText(HTMLParser):
        def __init__(self):super().__init__();self.exclude=0;self.parts=[]
        def handle_starttag(self,tag,attrs):
            if tag in ("script","style"):self.exclude+=1
        def handle_endtag(self,tag):
            if tag in ("script","style"):self.exclude=max(0,self.exclude-1)
        def handle_data(self,text):
            if not self.exclude:self.parts.append(text)
    parser=PlainText();parser.feed(raw)
    text=" ".join(" ".join(parser.parts).split())
    print("DIRECT LAW AMENDMENT LEN:",len(raw),"TEXT",len(text),flush=True)
    for word in ("개정이유","개정문","제1조","제2조","부칙"):
        at=text.find(word)
        print("DIRECT LAW AMENDMENT SNIPPET",word, text[max(0,at-90):at+290] if at>=0 else "NONE",flush=True)
except Exception as e: print("DIRECT LAW AMENDMENT ERROR:",type(e).__name__,str(e)[:180],flush=True)
