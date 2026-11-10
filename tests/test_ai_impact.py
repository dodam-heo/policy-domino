"""Contracts for the production ALL-event, source-grounded, resumable AI queue.

All model responses here are simulated; real inference is separately visible
only when a provider-backed production run emits LLM_EVENT_PROGRESS.
"""
from __future__ import annotations
import copy
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from policy_domino.analysis_evidence import evidence_identity, has_verified_action
from policy_domino.ai_impact import (
    SCHEMA, ModelConfig, ProviderHTTPFailure, build_catalog,
    eligible_actions, evidence_payload, call_model, parse_model_response,
    parse_native_gemini_response, make_model_request, validate_answer,
    remaining_chunks, run_incremental,
)


def fixture():
    events = [
        {"event_id": "v4:one", "title": "가상 종합 개정", "promulgated_at": "2026-11-06",
         "effective_date": "2027-01-01", "revision": "일부개정",
         "presentation_source": "v4_official_source", "impact_level": "high"},
        {"event_id": "v4:two", "title": "가상 별도 개정", "promulgated_at": "2026-11-06",
         "effective_date": "2027-01-01", "revision": "일부개정",
         "presentation_source": "v4_official_source", "impact_level": "not_assessed"},
        {"event_id": "legacy:three", "title": "재검증 대기 자료", "promulgated_at": "2026-10-01",
         "presentation_source": "legacy_official_directive_awaiting_recheck"},
        {"event_id": "v4:empty", "title": "본문·기관 연결 미확보",
         "presentation_source": "v4_official_source", "impact_level": "not_assessed"},
    ]
    actions = []
    for eid, amount in (("v4:one",7),("v4:two",2),("legacy:three",1)):
        for i in range(amount):
            actions.append({
                "id": f"{eid}:{i}", "event_id": eid, "agency": f"가상 공공기관 {i}",
                "agency_role": "직접 규율 대상", "law_title": "가상 행정규칙",
                "article": f"제{i+1}조", "work": "업무 기준 적용",
                "target_location": "행정 처리 기준", "basis": "https://www.law.go.kr/법령/가상",
                "impact_link_basis": "공식 신구 본문 직접 비교",
                "evidence_scope": "v4_verified_source" if not eid.startswith("legacy:") else "legacy_official_directive_awaiting_recheck",
                "changes": [{"before": f"기준 {i}명", "after": f"기준 {i+1}명"}],
            })
    return {"schema":"policy-domino-next-v1", "generated_at":"2026-11-10T01:00:00Z",
            "events":events, "actions":actions}


def actual_shaped_answer(context):
    return {"summary":"검증된 기관별 변경사항의 업무 적용 기준을 확인해야 합니다.",
            "findings":[{
                "action_id": item["action_id"], "evidence_id":item["evidence_id"],
                "operational_impact":"조문 변경으로 인해 해당 공공기관의 실제 업무 기준 적용이 달라집니다.",
                "review_task":"관련 업무 운영 기준과 시스템 설정의 반영 필요 여부를 확인합니다.",
            } for item in context["evidence"]]}


class Response:
    def __init__(self, content):
        self.content=content
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, n):
        return self.content


