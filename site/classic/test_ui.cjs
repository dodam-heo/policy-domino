const fs=require("node:fs");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const html=fs.readFileSync("site/classic/index.html","utf8");
const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
assert.equal(scripts.length,1,"Classic page must contain one working renderer");
new vm.Script(scripts[0][1],{filename:"site/classic/index.html"});
for(const label of ["기관별 변경 검토사항","공식 변경 전후 내용",
    "검토할 조치","이전 V2 개정 지시문 · 최신 재검증 대기",
    "어떤 업무를 검토하나?"]){
  assert.ok(html.includes(label),"Missing actionable content: "+label);
}
const d=JSON.parse(fs.readFileSync("site/classic/data.json","utf8"));
assert.ok(html.includes('data-law="high-impact"'));
assert.ok(html.includes('>영향도 큼</button>'));
assert.ok(!html.includes('data-law="standards"'));
assert.ok(!html.includes('data-law="actionable"'));
assert.ok(html.includes('e.impact_level==="high"'));
assert.equal(d.schema,"policy-domino-next-v1");
assert.ok(d.events.length>0&&d.actions.length>0,"Must display actual sourced work");
const high=d.events.filter(e=>e.impact_level==="high");
assert.ok(high.length>0,"Expected at least one multiple-institution official case");
for(const e of d.events){
  assert.ok(e.impact_scope && e.impact_scope.criteria);
  const agencies=new Set(d.actions.filter(a=>a.event_id===e.event_id).map(a=>a.agency));
  const links=e.downstream_changes?.filter(x=>x.status==="변경 조항 적용 관계 확인" &&
    x.title && x.article && x.evidence)||[];
  assert.equal(e.impact_level==="high",agencies.size>=2||links.length>=2,
    "Scope and filter mismatch: "+e.title);
}
const events=new Map(d.events.map(e=>[e.event_id,e]));
for(const a of d.actions){
  assert.ok(events.has(a.event_id),"Every action must have a clickable event");
  assert.ok(a.agency && a.work && a.article && a.required_change);
  assert.ok(a.changes?.length>0 && a.basis.startsWith("https://www.law.go.kr"));
  assert.ok(["v4_verified_source","legacy_official_directive_awaiting_recheck","official_institutional_program_dependency"].includes(a.evidence_scope));
  assert.notEqual(a.status,"조치 확인");
  assert.notEqual(a.status,"미조치 확인");
}
const official=d.actions.filter(a=>a.evidence_scope==="v4_verified_source");
const legacy=d.actions.filter(a=>a.evidence_scope==="legacy_official_directive_awaiting_recheck");
assert.ok(official.length>0&&legacy.length>0);
const institutional=d.actions.filter(a=>a.evidence_scope==="official_institutional_program_dependency");
assert.ok(institutional.length>=3,"Independent institutional applications must be visible");
for(const action of institutional){
  assert.ok(action.agency_basis?.startsWith("https://"));
  assert.ok(action.institution_evidence?.excerpt);
  assert.equal(action.institutional_implementation_verified,false);
  assert.equal(action.is_direct_legal_amendment,false);
  assert.match(action.changes[0].meaning,/원천 정책/);
}
console.log("CLASSIC_PASS",{events:d.events.length,agencyTasks:d.actions.length,
  official:official.length,oldOfficialPendingReview:legacy.length,institutionalReview:institutional.length});
