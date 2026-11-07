"""Policy Domino NEXT: law-version change -> affected operations -> action ledger.
Independent of the former RSS announcement watcher. Python standard library only.
No invented legal changes, agency identities, completion evidence or examples.
"""
from __future__ import annotations
import datetime as dt
import difflib
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data"/"next_state.json"
OUTPUT=ROOT/"site"/"data.json"
NOW=lambda:dt.datetime.now(dt.timezone.utc)
HEADERS={"User-Agent":"PolicyDomino/next (+public legal data monitoring)","Accept":"application/xml,text/xml,text/html,application/xhtml+xml"}
MOLEG="https://www.law.go.kr/DRF/"
# These are classifications of legal duties, not hardcoded example policies.
TASK_RULES=(
 {"id":"eligibility","phrases":("신청자격","대상자","지원대상","선정기준","소득기준","자격요건","자격이","해당하는 사람"),
  "category":"업무처리 기준","operation":"신청·심사·자격 판정","requirement":"변경된 대상자·자격·선정조건을 신청 접수와 심사기준에 반영"},
 {"id":"amount","phrases":("지급액","지급금액","지원금액","산정","계산","수수료","상한액","최저액","보험료","부담금","기준액","비율"),
  "category":"계산식·시스템","operation":"금액 산정·검증","requirement":"변경된 산정기준·금액·비율을 계산식과 해당 서비스 기능에 반영"},
 {"id":"documents","phrases":("신청서","제출서류","증빙서류","첨부서류","서식","구비서류","신청할 때","제출하여야"),
  "category":"신청·민원 서비스","operation":"신청 접수 및 서류 확인","requirement":"필요서류·서식·신청절차의 변경사항을 신청업무와 대외 안내에 반영"},
 {"id":"deadlines","phrases":("처리기간","신청기간","기한","기간 내","경과조치","유예기간","일 이내","개월 이내"),
  "category":"업무처리 기준·시스템","operation":"기한 관리","requirement":"신청·처리기한과 시행·경과조치에 따른 적용 시점 규칙을 변경"},
 {"id":"licensing","phrases":("허가","승인","신고","등록","인증","지정","검사","심사"),
  "category":"행정 업무·서비스","operation":"허가·신고·등록·심사","requirement":"변경된 허가·신고·심사 요건과 업무처리 절차를 적용"},
 {"id":"notices","phrases":("고지","안내","통지","공시","공고","공개하여야","게시"),
  "category":"대국민 서비스·안내","operation":"고지·통지·공개","requirement":"변경된 법적 고지·안내·공개 요건을 대국민 서비스에 반영"},
 {"id":"organization","phrases":("직제","정원","하부조직","전문직공무원","전문관","직급","기구","사무분장","직무","소속기관"),
  "category":"조직·인사 및 업무분장","operation":"조직·정원·직무 배정",
  "requirement":"변경된 직제·정원·업무분장 규정과 시행·경과조치를 소관 조직 운영기준에 반영"},
 {"id":"inspection","phrases":("점검","감독","준수","의무","금지","제재","과태료"),
  "category":"점검·관리 업무","operation":"점검·준수·감독","requirement":"변경된 의무·금지·점검 기준을 관련 업무의 판정·관리 절차에 반영"}
)
ROLES=(
 ("시장·군수·구청장",("시장·군수·구청장","시장ㆍ군수ㆍ구청장","시장, 군수 또는 구청장","시장·군수 또는 구청장","시장 군수 구청장"),"기초지방자치단체"),
 ("시·도지사",("시·도지사","시ㆍ도지사","특별시장","광역시장","도지사"),"광역지방자치단체"),
 ("교육감",("교육감",),"시·도교육청"),
 ("공공기관",("공공기관의 장","공공기관","공단","공사"),"관련 공공기관")
)
VALID_REVISIONS=("제정","일부개정","전부개정","일괄개정","타법개정","폐지","폐지제정")
DATE_RE=re.compile(r"20\d{2}(?:[.\-/]?\d{1,2}){2}")
def clean(s):
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",s or ""))).strip()
def digest(s):
    return hashlib.sha256(str(s).encode("utf-8")).hexdigest()[:18]
def stamp():
    return NOW().isoformat(timespec="seconds")
