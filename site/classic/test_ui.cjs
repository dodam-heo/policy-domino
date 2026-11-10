"use strict";
const fs=require("node:fs");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const template=fs.readFileSync("site/templates/agency.html","utf8");
const classic=fs.readFileSync("site/classic/index.html","utf8");
const impact=fs.readFileSync("site/impact/index.html","utf8");
const script=fs.readFileSync("site/assets/classic.js","utf8");
const styles=fs.readFileSync("site/assets/classic.css","utf8");
const view=require("../assets/impact-model.js");

assert.equal(classic,template.replace("__POLICY_DATA_URL__","./data.json"),
  "Classic route must be generated from the same template");
assert.equal(impact,template.replace("__POLICY_DATA_URL__","../classic/data.json"),
  "Impact route must read the same official source-backed dataset");
for(const page of [classic,impact]){
  assert.ok(page.includes('data-law="high-impact"'));
  assert.ok(page.includes('class="chip active" data-law="high-impact"'),
    "High impact must be selected in initial HTML");
  assert.ok(page.includes('>영향도 큼</button>'));
  assert.ok(!page.includes('data-law="standards"'));
  assert.ok(page.includes('../assets/classic.css'));
  assert.ok(page.includes('../assets/impact-model.js'));
  assert.ok(page.includes('../assets/classic.js'));
  assert.ok(!page.includes("<script>"),"Do not duplicate inline view logic");
}
new vm.Script(script,{filename:"site/assets/classic.js"});
assert.ok(styles.includes(".chip.active"));
assert.equal(view.DEFAULT_FILTER,"high-impact");
assert.ok(script.includes("document.body.dataset.policyDataUrl"));
assert.ok(script.includes("filter=DEFAULT_FILTER"));
const fixtures=[
  {event_id:"old-high",impact_level:"high",promulgated_at:"2026-01-01",title:"가상 과거 변경",revision:"개정"},
  {event_id:"new-low",impact_level:"not_assessed",promulgated_at:"2026-12-01",title:"가상 신규",revision:"제정"},
  {event_id:"new-high",impact_level:"high",promulgated_at:"2026-11-01",title:"가상 최근 변경",revision:"개정"}
];
assert.deepEqual(view.filterEvents(fixtures).map(e=>e.event_id),["new-high","old-high"]);
assert.equal(view.resolveSelection(view.filterEvents(fixtures),"new-low"),"new-high");
assert.equal(view.resolveSelection([],"old-high"),null);
assert.equal(view.filterEvents(fixtures,"all").length,3);
assert.equal(view.filterEvents(fixtures,"new").length,1);
assert.equal(view.sorted(fixtures)[0].event_id,"new-low");
for(const label of ["기관별 변경 검토사항","공식 변경 전후 내용",
    "검토할 조치","이전 V2 개정 지시문 · 최신 재검증 대기",
    "어떤 업무를 검토하나?"]){
  assert.ok(script.includes(label),"Missing operational detail: "+label);
}

const d=JSON.parse(fs.readFileSync("site/classic/data.json","utf8"));
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
