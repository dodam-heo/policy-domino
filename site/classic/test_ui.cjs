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
  assert.ok(page.includes('class="chip active" data-law="all"'),
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
assert.equal(view.DEFAULT_FILTER,"all");
assert.ok(script.includes("document.body.dataset.policyDataUrl"));
assert.ok(script.includes("filter=DEFAULT_FILTER"));
const fixtures=[
  {event_id:"old-high",impact_level:"high",promulgated_at:"2026-01-01",title:"가상 과거 변경",revision:"개정"},
  {event_id:"new-low",impact_level:"not_assessed",promulgated_at:"2026-12-01",title:"가상 신규",revision:"제정"},
  {event_id:"new-high",impact_level:"high",promulgated_at:"2026-11-01",title:"가상 최근 변경",revision:"개정"}
];
assert.deepEqual(view.filterEvents(fixtures).map(e=>e.event_id),["new-low","new-high","old-high"]);
assert.equal(view.resolveSelection(view.filterEvents(fixtures),"new-low"),"new-low");
assert.equal(view.resolveSelection([],"old-high"),null);
assert.equal(view.filterEvents(fixtures,"high-impact").length,2);
assert.equal(view.filterEvents(fixtures,"all").length,3);
assert.equal(view.filterEvents(fixtures,"new").length,1);
assert.equal(view.sorted(fixtures)[0].event_id,"new-low");
for(const label of ["변경 핵심","기관별 변경 검토사항","변경 전후",
    "검토할 조치","시행일·공식 근거","근거 재확인 필요"]){
  assert.ok(script.includes(label),"Missing operational detail: "+label);
}
for(const internalText of ["AI 분석 \\","이전 V2","검증 상태 · ","이번 변경에서 무엇을 확인했나",
  "AI 검토 초안 / 조치 완료 여부 미확인"]){
  assert.ok(!script.includes(internalText),"Remove internal copy: "+internalText);
}
assert.ok(!template.includes('class="workflow"'));
assert.ok(!template.includes('id="impactFilterHint"'));
assert.ok(!template.includes("사회적 중요도 등급"));
assert.ok(!template.includes("확인되지 않은 조치 여부는 임의로 표시"));

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
  assert.ok(["v4_verified_source","service_formula_dependency_verified",
    "service_cited_changed_article_verified"].includes(a.evidence_scope));
  if(a.service_id) assert.equal(a.comparison_scope,"source_policy_only");
  assert.ok(!("status" in a),"No agency implementation status may be published");
}
const official=d.actions.filter(a=>["v4_verified_source",
  "service_formula_dependency_verified"].includes(a.evidence_scope));
assert.ok(official.length>0);
assert.ok(d.events.every(e=>e.presentation_source==="v4_official_source"));
assert.ok(script.includes("실제 변경사항 · 신구 비교"));
assert.ok(script.includes('<details class="sourceChanges"'),
  "Actual changed clauses must be collapsed by default");
assert.ok(!script.includes('<details class="sourceChanges" open'),
  "Source comparisons must not begin expanded");
assert.ok(script.includes('sourceChangesHint')&&script.includes('펼쳐보기 ▾')&&script.includes('접기 ▴'),
  "Comparison disclosure must clearly communicate open/close actions");
assert.ok(script.includes('sourceChangesToggle'),
  "Change summary must expose an accessible disclosure control");
assert.ok(styles.includes(".sourceChanges .changePair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)}"),
  "Source before/after must remain horizontally paired");
assert.ok(styles.includes(".sourceChanges .changeCol+.changeCol{border-left:1px solid #e5ebef;border-top:0}"),
  "Mobile comparison must not be stacked");
assert.ok(script.includes("상위 정책 기준의 변경값"));
assert.ok(!script.includes("badgeStatus"),"No implementation-status badge");
assert.ok(!script.includes("status_evidence"),"No implementation-status evidence drawer");
assert.ok(!script.includes("반영 확인 필요"),"No implementation-state label");
console.log("CLASSIC_PASS",{events:d.events.length,agencyTasks:d.actions.length,
  official:official.length});
