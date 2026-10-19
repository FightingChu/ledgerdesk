"use strict";
// All selections belong to one loaded page and one reconciliation run.
const LedgerDeskReviews={
  initialize({api,action,notify,escapeHTML,reviewLabels,state,onRefresh,evidenceView}){
    const $=(selector)=>document.querySelector(selector);
    let rows=new Map(),selected=new Set(),enabled=false,bulkContext=null,caseContext=null,caseRequestRevision=0;
    const isIssue=(row)=>!(row.reasons.length===1&&row.reasons[0]==="matched");
    function updateSelection(){
      $("#bulk-count").textContent=`已选择 ${selected.size} 项（仅当前页）`;
      $("#bulk-review-open").disabled=!selected.size||!enabled;
      $("#bulk-clear").disabled=!selected.size;
      const all=$("#bulk-select-page");
      all.disabled=!rows.size||!enabled;
      all.checked=!!rows.size&&selected.size===rows.size;
      all.indeterminate=selected.size>0&&selected.size<rows.size;
      document.querySelectorAll("[data-select-case]").forEach((box)=>{box.checked=selected.has(box.dataset.selectCase);box.disabled=!enabled;});
    }
    function invalidate(){
      rows.clear();selected.clear();enabled=false;updateSelection();
      if($("#bulk-review-dialog").open&&!state.busy)$("#bulk-review-dialog").close();
    }
    function page(data){
      invalidate();
      enabled=!!data.run_id&&!data.stale&&!data.read_only;
      if(enabled)for(const row of data.items)if(isIssue(row))rows.set(row.case_key,row);
      updateSelection();
    }
    function selectionCell(row){
      return enabled&&rows.has(row.case_key)?`<input type="checkbox" data-select-case="${row.case_key}" aria-label="选择 ${escapeHTML(row.order_id)} / ${escapeHTML(row.channel)}">`:'<span class="muted" aria-label="此记录不可批量处理">—</span>';
    }
    $("#results-list").addEventListener("change",(event)=>{
      const box=event.target.closest("[data-select-case]");
      if(!box||state.busy||!enabled||!rows.has(box.dataset.selectCase))return;
      if(box.checked)selected.add(box.dataset.selectCase);else selected.delete(box.dataset.selectCase);
      updateSelection();
    });
    $("#bulk-select-page").addEventListener("change",(event)=>{
      if(state.busy||!enabled)return;
      selected=event.target.checked?new Set(rows.keys()):new Set();updateSelection();
    });
    $("#bulk-clear").addEventListener("click",()=>{if(!state.busy){selected.clear();updateSelection();}});
    $("#bulk-review-open").addEventListener("click",()=>{
      if(state.busy||!enabled||!selected.size||!state.batch)return;
      bulkContext={batchId:state.batch.batch.id,runId:state.batch.run.id,revision:state.pageRevision,
        items:[...selected].map((key)=>{const row=rows.get(key);return {case_key:key,evidence_sha256:row.evidence_sha256,expected_revision:row.review_revision};})};
      $("#bulk-review-form").reset();$("#bulk-review-errors").hidden=true;
      $("#bulk-review-summary").textContent=`将更新当前页所选 ${bulkContext.items.length} 项差异。`;
      $("#bulk-review-dialog").showModal();
    });
    $("#bulk-review-form").addEventListener("submit",(event)=>{
      event.preventDefault();
      action(event.submitter,async()=>{
        try{
          const snapshot=bulkContext;
          if(!snapshot||!state.batch||snapshot.revision!==state.pageRevision||snapshot.batchId!==state.batch.batch.id)throw new Error("页面已变化，请刷新后重新选择");
          const saved=await api(`/api/batches/${snapshot.batchId}/bulk-review`,{run_id:snapshot.runId,items:snapshot.items,
            status:$("#bulk-review-status").value,note:$("#bulk-review-note").value});
          $("#bulk-review-dialog").close();invalidate();await onRefresh();notify(`已保存 ${saved.count} 项处理记录`);
        }catch(error){$("#bulk-review-errors").textContent=error.message;$("#bulk-review-errors").hidden=false;}
      });
    });
    $("#bulk-review-refresh").addEventListener("click",async()=>{
      if(state.busy)return;
      $("#bulk-review-dialog").close();invalidate();
      try{await onRefresh();}catch(error){notify(error.message,true);}
    });
    async function openCase(key, historicalRun=null) {
      if(state.busy||!state.batch)return;
      const batchId=state.batch.batch.id,revision=state.pageRevision;
      const url=historicalRun?`/api/batches/${batchId}/runs/${encodeURIComponent(historicalRun)}/cases/${key}/info`:`/api/batches/${batchId}/cases/${key}/info?run_id=${encodeURIComponent(state.batch.run?.id||"")}`;
      const ownCaseRevision=++caseRequestRevision;
      const detail=await api(url);
      if(!state.batch||state.pageRevision!==revision||ownCaseRevision!==caseRequestRevision)return;
      const row=detail.item;
      caseContext={row,batchId,runId:detail.run_id,revision};
      $("#case-title").textContent=row.order_id+" / "+row.channel;
      $("#case-summary").innerHTML=`<div class="reason-list">${row.reason_labels.map((label)=>`<span class="badge danger">${label}</span>`).join("")}</div><div class="case-overview"><div><label>预计净到账</label><strong>¥ ${row.expected}</strong></div><div><label>账单净额</label><strong>¥ ${row.actual}</strong></div><div><label>差额</label><strong>¥ ${row.difference}</strong></div></div>`;
      await evidenceView.open({batchId,key,runId:detail.run_id,historical:!!historicalRun});
      if(!state.batch||state.pageRevision!==revision||ownCaseRevision!==caseRequestRevision)return;
      const editable=!(row.reasons.length===1&&row.reasons[0]==="matched")&&!detail.stale&&!detail.read_only&&!state.batch.batch.archived;
      $("#review-controls").hidden=!editable; $("#save-review").hidden=!editable;
      $("#review-status").value=row.review_status; $("#review-note").value=row.note;
      caseContext.editable=editable;
      $("#review-errors").hidden=true;
      $("#reload-case").hidden=!editable;
      $("#case-dialog").showModal();
    }
    $("#case-dialog").addEventListener("close",()=>{caseRequestRevision++;});
    $("#review-form").addEventListener("submit",(event)=>{
      event.preventDefault();
      action(event.submitter,async()=>{
        try{
          const snapshot=caseContext;
          if(!snapshot?.editable||!state.batch||snapshot.revision!==state.pageRevision||snapshot.batchId!==state.batch.batch.id)throw new Error("页面已变化，请关闭详情并刷新结果");
          await api(`/api/batches/${snapshot.batchId}/review`,{case_key:snapshot.row.case_key,evidence_sha256:snapshot.row.evidence_sha256,
            run_id:snapshot.runId,expected_revision:snapshot.row.review_revision,status:$("#review-status").value,note:$("#review-note").value});
          $("#case-dialog").close();await onRefresh();notify("处理记录已保存");
        }catch(error){$("#review-errors").textContent=error.message;$("#review-errors").hidden=false;}
      });
    });
    $("#reload-case").addEventListener("click",async()=>{
      if(state.busy||!caseContext)return;
      const key=caseContext.row.case_key;
      try{await onRefresh();await openCase(key);}catch(error){$("#review-errors").textContent=error.message;$("#review-errors").hidden=false;}
    });
    return {page,invalidate,selectionCell,openCase};
  }
};
