"use strict";
/** Only render an LLM suggestion when it matches the current official snapshot. */
(function(root) {
  const SCHEMA = "policy-domino-llm-impact-v1";
  const esc = value => String(value ?? "").replace(/[&<>"']/g,
    x => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[x]));
  function officialUrl(value) {
    try {
      const url = new URL(String(value));
      if(url.protocol !== "https:" || !["www.law.go.kr","law.go.kr"].includes(url.hostname))return "#";
      return esc(url.href);
    } catch (_) { return "#"; }
  }
  function verifiedCards(event, data, analysis) {
    if(!analysis || analysis.schema !== SCHEMA ||
       analysis.event_id !== event.event_id ||
       !analysis.source_generated_at ||
       analysis.source_generated_at !== data.generated_at ||
       !Array.isArray(analysis.findings)) return [];
    const official = new Map((data.actions || []).filter(a =>
      a.event_id === event.event_id && a.evidence_scope === "v4_verified_source"
    ).map(a => [a.id, a]));
    const used = new Set();
    return analysis.findings.filter(card => {
      const original = official.get(card.action_id);
      if(!original || used.has(card.action_id) ||
         original.agency !== card.agency ||
         original.basis !== card.basis_url ||
         original.article !== card.article ||
         typeof card.operational_impact !== "string" ||
         typeof card.review_task !== "string") return false;
      used.add(card.action_id);
      return true;
    });
  }
  function render(event, data, analysis) {
    const cards = verifiedCards(event, data, analysis);
    if(!cards.length)return "";
    return '<section class="aiAnalysis" aria-label="LLM 정책 영향 분석 초안">'+
      '<div class="aiAnalysisHead"><strong>AI 기관별 영향 분석</strong><span>LLM 초안 · 검토 필요</span></div>'+
      '<div class="aiAnalysisMeta">사용 모델: '+esc(analysis.model || "미확인")+' · 공식 변경 근거와 분리 표시</div>'+
      '<p class="aiAnalysisSummary">'+esc(analysis.summary || "")+'</p>'+
      cards.map(card =>
        '<article class="aiImpactCard"><b>'+esc(card.agency)+'</b>'+
        '<div class="aiImpactLocation">'+esc(card.law_title || "")+' · '+esc(card.article)+'</div>'+
        '<div class="aiImpactLabel">AI가 분석한 업무 영향</div>'+
        '<p>'+esc(card.operational_impact)+'</p>'+
        '<div class="aiImpactLabel">확인해야 할 조치</div>'+
        '<p>'+esc(card.review_task)+'</p>'+
        '<a href="'+officialUrl(card.basis_url)+'" target="_blank" rel="noopener noreferrer">공식 변경 근거 확인 ↗</a>'+
        '</article>').join("")+
      '<p class="aiAnalysisCaution">AI가 공개된 변경 근거를 해석한 검토 초안입니다. 실제 기관 업무 적용 및 조치 완료 여부는 확인되지 않았습니다.</p>'+
      '</section>';
  }
  const api = Object.freeze({SCHEMA, verifiedCards, render});
  root.PolicyDominoAiView = api;
  if(typeof module !== "undefined" && module.exports)module.exports = api;
})(typeof window === "undefined" ? globalThis : window);
