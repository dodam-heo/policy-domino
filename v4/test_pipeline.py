import unittest
import datetime as dt
from v4 import pipeline,events

def r(n,date="2026-11-07",kind="law",nextyear=False,discovery=""):
    return {"source":kind,"stable_id":str(n),"serial":str(n*10),
            "title":"무작위 공식 기준 "+str(n),"published_at":date,
            "effective_date":"2027-01-01" if nextyear else date,
            "revision":"일부개정","kind":"법령","number":str(n),
            "ministry":"가상부처","url":"https://www.law.go.kr",
            "discovery_kind":discovery}

class PublicationSafeguards(unittest.TestCase):
    def test_source_quality_reports_failure_and_partial_separately(self):
        a=r(5,kind="law",date="2026-11-01")
        b=r(6,kind="admrul",date="2026-11-02")
        c=r(7,kind="ordin",date="2026-11-03")
        ka,kb,kc=(events.key(x) for x in (a,b,c))
        state={"catalog":{ka:a,kb:b,kc:c},
               "inspected":{
                   ka:{"verification":"verified_changed_clauses"},
                   kb:{"verification":"detail_failed"}},
               "attempts":{kb:3}}
        audit=pipeline.evidence_audit(state,dt.date(2026,11,9))
        self.assertEqual(audit["law"]["verified_before_after"],1)
        self.assertEqual(audit["admrul"]["body_extraction_failed"],1)
        self.assertEqual(audit["admrul"]["exhausted_retries"],1)
        self.assertEqual(audit["ordin"]["pending"],1)
        self.assertEqual(audit["ordin"]["oldest_pending_published"],"2026-11-03")
        self.assertEqual(audit["law"]["partial_before_after"],0)
        self.assertEqual(sum(x["indexed"] for x in audit.values()),3)

    def test_bootstrap_is_not_automatically_impact_verified(self):
        state={"catalog":{events.key(r(1)):r(1)},"inspected":{},
               "coverage":[],"verified_snapshots":{}}
        d=pipeline.build(state,dt.date(2026,11,8))
        self.assertEqual(d["schema"],"policy-domino-v4")
        self.assertFalse(d["featured_events"])
        self.assertEqual(d["collection"]["pending_details"],1)
        self.assertFalse(d["collection"]["whole_corpus_complete"])

    def test_multiple_uninspected_sectors_visible_but_not_verified(self):
        records=[
            r(10,kind="law",date="2026-11-09",discovery="official_law_change_history"),
            r(20,kind="admrul",date="2026-11-09",discovery="official_date_index"),
            r(30,kind="ordin",date="2026-11-09",discovery="official_date_index"),
            r(40,kind="law",date="2025-04-01",
              discovery="legacy_index_only_not_verified"),
        ]
        state={"catalog":{events.key(x):x for x in records},"inspected":{},
               "coverage":[],"verified_snapshots":{}}
        data=pipeline.build(state,dt.date(2026,11,9))
        self.assertEqual(len(data["pending_index"]),3)
        self.assertEqual({x["source"] for x in data["pending_index"]},
                         {"law","admrul","ordin"})
        self.assertTrue(all(x["verification"]=="official_index_only"
                            for x in data["pending_index"]))
        self.assertEqual(data["collection"]["pending_details"],4)

    def test_structural_changes_do_not_starve_other_sectors(self):
        structural=r(11,discovery="official_law_change_history")
        structural["title"]="가상기관 직제 시행규칙"
        substantive=r(12,discovery="official_law_change_history")
        substantive["title"]="가상 주민지원 요건 개정"
        today=dt.date(2026,11,9)
        self.assertGreater(pipeline.candidate_rank(substantive,today)[0],
                           pipeline.candidate_rank(structural,today)[0])
        self.assertTrue(pipeline.structural_change_title(structural["title"]))
        self.assertFalse(pipeline.structural_change_title(substantive["title"]))

    def test_pending_list_balances_generic_document_types(self):
        rows=[]
        for n in range(1,10):
            item=r(n,kind="law",date="2026-11-09",
                   discovery="official_law_change_history")
            item["title"]=("가상기관"+str(n)+" 직제 시행규칙" if n<=7 else
                            "가상 법률의 자격 요건 변경"+str(n))
            rows.append(item)
        # Add non-structural historical candidates for other sources.
        rows.append(r(20,kind="admrul",date="2026-11-09",discovery="official_date_index"))
        state={"catalog":{events.key(x):x for x in rows},"inspected":{}}
        pending=pipeline.recent_uninspected(state,limit=4)
        self.assertTrue(any(x["source"]=="admrul" for x in pending))
        self.assertTrue(any("자격 요건" in x["title"] for x in pending))

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

    def test_retry_unverified_source_without_pretending_comparison(self):
        rec=r(25,discovery="official_date_index")
        key=events.key(rec)
        state={"catalog":{key:rec},
               "inspected":{key:{"verification":"official_record_only"}},
               "attempts":{key:1},"last_attempt_date":{key:"2026-11-08"}}
        self.assertEqual(len(pipeline.pick_work(state,dt.date(2026,11,9),1)),1)
        state["last_attempt_date"][key]="2026-11-09"
        self.assertEqual(pipeline.pick_work(state,dt.date(2026,11,9),1),[])
        state["last_attempt_date"][key]="2026-11-08"
        state["attempts"][key]=3
        self.assertEqual(pipeline.pick_work(state,dt.date(2026,11,9),1),[])

    def test_detail_queue_includes_all_official_document_types(self):
        recs=[r(n,kind="law",date="2026-11-09",
               discovery="official_law_change_history") for n in range(1,22)]
        recs += [r(30,kind="admrul",date="2026-11-09",
                    discovery="official_date_index"),
                 r(31,kind="ordin",date="2026-11-09",
                    discovery="official_date_index")]
        state={"catalog":{events.key(x):x for x in recs},"inspected":{}}
        items=pipeline.pick_work(state,dt.date(2026,11,9),8)
        self.assertEqual({x["source"] for x in items},
                         {"law","admrul","ordin"})

    def test_official_history_beats_old_legacy_metadata_on_work_queue(self):
        current=dt.date(2026,11,8)
        xs=[r(1,date="2025-01-01",nextyear=False,discovery="legacy_index_only_not_verified"),
            r(2,date="2026-11-07",discovery="official_law_change_history"),
            r(3,date="2026-09-21",nextyear=True)]
        state={"catalog":{events.key(x):x for x in xs},"inspected":{}}
        picked=pipeline.pick_work(state,current,2)
        self.assertEqual(picked[0]["stable_id"],"2")
        self.assertIn(picked[1]["stable_id"],("3","2"))

    def test_one_promulgation_does_not_join_different_law_types(self):
        a=events.inspect(r(1),load=lambda r:{"제1조":"a"},
            history=lambda r,x:None,annual=lambda r:None)[0]
        b=events.inspect(r(2),load=lambda r:{"제1조":"a"},
            history=lambda r,x:None,annual=lambda r:None)[0]
        a.update(promulgation_number="400",promulgated_at="2026-11-07",kind="법률")
        b.update(promulgation_number="400",promulgated_at="2026-11-07",kind="대통령령")
        self.assertEqual(len(events.cluster_promulgations([a,b])),2)

if __name__=="__main__":unittest.main()
