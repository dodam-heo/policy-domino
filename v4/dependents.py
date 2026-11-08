"""V4 downstream document discovery and validation from OFFICIAL full text.

Search results are a queue of unverified documents. The only output that may
enter Policy Domino's confirmed impact edges is a re-read official document
containing the exact changed provision or genuinely changed standard formula.
Neither an API search hit nor a shared title may become a domino.
"""
from __future__ import annotations
import re,hashlib
from v2 import collector as api
from v4 import collect_index,relationships

SOURCES=("admrul","law","ordin")
MAX_TERMS=3
MAX_CANDIDATES=1000

def title_queries(parent):
    terms=[parent.get("title","")]
    terms.extend(relationships.changed_standards(parent))
    out=[]
    for t in terms:
        t=str(t).strip()
        if 6<=len(t)<=80 and t not in out:out.append(t)
    return out[:MAX_TERMS]

def search_lexical_candidates(parent,fetch=None,max_pages=1):
    """Bounded official full-text discovery. Not proof of impact."""
    fetch=fetch or api.request
    queue=[]
    failures=[]
    seen=set()
    for term in title_queries(parent):
        for source in SOURCES:
            for page in range(1,max_pages+1):
                try:
                    kw={"search":2,"query":term,"display":100,"page":page,"sort":"ddes"}
                    if source in ("admrul","ordin"):kw["nw"]="1"
                    root=fetch(source,**kw)
                    nodes=collect_index.tags(root,source)
                    for node in nodes:
                        rec=collect_index.as_record(node,source)
                        if not rec:continue
                        if rec["source"]==parent["source"] and rec["stable_id"]==parent["stable_id"]:
                            continue
                        key=(rec["source"],rec["serial"])
                        if key in seen:continue
                        seen.add(key)
                        rec["search_term"]=term
                        rec["search_provenance"]="official_fulltext_candidate"
                        queue.append(rec)
                        if len(queue)>=MAX_CANDIDATES:return queue,failures
                    if len(nodes)<100:break
                except Exception as exc:
                    failures.append({"source":source,"term":term,
                                     "error":type(exc).__name__+": "+str(exc)[:110]})
                    break
    return queue,failures

def document_key(doc):
    return doc["source"]+"|"+doc["serial"]

def enqueue(state,parent,found):
    queue=state.setdefault("dependent_queue",{})
    attempted=state.setdefault("dependent_checked",{})
    added=0
    for item in found:
        if not item.get("serial"):continue
        key=parent["id"]+"|"+document_key(item)
        if key in attempted or key in queue:continue
        queue[key]={"parent_id":parent["id"],"target":item}
        added+=1
    return added

def process(state,read_source,limit=12):
    """Prove real changed-article/formula use before creating an impact link."""
    pending=state.setdefault("dependent_queue",{})
    checked=state.setdefault("dependent_checked",{})
    confirmed=state.setdefault("confirmed_dependencies",{})
    failed=state.setdefault("dependent_errors",[])
    events=state.get("inspected",{})
    done=0
    for key,item in list(pending.items()):
        if done>=limit:break
        parent=events.get(item["parent_id"])
        if parent is None:
            pending.pop(key,None)
            continue
        target=item["target"]
        try:
            clauses=read_source(target)
            target_event={**target,"id":api.uid(target["source"],target["serial"]),
                "source":target["source"],"stable_id":target.get("stable_id",""),
                "serial":target["serial"]}
            edge=relationships.evaluate(parent,target_event,clauses)
            checked[key]={"verified":bool(edge and edge["affected_verified"]),
                "citation_only":bool(edge and not edge["affected_verified"])}
            if edge and edge["affected_verified"]:
                edge.update({
                    "source_title":parent["title"],"target_title":target["title"],
                    "target_url":target.get("url",""),
                    "target_ministry":target.get("ministry",""),
                    "reference_source":"공식 원문을 다시 조회하여 조항·산식 확인",
                    "target_serial":target["serial"]
                })
                confirmed[key]=edge
            pending.pop(key,None)
        except Exception as exc:
            attempts=item.get("attempts",0)+1
            item["attempts"]=attempts
            if attempts>=3:
                failed.append({"source":parent["id"],"target":target["title"],
                               "error":str(exc)[:170]})
                pending.pop(key,None)
        done+=1
    return {"attempted":done,"confirmed_total":len(confirmed),
            "queued":len(pending),"failures":len(failed)}

def seed_delegated(state,events):
    """Official delegated provisions are priority targets to validate,
    not independently verified change obligations.
    """
    candidates=state.get("delegation_links",{})
    for event in events:
        doc=candidates.get(event["id"],{})
        found=[]
        for entry in doc.get("links",[])[:80]:
            if not entry.get("serial") or entry["source"]=="public_rule":continue
            # The delegated endpoint supplies the exact document serial but
            # may omit its stable ID. The detailed official source resolves
            # the correct regulation version by that serial.
            found.append({
                "source":entry["source"],"serial":entry["serial"],
                "stable_id":"","title":entry["title"],
                "ministry":"","url":entry.get("url",""),
                "discovery_kind":"official_delegated_reference"
            })
        enqueue(state,event,found)

def search_and_process(state,read_source,max_parents=4,max_docs=12,fetch=None):
    relevant=[e for e in state.get("inspected",{}).values()
              if e.get("verification") in ("verified_changed_clauses",
                                           "verified_annual_replacement")
              and e.get("changes")]
    relevant.sort(key=lambda e:e.get("promulgated_at",""),reverse=True)
    searched=state.setdefault("dependent_search_completed",{})
    errors=[]
    seed_delegated(state,relevant)
    for parent in relevant:
        if max_parents<=0:break
        if parent["id"] in searched:continue
        found,failures=search_lexical_candidates(parent,fetch)
        errors.extend(failures)
        enqueue(state,parent,found)
        searched[parent["id"]]={"candidates":len(found),
                                "search_errors":len(failures),
                                "partial_search":True}
        max_parents-=1
    result=process(state,read_source,max_docs)
    result["search_errors"]=errors
    return result
