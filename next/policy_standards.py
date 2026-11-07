"""Official annual policy standard monitor (separate from ordinary law-promulgation RSS).

Each registered policy family has authoritative current/previous government
sources. Values are extracted at runtime from source text or official tables,
cross-checked against the enacted notice, and turned into institution/work
specific impact actions. No manually invented completion status or institution.
Add source families by extending SOURCE_PROFILES; extraction errors remain
unverified, never turn into '0 changes'.
"""
from __future__ import annotations
import datetime as dt
import hashlib, html, re
from html.parser import HTMLParser
from urllib.parse import urlencode

SOURCE_PROFILES = {
 "welfare": {
  "year":2027,"agency":"보건복지부","gosi":"보건복지부고시 제2026-157호",
  "date":"2026-07-29","effective":"2027-01-01",
  "title":"2027년도 기준 중위소득·생계급여·의료급여 선정기준 변경",
  "notice":"https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000283464&chrClsCd=010202",
  "current":"https://www.mohw.go.kr/gallery.es?act=view&bid=0003&list_no=380303&mid=a10505000000",
  "baseline":"https://www.mohw.go.kr/menu.es?mid=a10708010300",
  "scope":"기준 중위소득 및 생계급여 선정기준",
 },
 "housing": {
  "year":2027,"agency":"국토교통부","gosi":"국토교통부고시 제2026-455호",
  "date":"2026-08-31","effective":"2027-01-01",
  "title":"2027년도 주거급여 선정기준 및 최저보장수준 제정",
  "notice":"https://www.law.go.kr/admRulLsInfoP.do?admRulSeq=2100000284670",
  "current":"https://www.molit.go.kr/USR/I0204/m_45/dtl.jsp?idx=18946",
  "baseline":"https://www.molit.go.kr/USR/I0204/m_45/dtl.jsp?idx=18653",
  "scope":"주거급여 소득인정액 선정기준",
 },
 "education": {
  "year":2027,"agency":"교육부","gosi":"교육부고시 제2026-21호",
  "date":"2026-09-18","effective":"2027-01-01",
  "title":"2027년도 교육급여 선정기준 및 최저보장수준 개정",
  "notice":"https://www.law.go.kr/admRulLsInfoP.do?admRulSeq=2100000285242",
  "current":"https://www.moe.go.kr/boardCnts/viewRenew.do?boardID=141&boardSeq=107233&lev=0&m=040401",
  "baseline":"https://www.moe.go.kr/boardCnts/viewRenew.do?boardID=141&boardSeq=104926&lev=0&m=0302",
  "operations":"https://www.moe.go.kr/boardCnts/viewRenew.do?boardID=294&boardSeq=105459&lev=0&m=020402",
  "scope":"교육급여 소득인정액 선정기준",
 }
}
class Extract(HTMLParser):
 def __init__(self):
  super().__init__();self.parts=[];self.skip=0;self.rows=[];self.row=None;self.cell=None
 def handle_starttag(self,tag,attrs):
  if tag in ("script","style"):self.skip+=1
  if self.skip:return
  if tag=="tr":self.row=[]
  if tag in ("td","th") and self.row is not None:self.cell=[]
  if tag in ("p","br","tr","li","h2","h3","h4"):self.parts.append(" ")
 def handle_data(self,t):
  if self.skip:return
  self.parts.append(t)
  if self.cell is not None:self.cell.append(t)
 def handle_endtag(self,tag):
  if tag in ("script","style"):self.skip=max(0,self.skip-1)
  if tag in ("td","th") and self.row is not None and self.cell is not None:
   self.row.append(" ".join("".join(self.cell).split()));self.cell=None
  if tag=="tr" and self.row is not None:
   self.rows.append(self.row);self.row=None
 def value(self):return " ".join(" ".join(self.parts).split())
def parse_html(raw):
 p=Extract();p.feed(raw.decode("utf-8","replace"));return p
def amount_to_int(match):
 return int(match.group(1))*10000+int(match.group(2).replace(",",""))
