"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const ai=require("../assets/ai-view.js");
const hash="a".repeat(64), changedHash="b".repeat(64);
const one={event_id:"v4:one"},two={event_id:"v4:two"},legacy={event_id:"legacy:one"};
const official={
  generated_at:"2026-11-10T01:00:00Z",
  events:[one,two,legacy],
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
  analyzed_at:"2026-11-10T07:21:39Z",
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
assert.equal(ai.latestAnalyzedAt(official,catalog),"2026-11-10T07:21:39Z");
assert.equal(ai.latestAnalyzedAt(official,null),null);
assert.equal(ai.latestAnalyzedAt(official,{...catalog,schema:"old-v1"}),null);
assert.match(ai.renderForAction(official.actions[0],c1),/AI 검토 의견/);
assert.ok(!ai.renderForAction(official.actions[0],c1).includes("Gemini 등 실제 분석 모델"));
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
assert.equal(ai.latestAnalyzedAt(updated,catalog),"2026-11-10T07:21:39Z");
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
assert.ok(app.includes("window.PolicyDominoAiView.renderForAction(a,aiFindings.get(a.id))"));
assert.ok(app.includes('data-agency-type='));
assert.ok(app.includes('data-agency-region='));
assert.ok(app.includes('data-agency-pick='));
assert.ok(!app.includes('class="statusFilters"'));
assert.ok(!app.includes('data-status='));
assert.ok(!app.includes('groupedActions('));
assert.ok(!app.includes('data-jump='));
assert.ok(app.includes("기관별 변경 검토사항"));
assert.ok(app.includes("window.PolicyDominoAiView.latestAnalyzedAt(DATA,AI_DATA)"));
assert.ok(app.includes('candidate?.schema==="policy-domino-llm-impact-v2"'));
assert.ok(!app.includes("candidate.source_generated_at===d.generated_at"));

/* Functional test: no status filter, and 684 real actions must stay hidden
 * until the user picks type → region → institution in the institution filter. */
(async function testInstitutionFilter(){
 const model=require("../assets/impact-model.js");
 const event={
   event_id:"v4:many",title:"전문직공무원 정원 특례 · 관련 법령 동시 개정",
   revision:"타법개정",law_type:"동일 공포번호 법령 17건",
   amendment_reason:"공식 정원 기준 개정",
   presentation_source:"v4_official_source",impact_level:"high",
   promulgated_at:"2026-11-06",effective_date:"2026-11-06"
 };
 const agencies=["고용노동부","공정거래위원회","국가데이터처",
   "서울특별시 강서구","서울특별시 양천구",
   "전북특별자치도 전주시","전남광주통합특별시 강진군",
   "서울특별시교육청","서울특별시 동부교육지원청",
   "전라남도교육청","세종특별자치시교육청",
   "서울특별시50플러스재단","재단법인신용보증재단",
   "시·군·구",
   ...Array.from({length:90},(_,i)=>"서울특별시 가상"+i+"구")];
 const actions=Array.from({length:684},(_,i)=>({
   ...official.actions[0],id:"review-"+i,event_id:event.event_id,
   agency:agencies[i%agencies.length],article:"제"+(i+1)+"조",
   status:i%2===0?"최신 근거 재확인 필요":"반영 확인 필요",
   work:"공식 기준 검토",required_change:"기관 기준 점검",
   changes:[{before:"종전",after:"변경"}]
 }));
 const data={schema:"policy-domino-next-v1",events:[event],actions,
   generated_at:"2026-11-10T07:00:00Z",health:{}};
 const aiData={schema:ai.SCHEMA,events:[]};
 const nodes=new Map();
 function element(id){
   if(!nodes.has(id)){
     let html="", cached=new Map();
     const item={textContent:"",value:"",hidden:false,dataset:{},oninput:null,
       classList:{add(){},remove(){},toggle(){}},
       set innerHTML(v){html=String(v);cached=new Map()},
       get innerHTML(){return html},
       querySelectorAll(selector){
         if(cached.has(selector))return cached.get(selector);
         const parsed=/^\[data-([a-z-]+)\]$/.exec(selector);
         if(!parsed)return [];
         const attr=parsed[1];
         const key=attr.replace(/-([a-z])/g,(_,letter)=>letter.toUpperCase());
         const re=new RegExp('<button\\b[^>]*data-'+attr+'="([^"]*)"[^>]*>','g');
         const buttons=[...html.matchAll(re)].map(hit=>({
           dataset:{[key]:hit[1]},onclick:null
         }));
         cached.set(selector,buttons);
         return buttons;
       }
     };
     nodes.set(id,item);
   }
   return nodes.get(id);
 }
 const document={body:{dataset:{policyDataUrl:"./data.json"}},
   getElementById:element,querySelectorAll(){return []}};
 const context={document,console,Date,Intl,URL,
   window:{PolicyDominoAiView:ai,PolicyDominoView:model,
     innerWidth:1200,addEventListener(){}},
   location:{hash:"",pathname:"/impact/",search:""},
   history:{replaceState(){}},
   fetch:async url=>({ok:true,json:async()=>String(url).includes("ai-impact")?aiData:data})};
 vm.runInNewContext(app,context,{filename:"classic.js"});
 await new Promise(resolve=>setImmediate(resolve));
 function click(selector,value){
   const prop=selector.slice(6,-1).replace(/-([a-z])/g,(_,letter)=>letter.toUpperCase());
   const btn=element("detail").querySelectorAll(selector)
     .find(item=>item.dataset[prop]===value);
   assert.ok(btn,"Filter choice missing: "+selector+" "+value);
   assert.equal(typeof btn.onclick,"function","Filter choice must be clickable");
   btn.onclick();
 }
 let html=element("detail").innerHTML;
 assert.match(html,/기관별 변경 검토사항/);
 assert.ok(html.includes("관련 기관 104곳"));
 assert.ok(!html.includes("data-status="));
 assert.ok(!html.includes("조치 확인 0"));
 assert.equal((html.match(/class="action"/g)||[]).length,0);
 assert.equal((html.match(/class="agencyTypeChoice(?: active)?"/g)||[]).length,4);
 assert.equal((html.match(/class="agencyPick/g)||[]).length,0);
 click("[data-agency-type]","지방자치단체");
 html=element("detail").innerHTML;
 assert.ok(html.includes('data-agency-region="서울특별시"'));
 assert.ok(html.includes('data-agency-region="전북특별자치도"'));
 assert.ok(html.includes('data-agency-region="전남광주통합특별시"'));
 assert.equal((html.match(/class="action"/g)||[]).length,0);
 click("[data-agency-region]","서울특별시");
 html=element("detail").innerHTML;
 assert.ok(html.includes('data-agency-pick="서울특별시 강서구"'));
 assert.ok(html.includes('id="agencySearch"'));
 assert.equal((html.match(/class="action"/g)||[]).length,0);
 const search=element("agencySearch");
 search.value="강서구";
 assert.equal(typeof search.oninput,"function");
 search.oninput();
 assert.match(element("agencyChoiceList").innerHTML,/서울특별시 강서구/);
 assert.ok(!element("agencyChoiceList").innerHTML.includes("서울특별시 양천구"));
 click("[data-agency-pick]","서울특별시 강서구");
 html=element("detail").innerHTML;
 const n=actions.filter(x=>x.agency==="서울특별시 강서구").length;
 assert.equal((html.match(/class="action"/g)||[]).length,n);
 assert.match(html,new RegExp("검토사항 "+n+"건"));
 assert.ok(!html.includes('data-status='));
 click("[data-agency-type]","교육청");
 html=element("detail").innerHTML;
 assert.ok(html.includes('data-agency-region="전라남도"'));
 assert.ok(html.includes('data-agency-region="세종특별자치시"'));
 assert.equal((html.match(/class="action"/g)||[]).length,0);
 click("[data-agency-region]","서울특별시");
 html=element("detail").innerHTML;
 assert.ok(html.includes('data-agency-pick="서울특별시교육청"'));
 assert.ok(html.includes('data-agency-pick="서울특별시 동부교육지원청"'));
 click("[data-agency-pick]","서울특별시교육청");
 html=element("detail").innerHTML;
 assert.equal((html.match(/class="action"/g)||[]).length,
   actions.filter(x=>x.agency==="서울특별시교육청").length);
 click("[data-agency-type]","공공기관·기타");
 html=element("detail").innerHTML;
 assert.ok(html.includes('data-agency-pick="서울특별시50플러스재단"'));
 assert.ok(!html.includes('data-agency-region="서울특별시"'));
 console.log("INSTITUTION_FILTER_PASS: 684 reviews, 104 source agencies, type/region/agency clicks, no status buttons");
})().catch(err=>{console.error(err);process.exitCode=1});

console.log("AI_CATALOG_VIEW_PASS: every event, partial results, unchanged cache reuse and source-level invalidation");
