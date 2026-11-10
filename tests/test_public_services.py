"""Offline contract tests for GOV24 source-backed programme discovery.

No sample institution/programme names are used by the production matcher.
"""
import copy
import json
import unittest
from pathlib import Path

from policy_domino.public_services import (
    SCHEMA, blank_catalog, normalize_service, collect_services,
    service_edges, agency_service_action, changed_concepts,
    matched_operating_rule,
)
from policy_domino.analysis_evidence import evidence_identity, has_verified_action


def legal_event(source="v4_official_source"):
    return {
        "event_id": "v4:dynamic-income", "title": "2027년도 기준 중위소득 변경",
        "promulgated_at": "2026-11-06", "effective_date": "2027-01-01",
        "revision": "기준 변경", "amendment_reason": "가구별 기준 변경",
        "presentation_source": source,
        "article_differences": [{
            "article": "중위소득:4인", "title": "선정기준",
            "before": "6,494,738원", "after": "6,929,885원",
            "source_url": "https://www.law.go.kr/행정규칙/가상기준",
        }],
    }


def record(sid="A", agency="가상주거공사", name="가상임대지원",
           criteria="기준 중위소득의 150% 이하"):
    return {
        "서비스ID": sid, "소관기관명": agency, "서비스명": name,
        "선정기준": criteria, "지원대상": "소득요건을 충족한 가구",
        "상세조회URL": "https://www.gov.kr/portal/rcvfvrSvc/test",
        "수정일시": "2026-11-09", "소관기관코드": "G12345",
        "소관기관유형": "공공기관",
    }


