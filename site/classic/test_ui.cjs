"use strict";
const fs=require("node:fs");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const template=fs.readFileSync("site/templates/agency.html","utf8");
const classic=fs.readFileSync("site/classic/index.html","utf8");
const impact=fs.readFileSync("site/impact/index.html","utf8");
const script=fs.readFileSync("site/assets/classic.js","utf8");
const styles=fs.readFileSync("site/assets/classic.css","utf8");
const {DEFAULT_FILTER,sorted,filterEvents,resolveSelection}=require("../assets/impact-model.js");

assert.equal(classic,template.replace("__POLICY_DATA_URL__","./data.json"),
  "Classic shell must be generated from one shared template");
assert.equal(impact,template.replace("__POLICY_DATA_URL__","../classic/data.json"),
  "Impact route must use the same markup and Classic dataset");
for(const html of [classic,impact]){
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
  assert.ok(["v4_verified_source","legacy_official_directive_awaiting_recheck"].includes(a.evidence_scope));
  assert.notEqual(a.status,"조치 확인");
  assert.notEqual(a.status,"미조치 확인");
}
const official=d.actions.filter(a=>a.evidence_scope==="v4_verified_source");
const legacy=d.actions.filter(a=>a.evidence_scope==="legacy_official_directive_awaiting_recheck");
assert.ok(official.length>0&&legacy.length>0);
console.log("CLASSIC_PASS",{events:d.events.length,agencyTasks:d.actions.length,
  official:official.length,oldOfficialPendingReview:legacy.length});