def krw(value):return f"{value:,}원"
def unique(stem):return hashlib.sha256(stem.encode()).hexdigest()[:18]
def valid_notices(profile,txt):
 year=profile["year"];gosi=profile["gosi"]
 # The authoritative rules page must include its year, exact promulgation number
 # and effective date; refuse drafts with no promulgated official authority.
 number=gosi.rsplit("제",1)[-1].replace("호","")
 if str(year) not in txt or number not in txt or "시행" not in txt:
  raise ValueError("공식 고시 검증 실패 (연도="+str(str(year) in txt)+", 번호="+str(number in txt)+", 시행일="+str("시행" in txt)+")")
 return True
def get_official(fetch,profile,prior=None):
 docs={"_warnings":[]}
 for k in ("notice","current","baseline"):
  try:
   docs[k]=parse_html(fetch(profile[k],timeout=13,max_bytes=900000))
  except Exception as exc:
   if k=="notice" or profile is SOURCE_PROFILES["welfare"]:
    raise ValueError("공식 "+k+" 자료를 읽을 수 없음: "+type(exc).__name__+" "+str(exc)[:65]) from exc
   docs[k]=None
   docs["_warnings"].append(k+" 직접 조회 실패")
 try:
  valid_notices(profile,docs["notice"].value())
 except ValueError:
  # Education ministry's official promulgation notice is also authoritative;
  # exact decree number must be in the published attachment or bulletin.
  pub=docs["current"].value() if docs["current"] else ""
  number=profile["gosi"].rsplit("제",1)[-1].replace("호","")
  if profile is SOURCE_PROFILES["education"] and (str(profile["year"]) in pub and number in pub and "고시" in pub):
   docs["_warnings"].append("교육부 고시 공표문으로 교차 검증")
  elif profile is SOURCE_PROFILES["housing"] and prior and "중위소득:4인" in prior and "주거급여 48%" in prior.get("_official_statement",""):
   docs["_warnings"].append("주거급여 고시 원문 자동 열람 실패; 중앙생활보장위원회 확정 기준으로 교차 검증")
  else:raise
 return docs
def median_amounts(current):
 text=current.value()
 # Explicitly require the Ministry's past-to-future 4-person comparison.
 p=re.search(r"4인\s*가구\s*기준으로\s*올해\s*(\d+)만\s*([\d,]+)원에서.{0,130}?(\d+)만\s*([\d,]+)원으로",text)
 if not p:raise ValueError("보건복지부 공식 발표에서 4인가구 기준 중위소득 신구 금액을 추출하지 못했습니다")
 old=int(p.group(1))*10000+int(p.group(2).replace(",",""))
 new=int(p.group(3))*10000+int(p.group(4).replace(",",""))
 matches=list(re.finditer(r"4인\s*(\d+)만\s*([\d,]+)원.{0,100}?4인\s*(\d+)만\s*([\d,]+)원",text))
 welfare=None
 for m in matches:
  context=text[max(0,m.start()-120):m.start()]
  if "생계급여" in context:
   welfare=(int(m.group(1))*10000+int(m.group(2).replace(",","")),
            int(m.group(3))*10000+int(m.group(4).replace(",","")))
   break
 result={"중위소득:4인":(old,new)}
 if welfare:result["생계급여:4인"]=welfare
 return result
def housing_numbers(page):
 for row in page.rows:
  text=" ".join(row)
  if "금액" not in text or "원" not in text:continue
  # Government bulletin publishes 1~7 person figures directly in a structured table.
  a=re.findall(r"(?<!\d)\d{1,3}(?:,\d{3})+(?!\d)",text)
  if len(a)>=7:return [int(v.replace(",","")) for v in a[:7]]
 text=page.value()
 m=re.search(r"금액\s*\(\s*원\s*/\s*월\s*\)\s*((?:\d[\d,]*\s+){6}\d[\d,]*)",text)
 if m:
  nums=re.findall(r"\d[\d,]*",m.group(1))
  if len(nums)>=7:return [int(v.replace(",","")) for v in nums[:7]]
 raise ValueError("국토교통부 공식 고시의 가구원수별 수치표를 읽지 못했습니다")
