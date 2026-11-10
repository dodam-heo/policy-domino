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
assert.match(ai.renderForAction(official.actions[0],c1),/AI 업무 영향·추가 검토사항 보기/);
assert.match(ai.renderForAction(official.actions[0],c1),/관련 업무 설정/);
assert.equal(ai.renderForAction(official.actions[1],c1),"");
assert.equal(ai.renderForAction(official.actions[0],null),"");
assert.equal(ai.eventEntry(one,{...catalog,schema:"old-v1"}),null);
assert.equal(ai.verifiedCards(one,official,null).length,0);
assert.equal(ai.progress(one,official,catalog).state,"partial");
assert.equal(ai.progress(two,official,catalog).state,"complete");
assert.equal(ai.progress(legacy,official,catalog).state,"awaiting_verified_evidence");

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
const injection=ai.renderForAction(official.actions[0],{
  ...c1,operational_impact:"<img src=x onerror=alert(1)>"
});
assert.ok(injection.includes("&lt;img"));
assert.ok(!injection.includes("<img"));

const page=fs.readFileSync("site/templates/agency.html","utf8");
assert.ok(page.includes('src="../assets/ai-view.js"'));
const app=fs.readFileSync("site/assets/classic.js","utf8");
new vm.Script(app,{filename:"classic.js"});
assert.ok(!app.includes("window.PolicyDominoAiView.render(e,DATA,AI_DATA)"));
assert.ok(app.includes("window.PolicyDominoAiView.renderForAction(a, aiFindings.get(a.id))"));
assert.ok(app.includes('<details class="impactAgencyGroup"'));
assert.ok(app.includes("target.open=true"));
assert.ok(app.includes("기관별 변경 검토사항"));
assert.ok(app.includes("window.PolicyDominoAiView.statusLabel(e,DATA,AI_DATA)"));
assert.ok(app.includes('candidate?.schema==="policy-domino-llm-impact-v2"'));
assert.ok(!app.includes("candidate.source_generated_at===d.generated_at"));

/* Regression for a real-sized event: 31 verified tasks must be organized by
   existing status and institution navigation, NEVER as 31 separate AI cards. */
(async function testAgencyFirstFullDetail() {
  const model=require("../assets/impact-model.js");
  const event={
    event_id:"v4:thirty-one",title:"전문직공무원 정원 특례 · 관련 법령 동시 개정",
    revision:"타법개정",law_type:"동일 공포번호 법령 17건",
    amendment_reason:"전문직공무원 정원의 배정 및 운영 특례 관련 규정을 변경",
    presentation_source:"v4_official_source",promulgated_at:"2026-11-06",
    effective_date:"2026-11-06",impact_level:"high"
  };
  const agencyNames=["고용노동부","공정거래위원회","국가데이터처"];
  const actions=Array.from({length:31},(_,i)=>({
    ...official.actions[0],id:"review-"+i,event_id:event.event_id,
    agency:agencyNames[i%agencyNames.length],article:"제"+(i+1)+"조",
    status:"반영 확인 필요",work:"정원 관리",
    required_change:"기관별 정원 현행화 필요",target_location:"업무 운영 기준",
    changes:[{before:"기존 기준",after:"개정 기준"}]
  }));
  const findings=actions.map(a=>card(a.id,a.agency,a.article,a.law_title,a.evidence_fingerprint,a.basis));
  const data={schema:"policy-domino-next-v1",events:[event],actions,
              generated_at:"2026-11-10T07:00:00Z",health:{}};
  const aiData={schema:ai.SCHEMA,events:[{
    event_id:event.event_id,eligible_actions:31,analyzed_actions:31,
    status:"complete",findings
  }]};
  const nodes=new Map();
  function element(id) {
    if(!nodes.has(id))nodes.set(id,{
      innerHTML:"",textContent:"",value:"",hidden:false,dataset:{},
      classList:{add(){},remove(){},toggle(){}},
      querySelectorAll(){return []}
    });
    return nodes.get(id);
  }
  const document={
    body:{dataset:{policyDataUrl:"./data.json"}},
    getElementById:element,querySelectorAll(){return []}
  };
  const context={
    document,console,Date,Intl,URL,window:{
      PolicyDominoAiView:ai,PolicyDominoView:model,
      innerWidth:1200,addEventListener(){}
    },
    location:{hash:"",pathname:"/impact/",search:""},
    history:{replaceState(){}},
    fetch:async url=>({
      ok:true,
      json:async()=>String(url).includes("ai-impact")?aiData:data
    })
  };
  vm.runInNewContext(app,context,{filename:"classic.js"});
  await new Promise(resolve=>setImmediate(resolve));
  const html=element("detail").innerHTML;
  assert.match(html,/이번 변경에서 무엇을 확인했나/);
  assert.match(html,/전문직공무원 정원의 배정 및 운영 특례/);
  assert.match(html,/기관별 변경 검토사항/);
  assert.match(html,/전체 31건 · 조치 확인 0 · 미조치 확인 0/);
  assert.match(html,/반영 확인 필요 31/);
  assert.match(html,/AI 분석 31\/31/);
  assert.ok(!html.includes('class="aiAnalysis"'));
  assert.ok(!html.includes("AI 기관별 영향 분석"));
  assert.equal((html.match(/class="impactAgencyGroup"/g)||[]).length,3);
  assert.equal((html.match(/class="aiActionNote"/g)||[]).length,31);
  const groupIndex=html.indexOf('class="impactAgencyGroup"');
  const agencyTitleIndex=html.indexOf("기관별 변경 검토사항");
  assert.ok(groupIndex>agencyTitleIndex,"Agency sections follow the central change and review overview");
  assert.ok(html.includes('data-jump="고용노동부"'));
  assert.ok(html.includes('data-jump="공정거래위원회"'));
  assert.ok(html.includes('data-jump="국가데이터처"'));
  assert.ok(!html.includes('<article class="aiImpactCard"'));
  const firstGroup=html.slice(groupIndex,html.indexOf("</details>",groupIndex));
  assert.ok(firstGroup.includes("AI 업무 영향·추가 검토사항 보기"),
    "LLM details must be nested in a review task within the agency group");
  console.log("AGENCY_FIRST_DETAIL_PASS: one core summary, 31 tasks nested inside 3 collapsed agency groups, status filters retained");
})().catch(err=>{console.error(err);process.exitCode=1});

console.log("AI_CATALOG_VIEW_PASS: every event, partial results, unchanged cache reuse and source-level invalidation");
