"use strict";
const LedgerDeskBatches={
  initialize({api,action,notify,escapeHTML,timeLabel,state,onOpen,onRefreshList}){
    const $=(selector)=>document.querySelector(selector);
    function render() {
      const status=$("#batch-state").value,query=$("#batch-search").value.trim().toLowerCase();
      const batches=state.batches.filter((batch)=>(status==="all"||!!batch.archived===(status==="archived"))&&`${batch.name} ${batch.description} ${batch.tags.join(" ")}`.toLowerCase().includes(query));
      $("#batch-count").textContent = state.batches.length;
      $("#list-count").textContent = batches.length;
      $("#empty-batches").hidden = !!batches.length;
      $("#batch-list").innerHTML = batches.map((batch) => `<tr data-batch="${batch.id}" tabindex="0" role="button" aria-label="打开 ${escapeHTML(batch.name)}"><td><div class="batch-name">${escapeHTML(batch.name)} ${batch.archived?'<span class="badge neutral">已归档</span>':""}</div><div class="batch-sub">${escapeHTML(batch.description || "独立核查批次")}</div><div class="reason-list">${batch.tags.map((tag)=>`<span class="badge neutral">${escapeHTML(tag)}</span>`).join("")}</div></td><td><span class="badge ${batch.is_sample ? "" : "neutral"}">${batch.is_sample ? "演示批次" : "用户导入"}</span></td><td>${batch.file_count} 份有效文件${batch.latest_summary?`<div class="batch-sub">${batch.latest_summary.groups} 组 · ${batch.latest_summary.issues} 项差异 · 差额 ${escapeHTML(batch.latest_summary.difference)}</div>`:""}</td><td>${timeLabel(batch.created_at)}</td><td>↗</td></tr>`).join("");
    }
    $("#edit-batch").addEventListener("click",()=>{if(state.busy)return;$("#batch-tags").value=state.batch.batch.tags.join("，");$("#batch-archived").checked=!!state.batch.batch.archived;$("#batch-settings").showModal();});
    $("#batch-settings-form").addEventListener("submit",(event)=>{event.preventDefault();const id=state.batch.batch.id,tags=$("#batch-tags").value.split(/[,，]/).map((tag)=>tag.trim()).filter(Boolean),archived=$("#batch-archived").checked;action(event.submitter,async()=>{await api(`/api/batches/${id}/update`,{tags,archived});$("#batch-settings").close();await onOpen(id,false);await onRefreshList();notify(archived?"批次已归档":"批次设置已保存");});});

    $("#batch-state").addEventListener("change",render);
    $("#batch-search").addEventListener("input",render);
    return {render};
  }
};
