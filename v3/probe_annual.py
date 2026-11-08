"""Live official-API regression probe. No synthetic event injection."""
from v2.collector import list_source,read_clauses,historical_predecessor,compare,request,row_of
from collections import defaultdict
import json,time
def show(title,record):
 print("PROBE",title,json.dumps({k:record.get(k) for k in
 ["title","source","serial","stable_id","published_at","effective_date","ministry"]},ensure_ascii=False),flush=True)
 try:
  current=read_clauses(record)
  print("PROBE_DETAIL",title,"clauses",len(current),"size",sum(len(x) for x in current.values()),"sample",str(list(current.items())[:1])[:160],flush=True)
  try:
   prior=historical_predecessor(record)
   print("PROBE_PRIOR",title,"exists",bool(prior),
         "prior",prior.get("record",{}).get("title") if prior else None,
         "annual",prior.get("annual_comparison") if prior else None,flush=True)
   if prior:
    changed=compare(prior["clauses"],current,record)
    print("PROBE_DIFF",title,"changes",len(changed),
          "first",str([(x['article'],x['before'][:50],x['after'][:50]) for x in changed[:2]])[:350],flush=True)
  except Exception as ex:print("PROBE_HISTORY_ERROR",title,type(ex).__name__,str(ex)[:250],flush=True)
 except Exception as ex:print("PROBE_DETAIL_ERROR",title,type(ex).__name__,str(ex)[:250],flush=True)
def main():
 import datetime as dt
 try:
  today=dt.date.today()
  found=list_source("admrul",limit=350,title_query=str(today.year+1),
          date_window=(today-dt.timedelta(days=210),today),fulltext=True)
  wanted=[r for r in found if "중위소득" in r["title"] or "교육급여" in r["title"] or "주거급여" in r["title"]]
  print("PROBE_FULLTEXT_WINDOW",json.dumps([{"title":x["title"],"date":x["published_at"]} for x in found[:3]+found[-3:]],ensure_ascii=False),flush=True)
  print("PROBE_FULLTEXT_YEAR",len(found),json.dumps(
   [{"name":x["title"],"effective":x.get("effective_date"),
     "date":x.get("published_at")} for x in wanted],ensure_ascii=False),flush=True)
 except Exception as ex:print("PROBE_FULLTEXT_YEAR_ERROR",type(ex).__name__,str(ex)[:300],flush=True)

 try:
  root=request("admrul",nw="1",sort="efdes",display=100,page=1)
  rows=[row_of(n,"admrul") for n in root.iter() if n.tag.split("}")[-1].lower()=="admrul"]
  rows=[x for x in rows if x]
  print("PROBE_EFFECTIVE_SORT",json.dumps([{"title":x["title"],"effective":x["effective_date"]} for x in rows[:15]],ensure_ascii=False),flush=True)
  print("PROBE_MEDIAN_FUTURE",json.dumps([x["title"] for x in rows if "중위소득" in x["title"]],ensure_ascii=False),flush=True)
 except Exception as ex: print("PROBE_EFFECTIVE_SORT_ERROR",type(ex).__name__,str(ex)[:200],flush=True)
 try:
  mid=list_source("admrul",limit=250,title_query=str(today.year+1),
       date_window=(dt.date(today.year,7,1),dt.date(today.year,7,31)),fulltext=True)
  print("PROBE_MONTH_YEAR",len(mid),json.dumps([x["title"] for x in mid if "중위소득" in x["title"]][:5],ensure_ascii=False),flush=True)
 except Exception as ex:print("PROBE_MONTH_YEAR_ERROR",type(ex).__name__,str(ex)[:200],flush=True)
 tests=[("교육급여","2027년 교육급여"),("주거급여","2027년 주거급여"),("기준 중위소득","기준 중위소득")]
 for name,query in tests:
  try:
   rows=list_source("admrul",limit=70,title_query=query)
   print("PROBE_SEARCH",name,"rows",len(rows),"names",json.dumps([x["title"] for x in rows[:12]],ensure_ascii=False),flush=True)
   future=[x for x in rows if ("2027" in x["title"] or "2027" in x["effective_date"])]
   if future:show(name,future[0])
  except Exception as ex:print("PROBE_SEARCH_ERROR",name,type(ex).__name__,str(ex)[:250],flush=True)
if __name__=="__main__":main()
