"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const ai=require("../assets/ai-view.js");
const hash="a".repeat(64), changedHash="b".repeat(64);
const one={event_id:"v4:one"},two={event_id:"v4:two"},legacy={event_id:"legacy:one"};
const official={
  generated_at:"2026-11-10T01:00:00Z",
  actions:[
    {id:"1",event_id:"v4:one",agency:"가상공공기관 가",law_title:"가상 직제",
      article:"제5조",basis:"https://www.law.go.kr/법령/가상",
      evidence_scope:"v4_verified_source",evidence_fingerprint:hash},
    {id:"2",event_id:"v4:one",agency:"가상공공기관 나",law_title:"가상 직제",
      article:"제6조",basis:"https://www.law.go.kr/법령/가상",
      evidence_scope:"v4_verified_source",evidence_fingerprint:changedHash},
    {id:"3",event_id:"v4:two",agency:"가상기관 다",law_title:"별도 규정",
      article:"제2조",basis:"https://www.law.go.kr/법령/별도",
      evidence_scope:"v4_verified_source",evidence_fingerprint:hash},
    {id:"4",event_id:"legacy:one",agency:"미확인 기관",law_title:"과거 규정",
      article:"제1조",basis:"https://www.law.go.kr/법령/가상",
      evidence_scope:"legacy_official_directive_awaiting_recheck",evidence_fingerprint:hash}
  ]
};
const card=(id,agency,article,law,hashValue,basis)=>({
  action_id:id,agency,article,law_title:law,basis_url:basis,
  evidence_fingerprint:hashValue,model:"gemini-3.5-flash-lite",
  operational_impact:"변경된 기준에 의해 인사 업무에 영향이 있습니다.",
  review_task:"관련 업무 설정과 정원 대장을 확인합니다."
});
const c1=card("1","가상공공기관 가","제5조","가상 직제",hash,"https://www.law.go.kr/법령/가상");
const c2=card("2","가상공공기관 나","제6조","가상 직제",changedHash,"https://www.law.go.kr/법령/가상");
const c3=card("3","가상기관 다","제2조","별도 규정",hash,"https://www.law.go.kr/법령/별도");
const catalog={schema:ai.SCHEMA,source_generated_at:official.generated_at,events:[
  {event_id:one.event_id,eligible_actions:2,analyzed_actions:1,status:"partial",findings:[c1]},
  {event_id:two.event_id,eligible_actions:1,analyzed_actions:1,status:"complete",findings:[c3]},
  {event_id:legacy.event_id,eligible_actions:0,analyzed_actions:0,
    status:"awaiting_verified_evidence",findings:[]}
]};
assert.equal(ai.verifiedCards(one,official,catalog).length,1);
assert.equal(ai.verifiedCards(two,official,catalog).length,1);
assert.equal(ai.verifiedCards(legacy,official,catalog).length,0);
assert.equal(ai.statusLabel(one,official,catalog),"AI 분석 1/2");
assert.equal(ai.statusLabel(two,official,catalog),"AI 분석 1/1");
assert.equal(ai.statusLabel(legacy,official,catalog),"AI 근거 확인 대기");
assert.match(ai.render(one,official,catalog),/분석 진행 중/);
assert.match(ai.render(one,official,catalog),/남은 검토사항 1건/);
assert.match(ai.render(two,official,catalog),/분석 완료/);
assert.match(ai.render(two,official,catalog),/가상기관 다/);
assert.match(ai.render(legacy,official,catalog),/공식 근거 검증 대기/);
assert.equal(ai.render(one,official,null),"");
assert.equal(ai.render(one,official,{...catalog,schema:"old-v1"}),"");

// Snapshot regeneration must NOT invalidate unchanged evidence.
assert.equal(ai.verifiedCards(one,{...official,generated_at:"another time"},catalog).length,1);

// But changing the source fingerprint for a single action invalidates only it.
const updated={...official,actions:official.actions.map(x=>
  x.id==="1"?{...x,evidence_fingerprint:changedHash}:x
)};
assert.equal(ai.verifiedCards(one,updated,catalog).length,0);
assert.equal(ai.verifiedCards(two,updated,catalog).length,1);
assert.equal(ai.progress(one,updated,catalog).state,"pending");
assert.equal(ai.verifiedCards(one,official,{
  ...catalog,events:[{...catalog.events[0],findings:[c1,c2]},...catalog.events.slice(1)]
}).length,2);

// Never trust model-supplied unsupported institutions, links or execution status.
assert.equal(ai.verifiedCards(one,official,{
  ...catalog,events:[{...catalog.events[0],findings:[{...c1,agency:"민간기업"}]},
                     ...catalog.events.slice(1)]
}).length,0);
assert.equal(ai.verifiedCards(one,official,{
  ...catalog,events:[{...catalog.events[0],findings:[{...c1,basis_url:"https://fake.invalid"}]},
                     ...catalog.events.slice(1)]
}).length,0);
const injection=ai.render(one,official,{
  ...catalog,events:[{...catalog.events[0],findings:[{
    ...c1,operational_impact:"<img src=x onerror=alert(1)>"
  }]},...catalog.events.slice(1)]
});
assert.ok(injection.includes("&lt;img"));
assert.ok(!injection.includes("<img"));

const page=fs.readFileSync("site/templates/agency.html","utf8");
assert.ok(page.includes('src="../assets/ai-view.js"'));
const app=fs.readFileSync("site/assets/classic.js","utf8");
new vm.Script(app,{filename:"classic.js"});
assert.ok(app.includes("window.PolicyDominoAiView.render(e,DATA,AI_DATA)"));
assert.ok(app.includes("window.PolicyDominoAiView.statusLabel(e,DATA,AI_DATA)"));
assert.ok(app.includes('candidate?.schema==="policy-domino-llm-impact-v2"'));
assert.ok(!app.includes("candidate.source_generated_at===d.generated_at"));
console.log("AI_CATALOG_VIEW_PASS: every event, partial results, unchanged cache reuse and source-level invalidation");
