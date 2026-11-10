"use strict";
/** One AI catalog; show a compact event progress label and action-level drafts only. */
(function(root) {
  const SCHEMA = "policy-domino-llm-impact-v2";
  const esc = value => String(value ?? "").replace(/[&<>"']/g,
    x => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[x]));

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
    const entry = eventEntry(event, catalog);
    if (!entry || !Array.isArray(entry.findings)) return [];
    const official = new Map(verifiedActions(event, data).map(a => [a.id, a]));
    const seen = new Set();
    return entry.findings.filter(card => {
      const original = official.get(card.action_id);
      if (!original || seen.has(card.action_id) ||
          card.evidence_fingerprint !== original.evidence_fingerprint ||
          card.agency !== original.agency ||
          card.law_title !== original.law_title ||
          card.article !== original.article ||
          card.basis_url !== original.basis ||
          typeof card.model !== "string" || !card.model ||
          typeof card.operational_impact !== "string" || !card.operational_impact.trim() ||
          typeof card.review_task !== "string" || !card.review_task.trim()) return false;
      seen.add(card.action_id);
      return true;
    });
  }
  function progress(event, data, catalog) {
    const entry = eventEntry(event, catalog);
    if (!entry) return null;
    const total = verifiedActions(event, data).length;
    const done = verifiedCards(event, data, catalog).length;
    const state = total === 0 ? "awaiting_verified_evidence" :
      done === total ? "complete" : done ? "partial" : "pending";
    return {total, done, state};
  }
  function latestAnalyzedAt(data, catalog) {
    if (catalog?.schema !== SCHEMA) return null;
    let latest = "";
    for (const event of data.events || []) {
      for (const card of verifiedCards(event, data, catalog)) {
        if (typeof card.analyzed_at === "string" &&
            /^\\d{4}-\\d{2}-\\d{2}T/.test(card.analyzed_at) &&
            card.analyzed_at > latest) latest = card.analyzed_at;
      }
    }
    return latest || null;
  }
  function renderForAction(action, card) {
    if (!card || card.action_id !== action.id) return "";
    // The caller must get card from verifiedCards(), which checks all
    // official event/action identity and current evidence fingerprints.
    return '<details class="aiActionNote">'+
      '<summary>AI 검토 의견</summary>'+
      '<div class="aiActionBody">'+
      '<div class="aiActionLabel">업무 영향</div>'+
      '<p>'+esc(card.operational_impact)+'</p>'+
      '<div class="aiActionLabel">추가 확인사항</div>'+
      '<p>'+esc(card.review_task)+'</p>'+
      '</div></details>';
  }
  const api = Object.freeze({
    SCHEMA, eventEntry, verifiedActions, verifiedCards,
    progress, latestAnalyzedAt, renderForAction
  });
  root.PolicyDominoAiView = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window === "undefined" ? globalThis : window);
