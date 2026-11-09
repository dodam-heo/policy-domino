const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {normalizePolicyData}=require('./impact_adapter.js');

const policy={
  id:'policy-1',source:'admrul',stable_id:'s1',title:'가상 산업지원 운영규정',
  ministry:'가상 부처',kind:'고시',revision:'일부개정',
  promulgated_at:'2026-11-08',effective_date:'2027-01-01',url:'https://www.law.go.kr/가상',
  comparison_status:'신구 본문 비교 완료',impact_category:'제도·업무 변경',
  changes:[{article:'제5조',type:'개정',before:'기준액 100만원',after:'기준액 200만원'}],
  effects:[{article:'제5조',old:'100만원',new:'200만원',context:'지원 기준액 200만원',
            operations:['금액·산식 적용']}],
  institution_actions:[{agency:'가상공단',work:'금액·산식 적용',article:'제5조',
    target_location:'산정·지급 기준표',what_to_change:'100만원 → 200만원',
    evidence_type:'변경된 동일 조문 내 업무주체·의무문 확인',
    required_change:'대상 금액 기준표 검토',status:'집행기관 업무 영향 검토 필요'}],
  dependency_actions:[{agency:'가상시청',work:'관련 규정에 따른 기준 적용',
    target_location:'가상시 시행조례',basis:'https://www.law.go.kr/조례',
    required_change:'인용되는 지급기준 검토'}],
  agency_candidates:[{agency:'가상부처',work:'금액·산식 적용',
    target_location:'산정 기준',what_to_change:'100만원 → 200만원'}]
};
const raw={schema:'policy-domino-impact-v3',generated_at:'2026-11-08T07:00:00Z',
  source_health:{status:'정상'},impact_health:{verified_documents:9},
  events:[policy]};
const data=normalizePolicyData(raw);
assert.equal(data.schema,'policy-domino-next-v1');
assert.equal(data.events.length,1);
assert.equal(data.events[0].event_id,'policy-1');
assert.equal(data.events[0].policy_profile,true);
assert.equal(data.actions.length,1,'only evidenced statutory duty enters agency action cards');
const first=data.actions.find(a=>a.agency==='가상공단');
assert.equal(first.target_location,'산정·지급 기준표');
assert.deepEqual(first.changes[0],{before:'100만원',after:'200만원',article:'제5조'});
assert.equal(first.status,'업무 반영 검토 필요');
const candidate=data.actions.find(a=>a.agency==='가상부처');
assert.equal(candidate,undefined,'issuer-only candidate must not be displayed as a required action');
assert.equal(data.actions.find(a=>a.agency==='가상시청'),undefined,
  'Official reference alone must not cause an agency compliance card');

// Regression from a real 2026 staffing-table update: lexical references to
// privacy protection do not make every ministry update the same headcount.
const org = {
  ...policy,id:'org1',title:'개인정보 보호위원회 직제',source:'law',
  impact_category:'조직개편·업무이관',ministry:'개인정보보호위원회,행정안전부',
  changes:[{article:'별표 0001',before:'정원표 총계 192',after:'정원표 총계 197'}],
  effects:[{article:'별표 0001',old:'192',new:'197',
    operations:['조직·인력'],context:'정원표 총계 197'}],
  institution_actions:[{
    agency:'개인정보 보호위원회',work:'조직·정원 관리',
    evidence_type:'개정된 공무원 정원표의 명시된 기관·항목',
    article:'별표 0001',verified_location:true,
    target_location:'별표 0001 · 공무원 정원 총계',
    what_to_change:'공무원 정원 총계 192명 → 197명 (+5명)',
    required_change:'개인정보 보호위원회 정원표 갱신 여부 검토'
  },{
    agency:'사무처장',work:'조직·인력',article:'별표 0001',
    evidence_type:'공식 규정의 집행주체·업무조항 확인',
    what_to_change:'192 → 197'
  }],
  dependency_actions:[{agency:'구청장',work:'조직·인력',
    target_location:'다른 법령',what_to_change:'192 → 197'}],
  agency_candidates:[{agency:'고용노동부장관',work:'조직·인력',article:'별표 0001'}]
};
const normalizedOrg=normalizePolicyData({schema:'policy-domino-impact-v3',
  events:[org],source_health:{},impact_health:{}});
assert.equal(normalizedOrg.actions.length,1,
  'One staffing change must not create cards for unrelated authorities');
assert.equal(normalizedOrg.actions[0].agency,'개인정보 보호위원회');
assert.equal(normalizedOrg.actions[0].change_units,'명');
assert.match(normalizedOrg.actions[0].change_label,/공무원 정원 총계/);
assert.equal(normalizedOrg.actions[0].changes[0].after,'197');
assert.match(normalizedOrg.events[0].change_summary,/192명 → 197명/);
assert.equal(data.actions.filter(a=>a.evidence_type==='downstream').length,0,
  'Referenced agencies must not inherit numerical or procedural change instructions');