class AllEventAITests(unittest.TestCase):
    def setUp(self):
        self.data=fixture()
        self.config=ModelConfig("https://example.org/v1","test-model","test-key")

    def test_all_collected_events_are_managed_even_without_proven_dependencies(self):
        c=build_catalog(self.data)
        self.assertEqual(c["schema"],SCHEMA)
        self.assertEqual(c["total_events"],4)
        self.assertEqual(c["eligible_events"],2)
        self.assertEqual(c["total_verified_actions"],9)
        self.assertEqual(c["status_counts"]["pending"],2)
        self.assertEqual(c["status_counts"]["awaiting_verified_evidence"],2)
        self.assertEqual(len(eligible_actions(self.data,"legacy:three")),0)
        self.assertTrue(all("evidence_fingerprint" in a
                            for a in self.data["actions"] if a["event_id"]!="legacy:three"))

    def test_no_high_impact_filter_or_first_three_truncation(self):
        c=build_catalog(self.data)
        chunks=remaining_chunks(c,self.data,3)
        self.assertEqual([(eid,len(batch)) for eid,batch in chunks],
                         [("v4:one",3),("v4:two",2),("v4:one",3),("v4:one",1)])

    def test_resume_after_checkpoint_without_repeating_successful_calls(self):
        saved=[]
        calls=[]
        def fake_model(config,context):
            calls.append([row["action_id"] for row in context["evidence"]])
            return actual_shaped_answer(context)
        def save(item):
            saved.append(copy.deepcopy(item))
        first=run_incremental(self.data,{},self.config,max_requests=2,
                              interval=0,model_request=fake_model,pause=lambda _:None,persist=save)
        self.assertEqual(first["total_analyzed_actions"],5)
        self.assertEqual(first["status_counts"]["partial"],1)
        self.assertEqual(first["status_counts"]["complete"],1)
        self.assertGreaterEqual(len(saved),3)
        self.assertEqual(len(calls),2)
        second=run_incremental(self.data,first,self.config,max_requests=3,
                               interval=0,model_request=fake_model,pause=lambda _:None)
        self.assertEqual(second["total_analyzed_actions"],9)
        self.assertEqual(second["status_counts"]["complete"],2)
        self.assertEqual(len(calls),4)
        again=run_incremental(self.data,second,self.config,max_requests=36,
                              interval=0,model_request=fake_model,pause=lambda _:None)
        self.assertEqual(again["requests_this_run"],0)
        self.assertEqual(len(calls),4)
        self.assertEqual(len({f["action_id"] for e in again["events"] for f in e["findings"]}),9)

    def test_generated_at_change_keeps_completed_findings_without_any_recall(self):
        provider=lambda config,context:actual_shaped_answer(context)
        first=run_incremental(self.data,{},self.config,
                              model_request=provider,interval=0,pause=lambda _:None)
        self.data["generated_at"]="2026-11-11T01:20:00Z"
        result=run_incremental(self.data,first,self.config,interval=0,
                               model_request=lambda *_:self.fail("Unchanged evidence should be cached"),
                               pause=lambda _:None)
        self.assertEqual(result["requests_this_run"],0)
        self.assertEqual(result["total_analyzed_actions"],9)

    def test_changed_evidence_invalidates_only_one_action_not_all_events(self):
        first=run_incremental(self.data,{},self.config,
                              model_request=lambda conf,context:actual_shaped_answer(context),
                              interval=0,pause=lambda _:None)
        self.data["actions"][1]["changes"][0]["after"]="정원 999명으로 변경"
        # The canonical source publisher recomputes fingerprints after a legal change.
        self.data["actions"][1]["evidence_fingerprint"]=evidence_identity(
            self.data["events"][0],self.data["actions"][1])
        catalog=build_catalog(self.data,first)
        self.assertEqual(catalog["total_analyzed_actions"],8)
        self.assertEqual(catalog["status_counts"]["partial"],1)
        self.assertEqual(catalog["status_counts"]["complete"],1)
        called=[]
        def fake_model(cfg,context):
            called.extend([e["action_id"] for e in context["evidence"]])
            return actual_shaped_answer(context)
        updated=run_incremental(self.data,first,self.config,
                                model_request=fake_model,interval=0,pause=lambda _:None)
        self.assertEqual(called,["v4:one:1"])
        self.assertEqual(updated["total_analyzed_actions"],9)

    def test_provider_quota_failure_preserves_partial_results_and_defers(self):
        calls=0
        snapshots=[]
        def fake_model(cfg,context):
            nonlocal calls
            calls+=1
            if calls>1: raise ProviderHTTPFailure(429,"LLM API HTTP 429 quota")
            return actual_shaped_answer(context)
        catalog=run_incremental(self.data,{},self.config,max_requests=20,
                                model_request=fake_model,interval=0,pause=lambda _:None,
                                persist=lambda c:snapshots.append(copy.deepcopy(c)))
        self.assertEqual(catalog["requests_this_run"],2)
        self.assertEqual(catalog["total_analyzed_actions"],3)
        self.assertEqual(catalog["status_counts"]["partial"],1)
        self.assertEqual(catalog["status_counts"]["pending"],1)
        self.assertIn("HTTP 429",catalog["last_error"])
        self.assertEqual(snapshots[-1]["total_analyzed_actions"],3)

    def test_failed_or_missing_model_does_not_claim_analysis(self):
        with patch.dict(os.environ, {"PD_LLM_API_KEY":"","PD_LLM_MODEL":""}):
            with self.assertRaises(RuntimeError):
                ModelConfig.from_env()
        catalog=build_catalog(self.data)
        self.assertEqual(catalog["total_analyzed_actions"],0)
        self.assertEqual(catalog["eligible_events"],2)

    def test_official_evidence_identity_is_stable_but_change_sensitive(self):
        e=self.data["events"][0]
        a=self.data["actions"][0]
        value=evidence_identity(e,a)
        self.data["generated_at"]="another snapshot"
        self.assertEqual(evidence_identity(e,a),value)
        a["changes"][0]["before"]="다른 이전 기준"
        self.assertNotEqual(evidence_identity(e,a),value)
        a["evidence_scope"]="legacy_official_directive_awaiting_recheck"
        self.assertFalse(has_verified_action(a))
        with self.assertRaises(ValueError):
            evidence_identity(e,a)

    def test_model_cannot_invent_agency_action_or_citation(self):
        build_catalog(self.data)
        event=self.data["events"][0]
        action=self.data["actions"][0]
        ctx=evidence_payload(event,[action],self.data["generated_at"])
        answer=actual_shaped_answer(ctx)
        answer["findings"][0]["action_id"]="invented"
        with self.assertRaisesRegex(ValueError,"unsupported action"):
            validate_answer(answer,ctx,"test-model",{action["id"]:action})
        answer=actual_shaped_answer(ctx)
        answer["findings"][0]["evidence_id"]="E999"
        with self.assertRaisesRegex(ValueError,"citation"):
            validate_answer(answer,ctx,"test-model",{action["id"]:action})

    def test_model_does_not_control_provenance_or_completed_status(self):
        build_catalog(self.data)
        action=self.data["actions"][0]
        ctx=evidence_payload(self.data["events"][0],[action],self.data["generated_at"])
        raw=actual_shaped_answer(ctx)
        raw["findings"][0].update({
            "agency":"엉뚱한 민간기업",
            "basis_url":"https://fake.invalid",
            "status":"조치 완료",
        })
        finding=validate_answer(raw,ctx,"gemini-test",{action["id"]:action})[0]
        self.assertEqual(finding["agency"],action["agency"])
        self.assertEqual(finding["basis_url"],action["basis"])
        self.assertNotIn("status",finding)
        self.assertEqual(finding["model"],"gemini-test")

    def test_provider_fallback_after_503_and_actual_model_provenance(self):
        models=[]
        def fake_model(cfg,ctx):
            models.append(cfg.model)
            if cfg.model=="gemini-3.8-flash":
                raise ProviderHTTPFailure(503,"LLM API HTTP 503")
            return actual_shaped_answer(ctx)
        config=ModelConfig("https://generativelanguage.googleapis.com/v1beta/openai",
                           "gemini-3.8-flash","test-key")
        with patch.dict(os.environ,{"PD_LLM_FALLBACK_MODEL":"gemini-3.5-flash-lite"}):
            result=run_incremental(self.data,{},config,max_requests=2,interval=0,
                                   model_request=fake_model,pause=lambda _:None)
        self.assertEqual(models,["gemini-3.8-flash","gemini-3.5-flash-lite",
                                 "gemini-3.5-flash-lite"])
        self.assertEqual(result["last_success_model"],"gemini-3.5-flash-lite")
        self.assertTrue(all(f["model"]=="gemini-3.5-flash-lite"
                            for e in result["events"] for f in e["findings"]))

    def test_non_gemini_503_does_not_switch_provider(self):
        calls=[]
        def fail(cfg,ctx):
            calls.append(cfg.model)
            raise ProviderHTTPFailure(503,"LLM API HTTP 503")
        with patch.dict(os.environ,{"PD_LLM_FALLBACK_MODEL":"gemini-3.5-flash-lite"}):
            catalog=run_incremental(self.data,{},self.config,max_requests=10,
                                    model_request=fail,interval=0,pause=lambda _:None)
        self.assertEqual(calls,["test-model"])
        self.assertEqual(catalog["total_analyzed_actions"],0)

    def test_error_diagnostics_support_gemini_array_503_without_secrets(self):
        build_catalog(self.data)
        ctx=evidence_payload(self.data["events"][0],self.data["actions"][:1],
                             self.data["generated_at"])
        n=[]
        def opener(req,timeout):
            n.append(1)
            raw=b'[{"error":{"status":"UNAVAILABLE","message":"private test secret"}}]'
            raise HTTPError(req.full_url,503,"Server",{},io.BytesIO(raw))
        with self.assertRaises(ProviderHTTPFailure) as outcome:
            call_model(self.config,ctx,open_request=opener,pause=lambda _:None)
        self.assertEqual(len(n),3)
        self.assertIn("HTTP 503",str(outcome.exception))
        self.assertNotIn("private test secret",str(outcome.exception))

    def test_real_model_http_request_contract_no_fake_success(self):
        build_catalog(self.data)
        ctx=evidence_payload(self.data["events"][0],self.data["actions"][:1],
                             self.data["generated_at"])
        requests=[]
        def opener(req,timeout):
            requests.append(req)
            payload=json.dumps({"choices":[{"message":{
                "content":json.dumps(actual_shaped_answer(ctx),ensure_ascii=False)
            }}]},ensure_ascii=False).encode()
            return Response(payload)
        result=call_model(self.config,ctx,open_request=opener)
        self.assertEqual(result["findings"][0]["action_id"],ctx["evidence"][0]["action_id"])
        self.assertEqual(requests[0].full_url,"https://example.org/v1/chat/completions")
        self.assertEqual(requests[0].get_header("Authorization"),"Bearer test-key")
        sent=json.loads(requests[0].data)
        self.assertEqual(sent["model"],"test-model")
        self.assertEqual(json.loads(sent["messages"][1]["content"])["evidence"][0]["agency"],
                         self.data["actions"][0]["agency"])

    def test_json_object_mode_for_provider_completions(self):
        build_catalog(self.data)
        ctx=evidence_payload(self.data["events"][0],self.data["actions"][:1],
                             self.data["generated_at"])
        sent=[]
        def opener(req,timeout):
            sent.append(json.loads(req.data))
            return Response(json.dumps({"choices":[{"message":{
                "content":json.dumps(actual_shaped_answer(ctx),ensure_ascii=False)
            }}]},ensure_ascii=False).encode())
        call_model(self.config,ctx,open_request=opener)
        self.assertEqual(sent[0]["response_format"],{"type":"json_object"})

    def test_provider_structured_json_normalizes_fenced_and_text_parts(self):
        result={"summary":"공공기관 검토사항입니다.","findings":[]}
        content=json.dumps(result,ensure_ascii=False)
        fence=chr(96)*3
        examples=[
            content,
            fence+"json\n"+content+"\n"+fence,
            fence+"\n"+content+"\n"+fence,
            [{"type":"text","text":content}],
            result,
        ]
        for item in examples:
            with self.subTest(item=str(item)[:30]):
                raw=json.dumps({"choices":[{"message":{"content":item}}]},
                               ensure_ascii=False).encode()
                self.assertEqual(parse_model_response(raw),result)

    def test_incomplete_or_nonstrict_json_stays_unpublished(self):
        raw_candidates=[
            {"choices":[{"message":{"content":None}}]},
            {"choices":[{"message":{"content":"hello not json"}}]},
            {"choices":[{"message":{"content":"[1,2,3]"}}]},
            {"choices":[{"message":{"content":"{incomplete"}}]},
        ]
        for example in raw_candidates:
            with self.subTest(example=str(example)[:50]):
                with self.assertRaisesRegex(ValueError,"structured JSON"):
                    parse_model_response(json.dumps(example).encode())

    def test_google_native_structured_transport_and_model_response(self):
        build_catalog(self.data)
        cfg=ModelConfig("https://generativelanguage.googleapis.com/v1beta/openai",
                        "gemini-3.5-flash-lite","my-private-gemini-key")
        ctx=evidence_payload(self.data["events"][0],self.data["actions"][:2],
                             self.data["generated_at"])
        request,native=make_model_request(cfg,ctx)
        self.assertTrue(native)
        self.assertEqual(request.full_url,
                         "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent")
        self.assertEqual(request.get_header("X-goog-api-key"),"my-private-gemini-key")
        self.assertIsNone(request.get_header("Authorization"))
        body=json.loads(request.data)
        self.assertEqual(body["contents"][0]["role"],"user")
        self.assertEqual(body["generationConfig"]["responseFormat"]["text"]["mimeType"],
                         "APPLICATION_JSON")
        self.assertEqual(body["generationConfig"]["responseFormat"]["text"]["schema"]["type"],
                         "object")
        self.assertEqual(body["generationConfig"]["maxOutputTokens"],4096)
        contexts=json.loads(body["contents"][0]["parts"][0]["text"])
        self.assertEqual(len(contexts["evidence"]),2)
        answer=actual_shaped_answer(ctx)
        def opener(req,timeout):
            self.assertEqual(timeout,45)
            response={"candidates":[{"content":{"parts":[{"text":json.dumps(answer,ensure_ascii=False)}]},
                                     "finishReason":"STOP"}]}
            return Response(json.dumps(response,ensure_ascii=False).encode())
        self.assertEqual(call_model(cfg,ctx,open_request=opener),answer)

    def test_native_gemini_response_rejects_truncated_output_without_fake_findings(self):
        payload={"candidates":[{"finishReason":"MAX_TOKENS",
                                "content":{"parts":[{"text":"{incomplete"}]}}]}
        with self.assertRaisesRegex(ValueError,"valid structured JSON"):
            parse_native_gemini_response(json.dumps(payload).encode())

    def test_prefer_proven_gemini_lite_without_first_hitting_overloaded_primary(self):
        cfg=ModelConfig("https://generativelanguage.googleapis.com/v1beta/openai",
                        "gemini-3.8-flash","test-key")
        calls=[]
        def provider(config,ctx):
            calls.append(config.model)
            return actual_shaped_answer(ctx)
        with patch.dict(os.environ, {"PD_LLM_FALLBACK_MODEL":"gemini-3.5-flash-lite",
                                     "PD_AI_PREFER_FALLBACK":"true"}):
            result=run_incremental(self.data,{},cfg,max_requests=2,
                                   interval=0,model_request=provider,pause=lambda _:None)
        self.assertEqual(calls,["gemini-3.5-flash-lite","gemini-3.5-flash-lite"])
        self.assertEqual(result["last_success_model"],"gemini-3.5-flash-lite")

    def test_fingerprint_mismatch_does_not_publish_stale_cached_facts(self):
        catalog=build_catalog(self.data)
        self.data["actions"][0]["evidence_fingerprint"]="1234"
        with self.assertRaisesRegex(ValueError,"fingerprint"):
            build_catalog(self.data,catalog)

    def test_duplicate_action_ids_block_catalog(self):
        self.data["actions"].append(copy.deepcopy(self.data["actions"][0]))
        with self.assertRaisesRegex(ValueError,"Duplicated"):
            build_catalog(self.data)


if __name__ == "__main__":
    unittest.main()