def date_str(s):
    value=str(s or "").strip()
    if re.fullmatch(r"\d{8}",value):
        try:return dt.datetime.strptime(value,"%Y%m%d").date().isoformat()
        except ValueError:return ""
    m=re.search(r"(20\d{2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})",value)
    if m:
        try:return dt.date(int(m.group(1)),int(m.group(2)),int(m.group(3))).isoformat()
        except ValueError:return ""
    return ""
def read_json(path,default):
    try:return json.loads(path.read_text("utf-8"))
    except (ValueError,OSError):return default
def xml_field(node,name):
    x=next((e for e in node.iter() if e.tag.split("}")[-1]==name),None)
    return clean("".join(x.itertext())) if x is not None else ""
def download(url,timeout=18,max_bytes=2500000):
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return response.read(max_bytes)
def api_request(endpoint,**params):
    oc=os.environ.get("LAW_OC","").strip()
    if not oc:raise RuntimeError("LAW_OC 인증값 미설정")
    uri=MOLEG+endpoint+"?"+urllib.parse.urlencode({"OC":oc,"type":"XML",**params})
    data=download(uri)
    try:return ET.fromstring(data)
    except ET.ParseError:raise ValueError("공식 API 응답이 XML 형식이 아닙니다")
def record_from_law(node):
    title=xml_field(node,"법령명한글")
    published=re.sub(r"\D","",xml_field(node,"공포일자"))
    kind=xml_field(node,"제개정구분명")
    law_id=xml_field(node,"법령ID")
    mst=xml_field(node,"법령일련번호")
    if not title or len(published)!=8 or not law_id or not mst:return None
    if not any(t in kind for t in VALID_REVISIONS):return None
    return {"id":law_id,"mst":mst,"title":title,"promulgated_at":date_str(published),
            "promulgation_number":xml_field(node,"공포번호"),
            "effective_date":date_str(xml_field(node,"시행일자")),
            "revision":kind,"ministry":xml_field(node,"소관부처명"),
            "law_type":xml_field(node,"법령구분명"),
            "url":"https://www.law.go.kr/법령/"+urllib.parse.quote(title)}
def official_laws(limit=80):
    # National Law Information Center structured promulgation records (not RSS posts).
    results=[]
    for page in (1,2):
        root=api_request("lawSearch.do",target="law",sort="ddes",display=100,page=page)
        nodes=[n for n in root.iter() if n.tag.split("}")[-1]=="law"]
        for n in nodes:
            rec=record_from_law(n)
            if rec:results.append(rec)
        if len(results)>=limit or len(nodes)<100:break
    unique={}
    for record in results:unique.setdefault((record["id"],record["promulgated_at"],record["promulgation_number"]),record)
    return sorted(unique.values(),key=lambda r:(r["promulgated_at"],r["promulgation_number"]),reverse=True)[:limit]
def public_law_list(limit=30):
    """Public official promulgation TABLE fallback (metadata only, no authenticated clause access).
    Prevents ordinary press releases and draft notices being mistaken for legal changes.
    """
    from html.parser import HTMLParser
    class Rows(HTMLParser):
        def __init__(self):
            super().__init__();self.rows=[];self.row=None;self.cell=None;self.row_link="";self.row_title=""
        def handle_starttag(self,tag,attrs):
            if tag=="tr":self.row=[];self.row_link="";self.row_title=""
            if self.row is not None and tag in ("td","th"):self.cell=[]
            if self.cell is not None and tag=="a":
                a=dict(attrs);href=html.unescape(a.get("href",""))
                if "lsInfoP.do?" in href:self.row_link=href
                label=a.get("title","").removesuffix(" 팝업으로 이동").strip()
                if label and len(label)>4:self.row_title=label
        def handle_data(self,data):
            if self.cell is not None:self.cell.append(data)
        def handle_endtag(self,tag):
            if tag in ("td","th") and self.row is not None and self.cell is not None:
                self.row.append(clean("".join(self.cell)));self.cell=None
            if tag=="tr" and self.row is not None:
                if len(self.row)>=8:self.rows.append((self.row,self.row_link,self.row_title))
                self.row=None
    raw=download("https://www.law.go.kr/LSW/nwRvsLsPop.do",timeout=18)
    parser=Rows();parser.feed(raw.decode("utf-8","replace"))
    laws=[]
    for row,href,full_title in parser.rows:
        for start in range(len(row)-7):
            candidate=row[start:start+8]
            index,title,ministry,change,law_type,number,published,effective=candidate
            if full_title and len(full_title)>len(title):title=full_title
            if not (re.fullmatch(r"\d+",index) and any(t in change for t in VALID_REVISIONS)):
                continue
            promulgated=date_str(published)
            if not promulgated or not title or not ministry or not number:continue
            unique=digest(title+"|"+number+"|"+promulgated)
            laws.append({"id":"pub:"+unique,"mst":"","title":title,
                "promulgated_at":promulgated,"promulgation_number":number,
                "effective_date":date_str(effective),"revision":change,
                "ministry":ministry,"law_type":law_type,
                "url":urllib.parse.urljoin("https://www.law.go.kr/LSW/nwRvsLsPop.do",href) if href.startswith("lsInfoP.do?") else "https://www.law.go.kr/LSW/nwRvsLsPop.do",
                "public_metadata_only":True})
            break
    dedup={(x["id"],x["effective_date"]):x for x in laws}
    return sorted(dedup.values(),key=lambda x:x["promulgated_at"],reverse=True)[:limit]


