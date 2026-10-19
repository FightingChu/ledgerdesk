"use strict";
const LedgerDeskEvidence={initialize({api,notify,escapeHTML}){
  const $=(s)=>document.querySelector(s);let context=null,revision=0,sourcePage=1,duplicatePage=1;
  function url(kind,page){const c=context,prefix=c.historical?`/api/batches/${c.batchId}/runs/${c.runId}/cases/${c.key}`:`/api/batches/${c.batchId}/cases/${c.key}`;return `${prefix}/evidence?run_id=${encodeURIComponent(c.runId)}&kind=${kind}&page=${page}&page_size=25`;}
  function draw(kind,data){
    const source=kind==='source';if(source)sourcePage=data.page;else duplicatePage=data.page;
    const target=source?'#case-rows':'#duplicate-rows',prefix=source?'source':'duplicate';
    $(target).innerHTML=data.items.map((row)=>source?`<tr><td>${row.side==='orders'?'业务单':'支付账单'}<div class="channel">${escapeHTML(row.filename)}</div></td><td>${row.line}</td><td>${escapeHTML(row.transaction_id||'—')}</td><td>${{expected:'预计净额',sale:'收款',refund:'退款'}[row.kind]}</td><td>${row.amount}</td></tr>`:`<tr><td>${escapeHTML(row.order_id)} / ${escapeHTML(row.channel)}</td><td>${escapeHTML(row.filename)} · ${row.line}</td><td>${escapeHTML(row.transaction_id)}</td><td>${row.kind==='refund'?'退款':'收款'}</td><td>${row.amount}</td></tr>`).join('');
    $(`#${prefix}-page-label`).textContent=`第 ${data.page} / ${data.total_pages} 页 · 共 ${data.total} 条`;$(`#${prefix}-prev`).disabled=data.page<=1;$(`#${prefix}-next`).disabled=data.page>=data.total_pages;
    if(!source)$('#duplicate-evidence').hidden=!data.total;
  }
  async function page(kind,value){const own=revision,data=await api(url(kind,value));if(own===revision)draw(kind,data);}
  for(const [id,kind,delta] of [['#source-prev','source',-1],['#source-next','source',1],['#duplicate-prev','duplicate',-1],['#duplicate-next','duplicate',1]])$(id).addEventListener('click',()=>{if(context)page(kind,(kind==='source'?sourcePage:duplicatePage)+delta).catch((e)=>notify(e.message,true));});
  $('#case-dialog').addEventListener('close',()=>{revision++;context=null;});
  async function open(value){context=value;revision++;await Promise.all([page('source',1),page('duplicate',1)]);}
  return {open};
}};
