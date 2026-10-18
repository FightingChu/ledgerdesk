"use strict";
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = { token: "", batches: [], templates: [], batch: null, filter: "issues", importSide: "orders", upload: null, currentCase: null, busy: false, importContext: null, revokeContext: null, previewRevision: 0, pageRevision: 0 };
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
  if (!response.ok) { const error = new Error(result.error || "操作失败"); error.errors = result.errors || []; throw error; }
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
  $("#batch-count").textContent = state.batches.length;
  $("#list-count").textContent = state.batches.length;
  $("#empty-batches").hidden = !!state.batches.length;
  $("#batch-list").innerHTML = state.batches.map((batch) => `<tr data-batch="${batch.id}" tabindex="0" role="button" aria-label="打开 ${escapeHTML(batch.name)}"><td><div class="batch-name">${escapeHTML(batch.name)}</div><div class="batch-sub">${escapeHTML(batch.description || "独立核查批次")}</div></td><td><span class="badge ${batch.is_sample ? "" : "neutral"}">${batch.is_sample ? "合成样例" : "用户导入"}</span></td><td>${batch.file_count} 份文件</td><td>${timeLabel(batch.created_at)}</td><td>↗</td></tr>`).join("");
}
function templateOptions(side) {
  return `<option value="">不使用模板</option>` + state.templates.filter((item)=>item.side===side)
    .map((item)=>`<option value="${item.id}">${escapeHTML(item.name)}</option>`).join("");
}
function currentMapping() {
  return Object.fromEntries([...$("#mapping-fields").querySelectorAll("select")].map((select)=>[select.name,select.value]));
}
function parseAliases() {
  const raw=$("#channel-aliases").value.trim();
  if (!raw) return {};
  let aliases;
  try { aliases=JSON.parse(raw); } catch { throw new Error("渠道别名必须是有效 JSON 对象"); }
  if (!aliases || Array.isArray(aliases) || typeof aliases!=="object") throw new Error("渠道别名必须是 JSON 对象");
  return aliases;
}
function renderHistory(data) {
  const history=data.history||[];
  $("#history-list").innerHTML=history.length<2 ? '<p class="hint">至少完成两次核对后才能比较。</p>' : history.slice(1).map((run,index)=>`<div class="history-row"><span>${timeLabel(run.created_at)} · ${escapeHTML(run.summary)}</span><button class="text-button" data-compare-from="${run.id}" data-compare-to="${history[index].id}">比较到较新版本</button></div>`).join("");
}
async function compareHistory(from,to) {
  const result=await api(`/api/batches/${state.batch.batch.id}/compare?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`);
  $("#history-compare").hidden=false;
  $("#history-compare").innerHTML=`新增 ${result.counts.added} 项 · 消失 ${result.counts.removed} 项 · 变化 ${result.counts.changed} 项`;
}
function showHome() {
  if (state.busy) return;
  state.pageRevision++;
  state.batch = null;
  $("#home-view").hidden = false; $("#detail-view").hidden = true;
  $("#breadcrumb").textContent = "核查批次";
  refreshList().catch((error) => notify(error.message, true));
}
async function openBatch(id, reset = true) {
  const revision=++state.pageRevision;
  const response=await api(`/api/batches/${id}`);
  if (revision!==state.pageRevision) return;
  state.batch=response;
  if (reset) { state.filter = "issues"; $("#search").value = ""; $("#reason-filter").value="all"; $("#status-filter").value="outstanding"; }
  const data = state.batch;
  $("#home-view").hidden = true; $("#detail-view").hidden = false;
  $("#breadcrumb").textContent = data.batch.name;
  $("#batch-title").textContent = data.batch.name;
  $("#batch-description").textContent = data.batch.description || "业务单与支付流水独立核对";
  $("#sample-notice").hidden = !data.batch.is_sample;
  $("#stale-notice").hidden = !data.stale;
  $("#legacy-currency-notice").hidden = !data.imports.some((item) => item.is_active && item.currency_policy === "legacy_unverified");
  for (const [side, target] of [["orders", "#order-files"], ["payments", "#payment-files"]]) {
    const files = data.imports.filter((item) => item.side === side && item.is_active);
    $(target).innerHTML = files.length ? files.map((item) => `<div class="source-file"><div class="file-entry" title="${escapeHTML(item.file_sha256)}">✓ ${escapeHTML(item.filename)} · ${item.row_count} 行</div><div class="file-actions"><button class="text-button" data-replace="${item.id}" aria-label="替换 ${escapeHTML(item.filename)}">替换文件</button><button class="text-button" data-revoke="${item.id}" aria-label="撤销 ${escapeHTML(item.filename)}">撤销</button></div></div>`).join("") : "尚未导入有效文件";
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
  $("#export-link").href = `/api/batches/${id}/export`;
  renderHistory(data);
  const labels = {create_batch:"创建批次",import_file:"导入文件",reconcile:"执行核对",review:"更新处理记录",revoke_import:"撤销文件",replace_import:"替换文件"};
  $("#audit-list").innerHTML = data.audit.map((item) => { const payload=JSON.parse(item.payload); const description=item.action==="import_file"?`${payload.filename} · ${payload.rows} 行`:item.action==="review"?`${reviewLabels[payload.status]} · ${payload.note}`:item.action==="revoke_import"?`${payload.filename} · ${payload.reason}`:item.action==="replace_import"?`${payload.filename} → ${payload.replacement_filename} · ${payload.reason}`:""; return `<div class="audit-item"><time>${timeLabel(item.created_at)}</time><span>${labels[item.action] || item.action} ${escapeHTML(description)}</span></div>`; }).join("");
  renderResults();
}
function renderResults() {
  if (!state.batch) return;
  const query = $("#search").value.trim().toLowerCase();
  const records = state.batch.results.filter((row) => {
    const matched = row.reasons.length === 1 && row.reasons[0] === "matched";
    const status=$("#status-filter").value, reason=$("#reason-filter").value;
    const statusMatches=status==="all" || (status==="not_required"?matched:!matched&&(status==="outstanding"?row.review_status!=="resolved":row.review_status===status));
    return statusMatches && (reason==="all"||row.reasons.includes(reason)) && (state.filter === "all" || (state.filter === "matched" ? matched : !matched)) && `${row.order_id} ${row.channel}`.toLowerCase().includes(query);
  });
  $$("[data-filter]").forEach((button) => button.classList.toggle("selected", button.dataset.filter === state.filter));
  $("#results-count").textContent = records.length;
  $("#results-list").innerHTML = records.map((row) => {
    const matched = row.reasons.length === 1 && row.reasons[0] === "matched";
    return `<tr><td><div class="order-id">${escapeHTML(row.order_id)}</div><div class="channel">${escapeHTML(row.channel)}</div></td><td class="number">${row.expected}</td><td class="number">${row.actual}</td><td class="number ${row.difference !== "0.00" ? "amount-diff" : ""}">${row.difference}</td><td><div class="reason-list">${row.reason_labels.map((label) => `<span class="badge ${matched ? "success" : "danger"}">${label}</span>`).join("")}</div></td><td><span class="badge ${row.review_status === "resolved" ? "success" : "neutral"}">${matched ? "无需处理" : reviewLabels[row.review_status]}</span></td><td><button class="text-button" data-case="${row.case_key}">查看 ↗</button></td></tr>`;
  }).join("");
  $("#empty-results").hidden = !!records.length;
  $("#empty-results").innerHTML = state.batch.run ? '<h3>当前筛选下没有记录</h3><p>尝试切换筛选或清除搜索条件。</p>' : '<span class="empty-icon">⇄</span><h3>准备好两份文件，就可以开始</h3><p>导入业务单和支付账单，确认映射后点击“执行核对”。</p>';
  const reason=$("#reason-filter").value, status=$("#status-filter").value;
  const params=new URLSearchParams(); if(reason!=="all") params.set("reason",reason); if(status!=="all"&&status!=="outstanding") params.set("status",status);
  $("#export-filter-link").hidden=!state.batch.run||state.batch.stale;
  $("#export-filter-link").href=`/api/batches/${state.batch.batch.id}/export${params.toString()?"?"+params.toString():""}`;
}
function startImport(side, replaceId=null) {
  if (state.busy) return;
  const original=state.batch.imports.find((item)=>item.id===replaceId);
  state.importContext={batchId:state.batch.batch.id,replaceId};
  state.previewRevision++;
  state.importSide=side; state.upload=null;
  $("#import-form").reset(); $("#mapping-area").hidden=true; $("#mapping-warning").hidden=true; $("#import-errors").hidden=true; $("#confirm-import").disabled=true;
  $("#replacement-reason-field").hidden=!replaceId;
  $("#replacement-reason").required=!!replaceId;
  $("#template-select").innerHTML=templateOptions(side);
  $("#channel-aliases").value="";
  $("#template-name").value="";
  $("#confirm-import").textContent=replaceId?"确认替换":"确认导入";
  $("#import-title").textContent=(replaceId?"替换":"导入")+(side==="orders"?"业务单":"支付账单");
  $("#import-help").textContent=side==="orders"?"每个渠道和订单号应有一条业务单。金额填写扣除预计退款后的净到账，不扣手续费。":"每行一笔收款或退款，金额填正数；退款类型使用 refund。流水号在同一渠道内应唯一。";
  if (original) $("#import-help").textContent=`替换 ${original.filename}。校验通过后原子切换有效文件，保留旧文件记录。可选择原 CSV 重新指定字段，替换前自动备份。`;
  $("#template-link").href=`/samples/${side}.csv`;
  $("#import-dialog").showModal();
}
async function previewFile() {
  const previewRevision=++state.previewRevision;
  const file=$("#csv-file").files[0]; state.upload=null; $("#confirm-import").disabled=true; $("#import-errors").hidden=true; $("#mapping-area").hidden=true;
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".csv") || file.size>5*1024*1024) { notify("请选择不超过 5 MiB 的 CSV 文件",true); return; }
  const selectedSide=state.importSide;
  const content=await new Promise((resolve,reject)=>{const reader=new FileReader(); reader.onload=()=>resolve(reader.result.split(",")[1]); reader.onerror=()=>reject(new Error("文件读取失败")); reader.readAsDataURL(file);});
  const preview=await api("/api/preview",{side:selectedSide,content});
  if (previewRevision!==state.previewRevision || !$("#import-dialog").open || $("#csv-file").files[0]!==file || state.importSide!==selectedSide) return;
  state.upload={filename:file.name,content};
  $("#mapping-fields").innerHTML=Object.entries(preview.mapping).map(([field,header])=>`<label class="field">${fieldLabels[field]}<select name="${field}" required><option value="">请选择列</option>${preview.headers.map((name)=>`<option value="${escapeHTML(name)}" ${name===header?"selected":""}>${escapeHTML(name)}</option>`).join("")}</select></label>`).join("");
  const ambiguous=Object.entries(preview.ambiguous_fields);
  $("#mapping-warning").hidden=!ambiguous.length;
  $("#mapping-warning").textContent=ambiguous.map(([field,columns])=>`${fieldLabels[field]}有多个候选列（${columns.join("、")}），请手动选择。`).join(" ");
  const selectedTemplate=state.templates.find((item)=>item.id===$("#template-select").value && item.side===selectedSide);
  if (selectedTemplate) {
    const templateMapping=JSON.parse(selectedTemplate.mapping), templateAliases=JSON.parse(selectedTemplate.channel_aliases||"{}");
    for (const [field,header] of Object.entries(templateMapping)) {
      const select=$("#mapping-fields").querySelector(`select[name="${CSS.escape(field)}"]`);
      if (select) select.value=header;
    }
    $("#channel-aliases").value=JSON.stringify(templateAliases);
  }
  $("#preview-count").textContent=`${preview.row_count} 行数据`;
  $("#preview-head").innerHTML=`<tr>${preview.headers.map((header)=>`<th>${escapeHTML(header)}</th>`).join("")}</tr>`;
  $("#preview-body").innerHTML=preview.rows.map((row)=>`<tr>${preview.headers.map((header)=>`<td>${escapeHTML(row[header])}</td>`).join("")}</tr>`).join("");
  const currency=preview.currency;
  $("#currency-summary").textContent=currency.defaulted ? "未检测到币种列：按工具约定默认人民币 CNY，不做汇兑。" : `币种列：${currency.columns.join("、")}；文件中的值：${currency.values.map((value)=>value||"（空白）").join("、")}${currency.value_count>currency.values.length?"（仅列出前 20 种值）":""}。${currency.valid?"统一按人民币 CNY 核对，不做汇兑。":"含无效币种，禁止导入。"}`;
  $("#currency-summary").classList.toggle("warning",!currency.valid);
  if (!currency.valid) {
    state.upload=null;
    $("#import-errors").textContent=`发现 ${currency.error_count} 行币种错误，整份文件不可导入。\n`+currency.errors.map((item)=>`第 ${item.line} 行：${item.message}`).join("\n");
    $("#import-errors").hidden=false;
  }
  $("#mapping-area").hidden=false; $("#confirm-import").disabled=!currency.valid;
}
function openCase(key) {
  const row=state.batch.results.find((item)=>item.case_key===key); if(!row)return;
  state.currentCase=row;
  $("#case-title").textContent=row.order_id+" / "+row.channel;
  $("#case-summary").innerHTML=`<div class="reason-list">${row.reason_labels.map((label)=>`<span class="badge danger">${label}</span>`).join("")}</div><div class="case-overview"><div><label>预计净到账</label><strong>¥ ${row.expected}</strong></div><div><label>账单净额</label><strong>¥ ${row.actual}</strong></div><div><label>差额</label><strong>¥ ${row.difference}</strong></div></div>`;
  $("#case-rows").innerHTML=row.rows.map((source)=>`<tr><td>${source.side==="orders"?"业务单":"支付账单"}<div class="channel">${escapeHTML(source.filename)}</div></td><td>${source.line}</td><td>${escapeHTML(source.transaction_id||"—")}</td><td>${{expected:"预计净额",sale:"收款",refund:"退款"}[source.kind]}</td><td class="number">${source.amount}</td></tr>`).join("");
  $("#duplicate-evidence").hidden=!row.duplicate_rows?.length;
  $("#duplicate-rows").innerHTML=(row.duplicate_rows||[]).map((source)=>`<tr><td>${escapeHTML(source.order_id)} / ${escapeHTML(source.channel)}</td><td>${escapeHTML(source.filename)} · 第 ${source.line} 行</td><td>${escapeHTML(source.transaction_id)}</td><td>${source.kind==="refund"?"退款":"收款"}</td><td class="number">${source.amount}</td></tr>`).join("");
  const editable=!(row.reasons.length===1&&row.reasons[0]==="matched")&&!state.batch.stale;
  $("#review-controls").hidden=!editable; $("#save-review").hidden=!editable;
  $("#review-status").value=row.review_status; $("#review-note").value=row.note;
  $("#case-dialog").showModal();
}
$("#new-batch").addEventListener("click",()=>{$("#batch-form").reset();$("#new-dialog").showModal();});
$("#batch-form").addEventListener("submit",(event)=>{event.preventDefault();action(event.submitter,async()=>{const form=new FormData(event.target);const result=await api("/api/batches",{name:form.get("name"),description:form.get("description")});$("#new-dialog").close();await refreshList();await openBatch(result.batch_id);notify("批次已创建");});});
$("#create-demo").addEventListener("click",(event)=>action(event.currentTarget,async()=>{const result=await api("/api/demo",{});await refreshList();await openBatch(result.batch_id);notify("合成样例批次已创建");}));
$("#back-home").addEventListener("click",showHome);$("#home-nav").addEventListener("click",showHome);
$("#batch-list").addEventListener("click",(event)=>{const row=event.target.closest("[data-batch]");if(row)openBatch(row.dataset.batch).catch((error)=>notify(error.message,true));});
$("#batch-list").addEventListener("keydown",(event)=>{if(event.key==="Enter"||event.key===" "){const row=event.target.closest("[data-batch]");if(row){event.preventDefault();row.click();}}});
$$(".close-dialog").forEach((button)=>button.addEventListener("click",()=>button.closest("dialog").close()));
$$(".import-trigger").forEach((button)=>button.addEventListener("click",()=>startImport(button.dataset.side)));
$("#csv-file").addEventListener("change",()=>previewFile().catch((error)=>notify(error.message,true)));
$("#import-form").addEventListener("submit",(event)=>{event.preventDefault();if(!state.upload)return;let aliases;try{aliases=parseAliases();}catch(error){notify(error.message,true);return;}const context={...state.importContext};const mapping=currentMapping();const payload={side:state.importSide,...state.upload,mapping,channel_aliases:aliases,replace_id:context.replaceId,reason:$("#replacement-reason").value};action(event.submitter,async()=>{try{const result=await api(`/api/batches/${context.batchId}/import`,payload);$("#import-dialog").close();await openBatch(context.batchId,false);await refreshList();notify(result.duplicate?"有效文件和映射均未变化，本次未重复入库":context.replaceId?"文件已替换，旧记录已保留，请重新核对":`已导入 ${result.row_count} 行，请执行核对`);}catch(error){$("#import-errors").textContent=error.message+(error.errors?.length?"\n"+error.errors.map((item)=>`第 ${item.line} 行：${item.message}`).join("\n"):"");$("#import-errors").hidden=false;}});});
$("#reconcile").addEventListener("click",(event)=>action(event.currentTarget,async()=>{const result=await api(`/api/batches/${state.batch.batch.id}/reconcile`,{});await openBatch(state.batch.batch.id,false);await refreshList();notify(result.reused?"源数据未变，已显示原核对结果":"核对完成");}));
$$("[data-filter]").forEach((button)=>button.addEventListener("click",()=>{state.filter=button.dataset.filter;$("#reason-filter").value="all";$("#status-filter").value=state.filter==="issues"?"outstanding":"all";renderResults();}));
$("#reason-filter").addEventListener("change",renderResults);
$("#status-filter").addEventListener("change",renderResults);
$("#template-select").addEventListener("change",()=>{
  const selected=state.templates.find((item)=>item.id===$("#template-select").value);
  if (!selected || !$("#mapping-area").hidden) {
    if (selected) {
      const mapping=JSON.parse(selected.mapping), aliases=JSON.parse(selected.channel_aliases||"{}");
      for (const [field,header] of Object.entries(mapping)) { const select=$("#mapping-fields").querySelector(`select[name="${CSS.escape(field)}"]`); if(select) select.value=header; }
      $("#channel-aliases").value=JSON.stringify(aliases);
    }
  }
});
$("#save-template").addEventListener("click",async()=>{try{const name=$("#template-name").value.trim();if(!name)throw new Error("请填写模板名称");const result=await api("/api/templates",{name,side:state.importSide,mapping:currentMapping(),channel_aliases:parseAliases()});state.templates=await api("/api/templates").then((data)=>data.templates);$("#template-select").innerHTML=templateOptions(state.importSide);$("#template-select").value=result.id;notify("映射模板已保存");}catch(error){notify(error.message,true);}});
$("#history-list").addEventListener("click",(event)=>{const button=event.target.closest("[data-compare-from]");if(button)compareHistory(button.dataset.compareFrom,button.dataset.compareTo).catch((error)=>notify(error.message,true));});
for (const id of ["#order-files","#payment-files"]) $(id).addEventListener("click",(event)=>{
  if(state.busy)return;
  const replace=event.target.closest("[data-replace]"),revoke=event.target.closest("[data-revoke]");
  if(replace){const file=state.batch.imports.find((item)=>item.id===replace.dataset.replace);startImport(file.side,file.id);}
  if(revoke){const file=state.batch.imports.find((item)=>item.id===revoke.dataset.revoke);state.revokeContext={batchId:state.batch.batch.id,importId:file.id};$("#revoke-form").reset();$("#revoke-errors").hidden=true;$("#revoke-description").textContent=`将撤销 ${file.filename}（${file.row_count} 行）。`;$("#revoke-dialog").showModal();}
});
$("#revoke-form").addEventListener("submit",(event)=>{event.preventDefault();const context={...state.revokeContext},reason=$("#revoke-reason").value;action(event.submitter,async()=>{try{await api(`/api/batches/${context.batchId}/revoke-import`,{import_id:context.importId,reason});$("#revoke-dialog").close();await openBatch(context.batchId,false);await refreshList();notify("文件已撤销，历史记录已保留，请重新核对");}catch(error){$("#revoke-errors").textContent=error.message;$("#revoke-errors").hidden=false;}});});
$("#search").addEventListener("input",renderResults);
$("#results-list").addEventListener("click",(event)=>{const button=event.target.closest("[data-case]");if(button)openCase(button.dataset.case);});
$("#review-form").addEventListener("submit",(event)=>{event.preventDefault();action(event.submitter,async()=>{const row=state.currentCase;await api(`/api/batches/${state.batch.batch.id}/review`,{case_key:row.case_key,evidence_sha256:row.evidence_sha256,status:$("#review-status").value,note:$("#review-note").value});$("#case-dialog").close();await openBatch(state.batch.batch.id,false);notify("处理记录已保存");});});
api("/api/bootstrap").then(async(data)=>{state.token=data.token;state.templates=(await api("/api/templates")).templates;$("#app-version").textContent=`v${data.version}`;await refreshList();}).catch((error)=>notify("本地服务连接失败："+error.message,true));
