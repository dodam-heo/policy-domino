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
assert.equal(data.actions.length,3,'verified and candidate agency cards must appear');
const first=data.actions.find(a=>a.agency==='가상공단');
assert.equal(first.target_location,'산정·지급 기준표');
assert.deepEqual(first.changes[0],{before:'100만원',after:'200만원',article:'제5조'});
assert.equal(first.status,'업무 반영 검토 필요');
const candidate=data.actions.find(a=>a.agency==='가상부처');
assert.equal(candidate.status,'집행기관 추가 조사');
assert.match(candidate.agency_role,/실제 집행기관 추가 조사/);
assert.equal(data.actions.find(a=>a.agency==='가상시청').evidence_type,'downstream');

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

const html=fs.readFileSync('site/index.html','utf8');
assert.match(html,/impact_adapter\.js/);
const inline=html.match(/<script>\s*([\s\S]*?)<\/script>/);
assert.ok(inline,'main agency-first script must be present');
new vm.Script(inline[1],{filename:'site/index.html'});
for(const section of ['agencyNavigator','groupedActions','어디를 바꾸나?','무엇이 달라지나?',
  '필요한 조치','data-law="standards"','normalizePolicyData(d)','<details class="legalDetails"']){
  assert.ok(html.includes(section),'Missing important original feature: '+section);
}
console.log('PASS: original agency-first controls, v2/v3 data models, before/after, verified/candidate agencies');
