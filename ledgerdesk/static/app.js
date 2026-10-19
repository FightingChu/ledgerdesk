"use strict";
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = { reportProfile:null, token: "", batches: [], templates: [], batch: null, filter: "issues", busy: false, revokeContext: null, pageRevision: 0, historyRun: null, historyPage: 1, historyPages: 1, historyRevision: 0, comparison: null, comparisonPage: 1, comparisonPages: 1, comparisonRevision: 0 };
const fieldLabels = { order_id: "订单号", transaction_id: "渠道流水号", amount: "金额（元）", event_type: "类型：sale / refund", channel: "渠道" };
const reviewLabels = { pending: "待处理", in_progress: "处理中", resolved: "已处理" };
const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const timeLabel = (value) => value ? new Date(value).toLocaleString("zh-CN", {hour12:false}) : "尚未核对";
function notify(message, error = false) {
  const element = $("#toast");
  element.textContent = message; element.classList.toggle("error", error); element.hidden = false;
  clearTimeout(notify.timer); notify.timer = setTimeout(() => { element.hidden = true; }, error ? 6500 : 3800);
}
async function api(path, data) {
  const options = data === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json", "X-LedgerDesk-Token":state.token}, body:JSON.stringify(data)};
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) { const error = new Error(result.error || "操作失败"); error.errors = result.errors || []; error.code=result.code; throw error; }
  return result;
}
async function action(button, operation) {
  if (state.busy) return;
  state.busy = true; if (button) button.disabled = true;
  try { await operation(); } catch (error) { notify(error.message, true); }
  finally { state.busy = false; if (button) button.disabled = false; }
}
async function refreshList() {
  state.batches = (await api("/api/batches")).batches;
  renderBatches();
}
function renderBatches(){batchView.render();}

