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
for(const label of ["① 정책에서 실제 바뀐 내용","② 원문 변경에 따른 업무 검토 후보","③ 변경이 파급되는 관련 규정","공식 변경 목록 확인 · 본문 비교 대기"]){
 assert.ok(html.includes(label),"Missing policy-first change presentation: "+label);
}
// Functional regression: even a change with zero verified actions must retain
// navigable source-law agency chips. Never relabel such agencies as operators.
for(const label of ["data-doc-jump","data-doc-agency","data-evidence",
                    "공식 변경 직접 검토","집행기관 추가 조사",
                    "agencyNavigator(current,sourceGroups)"]){
 assert.ok(html.includes(label),"Missing agency controls: "+label);
}
const standalone=scripts[0][1].replace(/load\(\);\s*$/,"")+
 "\n;globalThis.__agencyHelpers={sourceAgencyGroups,agencyNavigator,officialSourceDocumentGroups};";
const sandbox={document:{
  getElementById(){return {};},
  querySelectorAll(){return [];}
},window:{addEventListener(){}},URL,Date,Intl};
vm.runInNewContext(standalone,sandbox);
const sourceEvent={official_change_documents:[
 {agency:"가상공사",agency_role:"직제 규정에 명시된 기관",
  law_title:"가상공사 직제",source_url:"https://www.law.go.kr/법령/a",
  verification:"verified_repeal_notice"},
 {agency:"가상위원회",agency_role:"공포·개정 소관기관 (집행기관 미확인)",
  law_title:"가상지원규칙",source_url:"https://www.law.go.kr/법령/b",
  verification:"verified_changed_clauses"}
]};
const grouped=sandbox.__agencyHelpers.sourceAgencyGroups(sourceEvent);
assert.equal(grouped.length,2);
const chips=sandbox.__agencyHelpers.agencyNavigator([],grouped);
assert.ok(chips.includes('data-doc-jump')&&chips.includes('가상공사'));
const body=sandbox.__agencyHelpers.officialSourceDocumentGroups(grouped);
assert.ok(body.includes('data-doc-agency')&&body.includes('가상위원회'));
assert.ok(!body.includes('조치 완료'));
const d=JSON.parse(fs.readFileSync("site/classic/data.json","utf8"));
assert.ok(html.includes('data-law="high-impact"'));
assert.ok(html.includes('>영향도 큼</button>'));
assert.ok(!html.includes('data-law="standards"'));
assert.ok(!html.includes('data-law="actionable"'));
assert.ok(html.includes('e.impact_level==="high"'));
assert.equal(d.schema,"policy-domino-next-v1");
assert.ok(d.events.length>0&&d.actions.length>0,"Must display actual sourced work");
const high=d.events.filter(e=>e.impact_level==="high");
for(const e of d.events){
  assert.ok(e.impact_scope && e.impact_scope.criteria);
  const agencies=new Set(d.actions.filter(a=>a.event_id===e.event_id).map(a=>a.agency));
  const links=e.downstream_changes?.filter(x=>x.status==="변경 조항 적용 관계 확인" &&
    x.title && x.article && x.evidence)||[];
  const distinctLinks=new Set(links.map(x=>JSON.stringify([x.title.trim(),x.article.trim()])));
  assert.equal(e.impact_level==="high",agencies.size>=2||distinctLinks.size>=2,
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
assert.ok(official.length>0,"Need grounded official direct changes");
const institutional=d.actions.filter(a=>a.evidence_scope==="official_institutional_program_dependency");
// Automatic discovery may correctly return no result when live sources cannot be verified.
assert.ok(institutional.every(a=>a.discovery_method==="live_public_search_and_page_validation"),
  "Published institutional cases must come from live discovery, not registered examples");
for(const action of institutional){
  assert.ok(action.agency_basis?.startsWith("https://"));
  assert.ok(action.institution_evidence?.excerpt);
  assert.equal(action.institutional_implementation_verified,false);
  assert.equal(action.is_direct_legal_amendment,false);
  assert.match(action.changes[0].meaning,/원천 정책/);
}
console.log("CLASSIC_PASS",{events:d.events.length,agencyTasks:d.actions.length,
  official:official.length,oldOfficialPendingReview:legacy.length,institutionalReview:institutional.length});
