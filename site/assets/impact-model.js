"use strict";
/** Pure, source-agnostic list and selection rules for the agency-impact view. */
(function(root) {
  const DEFAULT_FILTER = "all";
  function typeOf(event) {
    const label=event.revision||event.change_type||event.type||"";
    return /폐지/.test(label)&&!/제정/.test(label)?"abolished":
      /제정|신설/.test(label)&&!/개정/.test(label)?"new":"amended";
  }
  function sorted(events) {
    return [...(events||[])].sort((a,b)=>
      String(b.promulgated_at||b.change_date||"").localeCompare(String(a.promulgated_at||a.change_date||""))||
      (Number(b.impact_priority)||0)-(Number(a.impact_priority)||0));
  }
  function filterEvents(events,filter=DEFAULT_FILTER,query="") {
    const q=String(query||"").trim().toLowerCase();
    return sorted(events).filter(e=>
      (filter==="all"||(filter==="high-impact"?e.impact_level==="high":typeOf(e)===filter)) &&
      (!q||[e.title,e.ministry,e.law_type,e.revision].some(v=>String(v||"").toLowerCase().includes(q)))
    );
  }
  function resolveSelection(visibleEvents,selectedId) {
    if(selectedId && visibleEvents.some(e=>e.event_id===selectedId))return selectedId;
    return visibleEvents[0]?.event_id||null;
  }
  const api=Object.freeze({DEFAULT_FILTER,typeOf,sorted,filterEvents,resolveSelection});
  root.PolicyDominoView=api;
  if(typeof module!=="undefined" && module.exports)module.exports=api;
})(typeof window==="undefined"?globalThis:window);
