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
