"""Narrow agency identification: one changed provision, one proved statutory duty.

No keyword overlap across unrelated articles or descriptions is sufficient.
"""
from __future__ import annotations
from v3 import evidence_gate

def assign(event,clauses):
    if evidence_gate.is_repeal(event):return []
    # Only changed articles provide a traceable source for an obligation.
    # Unchanged articles may help human research but are not independent proof
    # that another agency must change its operation.
    changes=event.get("changes",[])
    by_article={}
    for effect in event.get("effects",[]):
        by_article.setdefault(effect.get("article",""),[]).append(effect)
    existing={(a.get("agency"),a.get("article"),a.get("work"))
              for a in event.get("institution_actions",[])}
    output=[]
    seen=set()
    for change in changes:
        article=change.get("article","")
        if article not in clauses:continue
        # The stored official source must agree with the changed clause.
        current=clauses.get(article,"")
        if not current or (change.get("after") and current.strip()!=change["after"].strip()):
            continue
        for effect in by_article.get(article,[]):
            for actor in evidence_gate.action_for_change(event,change,effect):
                key=(actor["agency"],actor["article"],actor["work"])
                if key in existing or key in seen:continue
                seen.add(key)
                output.append(actor)
    return output[:32]
