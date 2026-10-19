"use strict";
globalThis.LedgerDeskAuditExport={initialize({context}){
  const update=()=>{
    const current=context();
    if(!current)return;
    const action=document.querySelector("#audit-action")?.value||"all";
    const until=document.querySelector("#audit-until-id")?.value||"";
    const query=new URLSearchParams({format:"csv",action});
    if(until)query.set("until_id",until);
    const link=document.querySelector("#audit-export-link");
    if(link){link.href=`/api/batches/${current.batchId}/audit-export?${query}`;link.hidden=false;}
  };
  document.querySelector("#audit-action")?.addEventListener("change",update);
  document.querySelector("#audit-export-link")?.addEventListener("click",update);
  return {update};
}};