def public_amendment(law):
    """Read the official public promulgated amendment (reason + operative directives).
    No API credential required. This does NOT imply that full historical clauses
    have been compared; amendment instructions are recorded as amendment evidence.
    """
    from html.parser import HTMLParser
    from urllib.parse import parse_qs, urlparse
    seq=parse_qs(urlparse(law.get("url","")).query).get("lsiSeq",[""])[0]
    if not seq.isdigit():raise ValueError("개별 공포법령 일련번호 미확인")
    uri="https://www.law.go.kr/LSW/lsRvsDocInfoR.do?lsiSeq="+seq+"&chrClsCd=010202"
    source=download(uri,timeout=16,max_bytes=400000).decode("utf-8","replace")
    class Body(HTMLParser):
        def __init__(self):super().__init__();self.parts=[];self.skip=0
        def handle_starttag(self,tag,attrs):
            if tag in ("style","script"):self.skip+=1
            if not self.skip and tag in ("p","br","tr","li"):self.parts.append("\n")
        def handle_endtag(self,tag):
            if tag in ("style","script"):self.skip=max(0,self.skip-1)
        def handle_data(self,txt):
            if not self.skip:self.parts.append(txt)
    parser=Body();parser.feed(source)
    raw="".join(parser.parts)
    normalized=clean(raw)
    if "【제정·개정문】" not in normalized:raise ValueError("공식 제정·개정문 본문 부재")
    reason=normalized.split("【제정·개정이유】",1)[-1].split("【제정·개정문】",1)[0].strip()
    document=normalized.split("【제정·개정문】",1)[-1].strip()
    if not document:raise ValueError("공포 개정문이 비어 있음")
    return {"reason":reason[:3000],"document":document[:16000],"url":uri}

def public_amendment_diffs(law,material):
    """Extract explicit amendment instructions, never invent a previous clause."""
    doc=material["document"].split("부칙",1)[0]
    # Clause revisions, and annex/form replacement instructions.
    starts=list(re.finditer(r"제\d+조(?:의\d+)?|별표\s*\d+|별지\s*제?\d+호",doc))
    excerpts=[]
    for i,m in enumerate(starts):
        end=starts[i+1].start() if i+1<len(starts) else len(doc)
        sentence=clean(doc[m.start():end])
        # Ignore references/short fragments and preserve text directly from official document.
        if len(sentence)<18 or not re.search(r"개정|신설|삭제|한다|추가|대체|변경|각각|전환",sentence):continue
        if sentence in [x["after"] for x in excerpts]:continue
        label=m.group(0)
        change_kind="신설" if "신설" in sentence else "삭제" if "삭제" in sentence else "개정"
        # Only quote a before/after pair if it is EXPLICIT in the amendment direction.
        quoted=re.search(r'[“"]([^”“"]{2,170})[”"]\s*(?:을|를|에서)\s*[“"]([^”“"]{2,170})[”"]\s*(?:로|으로)',sentence)
        old=quoted.group(1) if quoted else ""
        replacement=quoted.group(2) if quoted else sentence[:1050]
        excerpts.append({"id":digest(law["id"]+law["promulgated_at"]+label+sentence),
                         "article":label,"title":"공식 개정문","type":change_kind,
                         "before":old,"after":replacement,
                         "context":material["reason"][:1600],
                         "directive":sentence[:1700],
                         "source_url":material["url"],"diff":[]})
        if len(excerpts)>=22:break
    if not excerpts and len(doc)>=35 and re.search(r"일부개정|전부개정|신설|삭제|개정한다",doc):
        excerpts.append({"id":digest(law["id"]+law["promulgated_at"]+"개정문"),
                         "article":"개정문","title":"공식 개정문","type":"개정",
                         "before":"","after":doc[:1150],"context":material["reason"][:1600],
                         "directive":doc[:1700],"source_url":material["url"],"diff":[]})
    return excerpts