class PublicServicesTests(unittest.TestCase):
    def test_official_owner_and_program_are_taken_only_from_gov24_record(self):
        r=normalize_service(record(agency="가상정책재단",name="신청자 선정사업"))
        self.assertEqual((r["agency"],r["title"],r["agency_code"]),
                         ("가상정책재단","신청자 선정사업","G12345"))
        self.assertTrue(r["detail_url"].startswith("https://www.gov.kr/"))
        bad=record()
        bad["상세조회URL"]="https://fake.invalid/item"
        self.assertEqual(normalize_service(bad)["detail_url"],"")
        self.assertIsNone(normalize_service({**record(),"소관기관명":""}))

    def test_resumable_full_service_catalogue_and_bulk_details(self):
        listed = [record(str(i), agency="가상운영기관"+str(i))
                  for i in range(1001)]
        detail_rows = [
            {**record(str(i)), "법령": "「가상법률」 제1조에 따른 적용"}
            for i in range(201)
        ]
        calls = []
        def fetch(endpoint, key, params):
            self.assertEqual(key, "test-key")
            calls.append((endpoint, params["page"], params["perPage"]))
            size, page = params["perPage"], params["page"]
            if endpoint == "serviceDetail":
                return {"totalCount":201,
                        "data":detail_rows[(page-1)*size:page*size]}
            return {"totalCount":1001,
                    "data":listed[(page-1)*size:page*size]}
        saved = []
        partial = collect_services({}, "test-key", max_pages=1,
                                   max_details=0, fetch=fetch,
                                   checkpoint=lambda item:saved.append(
                                       copy.deepcopy(item)))
        self.assertFalse(partial["complete"])
        self.assertEqual(partial["next_page"], 2)
        self.assertEqual(len(partial["services"]), 1000)
        self.assertEqual(calls[0], ("serviceList", 1, 1000))

        middle = collect_services(partial, "test-key", max_pages=2,
                                  max_details=200, fetch=fetch)
        self.assertTrue(middle["complete"])
        self.assertEqual(middle["next_page"], 1)
        self.assertEqual(len(middle["services"]), 1001)
        self.assertFalse(middle["detail_complete"])
        self.assertEqual(middle["detail_next_page"], 2)
        self.assertEqual(sum(bool(s.get("detail"))
                             for s in middle["services"].values()), 200)
        self.assertIn(("serviceDetail", 1, 200), calls)
        final = collect_services(middle, "test-key", max_pages=2,
                                 max_details=200, fetch=fetch)
        self.assertTrue(final["detail_complete"])
        self.assertEqual(final["detail_next_page"], 1)
        self.assertEqual(sum(bool(s.get("detail"))
                             for s in final["services"].values()), 201)
        self.assertEqual(final["services"]["0"]["detail"]["laws"],
                         "「가상법률」 제1조에 따른 적용")
        self.assertTrue(saved)

    def test_failed_page_keeps_previous_official_services_and_cursor(self):
        prior={"schema":SCHEMA,"services":{
            "existing":normalize_service(record("existing"))},
            "next_page":1, "total_reported":10, "complete":False}
        def failed(endpoint, key, params):
            raise RuntimeError("Gov24 API HTTP 403")
        result=collect_services(prior, "test-key", fetch=failed)
        self.assertEqual(list(result["services"]),["existing"])
        self.assertEqual(result["next_page"],1)
        self.assertFalse(result["complete"])
        self.assertEqual(result["last_error"],"Gov24 API HTTP 403")

    def test_api_uses_documented_auth_query_then_header_fallback_without_secret_leak(self):
        from io import BytesIO
        from urllib.error import HTTPError
        from unittest.mock import patch
        from policy_domino.public_services import fetch_page
        seen=[]
        secret="test-only-secret-never-print"
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, length):
                return b'{"data":[],"totalCount":0}'
        def handler(request, timeout):
            seen.append(request)
            if len(seen)==1:
                raise HTTPError(request.full_url, 401, "denied",
                                {}, BytesIO(b'private diagnostic'))
            self.assertNotIn("serviceKey",request.full_url)
            self.assertEqual(request.get_header("Authorization"),
                             "Infuser "+secret)
            return Response()
        with patch("urllib.request.urlopen",handler):
            result=fetch_page("serviceList", secret,
                              {"page":1,"perPage":1000})
        self.assertEqual(result["data"],[])
        self.assertIn("serviceKey=",seen[0].full_url)
        self.assertEqual(len(seen),2)
        def always_denied(request,timeout):
            raise HTTPError(request.full_url,403,
                            "secret="+secret,{},BytesIO(b'private'))
        with patch("urllib.request.urlopen",always_denied):
            with self.assertRaisesRegex(RuntimeError,
                                        "both Swagger schemes tried") as error:
                fetch_page("serviceList",secret,{"page":1,"perPage":1000})
        self.assertNotIn(secret,str(error.exception))

    def test_named_standard_requires_real_numeric_legal_change(self):
        e=legal_event()
        self.assertIn("중위소득",{x["concept"] for x in changed_concepts(e)})
        unchanged=copy.deepcopy(e)
        unchanged["article_differences"][0]["after"]="6,494,738원"
        self.assertFalse(changed_concepts(unchanged))
        self.assertTrue(matched_operating_rule("중위소득","기준 중위소득 150% 이하"))
        self.assertFalse(matched_operating_rule("중위소득","중위소득 기준 변경"))
        self.assertFalse(matched_operating_rule("중위소득","일반적인 소득 지원 사업"))

    def test_dynamic_public_body_and_program_link_with_real_criteria(self):
        e=legal_event()
        a=normalize_service(record(agency="가상공공법인",name="가상공공서비스"))
        b=normalize_service(record("B",agency="가상장학기구",name="기준중위소득 지원사업",
                                   criteria="재학 요건에 해당하는 학생"))
        c=normalize_service(record("C",agency="가상기금공사",name="기타지원",
                                   criteria="연소득 2,000만원 이하"))
        catalog={"schema":SCHEMA,"services":{x["id"]:x for x in (a,b,c)}}
        edges=service_edges([e],catalog)
        self.assertEqual(len(edges),1)
        self.assertEqual(edges[0]["agency"],"가상공공법인")
        self.assertEqual(edges[0]["service"],"가상공공서비스")
        self.assertEqual(edges[0]["policy_concept"],"중위소득")
        self.assertIn("150%",edges[0]["operating_rule"])
        self.assertEqual(service_edges([{**e,"article_differences":[]}],catalog),[])
        self.assertEqual(service_edges([e],{"schema":"wrong","services":catalog["services"]}),[])

    def test_exact_changed_clause_citation_not_just_law_title(self):
        event={
            "event_id":"v4:changed-clause",
            "title":"가상급부법 시행령",
            "presentation_source":"v4_official_source",
            "promulgated_at":"2026-11-05","effective_date":"2027-01-01",
            "revision":"일부개정","amendment_reason":"",
            "article_differences":[{
                "article":"제5조",
                "before":"제5조 지원 기준 금액은 100만원이다.",
                "after":"제5조 지원 기준 금액은 120만원이다.",
                "source_url":"https://www.law.go.kr/법령/가상급부법시행령"
            }],
        }
        s=normalize_service(record("A","가상공공운영단","가상정책급여",
                                   "법령상 급부 조건을 충족한 신청인"))
        s["detail"]={"laws":"「가상급부법 시행령」 제5조에 따른 지원 기준을 적용",
                      "criteria":"제5조에 따른 지원 기준"}
        catalog={"schema":SCHEMA,"services":{s["id"]:s}}
        edges=service_edges([event],catalog)
        self.assertEqual(len(edges),1)
        self.assertEqual(edges[0]["evidence_status"],"service_clause_citation_matched")
        action=agency_service_action(event,edges[0])
        self.assertTrue(has_verified_action(action))
        self.assertEqual(action["evidence_scope"],
                         "service_cited_changed_article_verified")
        changed=copy.deepcopy(s)
        changed["detail"]["laws"]="가상급부법 시행령 제6조에 따른 지원 기준을 적용"
        self.assertEqual(service_edges([event],{"schema":SCHEMA,
            "services":{"A":changed}}),[])
        missing_operative=copy.deepcopy(s)
        missing_operative["detail"]["laws"]="「가상급부법 시행령」 제5조"
        self.assertEqual(service_edges([event],{"schema":SCHEMA,
            "services":{"A":missing_operative}}),[])

    def test_legacy_income_event_can_link_its_service_without_faking_ai_verification(self):
        from policy_domino.engine import classic_bridge
        root=Path(__file__).resolve().parents[1]
        v4=json.loads((root/"site/v4/data.json").read_text("utf-8"))
        legacy=json.loads((root/"site/classic/legacy_source.json").read_text("utf-8"))
        svc=normalize_service(record("DYN", "가상공공주거운영기관",
                                     "가상주거지원", "기준 중위소득 150% 이하"))
        catalog={"schema":SCHEMA,"services":{svc["id"]:svc}}
        published=classic_bridge.build(v4,legacy,service_catalog=catalog)
        links=[a for a in published["actions"] if a.get("service_id")=="DYN"]
        self.assertGreater(len(links),0)
        self.assertTrue(all(a["agency"]=="가상공공주거운영기관" for a in links))
        self.assertTrue(all(a["evidence_scope"]==
            "legacy_service_dependency_pending_recheck" for a in links))
        self.assertTrue(all(not has_verified_action(a) for a in links))

    def test_source_verified_program_enters_ai_queue_and_fingerprint(self):
        e=legal_event()
        s=normalize_service(record())
        edge=service_edges([e],{"schema":SCHEMA,"services":{s["id"]:s}})[0]
        action=agency_service_action(e,edge)
        self.assertTrue(has_verified_action(action))
        self.assertEqual(action["agency"],s["agency"])
        self.assertEqual(action["service"],s["title"])
        self.assertEqual(action["status"],"반영 확인 필요")
        old=evidence_identity(e,action)
        changed=copy.deepcopy(action)
        changed["service_evidence_rule"]="different published criterion"
        self.assertNotEqual(evidence_identity(e,changed),old)

    def test_legacy_legal_baseline_stays_pending_even_when_service_formula_matches(self):
        e=legal_event("legacy_official_directive_awaiting_recheck")
        s=normalize_service(record())
        edge=service_edges([e],{"schema":SCHEMA,"services":{s["id"]:s}})[0]
        action=agency_service_action(e,edge)
        self.assertEqual(action["evidence_scope"],"legacy_service_dependency_pending_recheck")
        self.assertFalse(has_verified_action(action))
        self.assertEqual(action["status"],"최신 근거 재확인 필요")

    def test_existing_official_legal_action_fingerprints_remain_unchanged(self):
        root=Path(__file__).resolve().parents[1]
        d=json.loads((root/"site/classic/data.json").read_text("utf-8"))
        events={e["event_id"]:e for e in d["events"]}
        checked=[a for a in d["actions"] if a.get("evidence_scope")=="v4_verified_source"]
        self.assertGreater(len(checked),0)
        for a in checked[:8]:
            self.assertEqual(evidence_identity(events[a["event_id"]],a),
                             a["evidence_fingerprint"])

    def test_no_api_key_never_fabricates_services(self):
        with self.assertRaises(ValueError):
            collect_services(blank_catalog(),"",fetch=lambda *_:self.fail("must not fetch"))


if __name__=="__main__":
    unittest.main()
