"""Offline tests for the REAL provider request and strict source/action binding.

No external account, model call, or payment is needed for these unit tests.
A real run uses PD_LLM_API_KEY and PD_LLM_MODEL.
"""
from __future__ import annotations

import json
import io
from urllib.error import HTTPError
import os
import unittest
from unittest.mock import patch

from policy_domino.ai_impact import (
    SCHEMA, ModelConfig, analyze, call_model, eligible_actions, select_event,
    validate_answer, evidence_payload
)


def fixture():
    event_id = "v4:verified-example"
    event = {
        "event_id": event_id, "title": "가상정책 변경",
        "promulgated_at": "2026-11-09", "effective_date": "2027-01-01",
        "presentation_source": "v4_official_source", "impact_level": "high",
    }
    def action(number, agency, scope="v4_verified_source", belongs=event_id):
        return {
            "id": str(number), "event_id": belongs,
            "agency": agency, "law_title": "가상정책 직제",
            "article": f"제{number}조", "work": "정원 운영",
            "target_location": "정원 관리 업무",
            "basis": "https://www.law.go.kr/법령/가상",
            "evidence_scope": scope,
            "changes": [{"before": "정원 20명", "after": "정원 25명"}],
        }
    return {"schema": "policy-domino-next-v1", "generated_at": "2026-11-10T01:00:00Z",
            "events": [event],
            "actions": [action(1,"가상공공기관 가"), action(2,"가상공공기관 나"),
                        action(3, "미검증기관", scope="legacy_official_directive_awaiting_recheck"),
                        action(4, "다른사건기관", belongs="v4:other")]}


def answer():
    return {
        "summary": "공식 정원 변경에 따라 해당 기관의 인사 운영 기준을 검토해야 합니다.",
        "findings": [{
            "action_id": "1", "evidence_id": "E1",
            "operational_impact": "변경된 인원 기준에 따라 정원 관리 업무에 영향이 있습니다.",
            "review_task": "정원 관리 표에서 변경된 수치를 확인하고 반영 여부를 검토합니다.",
        }]
    }


class FakeResponse:
    def __init__(self, value):
        self.value = value
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        return False
    def read(self, size):
        return self.value


class RealLLMImpactTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.config = ModelConfig("https://example.org/v1","test-model","private-test-key")

    def test_missing_api_key_and_model_fails_without_fake_results(self):
        with patch.dict(os.environ, {"PD_LLM_API_KEY":"", "PD_LLM_MODEL":""}):
            with self.assertRaisesRegex(RuntimeError, "must be configured"):
                ModelConfig.from_env()

    def test_provider_url_must_be_https_except_localhost(self):
        with patch.dict(os.environ, {"PD_LLM_API_KEY":"test", "PD_LLM_MODEL":"test",
                                    "PD_LLM_BASE_URL":"http://public.example.com/v1"}):
            with self.assertRaises(ValueError):
                ModelConfig.from_env()
        with patch.dict(os.environ, {"PD_LLM_API_KEY":"test", "PD_LLM_MODEL":"test",
                                    "PD_LLM_BASE_URL":"http://localhost:11434/v1"}):
            self.assertEqual(ModelConfig.from_env().base_url,"http://localhost:11434/v1")

    def test_only_current_official_source_actions_enter_prompt(self):
        event, actions = select_event(self.data,None,3)
        self.assertEqual(event["event_id"],"v4:verified-example")
        self.assertEqual([a["id"] for a in actions], ["1","2"])
        self.assertEqual(len(eligible_actions(self.data,event["event_id"])),2)

    def test_legacy_event_not_selected_for_model(self):
        data = fixture()
        data["events"][0]["presentation_source"] = "legacy_official_directive_awaiting_recheck"
        with self.assertRaisesRegex(ValueError,"currently verified"):
            select_event(data,"v4:verified-example",1)

    def test_real_http_transport_sends_bounded_document_evidence(self):
        context = evidence_payload(self.data["events"][0], self.data["actions"][:1],self.data["generated_at"])
        sent=[]
        def fake_opener(request,timeout):
            sent.append((request,timeout))
            content = json.dumps(answer(),ensure_ascii=False)
            payload = json.dumps({"choices":[{"message":{"content":content}}]},ensure_ascii=False).encode()
            return FakeResponse(payload)
        result=call_model(self.config,context,open_request=fake_opener)
        self.assertEqual(result,answer())
        req,timeout=sent[0]
        self.assertEqual(req.full_url,"https://example.org/v1/chat/completions")
        self.assertEqual(req.get_header("Authorization"),"Bearer private-test-key")
        self.assertEqual(timeout,90)
        submitted=json.loads(req.data)
        self.assertEqual(submitted["model"],"test-model")
        self.assertNotIn("temperature",submitted, "Reasoning models may reject a forced temperature")
        user=json.loads(submitted["messages"][1]["content"])
        self.assertEqual(user["evidence"][0]["before_after"][0]["before"],"정원 20명")
        self.assertEqual(user["evidence"][0]["agency"],"가상공공기관 가")

    def test_model_cannot_make_up_public_institutions_or_sources(self):
        source = evidence_payload(self.data["events"][0],self.data["actions"][:1],self.data["generated_at"])
        forged=answer()
        forged["findings"][0]["action_id"]="totally-fictional-action"
        with self.assertRaisesRegex(ValueError,"unsupported action"):
            validate_answer(forged,source,"test-model")

    def test_model_cannot_cite_another_agencys_source(self):
        context=evidence_payload(self.data["events"][0],self.data["actions"][:2],self.data["generated_at"])
        forged=answer()
        forged["findings"][0]["evidence_id"]="E2"
        with self.assertRaisesRegex(ValueError,"unrelated source"):
            validate_answer(forged,context,"test-model")

    def test_duplicate_actions_rejected(self):
        context=evidence_payload(self.data["events"][0],self.data["actions"][:2],self.data["generated_at"])
        forged=answer()
        forged["findings"].append(forged["findings"][0])
        with self.assertRaisesRegex(ValueError,"duplicated"):
            validate_answer(forged,context,"test-model")

    def test_model_cannot_change_status_or_inject_source_url(self):
        context=evidence_payload(self.data["events"][0],self.data["actions"][:1],self.data["generated_at"])
        forged=answer()
        forged["findings"][0]["agency"]="지어낸 기관"
        forged["findings"][0]["basis_url"]="https://phishing.invalid"
        forged["findings"][0]["status"]="조치 확인"
        output=validate_answer(forged,context,"test-model")
        finding=output["findings"][0]
        self.assertEqual(finding["agency"],"가상공공기관 가")
        self.assertEqual(finding["basis_url"],"https://www.law.go.kr/법령/가상")
        self.assertEqual(finding["status"],"AI 검토 제안 · 실제 반영 미확인")
        self.assertEqual(output["schema"], SCHEMA)
        self.assertEqual(output["source_generated_at"],self.data["generated_at"])

    def test_end_to_end_analysis_calls_model_only_for_verified_evidence(self):
        received=[]
        def fake_model(config,context):
            received.extend(context["evidence"])
            return answer()
        output=analyze(self.data,self.config,request_model=fake_model)
        self.assertEqual(len(received),2)
        self.assertTrue(all(a["source_verified"] for a in received))
        self.assertEqual(output["event_id"],"v4:verified-example")
        self.assertEqual(len(output["findings"]),1)

    def test_quota_429_reports_billing_not_generic_rate_limit(self):
        context=evidence_payload(self.data["events"][0],self.data["actions"][:1],self.data["generated_at"])
        for code in ("insufficient_quota", "credit_balance_exhausted",
                     "project_spend_limit_exceeded"):
            def error_opener(request,timeout):
                body=json.dumps({"error":{"code":code,"type":"insufficient_quota","message":"Never print this value"}}).encode()
                raise HTTPError(request.full_url,429,"Too Many Requests",{},io.BytesIO(body))
            with self.subTest(code=code):
                with self.assertRaisesRegex(RuntimeError,"HTTP 429, provider=.*Credit or spend limit"):
                    call_model(self.config,context,open_request=error_opener)

    def test_rate_limit_429_is_distinguished_from_account_quota(self):
        context=evidence_payload(self.data["events"][0],self.data["actions"][:1],self.data["generated_at"])
        def error_opener(request,timeout):
            body=json.dumps({"error":{"type":"rate_limit_exceeded","message":"Too many requests"}}).encode()
            raise HTTPError(request.full_url,429,"Too Many Requests",{},io.BytesIO(body))
        with self.assertRaisesRegex(RuntimeError,"quota/rate limit reached"):
            call_model(self.config,context,open_request=error_opener)

    def test_unknown_429_never_falsely_diagnoses_empty_balance(self):
        context=evidence_payload(self.data["events"][0],self.data["actions"][:1],self.data["generated_at"])
        def error_opener(request,timeout):
            raise HTTPError(request.full_url,429,"Too Many Requests",{},io.BytesIO(b""))
        with self.assertRaisesRegex(RuntimeError,"HTTP 429.*Provider rejected request"):
            call_model(self.config,context,open_request=error_opener)

    def test_gemini_array_error_is_reported_without_crashing_or_leaking_message(self):
        context=evidence_payload(self.data["events"][0],self.data["actions"][:1],self.data["generated_at"])
        for code, expected_status, expected_help in [
            ("RESOURCE_EXHAUSTED",429,"quota/rate limit"),
            ("INVALID_ARGUMENT",400,"request format"),
            ("PERMISSION_DENIED",403,"API key"),
            ("NOT_FOUND",404,"model ID"),
        ]:
            def error_opener(request,timeout):
                # Regression: actual failure run 42760269254 returned a JSON list.
                response=[{"error":{"code":expected_status,
                                    "status":code,
                                    "message":"DO NOT ECHO provider payload or secrets"}}]
                raise HTTPError(request.full_url,expected_status,"Bad Request",{},
                                io.BytesIO(json.dumps(response).encode()))
            with self.subTest(code=code):
                with self.assertRaises(RuntimeError) as failure:
                    call_model(self.config,context,open_request=error_opener)
                message=str(failure.exception)
                self.assertIn("HTTP "+str(expected_status),message)
                self.assertIn(code,message)
                self.assertIn(expected_help,message)
                self.assertNotIn("DO NOT ECHO",message)

    def test_empty_and_unexpected_provider_error_json_is_safe(self):
        context=evidence_payload(self.data["events"][0],self.data["actions"][:1],self.data["generated_at"])
        for response in (b"[]", b"[null]", b"[123]", b'"string"', b'{"error":42}',b'{'):
            def error_opener(request,timeout):
                raise HTTPError(request.full_url,429,"Too Many Requests",{},
                                io.BytesIO(response))
            with self.subTest(response=response):
                with self.assertRaisesRegex(RuntimeError,"LLM API HTTP 429"):
                    call_model(self.config,context,open_request=error_opener)

    def test_temporary_gemini_503_is_retried_then_real_model_answer_used(self):
        context=evidence_payload(self.data["events"][0],self.data["actions"][:1],self.data["generated_at"])
        attempts=[]
        pauses=[]
        def opener(request,timeout):
            attempts.append(request.full_url)
            if len(attempts)<3:
                error=b'[{"error":{"code":503,"status":"UNAVAILABLE"}}]'
                raise HTTPError(request.full_url,503,"Service Unavailable",{},
                                io.BytesIO(error))
            content=json.dumps(answer(),ensure_ascii=False)
            return FakeResponse(json.dumps({"choices":[{"message":{"content":content}}]}).encode())
        output=call_model(self.config,context,open_request=opener,pause=pauses.append)
        self.assertEqual(output,answer())
        self.assertEqual(len(attempts),3)
        self.assertEqual(pauses,[3,9])

    def test_persistent_503_fails_after_at_most_three_requests(self):
        context=evidence_payload(self.data["events"][0],self.data["actions"][:1],self.data["generated_at"])
        attempts=[]
        pauses=[]
        def opener(request,timeout):
            attempts.append(1)
            raise HTTPError(request.full_url,503,"Service Unavailable",{},
                            io.BytesIO(b'[{"error":{"status":"UNAVAILABLE"}}]'))
        with self.assertRaisesRegex(RuntimeError,"HTTP 503, provider=UNAVAILABLE"):
            call_model(self.config,context,open_request=opener,pause=pauses.append)
        self.assertEqual(len(attempts),3)
        self.assertEqual(pauses,[3,9])

    def test_nontransient_404_and_quota_429_never_retry(self):
        context=evidence_payload(self.data["events"][0],self.data["actions"][:1],self.data["generated_at"])
        for code, payload in [
            (404,{"error":{"status":"NOT_FOUND"}}),
            (429,{"error":{"code":"insufficient_quota"}}),
        ]:
            with self.subTest(status=code):
                attempts=[]
                pauses=[]
                def opener(request,timeout):
                    attempts.append(1)
                    raise HTTPError(request.full_url,code,"Error",{},
                                    io.BytesIO(json.dumps(payload).encode()))
                with self.assertRaises(RuntimeError):
                    call_model(self.config,context,open_request=opener,pause=pauses.append)
                self.assertEqual(len(attempts),1)
                self.assertEqual(pauses,[])

    def test_model_must_return_structured_json(self):
        context=evidence_payload(self.data["events"][0],self.data["actions"][:1],self.data["generated_at"])
        def fake_opener(request,timeout):
            return FakeResponse(json.dumps({"choices":[{"message":{"content":"I think it applies"}}]}).encode())
        with self.assertRaisesRegex(ValueError,"required JSON"):
            call_model(self.config,context,open_request=fake_opener)

    def test_data_has_to_be_current_and_action_bounded(self):
        data=fixture()
        data.pop("generated_at")
        with self.assertRaisesRegex(ValueError,"generation timestamp"):
            analyze(data,self.config,request_model=lambda config,context:answer())
        with self.assertRaisesRegex(ValueError,"1–5"):
            select_event(self.data,None,6)


if __name__ == "__main__":
    unittest.main()
