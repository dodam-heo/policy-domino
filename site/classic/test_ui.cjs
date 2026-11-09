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
assert.equal(d.schema,"policy-domino-next-v1");
assert.ok(d.events.length>0&&d.actions.length>0,"Must display actual sourced work");
const events=new Map(d.events.map(e=>[e.event_id,e]));
for(const a of d.actions){
  assert.ok(events.has(a.event_id),"Every action must have a clickable event");
  assert.ok(a.agency && a.work && a.article && a.required_change);
  assert.ok(a.changes?.length>0 && a.basis.startsWith("https://www.law.go.kr"));
  assert.ok(["v4_verified_source","legacy_official_directive_awaiting_recheck"].includes(a.evidence_scope));
  assert.notEqual(a.status,"조치 확인");
  assert.notEqual(a.status,"미조치 확인");
}
const official=d.actions.filter(a=>a.evidence_scope==="v4_verified_source");
const legacy=d.actions.filter(a=>a.evidence_scope==="legacy_official_directive_awaiting_recheck");
assert.ok(official.length>0&&legacy.length>0);
console.log("CLASSIC_PASS",{events:d.events.length,agencyTasks:d.actions.length,
  official:official.length,oldOfficialPendingReview:legacy.length});
