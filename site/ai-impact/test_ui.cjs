"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const ai = require("../assets/ai-view.js");

const event = {event_id:"v4:official-change"};
const base = {generated_at:"2026-11-10T01:00:00Z",actions:[
  {id:"direct",event_id:"v4:official-change",agency:"가상공공기관",
   article:"제5조",basis:"https://www.law.go.kr/법령/가상",
   evidence_scope:"v4_verified_source"},
  {id:"old",event_id:"v4:official-change",agency:"이전자료",
   article:"제5조",basis:"https://www.law.go.kr/법령/가상",
   evidence_scope:"legacy_official_directive_awaiting_recheck"}
]};
const card = {action_id:"direct",agency:"가상공공기관",article:"제5조",
  law_title:"가상정책법",basis_url:"https://www.law.go.kr/법령/가상",
  operational_impact:"정원 기준이 변경되어 인력 관리 방식에 영향을 줍니다.",
  review_task:"정원 관리표와 실제 배정 기준의 적용 여부를 확인합니다."};
const data = {schema:ai.SCHEMA,event_id:"v4:official-change",
  source_generated_at:"2026-11-10T01:00:00Z",model:"configured-model",
  summary:"공식 근거에 연결된 기관별 업무를 검토해야 합니다.",
  findings:[card]};

assert.equal(ai.verifiedCards(event,base,data).length,1);
const html = ai.render(event,base,data);
assert.match(html,/AI 기관별 영향 분석/);
assert.match(html,/검토 필요/);
assert.match(html,/가상공공기관/);
assert.match(html,/공식 변경 근거/);
assert.match(html,/configured-model/);

assert.equal(ai.render(event,{...base,generated_at:"new"},data),"",
  "Stale model evidence must never appear against refreshed official data");
assert.equal(ai.render({...event,event_id:"other"},base,data),"");
assert.equal(ai.render(event,base,null),"");
assert.equal(ai.render(event,base,{...data,schema:"fake"}),"");
assert.equal(ai.render(event,base,{...data,findings:[
  {...card,action_id:"old",agency:"이전자료"}]}),"",
  "Older unverified legacy actions are not model-supported");
assert.equal(ai.render(event,base,{...data,findings:[
  {...card,agency:"지어낸 기관"}]}),"",
  "Never display invented institution names");
assert.equal(ai.render(event,base,{...data,findings:[
  {...card,basis_url:"https://fake.invalid"}]}),"",
  "Never show a mismatched AI-issued source");
const injected = ai.render(event,base,{...data,summary:"<img src=x onerror=alert(1)>"});
assert.ok(injected.includes("&lt;img"));
assert.ok(!injected.includes("<img"));

const template = fs.readFileSync("site/templates/agency.html","utf8");
assert.ok(template.includes('src="../assets/ai-view.js"'));
const app = fs.readFileSync("site/assets/classic.js","utf8");
new vm.Script(app,{filename:"site/assets/classic.js"});
assert.ok(app.includes("window.PolicyDominoAiView.render(e,DATA,AI_DATA)"));
assert.ok(app.includes('candidate.source_generated_at===d.generated_at'));
assert.ok(app.includes("../ai-impact/data.json"));
console.log("AI_VIEW_PASS: true LLM output only, evidence snapshot and institution provenance gates");