def previous_mst(law):
    # Historical/previous versions are queried for the SAME stable law ID.
    root=api_request("lawSearch.do",target="eflaw",LID=law["id"],nw="1,2,3",
                     sort="ddes",display=100,page=1)
    records=[]
    for n in root.iter():
        if n.tag.split("}")[-1]!="law":continue
        obj=record_from_law(n)
        if obj and obj["id"]==law["id"]:
            records.append(obj)
    records.sort(key=lambda p:(p["promulgated_at"],p["promulgation_number"]),reverse=True)
    try:
        i=next(k for k,r in enumerate(records) if r["mst"]==law["mst"])
        return next((r["mst"] for r in records[i+1:] if r["mst"]!=law["mst"]),None)
    except StopIteration:
        return next((r["mst"] for r in records if r["promulgated_at"]<law["promulgated_at"]),None)
def article_map(mst):
    root=api_request("lawService.do",target="law",MST=mst)
    items={}
    for node in root.iter():
        if node.tag.split("}")[-1]!="조문단위":continue
        number=xml_field(node,"조문번호")
        branch=xml_field(node,"조문가지번호")
        label="제"+number+"조"+("의"+branch if branch and branch!="0" else "")
        if not number:continue
        title=xml_field(node,"조문제목")
        body=xml_field(node,"조문내용")
        # Only text owned by this single article; child paragraphs have legal force too.
        para=[clean("".join(e.itertext())) for e in node.iter()
              if e.tag.split("}")[-1] in ("항내용","호내용","목내용")]
        text=clean(" ".join([body]+para))
        if text:items[label]={"heading":title,"text":text[:10000]}
    return items
def classify_differences(old,new,law):
    out=[]
    for article in sorted(set(old)|set(new)):
        previous=old.get(article,{}).get("text","")
        updated=new.get(article,{}).get("text","")
        if previous==updated:continue
        typ="신설" if not previous else "삭제" if not updated else "변경"
        delta=list(difflib.ndiff([previous],[updated]))
        out.append({"id":digest(law["id"]+law["promulgated_at"]+article),
                    "article":article,"title":new.get(article,old.get(article,{})).get("heading",""),
                    "type":typ,"before":previous,"after":updated,
                    "source_url":law["url"],"diff":delta[:4]})
    return out[:80]
def infer_affected_roles(text,law):
    roles=[{"name":law["ministry"] or "소관부처 확인 필요",
            "role":"법령 소관·정책 총괄","level":"소관부처","confidence":"공식 법령 소관 정보"}]
    for role,aliases,level in ROLES:
        if any(p in text for p in aliases):
            roles.append({"name":role,"role":"해당 조문의 법정 업무 수행기관",
                          "level":level,"confidence":"변경 조문에 업무주체 명시"})
    # No invented lists of 226 municipalities or presumed public-agency assignments.
    return roles
