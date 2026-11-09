"""Discover institution/program impacts from live public documents, not a registry.

No preset agency, business, amount, source URL, or institution-specific action.
Only public search -> independently fetched official page -> exact old value,
matching changed field, period and an operational use can create a candidate.
Failure to find evidence yields zero suggestions, never an invented relation.
"""
from __future__ import annotations
import hashlib
import html
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

SEARCH_LIMIT = 6
MAX_EVENTS = 10
OFFICIAL_CHANGE_HOSTS = {"law.go.kr", "www.law.go.kr"}
OPERATION = re.compile(r"신청|접수|지급|산정|선정|자격|지원|입주|심사|급여|경곗값|기준표|대상자|소득기준|이용조건")
NON_PROGRAM = re.compile(r"보도자료|언론보도|보도설명|뉴스|기사|개정안|입법예고|행정예고")
AGENCY = re.compile(r"^[가-힣\s·()]{3,40}(?:부|처|청|위원회|공사|공단|재단|진흥원|관리원|정보원|연구원|교육청|대학교|지방자치단체)$")

def compact(value):
    return re.sub(r"\s+", "", str(value or ""))

def trusted(url):
    p = urlparse(str(url))
    host = (p.hostname or "").lower()
    return p.scheme == "https" and host not in OFFICIAL_CHANGE_HOSTS and (
        host.endswith(".go.kr") or host.endswith(".or.kr") or host.endswith(".ac.kr")
    )

def official_law_url(url):
    p=urlparse(str(url))
    return p.scheme=="https" and p.hostname in OFFICIAL_CHANGE_HOSTS

def _html_bytes(url, max_bytes=850000):
    if not trusted(url):
        raise ValueError("Untrusted institution URL")
    req=Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; PolicyDominoEvidenceBot/1.0)","Accept":"text/html"})
    with urlopen(req,timeout=9) as resp:
        if not trusted(resp.geturl()):
            raise ValueError("Redirected outside public institution sites")
        if "text/html" not in resp.headers.get("Content-Type","").lower():
            raise ValueError("Not HTML")
        data=resp.read(max_bytes+1)
    if len(data)>max_bytes:raise ValueError("Page too large")
    return data.decode("utf-8","replace")

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip=0;self.title=[];self.heading=[];self.parts=[];self._in_title=False
        self._heading_level=0;self._heading=[];self.publisher=""
    def handle_starttag(self,tag,attrs):
        attributes=dict(attrs)
        if tag in ("script","style","noscript","svg"):self.skip+=1
        if self.skip:return
        if tag=="meta" and attributes.get("property")=="og:site_name":
            self.publisher=attributes.get("content","").strip()
        if tag=="title":self._in_title=True
        if tag in ("h1","h2","h3") and not self._heading_level:
            self._heading_level=1;self._heading=[]
        if tag in ("p","li","tr","th","td","div","h1","h2","h3","br"):
            self.parts.append(" ")
    def handle_endtag(self,tag):
        if tag in ("script","style","noscript","svg"):
            self.skip=max(0,self.skip-1);return
        if tag=="title":self._in_title=False
        if tag in ("h1","h2","h3") and self._heading_level:
            v=" ".join("".join(self._heading).split())
            if v:self.heading.append(v)
            self._heading_level=0
    def handle_data(self,t):
        if self.skip:return
        if self._in_title:self.title.append(t)
        if self._heading_level:self._heading.append(t)
        self.parts.append(t)
    @property
    def text(self):
        return " ".join(" ".join(self.parts).split())
    @property
    def page_title(self):
        return " ".join("".join(self.title).split())

def parse_page(raw):
    p=Page();p.feed(raw);return p

def _numeric(value):
    v=re.sub(r"[^0-9]","",str(value))
    return int(v) if v else None

def changed_fields(event):
    """Read changed amounts from cited old/new source, never title-only similarity."""
    if event.get("presentation_source") not in (
        "v4_official_source","legacy_official_directive_awaiting_recheck"
    ):return []
    out=[]
    for d in event.get("article_differences",[]):
        old=str(d.get("before",""));new=str(d.get("after",""))
        field=str(d.get("article","")).split(":")[0].strip()
        if not (field and old and new and old!=new and official_law_url(d.get("source_url",""))):
            continue
        # Only a short, concrete named numerical standard is eligible;
        # large law paragraphs and arbitrary numbers are not.
        if len(field)>85 or len(old)>70 or len(new)>70:continue
        if not re.search(r"[가-힣]{2}",field):continue
        a=_numeric(old);b=_numeric(new)
        if not a or not b or a==b or a<10000:continue
        # A numeral in prose containing other numbers is ambiguous.
        if len(re.findall(r"\d[\d,]*",old))!=1 or len(re.findall(r"\d[\d,]*",new))!=1:continue
        out.append({"field":field,"before":old,"after":new,"old_amount":a,
                    "source_url":d["source_url"]})
    return out[:4]