const stale={...org,institution_actions:[org.institution_actions[1]]};
assert.equal(normalizePolicyData({schema:'policy-domino-impact-v3',
  events:[stale]}).actions.length,0,'Stale cached false actor cards must be suppressed');

const repealed={
 ...policy,id:'defunct-rule',title:'지역기관 정보관리 위기대응 규정',
 revision:'폐지',impact_category:'폐지·효력종료',
 impact_summary:'기존 규정 폐지 사실 확인. 대체 운영규정 확인 필요.',
 institution_actions:Array.from({length:35},(_,i)=>({
   agency:'가상위원회'+i,work:'조직·인력',
   evidence_type:'공식 규정의 집행주체·업무조항 확인',
   article:'제5조',what_to_change:'31 → 32'
 })),
 dependency_actions:[{agency:'가상부처',what_to_change:'31 → 32'}],
 agency_candidates:[{agency:'가상위원회',what_to_change:'31 → 32'}]
};
const repealData=normalizePolicyData({schema:'policy-domino-impact-v3',events:[repealed]});
assert.equal(repealData.actions.length,0);
assert.equal(repealData.events[0].policy_profile,true,
 'A repeal is a policy lifecycle event, not an operational mandate');
assert.match(repealData.events[0].change_summary,/폐지/);

// A real legal sentence must never be broken into unrelated before/after words.
const grounded={...policy,id:'sourced-changes',
  changes:[{article:'제35조',before:'제35조(검사) 해양시험청장은 검사업무를 수행한다.',
    after:'제35조(검사) 해양시험청장은 검사업무(정밀안전진단을 포함한다)를 수행한다.'}],
  effects:[{article:'제35조',old:'검사업무를',new:'검사업무(정밀안전진단을 포함한다)를',
            operations:['심사·인허가']},
           {article:'제35조',old:'제5조에',new:'운송사업자에게',
            operations:['심사·인허가']}],
  institution_actions:[{
    agency:'해양시험청장',article:'제35조',work:'심사·인허가',
    evidence_type:'변경된 동일 조문 내 업무주체·의무문 확인',
    change_pairs:[{
      before:'제35조(검사) 해양시험청장은 검사업무를 수행한다.',
      after:'제35조(검사) 해양시험청장은 검사업무(정밀안전진단을 포함한다)를 수행한다.',
      article:'제35조'
    }],
    what_to_change:'제35조의 심사·인허가 관련 문장이 변경됨'
  }]
};
const groundedUI=normalizePolicyData({
  schema:'policy-domino-impact-v3',events:[grounded]});
assert.equal(groundedUI.actions.length,1,'One source duty = one agency card');
assert.equal(groundedUI.actions[0].changes.length,1,
  'Only matched whole sentences, not all broken effects in an article');
assert.match(groundedUI.actions[0].changes[0].after,/수행한다\.$/);
assert.doesNotMatch(groundedUI.actions[0].changes[0].before,/^검사업무를$/);

const mixed={schema:'policy-domino-impact-v3',events:[policy,{
  ...policy,id:'policy-2',title:'가상 행정조직 직제',
  impact_category:'조직·내부운영',effects:[],
  institution_actions:[],dependency_actions:[],agency_candidates:[]
}]};
assert.equal(normalizePolicyData(mixed).events[1].policy_profile,false);

const old=normalizePolicyData({schema:'policy-domino-v2',events:[{
  id:'x',title:'가상 정책',source:'law',changes:[{
    article:'제2조',before:'일주일',after:'10일'
  }]
}],actions:[{event_id:'x',agency:'가상청',before:'일주일',after:'10일',
  required_change:'기한 검토'}]});
assert.equal(old.actions[0].changes[0].after,'10일');
assert.equal(old.events[0].event_id,'x');
assert.throws(()=>normalizePolicyData({schema:'unknown'}),/지원되지 않는/);

// The public landing page redirects to the maintained evidence-led dashboard.
// Compatibility tests must follow the actual route, not assert a retired
// inline UI or a category filter that was intentionally removed.
const landing=fs.readFileSync('site/index.html','utf8');
assert.match(landing,/\.\/impact\//);
const html=fs.readFileSync('site/impact/index.html','utf8');
const inline=html.match(/<script>\s*([\s\S]*?)<\/script>/);
assert.ok(inline,'maintained agency-impact screen must have its renderer');
new vm.Script(inline[1],{filename:'site/impact/index.html'});
for(const section of ['agencyNavigator','groupedActions','기관별 변경 검토사항',
                      'data-jump','data-doc-jump','data-law="all"']){
  assert.ok(html.includes(section),'Missing maintained agency UI: '+section);
}
for(const removed of ['data-law="lifecycle"','data-law="organization"',
                      'data-law="verified"']){
  assert.ok(!html.includes(removed),'Retired filter returned: '+removed);
}
console.log('PASS: V2/V3 adapter evidence gates and maintained /impact/ UI route');