def actions_from_diff(law,diffs):
    actions=[]
    today=NOW().date()
    for difference in diffs:
        joined=(difference["after"] or difference["before"])+(difference.get("context","") or "")
        roles=infer_affected_roles(joined,law)
        for rule in TASK_RULES:
            if not any(x in joined for x in rule["phrases"]):continue
            for role in roles:
                eid=digest(difference["id"]+role["name"]+rule["id"])
                future=bool(law["effective_date"] and law["effective_date"]>today.isoformat())
                actions.append({
                    "id":eid,"event_id":digest(law["id"]+law["promulgated_at"]+law["promulgation_number"]),
                    "law_title":law["title"],"law_id":law["id"],"change_date":law["promulgated_at"],
                    "ministry":law["ministry"],"agency":role["name"],"agency_level":role["level"],
                    "agency_role":role["role"],"agency_basis":role["confidence"],
                    "work":rule["operation"],"category":rule["category"],
                    "service":law["title"]+" 관련 법정 업무 (개별 서비스 추가 확인 필요)",
                    "required_change":rule["requirement"]+(" · 개정 지시: "+difference.get("directive","")[:250] if difference.get("directive") else ""),
                    "article":difference["article"],"before":difference["before"][:4000],
                    "after":difference["after"][:4000],"change_type":difference["type"],
                    "effective_date":law["effective_date"],"basis":difference.get("source_url",law["url"]),
                    "status":"시행 예정" if future else "반영 확인 필요",
                    "status_evidence":None,"status_checked_at":None,
                    "confidence":"공식 변경 문서 기반 기능 검토 대상",
                    "note":"조문에서 해당 업무 유형을 확인했습니다. 개별 사업·기관의 적용 관계는 추가 공식 근거가 있어야 확정됩니다."})
    # Duplicate tasks only by stable issue id, never by one common keyword.
    return list({a["id"]:a for a in actions}.values())
def changes_for(law,previous_snapshots=None):
    latest=article_map(law["mst"])
    if not latest:raise ValueError("조문을 찾지 못함")
    prior={}
    if previous_snapshots and previous_snapshots.get("mst")!=law["mst"]:
        prior=previous_snapshots.get("articles",{})
    if not prior:
        older=previous_mst(law)
        if older:prior=article_map(older)
    diffs=classify_differences(prior,latest,law) if prior else []
    return latest,diffs
def event_record(law,diffs,has_previous):
    return {**law,"event_id":digest(law["id"]+law["promulgated_at"]+law["promulgation_number"]),
            "change_count":len(diffs),"article_differences":diffs,
            "comparison_status":"신구 조문 대조 완료" if has_previous else "종전 조문 미확보",
            "source":"법제처 국가법령정보센터"}