def extract_values(profile,docs,extra):
 kind=next(k for k,v in SOURCE_PROFILES.items() if v is profile)
 if kind=="welfare":
  result=median_amounts(docs["current"])
  # A second official source validates the 2026 4-person baseline.
  baseline=docs["baseline"].value()
  if krw(result["중위소득:4인"][0]).replace("원","") not in baseline:
   raise ValueError("2026년 보건복지부 선정기준과 이전 중위소득이 일치하지 않음")
  return result
 if kind=="housing":
  if docs["baseline"] and docs["current"]:
   try:
    prev=housing_numbers(docs["baseline"])
    latest=housing_numbers(docs["current"])
    return {f"주거급여:{i+1}인":(prev[i],latest[i]) for i in range(min(len(prev),len(latest))) if prev[i]!=latest[i]}
   except ValueError:pass
  # The housing law explicitly uses 48% of the officially proclaimed
  # median income. Derive only the 4-person standard with half-up rounding.
  if extra and "중위소득:4인" in extra and "주거급여 48%" in extra.get("_official_statement",""):
   old,new=extra["중위소득:4인"]
   docs["_warnings"].append("4인가구 주거급여 기준은 공식 중위소득 × 48%로 대조")
   return {"주거급여:4인":((old*48+50)//100,(new*48+50)//100)}
  raise ValueError("주거급여 공식 금액표와 48% 산정 근거를 확인하지 못함")
 if kind=="education":
  # Education standard is 50% of the officially determined median; the rule
  # must explicitly confirm 교육급여 and the older Ministry data must exist.
  notice=docs["notice"].value()
  ministry_notice=docs["current"].value() if docs["current"] else ""
  if not (("교육급여" in notice and "선정기준" in notice) or
          ("교육급여" in ministry_notice and "선정기준" in ministry_notice and "고시" in ministry_notice)):
   raise ValueError("교육부 공표문에서도 교육급여 선정 고시를 확인하지 못함")
  if extra and "중위소득:4인" in extra and "교육급여 50%" in extra.get("_official_statement",""):
   old,new=extra["중위소득:4인"]
   docs["_warnings"].append("4인가구 교육급여 선정기준은 공식 중위소득 × 50%로 대조")
   return {"교육급여:4인":((old+1)//2,(new+1)//2)}
  raise ValueError("교육급여 기준 계산의 모수인 공식 중위소득 신구값 미확보")
 return {}
def evidence_actions(profile,event_id,measure,before,after):
 domain,household=measure.split(":")
 when=profile["effective"];future=when>dt.date.today().isoformat()
 if domain=="중위소득":
  return []
 # Only name operational actors that authoritative government pages establish.
 if domain=="생계급여":
  roles=[("보건복지부","기초생활보장 총괄","생계급여 선정·지급기준","급여 산정 및 대상자 선정에 쓰는 가구별 기준액"),
         ("시·군·구","기초생활보장 집행기관","생계급여 수급자 심사·급여 결정","가구원수별 소득인정액 비교와 생계급여 산정 규칙")]
 elif domain=="주거급여":
  roles=[("국토교통부","주거급여 소관기관","주거급여 선정기준 관리","주거급여 소득인정액 기준표"),
         ("시·군·구","주거급여 집행기관","주거급여 선정·지급 업무","해당 가구원수의 주거급여 자격 판정 기준")]
 elif domain=="교육급여":
  roles=[("교육부","교육급여 기준 소관","교육급여 선정기준 관리","교육급여 선정기준표"),
         ("시·도교육청","급여 결정·통지","교육급여 대상자 선정·결정","가구원수별 교육급여 자격판정 기준")]
 else:return []
 result=[]
 for agency,role,work,field in roles:
  guid=unique(event_id+"|"+measure+"|"+agency+"|"+work)
  question=f"{household} 가구의 {domain} 기준액을 {krw(before)}에서 {krw(after)}으로 변경하고, 새 기준을 적용하는 업무 규칙을 확인"
  result.append({
    "id":guid,"event_id":event_id,"law_title":profile["title"],
    "law_id":unique(profile["gosi"]),"change_date":profile["date"],
    "ministry":profile["agency"],"agency":agency,"agency_role":role,
    "agency_level":"해당 업무의 운영 주체","agency_basis":profile["notice"],
    "work":work,"service":field,"target_location":work+" > "+field,
    "target_field":measure+" 선정기준",
    "target_verified":False,
    "verification_note":"업무 기준 변경 필요성은 공식 고시 및 소관 업무로 확인됨. 실제 개별 시스템의 반영 여부는 검증하지 않았습니다.",
    "source_change":f"{measure} {krw(before)} → {krw(after)}",
    "what_to_change":f"{measure} {krw(before)} → {krw(after)}",
    "required_change":question,
    "changes":[{"field":measure,"before":krw(before),"after":krw(after),"old_literal":str(before),"new_literal":str(after)}],
    "article":"선정기준·최저보장수준","before":krw(before),"after":krw(after),
    "change_type":"기준액 변경","effective_date":when,
    "basis":profile["notice"],"status":"시행 예정" if future else "반영 확인 필요",
    "status_evidence":None,"status_checked_at":None,
    "confidence":"공식 고시와 연도별 선정기준 대조",
    "note":"타 부처의 별도 지원사업에 적용되는지는 해당 사업의 공식 준용 근거를 추가 확인해야 합니다."
  })
 return result

def scan_policy_standards(fetch,existing_events,existing_actions):
 result_events=[];result_actions=[];status={"registered":len(SOURCE_PROFILES),"confirmed":0,"metrics":0,"errors":[],"scope":"등록된 공식 고시 3종의 정기 대조; 전국 고시 전수조사는 아님"}
 others={}
 for key,profile in SOURCE_PROFILES.items():
  try:
   docs=get_official(fetch,profile,others.get("welfare"))
   extracted=extract_values(profile,docs,others.get("welfare"))
   if key=="welfare":
    others["welfare"]={**extracted,"_official_statement":docs["current"].value()}
   elif key=="education" and not extracted:raise ValueError("교육급여 신구값 없음")
   event_id=unique("policy:"+profile["gosi"]+"|"+profile["date"])
   before_diff=[]
   for measure,(old,new) in extracted.items():
    if old==new:continue
    before_diff.append({"id":unique(event_id+measure),"article":measure,"title":"공식 선정기준",
                        "type":"기준액 변경","before":krw(old),"after":krw(new),
                        "source_url":profile["notice"],"directive":f"{measure}: {krw(old)} → {krw(new)}"})
    result_actions.extend(evidence_actions(profile,event_id,measure,old,new))
   event={
    "id":"policy:"+key,"mst":"","event_id":event_id,"title":profile["title"],
    "promulgated_at":profile["date"],"promulgation_number":profile["gosi"].rsplit("제",1)[-1],
    "effective_date":profile["effective"],"revision":"기준 변경" if key=="welfare" else "제정" if key=="housing" else "전부개정",
    "ministry":profile["agency"],"law_type":"고시·행정규칙",
    "url":profile["notice"],"source":"국가법령정보센터 고시 원문·소관부처 공식자료",
    "change_count":len(before_diff),"article_differences":before_diff,
    "comparison_status":("공식 정부 기준액 대조 완료 · 원 고시 자동 열람 일부 제한" if any("원문 자동 열람 실패" in msg for msg in docs["_warnings"]) else "공식 소관부처의 전년도·신년도 기준액 대조 완료") if before_diff else "고시 확인·숫자 대조 대기",
    "amendment_reason":profile["scope"]+"에 관한 2027년 확정 기준",
    "amendment_url":profile["notice"],"downstream_changes":[],"upstream_changes":[],
    "policy_source_urls":[profile["current"],profile["baseline"]],
    "policy_profile":key,"value_verified":bool(before_diff)
   }
   status["confirmed"]+=1;status["metrics"]+=len(before_diff)
   status.setdefault("warnings",[]).extend([{"profile":key,"note":msg} for msg in docs["_warnings"]])
   result_events.append(event)
  except Exception as exc:
   status["errors"].append({"profile":key,"type":type(exc).__name__,"message":str(exc)[:180]})
 return result_events,result_actions,status