def _search_leads(body):
    """Parse ordinary result links and redirect links without trusting snippets."""
    class Links(HTMLParser):
        def __init__(self):
            super().__init__();self.urls=[]
        def handle_starttag(self,tag,attrs):
            if tag!="a":return
            h=dict(attrs).get("href","")
            if h:self.urls.append(h)
    decoded=html.unescape(body).replace("\\/", "/")
    parsed=Links()
    parsed.feed(decoded)
    # Include encoded URL strings when engines store leads in JSON scripts.
    leads=parsed.urls+re.findall(r"https?://[^\\s\"'<>]{8,400}",decoded)
    out=[]
    for lead in leads:
        lead=html.unescape(unquote(str(lead)))
        p=urlparse(lead)
        if "uddg=" in lead and "duckduckgo.com" in lead:
            lead=parse_qs(p.query).get("uddg",[""])[0]
        elif lead.startswith("/url?"):
            lead=parse_qs(urlparse(lead).query).get("q",[""])[0]
        elif p.hostname and p.hostname.endswith("google.com") and p.path=="/url":
            lead=parse_qs(p.query).get("q",[""])[0]
        if trusted(lead) and lead not in out:out.append(lead)
    return out

def search_public(query):
    """Search distinct general-purpose indexes; no institution seeds.

    Search and its availability are explicitly best effort. Source pages are
    subsequently retrieved and verified; no search result text is trusted.
    """
    from urllib.parse import urlencode
    urls=[
        "https://www.bing.com/search?"+urlencode({"format":"rss","q":query}),
        "https://search.naver.com/search.naver?"+urlencode({"where":"web","query":query}),
        "https://www.google.com/search?"+urlencode({"q":query,"num":"25"}),
        "https://html.duckduckgo.com/html/?"+urlencode({"q":query}),
    ]
    out=[]
    for url in urls:
        try:
            req=Request(url,headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36","Accept":"text/html,application/rss+xml"})
            with urlopen(req,timeout=7) as response:
                raw=response.read(550000)
            body=raw.decode("utf-8","replace")
            if body.lstrip().startswith("<?xml") or "<rss" in body[:1000]:
                try:
                    root=ET.fromstring(raw)
                    for n in root.findall(".//item/link"):
                        if n.text and trusted(n.text) and n.text not in out:out.append(n.text)
                except ET.ParseError:pass
            for link in _search_leads(body):
                if link not in out:out.append(link)
            if len(out)>=SEARCH_LIMIT:break
        except (OSError,ValueError):
            continue
    return out[:SEARCH_LIMIT]

def search_query(field,amount):
    # Generic index query: no institution/program names, source URLs or fixed values.
    return '"'+field+'" "'+f"{amount:,}"+'"'

def _nearby_proof(text,field,old,year):
    """The exact historical amount, named field and year must coexist locally."""
    value=compact(text).replace(",","")
    literal=str(old)
    for found in re.finditer(r"(?<!\d)"+re.escape(literal)+r"(?!\d)",value):
        start=max(0,found.start()-210);end=min(len(value),found.end()+210)
        chunk=value[start:end]
        if compact(field) not in chunk:continue
        if str(year) not in chunk:continue
        if not OPERATION.search(chunk):continue
        return chunk[max(0,found.start()-start-95):][:220]
    # Korean numeric notation (e.g., 649만 4,738원) is also official.
    high,low=divmod(old,10000)
    if high and low:
        native=re.compile(r"(?<!\d)"+str(high)+r"\s*만\s*"+str(low)+r"(?!\d)")
        for m in native.finditer(value):
            chunk=value[max(0,m.start()-210):m.end()+210]
            if compact(field) in chunk and str(year) in chunk and OPERATION.search(chunk):
                return chunk[:220]
    return ""

def _name(p):
    # Official publisher must be asserted by page metadata, not inferred
    # from the search result, bare domain, or the named policy's authority.
    candidates=[p.publisher]
    # Many institutional sites put a named publisher after a title delimiter.
    candidates += re.split(r"[|｜]",p.page_title)[1:]
    for c in candidates:
        c=" ".join(c.split()).strip(" -·")
        if AGENCY.fullmatch(c):
            return c
    return ""

def _program(p,field):
    candidates=list(p.heading[:8])+re.split(r"[|｜]",p.page_title)[:1]
    for candidate in candidates:
        c=" ".join(candidate.split()).strip()
        if not (5<=len(c)<=110) or NON_PROGRAM.search(c):continue
        if not OPERATION.search(c):continue
        if compact(c)==compact(field):continue
        if c in ("신청 안내","이용 안내","서비스 안내","지원 안내"):continue
        return c
    return ""

def candidate_action(event,change,url,page):
    if not trusted(url):return None
    name=_name(page);program=_program(page,change["field"])
    if not name or not program:return None
    try:year=int(str(event["effective_date"])[:4])-1
    except (ValueError,TypeError,KeyError):return None
    if year<1990:return None
    proof=_nearby_proof(page.text,change["field"],change["old_amount"],year)
    if not proof:return None
    # The named standard must be operative in this page; a press release
    # or incidental mention never gives a verified institutional dependency.
    source_year=year
    key="|".join([event["event_id"],url,program,change["field"]])
    old,new=change["before"],change["after"]
    review=(f"{program}에 표시된 {change['field']}의 기존 기준 {old}과 "
            f"변경 기준 {new}을 대조하고, 적용 연도 및 해당 업무 반영 필요 여부를 확인")
    return {
        "id":"discovered:"+hashlib.sha256(key.encode()).hexdigest()[:22],
        "event_id":event["event_id"],"agency":name,
        "agency_role":"공식자료 게시기관 (실제 수행·내부 담당 여부 미확인)",
        "work":program,"service":program,"law_title":event["title"],
        "article":change["field"],"effective_date":event.get("effective_date",""),
        "target_location":program+" · "+change["field"],
        "what_to_change":review,"required_change":review,
        "changes":[{"field":change["field"],"before":old,"after":new,
                    "meaning":"원천 정책 변경값 (기관 내부 반영 상태 미확인)"}],
        "basis":change["source_url"],"agency_basis":url,
        "institution_evidence":{"publisher":name,"heading":program,
            "excerpt":proof,"source_year":source_year,
            "followup_year":source_year+1,"program":program,
            "relationship":"official_public_page_numeric_match"},
        "status":"기관별 기준 반영 검토",
        "status_evidence":None,"confidence":"공식 웹페이지의 종전 기준값·연도·사용 맥락 확인",
        "verification_note":"공식 페이지에서 종전 금액·적용연도·기준 사용을 확인했으나 변경 후 내부 운영기준과 시스템 수정 여부는 미확인",
        "impact_link_basis":"원천 변경 조항과 공식 기관 페이지의 기준명·종전 금액·연도 일치",
        "evidence_scope":"official_institutional_program_dependency",
        "institutional_implementation_verified":False,
        "is_direct_legal_amendment":False,
        "discovery_method":"live_public_search_and_page_validation",
        "role_scope":"공식 게시자료 기준 검토",
    }

def discover(events, search=None, fetch=None):
    """New official candidates are discovered on each run; no manual registry."""
    search=search or search_public
    fetch=fetch or _html_bytes
    candidates=[];seen=set();health={"attempted":0,"pages_checked":0,"matched":0,"errors":0}
    eligible=sorted(events,key=lambda e:e.get("impact_priority",0),reverse=True)
    for event in eligible:
        if health["attempted"]>=MAX_EVENTS:break
        fields=changed_fields(event)
        if not fields:continue
        health["attempted"]+=1
        for changed in fields[:2]:
            try:urls=search(search_query(changed["field"],changed["old_amount"]))[:SEARCH_LIMIT]
            except Exception:
                health["errors"]+=1;continue
            for url in urls:
                if not trusted(url) or url in seen:continue
                seen.add(url)
                try:
                    page=parse_page(fetch(url))
                    health["pages_checked"]+=1
                    result=candidate_action(event,changed,url,page)
                    if result:
                        candidates.append(result);health["matched"]+=1
                except Exception:health["errors"]+=1
    return candidates,health

def connect(events,existing_actions,discovered_actions):
    actions=list(existing_actions)
    known={(a.get("event_id"),a.get("agency"),compact(a.get("article")),a.get("work"))
           for a in actions}
    added=[]
    for item in discovered_actions:
        if item.get("discovery_method")!="live_public_search_and_page_validation":continue
        if not item.get("agency_basis") or not item.get("institution_evidence",{}).get("excerpt"):continue
        key=(item["event_id"],item["agency"],compact(item["article"]),item["work"])
        if key in known:continue
        known.add(key);actions.append(item);added.append(item)
    return actions,added
