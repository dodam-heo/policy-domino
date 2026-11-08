"""Audit the already-published official differences and agency cards.

Read-only diagnostic; document titles are not registered as parser exceptions.
"""
import json,collections
from pathlib import Path
from v3 import impact
d=json.loads(Path("site/data.json").read_text("utf8"))
print("SCHEMA",d.get("schema"),"EVENTS",len(d.get("events",[])))
for e in d.get("events",[]):
    acts=e.get("institution_actions",[])
    if not acts:continue
    pair=collections.Counter((a.get("agency"),a.get("article"),a.get("work")) for a in acts)
    fragments=[a for a in acts if len(a.get("what_to_change",""))<90 and
               ("→" in a.get("what_to_change",""))]
    if len(acts)>=5 or any(n>=2 for n in pair.values()) or len(fragments)>=2:
        print("EVENT",json.dumps({"title":e["title"],"revision":e.get("revision"),
           "actions":len(acts),"unique_tasks":len(pair),
           "repeated":[[str(k),v] for k,v in pair.most_common(4) if v>=2],
           "action_samples":[{"agency":a.get("agency"),"article":a.get("article"),
              "work":a.get("work"),"change":a.get("what_to_change"),
              "excerpt":a.get("basis_excerpt","")[:130]} for a in acts[:5]]},
           ensure_ascii=False)[:3200])
        if any(n>=3 for n in pair.values()):
            for c in e.get("changes",[]):
                if any(a.get("article")==c.get("article") for a in acts):
                    print("CLAUSE_SAMPLE",json.dumps({"article":c.get("article"),
                      "before":c.get("before","")[:480],"after":c.get("after","")[:480]},
                      ensure_ascii=False)[:1200])
        if sum(1 for _ in ()):break
