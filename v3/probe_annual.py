"""Live official-API regression probe. No synthetic event injection."""
from v2.collector import list_source,read_clauses,historical_predecessor,compare
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
 tests=[("교육급여","2027년 교육급여"),("주거급여","2027년 주거급여"),("기준 중위소득","기준 중위소득")]
 for name,query in tests:
  try:
   rows=list_source("admrul",limit=70,title_query=query)
   print("PROBE_SEARCH",name,"rows",len(rows),"names",json.dumps([x["title"] for x in rows[:12]],ensure_ascii=False),flush=True)
   future=[x for x in rows if ("2027" in x["title"] or "2027" in x["effective_date"])]
   if future:show(name,future[0])
  except Exception as ex:print("PROBE_SEARCH_ERROR",name,type(ex).__name__,str(ex)[:250],flush=True)
if __name__=="__main__":main()
