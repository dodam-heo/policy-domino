"""Read-only on-repository audit for missing official changes and broken priority queues."""
import json
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
state=json.loads((ROOT/"data"/"v2_state.json").read_text("utf-8"))
published=json.loads((ROOT/"site"/"data.json").read_text("utf-8"))
records=state.get("events",{})
pending=state.get("pending",[])
events=published.get("events",[])
print("AUDIT_SCHEMA",published.get("schema"),"events",len(events),"record-cache",len(records),"pending",len(pending))
print("AUDIT_BACKLOG",json.dumps(Counter(x.get("source") for x in pending),ensure_ascii=False))
print("AUDIT_TYPES",json.dumps(Counter((x.get("impact_category"),x.get("source")) for x in events).most_common(14),ensure_ascii=False))
def sample(x):
 return {"name":x.get("title"),"ministry":x.get("ministry"),"source":x.get("source"),
 "event_id":x.get("id"),"date":x.get("promulgated_at",x.get("published_at")),
 "comparison":x.get("comparison_status"),"category":x.get("impact_category"),
 "effects":len(x.get("effects",[])),"actors":len(x.get("institution_actions",[])),
 "candidates":len(x.get("agency_candidates",[]))}
def matches(x):
 s=x.get("title","")
 return ("2027" in s or "기준 중위소득" in s or "주거급여" in s or "교육급여" in s)
for where,items in [("pending",pending),("records",list(records.values())),("published",events)]:
 picked=[sample(x) for x in items if matches(x)]
 print("AUDIT_YEAR_STANDARDS_"+where.upper(),len(picked),json.dumps(picked[:32],ensure_ascii=False))
print("AUDIT_TOP_PUBLISHED",json.dumps([sample(x) for x in events[:24]],ensure_ascii=False))
print("AUDIT_DEFAULT_VISIBLE",json.dumps([sample(x) for x in events if x.get("impact_category")=="제도·업무 변경" and x.get("effects")][:24],ensure_ascii=False))
if published.get("schema")!="policy-domino-impact-v3":raise SystemExit("unexpected schema")

import datetime as dt
today=dt.date(2026,11,8)
for source in ("law","admrul"):
 rows=[x for x in pending if x.get("source")==source]
 priorities=[x for x in rows if "2027" in x.get("title","") or x.get("effective_date","")>today.isoformat()]
 n=12
 chosen=priorities[:6]+[x for x in rows if x not in priorities[:6]][:6]
 print("AUDIT_PRIORITY_"+source.upper(),json.dumps([
  {"title":x["title"],"date":x["published_at"],"effective":x.get("effective_date")} for x in chosen],ensure_ascii=False))
print("AUDIT_FUTURE_QUEUE",sum(x.get("effective_date","")>today.isoformat() for x in pending))

from v2.collector import select_pending, priority_score, uid
pmap={uid(x["source"],x["stable_id"],x["serial"]):x for x in pending}
for kind in ("law","admrul"):
 rows=select_pending(pmap,kind,12,dt.date(2026,11,8))
 print("AUDIT_NEW_SELECTION_"+kind.upper(),json.dumps([
 {"name":r["title"],"score":priority_score(r,dt.date(2026,11,8)),"date":r["published_at"]}
 for _,r in rows],ensure_ascii=False))
