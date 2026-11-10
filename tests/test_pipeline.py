import unittest
import datetime as dt
from policy_domino.engine import pipeline,events

def r(n,date="2026-11-07",kind="law",nextyear=False,discovery=""):
    return {"source":kind,"stable_id":str(n),"serial":str(n*10),
            "title":"무작위 공식 기준 "+str(n),"published_at":date,
            "effective_date":"2027-01-01" if nextyear else date,
            "revision":"일부개정","kind":"법령","number":str(n),
            "ministry":"가상부처","url":"https://www.law.go.kr",
            "discovery_kind":discovery}

class PublicationSafeguards(unittest.TestCase):
    def test_bootstrap_is_not_automatically_impact_verified(self):
        state={"catalog":{events.key(r(1)):r(1)},"inspected":{},
               "coverage":[],"verified_snapshots":{}}
        d=pipeline.build(state,dt.date(2026,11,8))
        self.assertEqual(d["schema"],"policy-domino-v4")
        self.assertFalse(d["featured_events"])
        self.assertEqual(d["collection"]["pending_details"],1)
        self.assertFalse(d["collection"]["whole_corpus_complete"])

    def test_wrong_article_citations_not_counted_as_dependents(self):
        a=r(1);b=r(2)
        ea,eb=events.inspect(a,[],load=lambda x:{"제1조":"조항"},
                             history=lambda x,y:None,annual=lambda x:None)[0],None
        ea["verification"]="verified_changed_clauses"
        ea["changed_articles"]=["제35조"]
        ea["excerpts"]=[{"article":"제35조","before":"처리기한 30일",
                         "after":"처리기한 15일"}]
        ea["actors"]=[]
        eb=dict(ea,id=events.key(b),title=b["title"],stable_id=b["stable_id"],serial=b["serial"],
                verification="official_record_only",changed_articles=[],excerpts=[])
        state={"catalog":{events.key(a):a,events.key(b):b},
               "inspected":{ea["id"]:ea,eb["id"]:eb},
               "coverage":[],"verified_snapshots":{
                    eb["id"]:{"source":"law","stable_id":b["stable_id"],"serial":b["serial"],
                      "clauses":{"제1조":"「무작위 공식 기준 1」에 따라 업무를 수행한다."}}
                 }}
        d=pipeline.build(state,dt.date(2026,11,8))
        self.assertEqual(d["links"]["confirmed_provision_or_formula_use"],0)

    def test_official_history_beats_old_legacy_metadata_on_work_queue(self):
        current=dt.date(2026,11,8)
        xs=[r(1,date="2025-01-01",nextyear=False,discovery="legacy_index_only_not_verified"),
            r(2,date="2026-11-07",discovery="official_law_change_history"),
            r(3,date="2026-09-21",nextyear=True)]
        state={"catalog":{events.key(x):x for x in xs},"inspected":{}}
        picked=pipeline.pick_work(state,current,2)
        self.assertEqual(picked[0]["stable_id"],"2")
        self.assertIn(picked[1]["stable_id"],("3","2"))

    def test_official_index_is_visible_before_detail_without_fabricating_impact(self):
        sources=[r(i,kind=kind,discovery="official_date_index")
                 for i,kind in enumerate(("law","admrul","ordin"),1)]
        historical=r(9,discovery="legacy_index_only_not_verified")
        catalog={events.key(x):x for x in sources+[historical]}
        d=pipeline.build({"catalog":catalog,"inspected":{},
                          "coverage":[],"verified_snapshots":{}},
                         dt.date(2026,11,10))
        titles=[doc["title"] for group in d["other_events"]
                for doc in group["source_docs"]]
        self.assertEqual(set(titles),{x["title"] for x in sources})
        self.assertEqual(d["collection"]["official_catalogue"],3)
        self.assertEqual(d["collection"]["legacy_index_pending_recheck"],1)
        self.assertEqual(d["collection"]["pending_details"],3)
        self.assertFalse(d["featured_events"])

    def test_failed_detail_rejoins_queue_after_retry_date(self):
        record=r(1,discovery="official_date_index")
        previous=events.index_only(record)
        previous["verification"]="detail_failed"
        state={"catalog":{events.key(record):record},
               "inspected":{events.key(record):previous},
               "retry_after":{events.key(record):"2026-11-09"}}
        self.assertEqual(len(pipeline.pick_work(state,dt.date(2026,11,10),10)),1)
        state["retry_after"][events.key(record)]="2026-11-15"
        self.assertEqual(pipeline.pick_work(state,dt.date(2026,11,10),10),[])

    def test_one_promulgation_does_not_join_different_law_types(self):
        a=events.inspect(r(1),load=lambda r:{"제1조":"a"},
            history=lambda r,x:None,annual=lambda r:None)[0]
        b=events.inspect(r(2),load=lambda r:{"제1조":"a"},
            history=lambda r,x:None,annual=lambda r:None)[0]
        a.update(promulgation_number="400",promulgated_at="2026-11-07",kind="법률")
        b.update(promulgation_number="400",promulgated_at="2026-11-07",kind="대통령령")
        self.assertEqual(len(events.cluster_promulgations([a,b])),2)

if __name__=="__main__":unittest.main()
