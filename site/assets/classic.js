"use strict";
(function(){
const $=id=>document.getElementById(id);
const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function validUrl(raw){try{const u=new URL(raw);return ["https:","http:"].includes(u.protocol)?esc(u.href):"#"}catch(e){return "#"}}
function fmtDate(s){if(!s)return "미확인";if(/^\d{4}-\d{2}-\d{2}$/.test(s))return s.replaceAll("-",". ");let d=new Date(s);return Number.isNaN(d.getTime())?esc(s):new Intl.DateTimeFormat("ko-KR",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"}).format(d)}
const {typeOf,sorted,filterEvents:filterPolicyEvents,resolveSelection,DEFAULT_FILTER}=window.PolicyDominoView;
function typeLabel(e){let k=typeOf(e);return k==="new"?"신규":k==="abolished"?"폐지":"개정"}
function typeClass(e){return typeOf(e)==="new"?"add":typeOf(e)==="abolished"?"remove":""}
function matchingActions(event){return (DATA.actions||[]).filter(a=>a.event_id===event.event_id)}
let DATA={events:[],actions:[],health:{}},AI_DATA=null,selectedId=null,filter=DEFAULT_FILTER,actionFilter="all";
function filteredEvents(){return filterPolicyEvents(DATA.events,filter,$("q").value)}
function getEvent(){return (DATA.events||[]).find(e=>e.event_id===selectedId)||null}
function showEmpty(title,body){return '<div class="empty"><svg width="35" height="35" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M3 4h18v16H3z"/><path d="M7 8h10M7 12h10M7 16h6"/></svg><b>'+esc(title)+'</b><p style="margin-top:8px">'+esc(body)+'</p></div>'}
function eventRow(e){
const num=matchingActions(e).length,hasDiff=e.article_differences?.length||0,chosen=selectedId===e.event_id,aiProgress=window.PolicyDominoAiView.statusLabel(e,DATA,AI_DATA);
return '<button type="button" class="lawItem'+(chosen?' active':'')+'" data-event="'+esc(e.event_id)+'" aria-selected="'+chosen+'"><div class="lawTop"><span class="lawType '+typeClass(e)+'">'+typeLabel(e)+'</span><span class="lawDate">공포·확정 '+fmtDate(e.promulgated_at||e.change_date)+'</span></div><div class="lawName">'+esc(e.title||"이름 미확인")+'</div><div class="lawMeta">'+esc(e.ministry||"소관기관 미확인")+' · '+esc(e.law_type||"정책·법령")+'</div><div class="lawFoot">'+(e.impact_level==="high"?'<span class="mini" title="'+esc(e.impact_reason||"")+'">영향도 큼'+(e.impact_scope?.provisional?' · 재검증 대기':'')+'</span>':'')+'<span class="mini">'+(e.presentation_source==="v4_official_source"?"공식 신구 본문":"이전 V2 근거 · 재검증 대기")+'</span>'+(num?'<span class="mini">기관별 검토 '+num+'건</span>':'<span class="mini">기관별 영향 분석 대기</span>')+(aiProgress?'<span class="mini">'+esc(aiProgress)+'</span>':'')+'<span>'+(hasDiff?'변경 조문 '+hasDiff+'개 · ':'')+'기관별 변경 보기 ›</span></div></button>'
}
function displayList(){
$("impactFilterHint").hidden=filter!=="high-impact";
const events=filteredEvents();
$("listCount").textContent=(DATA.events||[]).length+"개 공식 변경 사건 중 "+events.length+"개 표시";
$("lawList").innerHTML=events.length?events.map(eventRow).join(""):showEmpty(DATA.health?.source_status==="수집 실패"?"공식 변경내역을 가져오지 못했습니다.":"표시할 확정 변경내역이 없습니다.",DATA.health?.source_status==="수집 실패"?"원천 연결 상태를 확인해 주세요. 변경이 없다는 뜻은 아닙니다.":"검색 조건을 변경하거나 공식 수집 상태를 확인하세요.");
$("lawList").querySelectorAll("[data-event]").forEach(b=>b.onclick=()=>choose(b.dataset.event));
}
function badgeStatus(s){let cls=s==="조치 확인"?"done":s==="미조치 확인"?"pending":s==="시행 예정"?"upcoming":"";return '<span class="status '+cls+'">'+esc(s||"반영 확인 필요")+'</span>'}
function agencyNavigator(items){
 const counts=new Map();
 for(const item of items){const name=item.agency||"기관 확인 필요";counts.set(name,(counts.get(name)||0)+1)}
 if(!counts.size)return "";
 return '<nav class="agencyNav" aria-label="기관별 바로가기">'+[...counts].sort((a,b)=>a[0].localeCompare(b[0],"ko")).map(([name,n])=>'<button class="agencyJump" type="button" data-jump="'+esc(name)+'">'+esc(name)+' · '+n+'</button>').join("")+'</nav>';
}
function overviewText(e,all){
 const reason=String(e.amendment_reason||"").replace(/\s+/g," ").trim();
 if(reason)return reason.slice(0,165)+(reason.length>165?"…":"");
 const example=all.map(a=>a.source_change||a.what_to_change).find(Boolean);
 return example?String(example).slice(0,165):"공식 변경의 상세 내용은 확인 중입니다. 근거가 없는 내용을 생성하지 않습니다.";
}
function groupedActions(items){
if(!items.length)return "";
const ordered=items.slice().sort((a,b)=>(a.agency||"").localeCompare(b.agency||"","ko")||(a.work||"").localeCompare(b.work||"","ko")||(a.article||"").localeCompare(b.article||"","ko"));
const byAgency=new Map();
for(const item of ordered){let agency=item.agency||"기관 확인 필요";if(!byAgency.has(agency))byAgency.set(agency,[]);byAgency.get(agency).push(item)}
return [...byAgency].map(([agency,list])=>'<section class="impactAgencyGroup" data-agency="'+esc(agency)+'"><div class="groupHeading"><strong>'+esc(agency)+'</strong><span>변경 대상 '+list.length+'건</span></div>'+list.map(actionCard).join("")+'</section>').join("");
}
function actionCard(a){
const changes=(a.changes||[]);
const comparison=changes.length?'<div class="valueRows">'+changes.map(p=>'<div class="valueRow"><div class="oldValue"><small>기존</small>'+esc(p.before||"미확인")+'</div><div class="valueArrow">→</div><div class="newValue"><small>변경</small>'+esc(p.after||"미확인")+'</div></div>').join('')+'</div>':'<div class="actionSummaryText">'+esc(a.what_to_change||a.source_change||"공식 개정문에서 변경된 항목")+'</div>';
const added=(a.new_items||[]).length?'<p class="taskDesc"><b>새로 추가할 항목:</b> '+esc(a.new_items.slice(0,6).join(" · "))+'</p>':'';
const sourceTag=a.evidence_scope==="v4_verified_source"?"공식 신구 조문 확인":a.evidence_scope==="legacy_official_directive_awaiting_recheck"?"이전 V2 개정 지시문 · 최신 재검증 대기":"근거 재확인 중";
const name=esc(a.agency||"적용 기관 미확인");
const task=esc(a.target_location||a.service||"구체적인 업무·서비스 위치 확인 필요");
const func=esc(a.work||a.category||"업무 조치");
return '<article class="action"><div class="actionTop"><div><div class="agency">'+name+'</div><div class="role">'+esc(a.agency_role||"이 변경을 적용하는 기관")+'</div></div>'+badgeStatus(a.status)+'</div>'+
'<div class="locationTitle" style="color:#377387">검증 상태 · '+esc(sourceTag)+'</div><div class="locationTitle">어떤 업무를 검토하나?</div><div class="locationBox">'+func+' <span style="color:#90a7b6">›</span> '+task+'</div>'+
'<div class="locationTitle">공식 변경 전후 내용</div>'+comparison+added+
'<div class="instruction"><b>검토할 조치</b>'+esc(a.required_change||"실제 업무에 반영해야 할 변경사항 확인 필요")+'</div>'+
'<details class="evidenceDrawer"><summary>적용일 · 개정 근거 · 검증 정보 보기</summary>'+
'<div class="evidence"><b>해당 기관의 개정 근거:</b> '+esc(a.law_title||"")+' · '+esc(a.article||"")+
'<br><b>적용 시점:</b> '+esc(a.effective_date||"시행일 추가 확인")+
'<br><b>도미노 연결:</b> '+esc(a.impact_link_basis||"직접 변경")+
' · <a target="_blank" rel="noopener" href="'+validUrl(a.basis)+'">공식 개정문 보기 ↗</a>'+
'<br><b>조치 확인:</b> '+esc(a.status_evidence||"공개 근거 미확인 · 완료/미조치 확정 불가")+'</div>'+
'<p class="verification">'+esc(a.verification_note||a.note||"구체적인 업무시스템·서비스 명칭과 실제 적용 상태는 별도 확인 필요")+'</p></details></article>';
}
function differences(e){
const ds=e.article_differences||[];
if(!ds.length)return '<p class="smallNote">공식 공포 정보는 확인됐지만 종전·변경 조문의 실제 비교가 아직 완료되지 않았습니다. 변경 전후 내용을 추측해 채우지 않습니다.</p>';
return ds.map(d=>'<div class="change"><div class="changeHead"><span>'+esc(d.article||"변경 조문")+' '+esc(d.title||"")+'</span><span>'+esc(d.type||"변경")+'</span></div><div class="changePair"><div class="changeCol before"><small>종전 내용</small><p>'+esc(d.before||(d.type==="신설"?"신설 이전 규정 없음":"종전 조문 전문 별도 대조 필요"))+'</p></div><div class="changeCol after"><small>'+(d.directive?"공식 개정 지시문":"변경 후 조문")+'</small><p>'+esc(d.directive||d.after||"변경 내용 확인 필요")+'</p></div></div></div>').join("")
}
function detailHTML(e){
 const all=matchingActions(e),current=all.filter(a=>actionFilter==="all"||a.status===actionFilter);
 const countDone=all.filter(a=>a.status==="조치 확인").length;
 const countNot=all.filter(a=>a.status==="미조치 확인").length;
 const institutions=new Set(all.map(a=>a.agency).filter(Boolean)).size;
 const dependent=(e.downstream_changes||[]).length;
 const impactSummary=e.impact_level==="high"?'<div class="smallNote" style="margin:8px 0">영향 범위: '+esc(e.impact_reason||"")+' · '+esc(e.impact_scope?.note||"")+'</div>':'';
 const provenance=e.presentation_source==="v4_official_source"?"현재 공식 신구 본문 검증":"이전 V2 공식 개정 지시문 · 최신 재검증 대기";
 const header='<div class="detailHeader"><button type="button" class="back" id="back">← 신규·개정 목록으로</button><div class="detailKicker">'+typeLabel(e)+' · '+esc(e.law_type||"법령·제도")+'</div><h2 class="detailTitle">'+esc(e.title||"변경 사건")+'</h2><div class="detailMeta"><span>'+esc(provenance)+'</span><span class="separator">·</span><span>'+esc(e.ministry||"소관기관 확인 필요")+'</span><span class="separator">·</span><span>공포·확정 '+fmtDate(e.promulgated_at||e.change_date)+'</span></div></div>';
 const overview='<section class="changeOverview"><div class="overviewLabel">이번 변경에서 무엇을 확인했나</div><div class="overviewText">'+esc(overviewText(e,all))+'</div><div class="overviewFoot"><span>검토 대상 기관 '+institutions+'곳</span><span>근거 있는 검토 항목 '+all.length+'건</span>'+(dependent?'<span>연결된 하위규정 '+dependent+'건</span>':'')+'</div></section>';
 const facts='<div class="dateGroup"><div class="fact"><small>시행일</small><strong>'+fmtDate(e.effective_date)+'</strong></div><div class="fact"><small>제·개정 구분</small><strong>'+esc(e.revision||e.change_type||"변경")+'</strong></div></div>';
 const filters='<div class="statusFilters"><button class="statusFilter '+(actionFilter==="all"?"active":"")+'" data-status="all">전체 '+all.length+'</button>'+["조치 확인","미조치 확인","반영 확인 필요","최신 근거 재확인 필요"].map(s=>'<button class="statusFilter '+(actionFilter===s?"active":"")+'" data-status="'+esc(s)+'">'+esc(s)+' '+all.filter(a=>a.status===s).length+'</button>').join("")+'</div>';
 const impact='<section><div class="actionSummary"><h3 class="sectionHeading" style="margin:0">기관별 변경 검토사항</h3><div class="actionTotal">전체 '+all.length+'건 · 조치 확인 '+countDone+' · 미조치 확인 '+countNot+'</div></div><p class="smallNote" style="margin:0 0 12px">기관의 업무 운영에서 무엇을 변경해야 하는지 확인합니다. 법령 자체를 다시 개정하라는 뜻은 아닙니다.</p>'+filters+agencyNavigator(current)+(current.length?groupedActions(current):showEmpty(all.length?"해당 상태의 항목은 없습니다.":"기관별 영향 분석 결과가 아직 없습니다.",all.length?"다른 상태를 선택하세요.":"공식적으로 연결된 기관과 업무가 확인될 때 표시됩니다."))+'</section>';
 const legal='<details class="legalDetails"><summary>개정 이유·상세 조문·공식 근거 펼쳐 보기</summary>'+(e.amendment_reason?'<div class="legalReasonFull"><b>공식 개정 이유 및 주요내용</b><p style="margin-top:8px">'+esc(e.amendment_reason)+'</p></div>':'')+differences(e)+'<a class="refLink" href="'+validUrl(e.amendment_url||e.url)+'" target="_blank" rel="noopener">공식 원문 열기 ↗</a></details>';
 return header+'<div class="detailBody">'+overview+impactSummary+facts+'<div class="sectionGap"></div>'+window.PolicyDominoAiView.render(e,DATA,AI_DATA)+impact+legal+'<div class="copyMeta">실제 적용 여부와 구체적 업무시스템명은 확인 근거가 있을 때만 확정합니다. 내부자료에 접근하지 않습니다.</div></div>';
}
function renderDetail(){
const e=getEvent();
$("detail").innerHTML=e?detailHTML(e):showEmpty("변경 사건을 선택해 주세요.","법령·정책 변경을 선택하면 기관별로 무엇을 바꿔야 하는지 한 번에 보여줍니다.");
const back=$("back");if(back)back.onclick=()=>{$("layout").classList.remove("detailOpen");history.replaceState(null,"",location.pathname+location.search)};
$("detail").querySelectorAll("[data-status]").forEach(b=>b.onclick=()=>{actionFilter=b.dataset.status;renderDetail()});
$("detail").querySelectorAll("[data-jump]").forEach(b=>b.onclick=()=>{const target=[...$("detail").querySelectorAll("[data-agency]")].find(x=>x.dataset.agency===b.dataset.jump);if(target)target.scrollIntoView({behavior:"smooth",block:"start"})});
}
function choose(id){
selectedId=id;actionFilter="all";$("layout").classList.add("detailOpen");displayList();renderDetail();
try{history.replaceState(null,"","#change="+encodeURIComponent(id))}catch(e){}
if(window.innerWidth<=850)window.scrollTo({top:0,behavior:"smooth"});
}
function render(){
displayList();renderDetail();
}
async function load(){
try{
const dataUrl=document.body.dataset.policyDataUrl;
if(!dataUrl)throw Error("정책 데이터 경로가 설정되지 않았습니다.");
let response=await fetch(dataUrl+"?v="+Date.now(),{cache:"no-store"});if(!response.ok)throw Error("HTTP "+response.status);
let d=await response.json();if(d.schema!=="policy-domino-next-v1")throw Error("기존 데이터 형식이므로 새 변경내역과 연결되지 않았습니다.");
DATA=d;AI_DATA=null;
try{
  const aiResponse=await fetch("../ai-impact/data.json?v="+Date.now(),{cache:"no-store"});
  if(aiResponse.ok){const candidate=await aiResponse.json();
    if(candidate?.schema==="policy-domino-llm-impact-v2"){AI_DATA=candidate;}
  }
}catch(_){/* No model output: never imply that an AI analysis was performed. */}
const h=d.health||{},partial=h.source_status==="메타데이터만 연결",amendment=h.source_status==="공식 공포·개정문 연결",bad=h.source_status==="수집 실패";
$("system").classList.toggle("error",bad);
$("sourceTitle").textContent=bad?"공식 변경 데이터 수집 실패":"실제 정책 변경과 기관별 검토 업무";
$("sourceDesc").textContent=bad?(h.error||"공식 변경 자료를 불러오지 못했습니다."):"신구 조문·공식 개정 지시문 기반 "+(d.events||[]).length+"개 변경 사건 · 기관별 검토 "+(d.actions||[]).length+"건. 현재 공식 본문과 이전 V2 자료는 검증 상태를 분리합니다. 내부 조치 완료 여부는 확인되지 않았습니다.";
$("lastChecked").textContent="최종 확인 "+(d.generated_at?new Date(d.generated_at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"}):"미확인");
const fragment=decodeURIComponent((location.hash||"").replace(/^#change=/,""));
if(fragment&&(d.events||[]).some(e=>e.event_id===fragment)){
  selectedId=fragment;
  if(!filterPolicyEvents(d.events,filter,"").some(e=>e.event_id===fragment))filter="all";
}
selectedId=resolveSelection(filteredEvents(),selectedId);
document.querySelectorAll("[data-law]").forEach(b=>b.classList.toggle("active",b.dataset.law===filter));
render();
}catch(e){DATA={events:[],actions:[],health:{source_status:"수집 실패"}};$("system").classList.add("error");$("sourceTitle").textContent="새 시스템 데이터를 불러오지 못했습니다.";$("sourceDesc").textContent=e.message;render();}
}
document.querySelectorAll("[data-law]").forEach(b=>b.onclick=()=>{
  filter=b.dataset.law;
  document.querySelectorAll("[data-law]").forEach(x=>x.classList.toggle("active",x.dataset.law===filter));
  selectedId=resolveSelection(filteredEvents(),selectedId);
  render();
});
$("q").oninput=()=>{selectedId=resolveSelection(filteredEvents(),selectedId);render()};$("reload").onclick=load;
window.addEventListener("popstate",()=>{if(!location.hash){$("layout").classList.remove("detailOpen")}});
load();
})();
