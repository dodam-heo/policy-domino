"""Policy-wide source presentation: no rule-specific phrase patches."""
import copy
import unittest

from policy_domino.engine import source_change, agency_actions
from policy_domino.ai_impact import build_catalog, source_summary_payload, validate_source_summary

LAW_URL="https://www.law.go.kr/법령/가상"

def make_change(article, before, after):
    return {"article":article, "before":before, "after":after,
            "source_url":LAW_URL}

class OfficialChangePresentationTests(unittest.TestCase):
    def test_grammar_fragments_are_not_misrepresented_as_an_explanation(self):
        before="제95조(전산정보처리조직의 이용) 법 제39조의2제1항에 따라 국토교통부장관이 전산정보처리조직을 이용하여 업무를 처리할 수 있다."
        after="제95조(전산정보처리조직의 이용) 법 제39조의2제1항에 따른 전산정보처리조직을 이용하여 업무를 처리할 수 있다."
        changes=source_change.source_pairs([make_change("제95조",before,after)])
        self.assertEqual(len(changes),1)
        summary=source_change.concise_summary(changes,1)
        self.assertIn("전산정보처리조직",summary)
        self.assertIn("규정을 개정",summary)
        self.assertNotIn("따라 국토교통부장관이 → 따른",summary)
        self.assertIn("국토교통부장관이",summary)
        self.assertIn("문구가 바뀌었습니다",summary)
        rendered="".join(p["text"] for p in changes[0]["preview"]["after"])
        self.assertTrue(rendered)
        self.assertTrue(any(p["changed"] for p in changes[0]["preview"]["after"]))


    def test_factual_fallback_exists_without_ai_and_does_not_invent_results(self):
        no_ai=source_change.concise_summary([],0,title="가상 급여 지원 기준",revision="일부개정")
        self.assertIn("가상 급여 지원 기준",no_ai)
        self.assertIn("원문",no_ai)
        self.assertNotIn("100만원",no_ai)
        made=source_change.concise_summary([],0,title="가상 규정",revision="제정")
        self.assertIn("새로 제정",made)
        old="제2조(정원) 정원 총계는 192명이다."
        new="제2조(정원) 정원 총계는 197명이다."
        changes=source_change.source_pairs([make_change("제2조",old,new)])
        output=source_change.concise_summary(changes,1,title="가상 직제",revision="일부개정")
        self.assertIn("192명",output)
        self.assertIn("197명",output)
        self.assertIn("가상 직제",output)
    def test_operational_amount_compares_whole_values_with_source_heading(self):
        old="제2조(정원) 가상청 공무원 정원 총계는 192명이다."
        new="제2조(정원) 가상청 공무원 정원 총계는 197명이다."
        pair=source_change.source_pairs([make_change("제2조",old,new)])
        summary=source_change.concise_summary(pair,1)
        self.assertIn("192명",summary)
        self.assertIn("197명",summary)
        self.assertNotIn("2 → 7",summary)

    def test_formal_punctuation_does_not_appear_as_substantive_rule(self):
        self.assertEqual(source_change.category(
            "일간신문, 방송으로 공고한다.", "일간신문·방송으로 공고한다."
        ),"표기 정비")

    def test_all_source_articles_are_independent_of_first_three_actions(self):
        changes=[make_change(f"제{i}조",
            f"제{i}조(접수) 신청서를 {i}일 이내 접수한다.",
            f"제{i}조(접수) 신청서를 {i+1}일 이내 접수한다.") for i in range(1,13)]
        full=source_change.source_pairs(changes)
        self.assertEqual(len(full),12)
        document={
            "title":"가상청 직제","kind":"대통령령",
            "verification":"verified_changed_clauses",
            "changed_articles":[x["article"] for x in changes],
            "excerpts":full[:3],"source_pairs":full,
            "url":LAW_URL,
        }
        event,actions=agency_actions.group_event({
            "id":"12","date":"2026-11-10","source_count":1,
            "agency_count":1,"source_docs":[document],"dependencies":[]})
        self.assertEqual(event["change_count"],12)
        self.assertEqual(len(event["article_differences"]),12)
        self.assertTrue(event["source_fingerprint"])
        self.assertLessEqual(len(actions),3)


    def test_source_summary_priority_favors_verified_cross_institution_event(self):
        from policy_domino.ai_impact import source_summary_priority
        high={"event_id":"high","promulgated_at":"2026-11-06",
              "source_fingerprint":"abc","impact_priority":175,
              "article_differences":[{"before":"옛 기준","after":"새 기준"}]}
        recent={"event_id":"recent","promulgated_at":"2026-11-10",
                "source_fingerprint":"def","impact_priority":5,
                "article_differences":[{"before":"옛 문장","after":"새 문장"}]}
        self.assertGreater(source_summary_priority(high),source_summary_priority(recent))

    def test_ai_summary_must_bind_to_actual_source_evidence(self):
        before="제5조(공고) 조성계획안 공모는 관보와 일간신문에 공고하여야 한다."
        after="제5조(공고) 조성계획안 공모는 관보, 신문, 인터넷신문 및 방송에 공고하여야 한다."
        pair=source_change.source_pairs([make_change("제5조",before,after)])
        event={
            "event_id":"v4:sample","title":"가상 공고 방식에 관한 규칙",
            "source_verification":"verified_changed_clauses",
            "article_differences":pair,"promulgated_at":"2026-11-10"
        }
        event["source_fingerprint"]=source_change.fingerprint(event)
        self.assertEqual(len(source_summary_payload(event)["source_changes"]),1)
        answer={"summary":"조성계획안 공모를 기존 관보와 일간신문에서 인터넷신문 및 방송까지 포함하도록 공고 매체를 확대합니다.","findings":[]}
        self.assertTrue(validate_source_summary(answer,event))
        invented={"summary":"조성계획안 공모 매체가 바뀌면서 2028년부터 공공기관 지급액이 999만원으로 인상됩니다.","findings":[]}
        self.assertEqual(validate_source_summary(invented,event),"")

        data={"schema":"policy-domino-next-v1","events":[event],"actions":[]}
        first=build_catalog(data)
        first["events"][0]["source_summary"]={
            "text":answer["summary"],"model":"test","source_fingerprint":event["source_fingerprint"]}
        reused=build_catalog(data,first)
        self.assertEqual(reused["events"][0]["source_summary"]["text"],answer["summary"])
        changed=copy.deepcopy(data)
        changed["events"][0]["article_differences"][0]["after"]="제5조(공고) 방송 공고를 하지 않는다."
        changed["events"][0]["source_fingerprint"]=source_change.fingerprint(changed["events"][0])
        invalidated=build_catalog(changed,first)
        self.assertNotIn("source_summary",invalidated["events"][0])

if __name__=="__main__":
    unittest.main()