async function refreshTemplates(){state.templates=(await api("/api/templates")).templates;}
function renderTemplates(){
  $("#templates-list").innerHTML=state.templates.length?state.templates.map((item)=>`<article class="template-card"><h3>${escapeHTML(item.name)} <span class="badge neutral">${item.side==="orders"?"业务单":"支付账单"} · 修订 ${item.revision}</span></h3><p class="hint">${Object.entries(JSON.parse(item.mapping)).map(([field,column])=>`${fieldLabels[field]||field} → ${column}`).map(escapeHTML).join("；")}</p><div class="template-save"><input aria-label="${escapeHTML(item.name)}的副本名称" data-copy-name="${item.id}" maxlength="80" placeholder="新模板名称"><button class="button secondary small" data-copy-template="${item.id}">复制</button><button class="button secondary small" data-delete-template="${item.id}">删除</button></div></article>`).join(""):'<p class="hint">暂无模板。在导入预览中选择列后可保存模板。</p>';
}
function renderHistory(data) {
  const history=data.history||[];
  $("#history-compare").hidden=true;
  $("#compare-pages").hidden=true;
  state.comparison=null;state.comparisonRevision++;
  $("#history-compare").textContent="";
  $("#history-list").innerHTML=history.length?history.map((run,index)=>`<div class="history-row"><span>${timeLabel(run.created_at)} · ${run.summary.groups} 组 · ${run.summary.issues} 项差异</span><div class="file-actions"><button class="text-button" data-run="${run.id}">查看历史详情</button>${index?`<button class="text-button" data-compare-from="${run.id}" data-compare-to="${history[index-1].id}">比较到较新版本</button>`:""}</div></div>`).join(""):'<p class="hint">执行核对后可查看历史版本。</p>';
}
async function compareHistory(from,to,page=1) {
  const ownRevision=++state.comparisonRevision;state.comparison={from,to};
  $("#compare-prev").disabled=true;$("#compare-next").disabled=true;
  const batchId=state.batch.batch.id, revision=state.pageRevision;
  const result=await api(`/api/batches/${batchId}/compare-page?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&page=${page}&page_size=50`);
  if(revision!==state.pageRevision||ownRevision!==state.comparisonRevision)return;
  state.comparisonPage=result.page;state.comparisonPages=result.total_pages;
  $("#compare-pages").hidden=false;$("#compare-page-label").textContent=`第 ${result.page} / ${result.total_pages} 页，共 ${result.total} 项变化`;
  $("#compare-prev").disabled=result.page<=1;$("#compare-next").disabled=result.page>=result.total_pages;
  $("#history-compare").hidden=false;
  const added=result.items.filter((row)=>row.kind==="added").map((row)=>row.after),removed=result.items.filter((row)=>row.kind==="removed").map((row)=>row.before),changed=result.items.filter((row)=>row.kind==="changed");
  const describe=(row)=>`${escapeHTML(row.order_id)} / ${escapeHTML(row.channel)} · 预计 ${row.expected} · 实际 ${row.actual} · 差额 ${row.difference} · ${row.reason_labels.map(escapeHTML).join("、")}`;
  const fields={expected:"预计金额",actual:"账单金额",difference:"差额",reasons:"异常类型",source_evidence_sha256:"源证据",review_snapshot:"处理快照"};
  $("#history-compare").innerHTML=`<h3>新增 ${result.counts.added} 项 · 消失 ${result.counts.removed} 项 · 变化 ${result.counts.changed} 项</h3>${added.map((row)=>`<p class="history-change">新增：${describe(row)}</p>`).join("")}${removed.map((row)=>`<p class="history-change">消失：${describe(row)}</p>`).join("")}${changed.map((item)=>`<div class="history-change"><strong>变化：${item.changed_fields.map((field)=>fields[field]||field).join("、")}</strong><p>之前：${describe(item.before)}</p><p>之后：${describe(item.after)}</p></div>`).join("")}`;
}
async function viewHistory(runId,page=1){
  if(!state.batch||state.busy)return;
  const batchId=state.batch.batch.id,revision=state.pageRevision,ownRevision=++state.historyRevision;
  state.historyRun=runId;
  if(!$("#history-dialog").open)$("#history-dialog").showModal();
  $("#history-rows").innerHTML="";$("#history-page-label").textContent="正在加载…";
  $("#history-prev").disabled=true;$("#history-next").disabled=true;
  const detail=await api(`/api/batches/${batchId}/runs/${encodeURIComponent(runId)}/results?page=${page}&page_size=50`);
  if(revision!==state.pageRevision||ownRevision!==state.historyRevision||!$("#history-dialog").open)return;
  state.historyPage=detail.page;state.historyPages=detail.total_pages;
  $("#history-title").textContent=`${timeLabel(detail.created_at)} · ${detail.total} 个订单分组`;
  $("#history-page-label").textContent=`第 ${detail.page} / ${detail.total_pages} 页 · 当前 ${detail.items.length} 项`;
  $("#history-prev").disabled=detail.page<=1;$("#history-next").disabled=detail.page>=detail.total_pages;
  $("#history-rows").innerHTML=detail.items.map((row)=>`<tr><td>${escapeHTML(row.order_id)}<br>${escapeHTML(row.channel)}</td><td>${row.expected} / ${row.actual} / ${row.difference}</td><td>${row.reason_labels.map(escapeHTML).join("、")}</td><td>${row.reasons.length===1&&row.reasons[0]==="matched"?"无需处理":reviewLabels[row.review_status]||"未记录"}<br>${escapeHTML(row.note)}</td><td><button class="text-button" data-history-case="${row.case_key}">查看 ${row.source_count} 条源行</button></td></tr>`).join("");
}
function showHome() {
  if (state.busy) return;
  state.pageRevision++;
  reviewView.invalidate();
  state.batch = null;
  $("#home-view").hidden = false; $("#detail-view").hidden = true;
  $("#breadcrumb").textContent = "核查批次";
  refreshList().catch((error) => notify(error.message, true));
}
async function openBatch(id, reset = true) {
  const revision=++state.pageRevision;
  reviewView.invalidate();
  const response=await api(`/api/batches/${id}/overview`);
  if (revision!==state.pageRevision) return;
  state.batch=response;
  if (reset) { state.filter = "issues"; $("#search").value = ""; $("#reason-filter").value="all"; $("#status-filter").value="outstanding"; }
  const data = state.batch;
  $("#home-view").hidden = true; $("#detail-view").hidden = false;
  $("#breadcrumb").textContent = data.batch.name;
  $("#batch-title").textContent = data.batch.name;
  $("#batch-description").textContent = data.batch.description || "业务单与支付流水独立核对";
  $("#sample-notice").hidden = !data.batch.is_sample;
  $("#archived-notice").hidden=!data.batch.archived;
  $("#reconcile").hidden=!!data.batch.archived;
  $("#queue-reconcile").hidden=!!data.batch.archived;
  $$(".import-trigger").forEach((button)=>button.hidden=!!data.batch.archived);
  $("#stale-notice").hidden = !data.stale;
  $("#legacy-currency-notice").hidden = !data.imports.some((item) => item.is_active && item.currency_policy === "legacy_unverified");
  for (const [side, target] of [["orders", "#order-files"], ["payments", "#payment-files"]]) {
    const files = data.imports.filter((item) => item.side === side && item.is_active);
    $(target).innerHTML = files.length ? files.map((item) => `<div class="source-file"><div class="file-entry" title="${escapeHTML(item.file_sha256)}">✓ ${escapeHTML(item.filename)} · ${item.row_count} 行</div><div class="file-actions" ${data.batch.archived?"hidden":""}><button class="text-button" data-replace="${item.id}" aria-label="替换 ${escapeHTML(item.filename)}">替换文件</button><button class="text-button" data-revoke="${item.id}" aria-label="撤销 ${escapeHTML(item.filename)}">撤销</button></div></div>`).join("") : "尚未导入有效文件";
  }
  const inactive=data.imports.filter((item)=>!item.is_active);
  $("#inactive-imports").hidden=!inactive.length;
  $("#inactive-files").innerHTML=inactive.map((item)=>`<div class="audit-item"><time>${timeLabel(item.revoked_at)}</time><span>${escapeHTML(item.filename)} · ${item.row_count} 行 · ${data.imports.some((next)=>next.replaces_id===item.id)?"已替换":"已撤销"}<br>原因：${escapeHTML(item.revoked_reason)}</span></div>`).join("");
  const s = data.run?.summary;
  const metrics = s ? [["预计净到账", s.expected_total, "业务单合计，含待核查重复行", true], ["账单净额", s.actual_total, "收款减退款，含待核查重复行", true], ["金额一致", s.matched, `共 ${s.groups} 个订单分组`, false], ["需核查差异", s.issues, "人工处理不改变金额一致性", false]] : [["预计净到账", "—", "导入两类文件后执行核对", false], ["账单净额", "—", "按渠道与订单号匹配", false], ["金额一致", "—", "等待核对", false], ["需核查差异", "—", "等待核对", false]];
  $("#metrics").innerHTML = metrics.map(([label,value,note,currency], index) => `<div class="metric ${index === 3 ? "alert" : ""}"><label>${label}</label><strong>${currency ? '<span class="currency">¥</span>' : ""}${escapeHTML(value)}</strong><small>${note}</small></div>`).join("");
  $("#run-time").textContent = data.run ? "核对于 " + timeLabel(data.run.created_at) : "等待导入与核对";
  $("#reconcile").textContent = data.run ? "重新核对 ↗" : "执行核对 ↗";
  $("#export-link").hidden = !data.run || data.stale;
  $("#export-link").href = `/api/batches/${id}/export?run_id=${encodeURIComponent(data.run?.id||"")}`;
  renderHistory(data);
  auditView.reset();
  await renderResults();
}
let resultView,reviewView,auditView,batchView,importView,reportView,presetView;
function renderResults(){return resultView.load();}
function startImport(side,replaceId=null){importView.start(side,replaceId);}
function openCase(key,historicalRun=null){return reviewView.openCase(key,historicalRun);}

