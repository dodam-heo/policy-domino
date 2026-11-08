/* Policy Domino: presentation compatibility adapter.
   Preserve original agency-first presentation while consuming verified, source-wide data.
   No policy names, eligible sectors, amounts or derived thresholds are registered here. */
(function (root) {
  "use strict";
  const text = value => String(value ?? "").trim();
  const first = (...values) => values.find(v => text(v)) ?? "";
  const unique = items => [...new Set(items.filter(Boolean))];
  const operational = e =>
    (["제도·업무 변경","조직개편·업무이관"].includes(e.impact_category) &&
    Array.isArray(e.effects) && e.effects.length > 0) ||
    (/연도별/.test(e.comparison_status || "") && (e.changes || []).length > 0) ||
    (e.impact_category === "폐지·효력종료" && /폐지/.test(e.revision || "") && !/제정/.test(e.revision || ""));

  function changedValues(event, action, evidenceType) {
    // Prefer the actual whole source statements vetted and assigned to this
    // specific agency duty. Never re-pair arbitrary word fragments from other
    // changes to the same article.
    if (Array.isArray(action.change_pairs) && action.change_pairs.length)
      return action.change_pairs.slice(0, 3).map(x => ({
        before: text(x.before), after: text(x.after),
        article: text(x.article), confidence: text(x.confidence)
      }));
    // A referenced downstream rule is NOT an instruction to replicate the
    // source institution's numerical value (e.g. its staffing headcount).
    if (evidenceType === "downstream") return [];
    const effects = Array.isArray(event.effects) ? event.effects : [];
    const article = text(action.article);
    const work = text(action.work);
    // Do not take the first unrelated change just because the event contains
    // one effect. An agency card must point to that actual changed article.
    if (!article || !work) return [];
    const matching=effects.filter(x => x.article === article &&
      (x.operations || []).includes(work) ||
      (x.article === article && work === "조직·정원 관리" &&
        (x.operations || []).includes("조직·인력")));
    return matching.slice(0, 3).map(x => ({
      before:first(x.old, "기존 해당 항목 없음"),
      after:first(x.new, "삭제"),
      article:text(x.article)
    }));
  }

  function convertAction(e, a, evidenceType) {
    const agency = first(a.agency, "기관 미확인");
    const level = evidenceType === "direct" ? "변경 규정에 명시된 집행기관" :
      evidenceType === "downstream" ? "연관 규정 소관·집행기관 검토 (근거 수준 확인)" :
      "공식 문서 소관기관 · 실제 집행기관 추가 조사";
    const changes = changedValues(e, a, evidenceType);
    const linkedEvidence = first(a.evidence_type, a.agency_role,
      a.basis_excerpt, evidenceType === "direct" ? "공식 법령에 명시된 집행주체" :
      "행정규정의 소관기관 또는 참조 문서");
    const status = evidenceType === "candidate" ?
      "집행기관 추가 조사" : evidenceType === "downstream" ?
      first(a.status, "연관 제도 적용 검토") : "업무 반영 검토 필요";
    return {
      event_id: e.id, agency, agency_role: level, work: first(a.work, "업무 기준 변경"),
      target_location: first(a.target_location, a.article, "업무 기준 적용 위치 확인"),
      what_to_change: first(a.what_to_change, changes.map(x => x.before + " → " + x.after).join(" / ")),
      required_change: first(a.required_change, "관련 업무에 변경 기준이 적용되는지 검토"),
      changes,
      sentence_verified: Array.isArray(a.change_pairs) && a.change_pairs.length > 0,
      change_label: evidenceType === "direct" && text(a.target_location).includes(" · ") ?
        text(a.target_location) : "",
      change_units: text(a.evidence_type).includes("공무원 정원표") ? "명" : "",
      status,
      article: first(a.article, a.basis_article),
      basis: first(a.source_url, a.basis, e.url),
      law_title: e.title,
      effective_date: e.effective_date,
      impact_link_basis: linkedEvidence,
      verification_note: first(a.verification_note,
        evidenceType === "candidate" ?
        "소관기관은 확인했지만 실제 집행기관·부서와 변경 조치 여부는 미확인입니다." :
        "공식 변경·참조 근거는 확인했으나 기관별 내부 규정·시스템 반영 여부는 미확인입니다."),
      status_evidence: "공식 자료에서 실제 조치 완료 여부 확인되지 않음",
      evidence_type: evidenceType
    };
  }

  function convertedEvent(e) {
    const changes = Array.isArray(e.changes) ? e.changes : [];
    const comparison = text(e.comparison_status);
    const category = first(e.impact_category,
      /직제|정원|승진|인사|조직/.test(e.title || "") ? "조직·내부운영" : "기타 변경");
    const effect = Array.isArray(e.effects) ? e.effects.find(x => x.old || x.new) : null;
    const summary = effect ?
      [first(effect.old, "신설"), " → ", first(effect.new, "삭제")].join("") : "";
    return {
      ...e,
      event_id: e.id,
      change_type: first(e.revision, e.kind, "개정"),
      law_type: first(e.kind, e.source === "admrul" ? "고시·행정규칙" : "법령"),
      article_differences: changes.map(x => ({
        article: x.article, type: x.type, before: x.before, after: x.after
      })),
      policy_profile: operational(e),
      impact_category: category,
      impact_priority: ((e.priority || 0) +
          ((e.policy_links || []).length * 30) +
          (e.effective_date > new Date().toISOString().slice(0,10) ? 40 : 0) +
          (/연도별/.test(comparison) ? 25 : 0) +
          (e.impact_category === "조직개편·업무이관" ? 25 : 0)),
      change_summary: first(
        e.impact_summary,
        (e.institution_actions || []).find(a => a.verified_location &&
          a.evidence_type === "개정된 공무원 정원표의 명시된 기관·항목")?.what_to_change,
        e.impact_category === "조직개편·업무이관" ?
          "조직 직제·정원표 변경 확인 · 정확한 담당 기관과 변경 항목을 확인하세요" : summary),
      amendment_reason: text(e.amendment_reason),
      amendment_url: first(e.url),
      comparison_status: comparison
    };
  }

  function normalizeV3(d) {
    const events = (d.events || []).map(convertedEvent);
    const actions = [];
    for (const e of d.events || []) {
      // Evidence rules are uniform across policy types. A staffing table
      // and a changed statutory duty have different evidence formats, but
      // neither qualifies because of its specific agency or document title.
      const direct = e.institution_actions || [];
      // A candidate source, issuer, or mere official reference is not an
      // affected agency required to change its own business rules. Only
      // scoped, source-backed obligations can enter action cards.
      if (!(/폐지/.test(e.revision || "") && !/제정/.test(e.revision || ""))) {
        direct.filter(a => a.verified_location === true ||
          a.evidence_type === "변경된 동일 조문 내 업무주체·의무문 확인")
          .forEach(a => actions.push(convertAction(e, a, "direct")));
      }
    }
    return {
      schema: "policy-domino-next-v1",
      events, actions, generated_at: d.generated_at,
      health: {
        source_status: d.source_health?.status === "수집 실패" ? "수집 실패" :
          d.source_health?.partial ? "부분 수집" : "공식 공포·개정문 연결",
        compared: d.impact_health?.verified_documents || 0,
        amendments_verified_total: d.impact_health?.verified_documents || 0,
        official_links: (d.impact_health?.dependent_rules_found || 0) +
          (d.impact_health?.cross_policy_links?.links || 0),
        pending_details: d.source_health?.pending_details || 0,
        errors: d.source_health?.errors || []
      }
    };
  }

  function normalizeV2(d) {
    const events = (d.events || []).map(e => ({
      ...e, event_id: e.id, change_type: first(e.revision, e.kind, "개정"),
      law_type: first(e.kind, e.source === "law" ? "법령" : "고시·행정규칙"),
      article_differences: e.changes || [],
      policy_profile: (e.changes || []).length > 0 &&
        !/직제|정원|승진|인사|조직/.test(e.title || ""),
      amendment_url: e.url
    }));
    const actions = (d.actions || []).map(a => {
      const e = (d.events || []).find(item => item.id === a.event_id);
      return {
        ...a, event_id: a.event_id, agency_role: first(a.agency_role,
          "공식 규정 소관 또는 변경 업무주체"),
        status: "업무 반영 검토 필요",
        law_title: e?.title || "",
        basis: first(a.basis, e?.url),
        changes: a.changes || (a.before || a.after ?
          [{before: a.before || "미확인", after: a.after || "미확인"}] : []),
        status_evidence: "실제 조치 완료 또는 미조치 확인 근거 없음"
      };
    });
    return {
      schema: "policy-domino-next-v1",
      events, actions, generated_at: d.generated_at,
      health: {
        source_status: d.health?.status === "수집 실패" ? "수집 실패" : "공식 공포·개정문 연결",
        compared: d.health?.verified_compared || 0,
        amendments_verified_total: d.health?.verified_compared || 0
      }
    };
  }

  function normalizePolicyData(input) {
    if (!input || typeof input !== "object") throw Error("공식 데이터 형식을 확인할 수 없습니다.");
    if (input.schema === "policy-domino-next-v1") return input;
    if (input.schema === "policy-domino-impact-v3") return normalizeV3(input);
    if (input.schema === "policy-domino-v2") return normalizeV2(input);
    throw Error("지원되지 않는 정책 영향 데이터 형식: " + String(input.schema));
  }
  root.normalizePolicyData = normalizePolicyData;
  if (typeof module !== "undefined" && module.exports)
    module.exports = {normalizePolicyData};
})(typeof window === "undefined" ? globalThis : window);
