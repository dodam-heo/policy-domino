"use strict";
(function(){
const $=id=>document.getElementById(id);
const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function validUrl(raw){try{const u=new URL(raw);return ["https:","http:"].includes(u.protocol)?esc(u.href):"#"}catch(e){return "#"}}
function fmtDate(s){if(!s)return "미확인";if(/^\d{4}-\d{2}-\d{2}$/.test(s))return s.replaceAll("-",". ");let d=new Date(s);return Number.isNaN(d.getTime())?esc(s):new Intl.DateTimeFormat("ko-KR",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"}).format(d)}
function fmtMoment(s){if(!s)return "미확인";const d=new Date(s);return Number.isNaN(d.getTime())?"미확인":new Intl.DateTimeFormat("ko-KR",{timeZone:"Asia/Seoul",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"}).format(d)}
const {typeOf,sorted,filterEvents:filterPolicyEvents,resolveSelection,DEFAULT_FILTER}=window.PolicyDominoView;
function typeLabel(e){let k=typeOf(e);return k==="new"?"신규":k==="abolished"?"폐지":"개정"}
function typeClass(e){return typeOf(e)==="new"?"add":typeOf(e)==="abolished"?"remove":""}
function matchingActions(event){return (DATA.actions||[]).filter(a=>a.event_id===event.event_id)}
let DATA={events:[],actions:[],health:{}},AI_DATA=null,selectedId=null,filter=DEFAULT_FILTER;
let selectedAgency=null,agencySearch="",resultLimit=20,lawVisibleLimit=80;
const openAgencyTypes=new Set(),openAgencyRegions=new Set();
function filteredEvents(){return filterPolicyEvents(DATA.events,filter,$("q").value)}
function getEvent(){return (DATA.events||[]).find(e=>e.event_id===selectedId)||null}
function showEmpty(title,body){return '<div class="empty"><svg width="35" height="35" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M3 4h18v16H3z"/><path d="M7 8h10M7 12h10M7 16h6"/></svg><b>'+esc(title)+'</b><p style="margin-top:8px">'+esc(body)+'</p></div>'}
function eventRow(e){
const num=matchingActions(e).length,chosen=selectedId===e.event_id;
return '<button type="button" class="lawItem'+(chosen?' active':'')+'" data-event="'+esc(e.event_id)+'" aria-selected="'+chosen+'">'+
 '<div class="lawTop"><span class="lawType '+typeClass(e)+'">'+typeLabel(e)+'</span><span class="lawDate">'+fmtDate(e.promulgated_at||e.change_date)+'</span></div>'+
 '<div class="lawName">'+esc(e.title||"법령명 확인 중")+'</div>'+
 '<div class="lawMeta">'+esc(e.ministry||"소관기관 확인 중")+'</div>'+
 '<div class="lawFoot">'+(num?'<span class="mini">검토사항 '+num+'건</span>':'<span class="mini">영향 검토 중</span>')+
 (e.source_verification==="official_index_only"?
 '<span class="mini">본문 대조 대기</span>':
 e.source_verification==="detail_pending"?
 '<span class="mini">원문 재확인 대기</span>':'')+
 ((e.source_documents||[]).some(d=>d.needs_attachment_check)?
 '<span class="mini">첨부 표 확인 대기</span>':'')+
 '<span>기관별 보기 ›</span></div></button>';
}
function displayList(){

const events=filteredEvents();
$("listCount").textContent="전체 "+(DATA.events||[]).length+"건 · 표시 "+events.length+"건";
$("lawList").innerHTML=events.length?events.slice(0,lawVisibleLimit).map(eventRow).join("")+
 (events.length>lawVisibleLimit?'<button type="button" class="listMore" id="lawMore">더 보기 · 남은 '+(events.length-lawVisibleLimit)+'건</button>':""):showEmpty(DATA.health?.source_status==="수집 실패"?"공식 변경내역을 가져오지 못했습니다.":"표시할 확정 변경내역이 없습니다.",DATA.health?.source_status==="수집 실패"?"원천 연결 상태를 확인해 주세요. 변경이 없다는 뜻은 아닙니다.":"검색 조건을 변경하거나 공식 수집 상태를 확인하세요.");
$("lawList").querySelectorAll("[data-event]").forEach(b=>b.onclick=()=>choose(b.dataset.event));
const more=$("lawMore");
if(more)more.onclick=()=>{lawVisibleLimit+=80;displayList()};
}
function badgeStatus(s){let cls=s==="조치 확인"?"done":s==="미조치 확인"?"pending":s==="시행 예정"?"upcoming":"";const label=s==="최신 근거 재확인 필요"?"확인 중":(s||"반영 확인 필요");return '<span class="status '+cls+'">'+esc(label)+'</span>'}
// Institution grouping comes from the official source name. Region labels
// are parsed dynamically; no ministry, region, school or service is enrolled
// through a hardcoded name mapping.
const INSTITUTION_CATEGORIES=["중앙행정기관","지방자치단체","교육청","공공기관·기타"];
const REGION_PREFIX=/^([가-힣]+?(?:특별자치시|특별자치도|특별시|광역시|도))(?=\s|교육청|교육지원청|$)/;
function institutionRegion(name){
 const matched=String(name||"").match(REGION_PREFIX);
 return matched?matched[1]:"지역 구분 없음";
}
function institutionType(name){
 const label=String(name||"").trim();
 if(/교육청|교육지원청/.test(label))return "교육청";
 if(institutionRegion(label)!=="지역 구분 없음"||
    /^(?:시·군·구|지방자치단체)$/.test(label)||
    /^[가-힣]{2,12}(?:시|군|구|시청|군청|구청)$/.test(label))return "지방자치단체";
 if(/(?:부|처|청|위원회)$/.test(label))return "중앙행정기관";
 return "공공기관·기타";
}
function overviewText(e){
 const summary=String(e.change_summary||"").trim();
 if(summary)return summary;
 const d=(e.article_differences||[]).find(x=>x.before!==x.after);
 return d?String(d.article||"변경 조문")+"의 규정 변경":"공식 신구 조문 대조 중";
}
function agencyEntries(items){
 const counts=new Map();
 for(const a of items){
   const name=a.agency||"기관 확인 필요";
   counts.set(name,(counts.get(name)||0)+1);
 }
 return [...counts].map(([name,count])=>({name,count,
   type:institutionType(name),region:institutionRegion(name)}))
   .sort((a,b)=>a.name.localeCompare(b.name,"ko"));
}
function sidebarAgencyButton(entry){
 return '<button type="button" class="sideAgency'+(selectedAgency===entry.name?' active':'')+
 '" data-agency-pick="'+esc(entry.name)+'" aria-pressed="'+(selectedAgency===entry.name)+'">'+
 '<span class="sideAgencyName">'+esc(entry.name)+'</span>'+
 '<span class="sideCount">'+entry.count+'</span></button>';
}
function sidebarGroups(entries){
 const q=agencySearch.toLocaleLowerCase("ko");
 const matched=q?entries.filter(x=>x.name.toLocaleLowerCase("ko").includes(q)):entries;
 const rows=INSTITUTION_CATEGORIES.map(type=>{
   const list=matched.filter(x=>x.type===type);
   if(!list.length)return "";
   const hasRegions=type==="지방자치단체"||type==="교육청";
   let children="";
   if(hasRegions){
     const regions=new Map();
     for(const x of list){
       if(!regions.has(x.region))regions.set(x.region,[]);
       regions.get(x.region).push(x);
     }
     children=[...regions].sort((a,b)=>a[0].localeCompare(b[0],"ko"))
       .map(([region,part])=>{
         const key=type+"|"+region, show=q||openAgencyRegions.has(key)||
           part.some(x=>x.name===selectedAgency);
         return '<details class="sideRegion" data-side-region="'+esc(key)+'"'+(show?' open':'')+'>'+
           '<summary>'+esc(region)+' <span>'+part.length+'</span></summary>'+
           '<div class="sideAgencyList">'+part.map(sidebarAgencyButton).join("")+'</div></details>';
       }).join("");
   }else{
     children='<div class="sideAgencyList">'+list.map(sidebarAgencyButton).join("")+'</div>';
   }
   const opened=q||openAgencyTypes.has(type)||
     list.some(x=>x.name===selectedAgency);
   return '<details class="sideType" data-side-type="'+esc(type)+'"'+(opened?' open':'')+'>'+
     '<summary>'+esc(type)+' <span>'+list.length+'</span></summary>'+
     '<div class="sideTypeBody">'+children+'</div></details>';
 }).filter(Boolean);
 return rows.length?rows.join(""):'<p class="agencyNoMatch">검색 결과가 없습니다.</p>';
}
function institutionSidebar(entries){
 return '<aside class="agencySidebar" aria-label="기관명 필터">'+
 '<div class="agencySideHeading">기관명 검색</div>'+
 '<input type="search" id="agencySearch" class="agencySearch" value="'+esc(agencySearch)+
 '" placeholder="기관명 검색" aria-label="기관명 검색" autocomplete="off">'+
 '<button type="button" class="sideAll'+(!selectedAgency?' active':'')+
 '" data-agency-all aria-pressed="'+(!selectedAgency)+'">'+
 '<span>전체 기관</span><span>'+entries.length+'</span></button>'+
 '<div id="agencySidebarGroups" class="agencySidebarGroups">'+sidebarGroups(entries)+'</div></aside>';
}
function allAgencyResults(entries,all,aiFindings){
 const shown=entries.slice(0,resultLimit);
 const count=all.length;
 const groups=shown.map((entry,i)=>{
   const tasks=all.filter(x=>(x.agency||"기관 확인 필요")===entry.name);
   const cards=tasks.map(a=>actionCard(a,aiFindings)).join("");
   return '<details class="agencyResultGroup"'+(i===0?' open':'')+'>'+
     '<summary>'+esc(entry.name)+'<span>'+entry.count+'건</span></summary>'+
     '<div class="agencyResultCards">'+cards+'</div></details>';
 }).join("");
 return '<div class="agencyResultHeader"><strong>전체 기관</strong>'+
 '<span>'+entries.length+'개 기관 · '+count+'건</span></div>'+
 '<div class="agencyResultList">'+groups+'</div>'+
 (entries.length>shown.length?'<button type="button" class="agencyMore" data-agency-more>'+
 '기관 더 보기 ('+(entries.length-shown.length)+'개 남음)</button>':"");
}
function selectedAgencyResults(name,all,aiFindings){
 const tasks=all.filter(x=>(x.agency||"기관 확인 필요")===name);
 return '<div class="agencyResultHeader"><strong>'+esc(name)+'</strong>'+
 '<span>검토사항 '+tasks.length+'건</span></div>'+
 '<div class="agencySelectedCards">'+tasks.map(a=>actionCard(a,aiFindings)).join("")+'</div>';
}
function actionCard(a, aiFindings){
const changes=a.changes||[];
const upstream=a.comparison_scope==="source_policy_only";
const comparison=changes.length?'<div class="valueRows">'+changes.map(p=>
 '<div class="valueRow"><div class="oldValue"><small>변경 전</small>'+esc(p.before||"미확인")+
 '</div><div class="valueArrow">→</div><div class="newValue"><small>변경 후</small>'+
 esc(p.after||"미확인")+'</div></div>').join("")+'</div>':
 '<p class="actionSummaryText">'+esc(a.what_to_change||a.source_change||"변경사항 확인 중")+'</p>';
const added=(a.new_items||[]).length?'<p class="taskDesc"><b>추가 항목</b> '+
 esc(a.new_items.slice(0,6).join(" · "))+'</p>':"";
const task=esc(a.target_location||a.service||"업무 위치 확인 중");
const role=esc(a.work||a.category||"업무");
const provenance=a.evidence_scope==="v4_verified_source"?"공식 근거 확인":
 a.service_id?"공공서비스 적용관계 확인":"근거 확인 중";
return '<article class="action">'+
 '<div class="actionTop"><div class="actionLawTitle">'+
 (a.service_id?esc(a.service||"공공서비스"):esc(a.law_title||a.agency||"변경 항목")+
 ' · '+esc(a.article||"조문 확인 중"))+'</div>'+badgeStatus(a.status)+'</div>'+
 '<div class="locationBox">'+role+' <span class="taskArrow">›</span> '+task+'</div>'+
 '<div class="locationTitle">'+(upstream?"상위 정책 기준의 변경값 · 이 사업 자체 금액 아님":"변경 전후")+'</div>'+comparison+added+
 '<div class="instruction"><b>검토할 조치</b>'+
 esc(a.required_change||"반영 필요 여부 확인")+'</div>'+
 window.PolicyDominoAiView.renderForAction(a,aiFindings.get(a.id))+
 '<details class="evidenceDrawer"><summary>시행일·공식 근거</summary>'+
 '<div class="evidence"><b>'+esc(a.law_title||"근거 확인 중")+' · '+esc(a.article||"")+'</b>'+
 '<div>시행일 '+esc(a.effective_date||"확인 중")+' · '+esc(provenance)+'</div>'+
 '<a target="_blank" rel="noopener" href="'+validUrl(a.basis)+'">법령 변경 근거 ↗</a>'+
 (a.service_id&&a.service_url?
 ' · <a target="_blank" rel="noopener" href="'+validUrl(a.service_url)+'">공공서비스 기준 확인 ↗</a>':'')+
 (a.service_id&&a.reported_receiving_institution?
 '<div>정부24 등록 접수기관: '+esc(a.reported_receiving_institution)+'</div>':'')+
 (a.status_evidence?'<div>조치 상태 근거: '+esc(a.status_evidence)+'</div>':'')+
 '</div></details></article>';
}
function differences(e,limit){
const ds=(e.article_differences||[]).slice(0,limit||undefined);
if(!ds.length)return '<p class="smallNote">공식 공포 정보는 확인됐지만 종전·변경 조문의 실제 비교가 아직 완료되지 않았습니다. 변경 전후 내용을 추측해 채우지 않습니다.</p>';
return ds.map(d=>'<div class="change"><div class="changeHead"><span>'+esc(d.article||"변경 조문")+' '+esc(d.title||"")+'</span><span>'+esc(d.type||"변경")+'</span></div><div class="changePair"><div class="changeCol before"><small>종전 내용</small><p>'+esc(d.before||(d.type==="신설"?"신설 이전 규정 없음":"종전 조문 전문 별도 대조 필요"))+'</p></div><div class="changeCol after"><small>'+(d.directive?"공식 개정 지시문":"변경 후 조문")+'</small><p>'+esc(d.directive||d.after||"변경 내용 확인 필요")+'</p></div></div></div>').join("")
}
function legalRelationships(event){
 // The counts are the actual official source records carried by the
 // evidence pipeline, NOT numbers guessed from the title of the event.
 const laws=[],seenLaws=new Set();
 for(const item of event.simultaneous_laws||[]){
   if(!item.title||!item.url||validUrl(item.url)==="#")continue;
   const key=item.title+"|"+item.url;
   if(seenLaws.has(key))continue;
   seenLaws.add(key);laws.push(item);
 }
 const cites=new Map();
 for(const item of event.citing_regulations||[]){
   if(!item.title||!item.url||validUrl(item.url)==="#")continue;
   const key=item.title+"|"+item.url;
   if(!cites.has(key))cites.set(key,{title:item.title,url:item.url,
      references:[]});
   const refs=cites.get(key).references;
   if(!refs.some(x=>x.source_title===item.source_title&&
     x.source_article===item.source_article&&
     x.target_article===item.target_article))refs.push(item);
 }
 const lawSection=laws.length>0?
 '<details class="lawConnection"><summary>동시 개정된 법령 '+laws.length+'건 확인</summary>'+
 '<div class="lawConnectionBody"><p class="lawConnectionNote">동일 공포번호로 함께 개정된 법령</p>'+
 laws.map(law=>'<div class="lawConnectionItem"><div class="lawConnectionMain">'+
 '<strong>'+esc(law.title)+'</strong><small>'+esc(law.kind||"")+
 (law.changed_articles?.length?' · 변경 조문 '+law.changed_articles.length+'개':'')+
 '</small></div><a href="'+validUrl(law.url)+
 '" target="_blank" rel="noopener">법령 원문 ↗</a></div>').join("")+'</div></details>':"";
 const refs=[...cites.values()];
 const citingSection=refs.length>0?
 '<details class="lawConnection"><summary>변경 조문을 인용하는 관련 규정 '+
 refs.length+'건 확인</summary><div class="lawConnectionBody">'+
 refs.map(rule=>'<div class="lawConnectionItem">'+
 '<div class="lawConnectionMain"><strong>'+esc(rule.title)+'</strong>'+
 rule.references.map(ref=>'<small>'+
 esc(ref.source_title||"")+' '+esc(ref.source_article||"")+
 ' → '+esc(ref.target_article||"")+' · '+esc(ref.proof||"적용 관계 확인")+
 '</small>').join("")+'</div>'+
 '<a href="'+validUrl(rule.url)+
 '" target="_blank" rel="noopener">관련 규정 ↗</a></div>').join("")+
 '</div></details>':"";
 return lawSection||citingSection?'<section class="lawConnections" aria-label="법령 연결 관계">'+
 lawSection+citingSection+'</section>':"";
}
function detailHTML(e){
 const all=matchingActions(e),entries=agencyEntries(all);
 const active=selectedAgency&&entries.some(x=>x.name===selectedAgency);
 if(selectedAgency&&!active)selectedAgency=null;
 const aiFindings=new Map(window.PolicyDominoAiView.verifiedCards(e,DATA,AI_DATA)
   .map(f=>[f.action_id,f]));
 const provenance=e.presentation_source==="v4_official_source"?"":" · 최신 근거 재확인 필요";
 const header='<div class="detailHeader"><button type="button" class="back" id="back">← 목록으로</button>'+
 '<div class="detailKicker">'+esc(e.ministry||"발령기관 확인 중")+' · '+esc(e.law_type||"정책 변경")+' · '+typeLabel(e)+'</div>'+
 '<h2 class="detailTitle">'+esc(e.title||"변경사항")+'</h2>'+
 '<div class="detailMeta">공포·확정 '+fmtDate(e.promulgated_at||e.change_date)+esc(provenance)+'</div></div>';
 const overview='<section class="changeOverview"><div class="overviewLabel">변경 핵심</div>'+
 '<div class="overviewText">'+esc(overviewText(e))+'</div>'+
 '<div class="overviewEffective">시행일 '+fmtDate(e.effective_date)+'</div></section>';
 const impact='<section class="agencyImpactSection">'+
 '<div class="agencySectionHead"><h3 class="sectionHeading">기관별 변경 검토사항</h3>'+
 '<span>'+entries.length+'개 기관 · '+all.length+'건</span></div>'+
 '<div class="agencyWorkbench">'+institutionSidebar(entries)+
 '<div class="agencyResults" aria-live="polite">'+
 (all.length?(selectedAgency?selectedAgencyResults(selectedAgency,all,aiFindings):
    allAgencyResults(entries,all,aiFindings)):
    showEmpty("기관별 검토사항 확인 중","공식 근거가 확인되면 표시됩니다."))+
 '</div></div></section>';
 const sourceChanges='<section class="sourceChanges"><h3 class="sectionHeading">실제 변경사항 · 신구 비교</h3>'+differences(e,3)+'</section>';
 const missingAttachments=(e.source_documents||[]).flatMap(d=>d.unresolved_attachments||[]);
 const annexes=missingAttachments.length?
 '<details class="legalDetails"><summary>미확인 공식 별표·첨부 '+missingAttachments.length+'건</summary>'+
 missingAttachments.map(d=>'<div><a class="refLink" href="'+validUrl(d.url)+
 '" target="_blank" rel="noopener">'+esc(d.title||d.label||"공식 첨부")+' ↗</a> · 원문 수치 검증 대기</div>').join("")+
 '</details>':"";
 const legal='<details class="legalDetails"><summary>전체 개정 이유·상세 조문 보기</summary>'+
 (e.amendment_reason?'<div class="legalReasonFull"><b>공식 개정 이유</b><p style="margin-top:8px">'+
 esc(e.amendment_reason)+'</p></div>':'')+differences(e)+
 '<a class="refLink" href="'+validUrl(e.amendment_url||e.url)+
 '" target="_blank" rel="noopener">공식 원문 보기 ↗</a></details>';
 return header+'<div class="detailBody">'+overview+sourceChanges+annexes+legal+
 legalRelationships(e)+impact+'</div>';
}
function bindSidebarGroups(){
 $("detail").querySelectorAll("[data-agency-pick]").forEach(b=>b.onclick=()=>{
   selectedAgency=b.dataset.agencyPick;
   renderDetail();
 });
 $("detail").querySelectorAll("[data-side-type]").forEach(d=>{
   d.ontoggle=()=>{if(d.open)openAgencyTypes.add(d.dataset.sideType);
     else openAgencyTypes.delete(d.dataset.sideType)};
 });
 $("detail").querySelectorAll("[data-side-region]").forEach(d=>{
   d.ontoggle=()=>{if(d.open)openAgencyRegions.add(d.dataset.sideRegion);
     else openAgencyRegions.delete(d.dataset.sideRegion)};
 });
}
function renderDetail(){
 const e=getEvent();
 $("detail").innerHTML=e?detailHTML(e):
   showEmpty("변경 사건을 선택해 주세요.","법령·정책 변경을 선택하면 기관별로 무엇을 바꿔야 하는지 한 번에 보여줍니다.");
 const back=$("back");
 if(back)back.onclick=()=>{$("layout").classList.remove("detailOpen");
    history.replaceState(null,"",location.pathname+location.search)};
 const all=$("detail").querySelector("[data-agency-all]");
 if(all)all.onclick=()=>{selectedAgency=null;agencySearch="";resultLimit=20;renderDetail()};
 bindSidebarGroups();
 const search=$("agencySearch");
 if(search)search.oninput=()=>{
   agencySearch=search.value.trim();
   const list=$("agencySidebarGroups");
   if(list){list.innerHTML=sidebarGroups(agencyEntries(matchingActions(e)));
     bindSidebarGroups();}
 };
 const more=$("detail").querySelector("[data-agency-more]");
 if(more)more.onclick=()=>{resultLimit+=20;renderDetail()};
}
function choose(id){
if(selectedId!==id){selectedAgency=null;agencySearch="";resultLimit=20;openAgencyTypes.clear();openAgencyRegions.clear();}
selectedId=id;$("layout").classList.add("detailOpen");displayList();renderDetail();
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
const h=d.health||{},bad=h.source_status==="수집 실패";
$("system").classList.toggle("error",bad);
$("sourceTitle").textContent=bad?"자료 갱신 실패":"정책 변경 "+d.events.length+"건 · 기관별 검토사항 "+d.actions.length+"건";
const lastAI=window.PolicyDominoAiView.latestAnalyzedAt(DATA,AI_DATA);
$("sourceDesc").textContent=bad?(h.error||"최근 자료를 불러오지 못했습니다."):
 lastAI?"AI 검토 반영 · 마지막 분석 "+fmtMoment(lastAI):
 AI_DATA?"AI 검토 결과 확인 중":"AI 검토 결과 대기";
$("lastChecked").textContent="자료 갱신 "+fmtMoment(d.generated_at)+" · 6시간 간격 자동 점검 설정";
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
$("q").oninput=()=>{lawVisibleLimit=80;selectedId=resolveSelection(filteredEvents(),selectedId);render()};$("reload").onclick=load;
window.addEventListener("popstate",()=>{if(!location.hash){$("layout").classList.remove("detailOpen")}});
load();
})();
