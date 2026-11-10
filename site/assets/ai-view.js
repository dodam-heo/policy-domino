"use strict";
/** Entire event catalog. Cached AI cards must match CURRENT action evidence. */
(function(root) {
  const SCHEMA = "policy-domino-llm-impact-v2";
  const esc = value => String(value ?? "").replace(/[&<>"']/g,
    x => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[x]));
  function officialUrl(value) {
    try {
      const url = new URL(String(value));
      if(url.protocol !== "https:" ||
        !["www.law.go.kr","law.go.kr"].includes(url.hostname)) return "#";
      return esc(url.href);
    } catch (_) { return "#"; }
  }
  function eventEntry(event, catalog) {
    return catalog?.schema === SCHEMA && Array.isArray(catalog.events)
      ? catalog.events.find(item => item.event_id === event.event_id) || null : null;
  }
  function verifiedActions(event, data) {
    return (data.actions || []).filter(a => a.event_id === event.event_id &&
      a.evidence_scope === "v4_verified_source" &&
      typeof a.evidence_fingerprint === "string" &&
      a.evidence_fingerprint.length === 64);
  }
  function verifiedCards(event, data, catalog) {
    const entry = eventEntry(event,catalog);
    if(!entry || !Array.isArray(entry.findings))return [];
    const official = new Map(verifiedActions(event,data).map(a=>[a.id,a]));
    const seen = new Set();
    return entry.findings.filter(card=>{
      const original=official.get(card.action_id);
      if(!original || seen.has(card.action_id) ||
         card.evidence_fingerprint !== original.evidence_fingerprint ||
         card.agency !== original.agency ||
         card.law_title !== original.law_title ||
         card.article !== original.article ||
         card.basis_url !== original.basis ||
         typeof card.model !== "string" || !card.model ||
         typeof card.operational_impact !== "string" ||
         typeof card.review_task !== "string")return false;
      seen.add(card.action_id);
      return true;
    });
  }
  function progress(event,data,catalog) {
    const entry=eventEntry(event,catalog);
    if(!entry)return null;
    const total=verifiedActions(event,data).length;
    const done=verifiedCards(event,data,catalog).length;
    const state=total===0?"awaiting_verified_evidence":done===total?"complete":done?"partial":"pending";
    return {total,done,state};
  }
  function statusLabel(event,data,catalog) {
    const p=progress(event,data,catalog);
    if(!p)return "";
    if(!p.total)return "AI 근거 확인 대기";
    return "AI 분석 "+p.done+"/"+p.total;
  }
  function render(event,data,catalog) {
    const p=progress(event,data,catalog);
    if(!p)return "";
    const entry=eventEntry(event,catalog);
    const cards=verifiedCards(event,data,catalog);
    const state=p.total===0?"공식 근거 검증 대기":p.state==="complete"?"분석 완료":"분석 진행 중";
    return '<section class="aiAnalysis" aria-label="정책 사건별 실제 LLM 영향 분석">'+
      '<div class="aiAnalysisHead"><strong>AI 기관별 영향 분석</strong><span>'+esc(state)+'</span></div>'+
      '<div class="aiAnalysisMeta">'+(p.total
        ?'공식 근거 있는 검토사항 '+p.total+'건 중 AI 분석 '+p.done+'건'
        :'현재 공식 신구 조문과 기관 업무 관계 검증 대기')+'</div>'+
      (cards.length ? cards.map(card=>
        '<article class="aiImpactCard"><b>'+esc(card.agency)+'</b>'+
        '<div class="aiImpactLocation">'+esc(card.law_title)+' · '+esc(card.article)+'</div>'+
        '<div class="aiImpactLabel">AI가 분석한 업무 영향</div>'+
        '<p>'+esc(card.operational_impact)+'</p>'+
        '<div class="aiImpactLabel">확인해야 할 조치</div>'+
        '<p>'+esc(card.review_task)+'</p>'+
        '<div class="aiImpactLocation">실제 분석 모델: '+esc(card.model)+'</div>'+
        '<a href="'+officialUrl(card.basis_url)+'" target="_blank" rel="noopener noreferrer">공식 변경 근거 확인 ↗</a>'+
        '</article>').join("")
        :'<p class="aiAnalysisCaution">'+(p.total
          ?'공식 근거는 확인됐으며, LLM 분석을 순차 진행할 예정입니다.'
          :'AI가 근거 없이 기관별 영향을 만들어 표시하지 않습니다.')+'</p>')+
      (p.total && p.done<p.total
        ?'<p class="aiAnalysisCaution">남은 검토사항 '+(p.total-p.done)+'건은 다음 AI 분석 실행 때 이어서 처리합니다.</p>':'')+
      (cards.length?'<p class="aiAnalysisCaution">이 결과는 공개 근거를 읽은 LLM의 검토 초안이며, 기관의 실제 업무 반영·조치 완료를 확인한 것은 아닙니다.</p>':'')+
      '</section>';
  }
  const api=Object.freeze({SCHEMA,eventEntry,verifiedCards,progress,statusLabel,render});
  root.PolicyDominoAiView=api;
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
})(typeof window==="undefined"?globalThis:window);