$("#new-batch").addEventListener("click",()=>{$("#batch-form").reset();$("#new-dialog").showModal();});
$("#batch-form").addEventListener("submit",(event)=>{event.preventDefault();action(event.submitter,async()=>{const form=new FormData(event.target);const result=await api("/api/batches",{name:form.get("name"),description:form.get("description")});$("#new-dialog").close();await refreshList();await openBatch(result.batch_id);notify("批次已创建");});});
$("#create-demo").addEventListener("click",(event)=>action(event.currentTarget,async()=>{const result=await api("/api/demo",{});await refreshList();await openBatch(result.batch_id);notify("合成样例批次已创建");}));
$("#back-home").addEventListener("click",showHome);$("#home-nav").addEventListener("click",showHome);
$("#batch-list").addEventListener("click",(event)=>{if(state.busy)return;const row=event.target.closest("[data-batch]");if(row)openBatch(row.dataset.batch).catch((error)=>notify(error.message,true));});
$("#batch-list").addEventListener("keydown",(event)=>{if(event.key==="Enter"||event.key===" "){const row=event.target.closest("[data-batch]");if(row){event.preventDefault();row.click();}}});
$$(".close-dialog").forEach((button)=>button.addEventListener("click",()=>{if(!state.busy)button.closest("dialog").close();}));
$$("dialog").forEach((dialog)=>dialog.addEventListener("cancel",(event)=>{if(state.busy)event.preventDefault();}));
$$(".import-trigger").forEach((button)=>button.addEventListener("click",()=>startImport(button.dataset.side)));
$("#reconcile").addEventListener("click",(event)=>action(event.currentTarget,async()=>{const result=await api(`/api/batches/${state.batch.batch.id}/reconcile`,{});await openBatch(state.batch.batch.id,false);await refreshList();notify(result.reused?"源数据未变，已显示原核对结果":"核对完成");}));
$$("[data-filter]").forEach((button)=>button.addEventListener("click",()=>{state.filter=button.dataset.filter;$("#reason-filter").value="all";$("#status-filter").value=state.filter==="issues"?"outstanding":"all";renderResults();}));
$("#reason-filter").addEventListener("change",renderResults);
$("#status-filter").addEventListener("change",renderResults);
$("#history-dialog").addEventListener("close",()=>{state.historyRevision++;});
$("#history-rows").addEventListener("click",(event)=>{const button=event.target.closest("[data-history-case]");if(button)openCase(button.dataset.historyCase,state.historyRun).catch((error)=>notify(error.message,true));});
$("#history-prev").addEventListener("click",()=>viewHistory(state.historyRun,state.historyPage-1).catch((error)=>notify(error.message,true)));
$("#history-next").addEventListener("click",()=>viewHistory(state.historyRun,state.historyPage+1).catch((error)=>notify(error.message,true)));
for(const [id,delta] of [["#compare-prev",-1],["#compare-next",1]])$(id).addEventListener("click",()=>{if(state.comparison)compareHistory(state.comparison.from,state.comparison.to,state.comparisonPage+delta).catch((error)=>notify(error.message,true));});
$("#history-list").addEventListener("click",(event)=>{const compare=event.target.closest("[data-compare-from]"),run=event.target.closest("[data-run]");if(compare)compareHistory(compare.dataset.compareFrom,compare.dataset.compareTo).catch((error)=>notify(error.message,true));if(run)viewHistory(run.dataset.run).catch((error)=>notify(error.message,true));});
for (const id of ["#order-files","#payment-files"]) $(id).addEventListener("click",(event)=>{
  if(state.busy)return;
  const replace=event.target.closest("[data-replace]"),revoke=event.target.closest("[data-revoke]");
  if(replace){const file=state.batch.imports.find((item)=>item.id===replace.dataset.replace);startImport(file.side,file.id);}
  if(revoke){const file=state.batch.imports.find((item)=>item.id===revoke.dataset.revoke);state.revokeContext={batchId:state.batch.batch.id,importId:file.id};$("#revoke-form").reset();$("#revoke-errors").hidden=true;$("#revoke-description").textContent=`将撤销 ${file.filename}（${file.row_count} 行）。`;$("#revoke-dialog").showModal();}
});
$("#revoke-form").addEventListener("submit",(event)=>{event.preventDefault();const context={...state.revokeContext},reason=$("#revoke-reason").value;action(event.submitter,async()=>{try{await api(`/api/batches/${context.batchId}/revoke-import`,{import_id:context.importId,reason});$("#revoke-dialog").close();await openBatch(context.batchId,false);await refreshList();notify("文件已撤销，历史记录已保留，请重新核对");}catch(error){$("#revoke-errors").textContent=error.message;$("#revoke-errors").hidden=false;}});});
$("#manage-templates").addEventListener("click",(event)=>action(event.currentTarget,async()=>{await refreshTemplates();renderTemplates();$("#template-errors").hidden=true;$("#templates-dialog").showModal();}));
$("#templates-list").addEventListener("click",(event)=>{const copy=event.target.closest("[data-copy-template]"),remove=event.target.closest("[data-delete-template]");if(!copy&&!remove)return;action(event.target,async()=>{const id=copy?.dataset.copyTemplate||remove.dataset.deleteTemplate;if(copy){const name=$("#templates-list").querySelector(`[data-copy-name="${id}"]`).value;await api("/api/templates/copy",{id,name});}else await api("/api/templates/delete",{id});await refreshTemplates();renderTemplates();notify(copy?"模板副本已创建":"模板已删除，已有导入数据保留");});});
$("#templates-file").addEventListener("change",(event)=>{const file=event.target.files[0];if(!file)return;action(null,async()=>{try{if(file.size>256*1024)throw new Error("模板文件不能超过 256 KiB");let bundle;try{bundle=JSON.parse(await file.text());}catch{throw new Error("模板文件必须是有效 JSON");}await api("/api/templates/import",{bundle});await refreshTemplates();renderTemplates();$("#template-errors").hidden=true;notify("模板文件已导入");}catch(error){$("#template-errors").textContent=error.message;$("#template-errors").hidden=false;}finally{event.target.value="";}});});
importView=LedgerDeskImport.initialize({api,action,notify,escapeHTML,state,fieldLabels,refreshTemplates,onImported:async(batchId)=>{await openBatch(batchId,false);await refreshList();}});
batchView=LedgerDeskBatches.initialize({api,action,notify,escapeHTML,timeLabel,state,onOpen:openBatch,onRefreshList:refreshList});
const evidenceView=LedgerDeskEvidence.initialize({api,notify,escapeHTML});
reviewView=LedgerDeskReviews.initialize({api,action,notify,escapeHTML,reviewLabels,state,evidenceView,onRefresh:async()=>{if(state.batch)await openBatch(state.batch.batch.id,false);}});
auditView=LedgerDeskAudit.initialize({api,notify,escapeHTML,timeLabel,reviewLabels,context:()=>state.batch?{batchId:state.batch.batch.id,revision:state.pageRevision}:null});
resultView=LedgerDeskResults.initialize({api,notify,escapeHTML,reviewLabels,
  context:()=>state.batch?{batch:state.batch,revision:state.pageRevision,group:state.filter,profileId:state.reportProfile}:null,
  onPage:reviewView.page,onInvalidate:reviewView.invalidate,selectionCell:reviewView.selectionCell,isBusy:()=>state.busy,
  onCase:openCase,onRefresh:async()=>{if(state.batch&&!state.busy)await openBatch(state.batch.batch.id,false);}});
LedgerDeskData.initialize({api,action,timeLabel,escapeHTML,notify});
const currentQuery=()=>resultView.query();
LedgerDeskWorkbench.initialize({api,action,notify,escapeHTML,state,query:currentQuery,onOpen:openBatch});
LedgerDeskRules.initialize({api,action,notify,state,onRefresh:async(id)=>{await openBatch(id,false);await refreshList();}});
reportView=LedgerDeskReports.initialize({api,action,notify,escapeHTML,state,onChange:()=>resultView.exports()});
presetView=LedgerDeskPresets.initialize({api,action,notify,state,query:currentQuery,onApply:(p)=>{state.filter=p.group;$("#reason-filter").value=p.reason;$("#status-filter").value=p.status;$("#search").value=p.q;renderResults();}});
LedgerDeskTasks.initialize({api,action,notify,escapeHTML,state,query:currentQuery});
LedgerDeskBackupPolicy.initialize({api,action,notify});

api("/api/bootstrap").then(async(data)=>{state.token=data.token;state.templates=(await api("/api/templates")).templates;$("#app-version").textContent=`v${data.version}`;await refreshList();await Promise.all([reportView.load(),presetView.load()]);}).catch((error)=>notify("本地服务连接失败："+error.message,true));
