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
assert.ok(app.includes('class="agencyWorkbench"'));
assert.ok(app.includes('data-side-type='));
assert.ok(app.includes('data-side-region='));
assert.ok(app.includes('data-agency-pick='));
assert.ok(app.includes('data-agency-more'));
assert.ok(app.includes("동시 개정된 법령"));
assert.ok(app.includes("변경 조문을 인용하는 관련 규정"));
assert.ok(!app.includes('class="statusFilters"'));
assert.ok(!app.includes('data-status='));
assert.ok(!app.includes('data-jump='));
assert.ok(app.includes("기관별 변경 검토사항"));
assert.ok(app.includes("실제 변경사항 · 신구 비교"));
assert.ok(app.includes("발령기관 확인 중"));
assert.ok(app.includes("source_policy_only"));
assert.ok(app.includes("window.PolicyDominoAiView.latestAnalyzedAt(DATA,AI_DATA)"));
assert.ok(app.includes('candidate?.schema==="policy-domino-llm-impact-v2"'));
assert.ok(!app.includes("candidate.source_generated_at===d.generated_at"));

/* Real interaction regression: 684 reviews should be navigable through
   a sidebar; source-backed legal links must be counted independently. */
(async function testAgencySidebarAndLegalConnections() {
 const model=require("../assets/impact-model.js");
 const event={
   event_id:"v4:large",title:"전문직공무원 정원 특례 · 관련 법령 3건 동시 개정",
   impact_level:"high",revision:"타법개정",law_type:"동일 공포번호 법령 3건",
   amendment_reason:"전문직공무원 정원의 배정 및 운영에 관한 규정 개정",
   promulgated_at:"2026-11-06",effective_date:"2026-11-06",
   presentation_source:"v4_official_source",
   simultaneous_laws:[
     {title:"가상청 직제",kind:"대통령령",url:"https://www.law.go.kr/법령/가상청직제",
      changed_articles:["제7조","제8조"]},
     {title:"가상위원회 직제",kind:"대통령령",url:"https://www.law.go.kr/법령/가상위원회직제",
      changed_articles:["제9조"]},
     {title:"가상연구청 직제",kind:"대통령령",url:"https://www.law.go.kr/법령/가상연구청직제",
      changed_articles:["제10조"]}
   ],
   citing_regulations:[
     {title:"가상청 직제 시행규칙",source_title:"가상청 직제",
      source_article:"제7조",target_article:"제12조",
      proof:"변경 조항 직접 인용",
      url:"https://www.law.go.kr/법령/가상청직제시행규칙"},
     {title:"가상청 직제 시행규칙",source_title:"가상청 직제",
      source_article:"제8조",target_article:"제13조",
      proof:"변경 조항 직접 인용",
      url:"https://www.law.go.kr/법령/가상청직제시행규칙"},
     {title:"가상연구청 직제 시행규칙",source_title:"가상연구청 직제",
      source_article:"제10조",target_article:"제3조",
      proof:"변경 조항 직접 인용",
      url:"https://www.law.go.kr/법령/가상연구청직제시행규칙"}
   ]
 };
 const agencies=[
   "고용노동부","공정거래위원회","국가데이터처",
   "서울특별시 강서구","서울특별시 양천구",
   "전북특별자치도 전주시","전남광주통합특별시 강진군",
   "서울특별시교육청","서울특별시 동부교육지원청",
   "전라남도교육청","세종특별자치시교육청",
   "서울특별시50플러스재단","재단법인신용보증재단",
   "시·군·구",
   ...Array.from({length:90},(_,i)=>"서울특별시 가상"+i+"구")
 ];
 const actions=Array.from({length:684},(_,i)=>({
   ...official.actions[0],id:"check-"+i,event_id:event.event_id,
   agency:agencies[i%agencies.length],article:"제"+(i+1)+"조",
   work:"운영 기준",
   required_change:"변경된 운영 기준을 확인",
   changes:[{before:"종전",after:"개정"}]
 }));
 const source={schema:"policy-domino-next-v1",events:[event],actions,
   generated_at:"2026-11-10T09:00:00Z",health:{}};
 const aiData={schema:ai.SCHEMA,events:[]};
 const nodes=new Map();
 function element(id){
   if(!nodes.has(id)){
     let html="",stored=new Map();
     const node={
       textContent:"",value:"",hidden:false,dataset:{},oninput:null,
       classList:{add(){},remove(){},toggle(){}},
       set innerHTML(value){html=String(value);stored=new Map()},
       get innerHTML(){return html},
       querySelectorAll(selector){
         if(stored.has(selector))return stored.get(selector);
         const parsed=/^\[data-([a-z-]+)\]$/.exec(selector);
         if(!parsed)return [];
         const attr=parsed[1],key=attr.replace(/-([a-z])/g,
           (_,letter)=>letter.toUpperCase());
         const exp=new RegExp('<(?:button|details)\\b[^>]*data-'+attr+
           '(?:="([^"]*)")?[^>]*>','g');
         const items=[...html.matchAll(exp)].map(hit=>({
           dataset:{[key]:hit[1]||""},onclick:null,ontoggle:null,
           open:hit[0].includes(" open")
         }));
         stored.set(selector,items);
         return items;
       },
       querySelector(selector){return this.querySelectorAll(selector)[0]||null}
     };
     nodes.set(id,node);
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
   fetch:async url=>({ok:true,json:async()=>String(url).includes("ai-impact")?
      aiData:source})};
 vm.runInNewContext(app,context,{filename:"classic.js"});
 await new Promise(resolve=>setImmediate(resolve));
 function click(selector,value){
   const parsed=/^\[data-([a-z-]+)\]$/.exec(selector);
   const prop=parsed[1].replace(/-([a-z])/g,(_,l)=>l.toUpperCase());
   const item=element("detail").querySelectorAll(selector)
     .find(x=>value===undefined || x.dataset[prop]===value);
   assert.ok(item,"Missing click target "+selector+" "+value);
   assert.equal(typeof item.onclick,"function","Not wired: "+selector);
   item.onclick();
 }
 let html=element("detail").innerHTML;
 assert.match(html,/동시 개정된 법령 3건 확인/);
 assert.match(html,/변경 조문을 인용하는 관련 규정 2건 확인/);
 assert.equal((html.match(/법령 원문 ↗/g)||[]).length,3);
 assert.equal((html.match(/관련 규정 ↗/g)||[]).length,2);
 assert.ok(html.indexOf("동시 개정된 법령")<
           html.indexOf("기관별 변경 검토사항"),
           "Legal relations must precede the institution workbench");
 assert.match(html,/104개 기관 · 684건/);
 assert.match(html,/class="agencyWorkbench"/);
 assert.match(html,/class="agencySidebar"/);
 assert.match(html,/class="agencyResults"/);
 assert.ok(html.includes("data-agency-all"));
 assert.ok(!html.includes("data-status="));
 assert.equal((html.match(/class="agencyResultGroup"/g)||[]).length,20);
 assert.ok(html.includes("data-agency-more"));
 assert.match(html,/data-side-type="지방자치단체"/);
 assert.match(html,/data-side-region="지방자치단체\|서울특별시"/);
 assert.match(html,/data-side-type="교육청"/);
 assert.match(html,/data-side-region="교육청\|서울특별시"/);
 assert.ok(html.includes('data-agency-pick="서울특별시 강서구"'));
 click("[data-agency-pick]","서울특별시 강서구");
 html=element("detail").innerHTML;
 const n=actions.filter(x=>x.agency==="서울특별시 강서구").length;
 assert.match(html,/검토사항 /);
 assert.equal((html.match(/class="action"/g)||[]).length,n);
 assert.ok(!html.includes("data-agency-more"));
 assert.match(html,/동시 개정된 법령 3건 확인/);
 click("[data-agency-all]");
 html=element("detail").innerHTML;
 assert.equal((html.match(/class="agencyResultGroup"/g)||[]).length,20);
 click("[data-agency-more]");
 html=element("detail").innerHTML;
 assert.equal((html.match(/class="agencyResultGroup"/g)||[]).length,40);
 const search=element("agencySearch");
 search.value="강서구";
 assert.equal(typeof search.oninput,"function");
 search.oninput();
 const nav=element("agencySidebarGroups").innerHTML;
 assert.match(nav,/서울특별시 강서구/);
 assert.ok(!nav.includes('data-agency-pick="서울특별시 양천구"'));
 assert.match(nav,/data-side-type="지방자치단체" open/);
 assert.match(nav,/data-side-region="지방자치단체\|서울특별시" open/);
 console.log("AGENCY_LEGAL_WORKBENCH_PASS: official 3 co-amendments, 2 citation documents, 684 reviews in paged sidebar/agency cards");
})().catch(err=>{console.error(err);process.exitCode=1});

console.log("AI_CATALOG_VIEW_PASS: every event, partial results, unchanged cache reuse and source-level invalidation");