def main():
    STATE.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    state=read_json(STATE,{"snapshots":{},"events":[],"actions":[]})
    now=stamp()
    health={"generated_at":now,"collector":"국가법령정보센터 공식 공포일·연혁·조문 API",
            "source_status":"확인 중","error":None,"partial":False,"compared":0,"official_records":0}
    laws=[]
    try:
        laws=official_laws(limit=70)
        if not laws:raise ValueError("공식 법령 목록에서 유효한 제·개정 법령을 얻지 못했습니다")
        health["source_status"]="정상"
    except Exception as exc:
        health["source_status"]="수집 실패"
        health["error"]=str(exc)[:220]
        # Official public promulgation index works without an API account,
        # but its entries do not contain authenticated before/after articles.
        try:
            laws=public_law_list(limit=30)
            if laws:
                health["source_status"]="메타데이터만 연결"
                health["error"]="법령 공포 목록은 확인했지만 종전·변경 조문 비교에는 LAW_OC API 인증이 필요합니다."
        except Exception as source_error:
            health["fallback_error"]=type(source_error).__name__
    health["official_records"]=len(laws)
    snapshots=state.get("snapshots",{})
    events={e["event_id"]:e for e in state.get("events",[]) if e.get("event_id")}
    actions={a["id"]:a for a in state.get("actions",[]) if a.get("id")}
    # Inspect the newest legal events, rotating to distribute requests across the coverage.
    cursor=int(state.get("cursor",0))
    selected=([laws[0]] if laws else [])+(laws[cursor:cursor+6] if laws else [])
    selected=list({(x.get("mst") or x["id"]):x for x in selected}.values())
    health["partial"]=bool(len(laws)>len(selected))
    health["errors"]=[]
    health["amendments_read"]=0
    for law in laws:
        if law.get("public_metadata_only"):
            eid=digest(law["id"]+law["promulgated_at"]+law["promulgation_number"])
            # Replace obsolete truncated-title rows from an older version of the parser.
            for previous_id,previous in list(events.items()):
                if previous_id==eid or not previous.get("public_metadata_only"):continue
                if (previous.get("promulgation_number")==law["promulgation_number"]
                      and previous.get("promulgated_at")==law["promulgated_at"]
                      and previous.get("ministry")==law["ministry"]
                      and previous.get("effective_date")==law["effective_date"]):
                    del events[previous_id]
            old=events.get(eid)
            if not old or not old.get("article_differences"):
                events[eid]=event_record(law,[],False)
    # Public amendment documents are retrieved independently of the authenticated API.
    public_selected=[law for law in selected if law.get("public_metadata_only")]
    documents={}
    with ThreadPoolExecutor(max_workers=6) as pool:
        work={pool.submit(public_amendment,law):law for law in public_selected}
        for job,law in work.items():
            try:documents[law["id"]]=job.result()
            except Exception as exc:
                health["errors"].append({"law":law["title"],"reason":type(exc).__name__})
    for law in selected:
        if law.get("public_metadata_only"):
            event_id=digest(law["id"]+law["promulgated_at"]+law["promulgation_number"])
            material=documents.get(law["id"])
            if material:
                diffs=public_amendment_diffs(law,material)
                evt=event_record(law,diffs,False)
                evt["comparison_status"]="공식 개정문 분석 완료 · 신구 전체조문 별도 대조"
                evt["amendment_reason"]=material["reason"]
                evt["amendment_url"]=material["url"]
                evt["amendment_document"]=material["document"][:9000]
                events[event_id]=evt
                health["amendments_read"]+=1
                for task in actions_from_diff(law,diffs):
                    if task["id"] in actions:
                        previous=actions[task["id"]]
                        for field in ("status","status_evidence","status_checked_at"):
                            if previous.get(field):task[field]=previous[field]
                    actions[task["id"]]=task
            continue
        event_id=digest(law["id"]+law["promulgated_at"]+law["promulgation_number"])
        try:
            latest,diffs=changes_for(law,snapshots.get(law["id"]))
            has_previous=bool(diffs) or snapshots.get(law["id"],{}).get("mst")!=law["mst"] and bool(snapshots.get(law["id"],{}).get("articles"))
            snapshots[law["id"]]={"mst":law["mst"],"articles":latest,"retrieved_at":now}
            evt=event_record(law,diffs,has_previous)
            # Preserve a previously verified comparison when re-fetching the same revision.
            prev=events.get(event_id)
            if prev and prev.get("comparison_status")=="신구 조문 대조 완료" and not diffs:evt=prev
            events[event_id]=evt
            health["compared"]+=1
            for task in actions_from_diff(law,diffs):
                if task["id"] in actions:
                    # Status history takes priority over new inference.
                    older=actions[task["id"]]
                    for key in ("status","status_evidence","status_checked_at"):
                        if older.get(key):task[key]=older[key]
                actions[task["id"]]=task
        except Exception as exc:
            health["errors"].append({"law":law["title"],"reason":type(exc).__name__})
    if health["amendments_read"] and health["source_status"]=="메타데이터만 연결":
        health["source_status"]="공식 공포·개정문 연결"
        health["error"]="제·개정문과 변경 지시사항을 확보했습니다. 이전 전체 조문과 기관별 실제 조치 여부까지는 검증되지 않았습니다."
    if laws:cursor=(cursor+6)%len(laws)
    sorted_events=sorted(events.values(),key=lambda e:(e.get("promulgated_at",""),e.get("event_id","")),reverse=True)[:300]
    sorted_actions=sorted(actions.values(),key=lambda a:(a.get("change_date",""),a.get("id","")),reverse=True)[:1200]
    counts={k:sum(x["status"]==k for x in sorted_actions) for k in ("조치 확인","미조치 확인","반영 확인 필요","시행 예정")}
    health["data_scope"]={"events":len(sorted_events),"actions":len(sorted_actions),
                           "agencies_named":len(set(a["agency"] for a in sorted_actions)),
                           "source_checked":health["compared"],"all_changes_scanned":False}
    payload={"schema":"policy-domino-next-v1","generated_at":now,"health":health,
             "events":sorted_events,"actions":sorted_actions,"status_counts":counts,
             "disclaimer":"개별 서비스·시스템과 실제 조치 여부는 공식 관계·확인근거가 있을 때만 확정. 내부문서·내부시스템 접근 없음."}
    OUTPUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    STATE.write_text(json.dumps({"cursor":cursor,"snapshots":snapshots,
                       "events":sorted_events,"actions":sorted_actions},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"source":health["source_status"],"official_records":len(laws),
                       "compared":health["compared"],"events":len(sorted_events),
                       "actions":len(sorted_actions),"errors":health["errors"]},ensure_ascii=False))
if __name__=="__main__":main()
