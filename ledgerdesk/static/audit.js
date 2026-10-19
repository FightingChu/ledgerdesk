"use strict";
const LedgerDeskAudit={
  initialize({api,notify,escapeHTML,timeLabel,reviewLabels,context}){
    const $=(selector)=>document.querySelector(selector);
    let page=1,pages=1,until=null,revision=0;
    function description(item){
      const p=item.payload;
      if(item.action==="import_file")return `${p.filename} · ${p.rows} 行`;
      if(item.action==="revoke_import")return `${p.filename} · ${p.reason}`;
      if(item.action==="replace_import")return `${p.filename} → ${p.replacement_filename} · ${p.reason}`;
      if(item.action==="review")return `${p.order_id||"历史差异"}${p.channel?" / "+p.channel:""} · ${reviewLabels[p.status]||p.status} · ${p.note}`;
      if(item.action==="bulk_review")return `${p.count} 项 · ${reviewLabels[p.status]||p.status} · ${p.note||"未填写备注"}`;
      if(item.action==="update_batch")return `${p.archived?"已归档":"进行中"} · ${(p.tags||[]).join("、")||"无标签"}`;
      return "";
    }
    function changeDetails(p){
      if(!p.before||!p.after)return "";
      return `<details class="audit-change"><summary>查看处理变更</summary><p>之前：${escapeHTML(reviewLabels[p.before.status]||p.before.status)} · ${escapeHTML(p.before.note||"无备注")}</p><p>之后：${escapeHTML(reviewLabels[p.after.status]||p.after.status)} · ${escapeHTML(p.after.note||"无备注")}</p><p class="hint">处理版本 ${p.before.revision} → ${p.after.revision}${p.operation_id?` · 批量操作 ${escapeHTML(p.operation_id)}`:""}</p></details>`;
    }
    async function load(reset=false){
      const current=context();if(!current||!$("#audit-panel").open)return;
      if(reset){page=1;until=null;}
      const own=++revision,params=new URLSearchParams({page:String(page),page_size:"25",action:$("#audit-action").value});
      if(until!==null)params.set("until_id",until);
      $("#audit-page-label").textContent="正在加载操作记录…";
      $("#audit-prev").disabled=true;$("#audit-next").disabled=true;
      try{
        const data=await api(`/api/batches/${current.batchId}/audit?${params}`);
        if(own!==revision||context()?.revision!==current.revision)return;
        page=data.page;pages=data.total_pages;until=data.until_id;
        $("#audit-list").innerHTML=data.items.map((item)=>`<article class="audit-item"><time>${escapeHTML(timeLabel(item.created_at))}</time><div><strong>${escapeHTML(data.actions[item.action]||item.action)}</strong><p>${escapeHTML(description(item))}</p>${changeDetails(item.payload)}</div></article>`).join("")||'<p class="hint">当前类型没有操作记录。</p>';
        $("#audit-page-label").textContent=`第 ${page} / ${pages} 页 · 共 ${data.total} 条`;
        $("#audit-prev").disabled=page<=1;$("#audit-next").disabled=page>=pages;
      }catch(error){
        if(own!==revision||context()?.revision!==current.revision)return;
        $("#audit-list").textContent="";$("#audit-page-label").textContent="操作记录加载失败，请刷新";notify(error.message,true);
      }
    }
    function reset(){revision++;page=1;until=null;$("#audit-action").value="all";$("#audit-list").textContent="";load(true);}
    $("#audit-panel").addEventListener("toggle",()=>{if($("#audit-panel").open)load(true);});
    $("#audit-action").addEventListener("change",()=>load(true));
    $("#audit-refresh").addEventListener("click",()=>load(true));
    $("#audit-prev").addEventListener("click",()=>{if(page>1){page--;load();}});
    $("#audit-next").addEventListener("click",()=>{if(page<pages){page++;load();}});
    return {reset};
  }
};
