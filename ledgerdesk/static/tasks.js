"use strict";
const LedgerDeskTasks={initialize({api,action,notify,escapeHTML,state,query}){
  const $=(s)=>document.querySelector(s);let page=1,pages=1,timer=null,loading=false,revision=0,signature=null;
  const labels={queued:'等待',running:'执行中',succeeded:'完成',failed:'失败',cancelled:'已取消',interrupted:'已中断'};
  async function load(){
    if(loading)return;loading=true;const own=++revision;
    try{const data=await api(`/api/jobs?page=${page}&page_size=25&state=${$('#tasks-state').value}`);if(own!==revision)return;page=data.page;pages=data.total_pages;
      const snapshot=JSON.stringify(data);
      if(snapshot!==signature)$('#tasks-list').innerHTML=data.items.map((j)=>`<article class="task-card"><strong>${{reconcile:'核对',report:'报告',backup:'备份'}[j.kind]} · ${labels[j.state]}</strong><p>${escapeHTML(j.phase)} · 尝试 ${j.attempt} · ${j.progress}/${j.total}</p><p class="hint">${escapeHTML(j.id)}${j.error?' · '+escapeHTML(j.error):''}</p><div class="file-actions">${['queued','running'].includes(j.state)?`<button class="text-button" data-task-cancel="${j.id}">取消任务</button>`:''}${['failed','cancelled','interrupted'].includes(j.state)?`<button class="text-button" data-task-retry="${j.id}">重试任务</button>`:''}${j.kind==='report'&&j.state==='succeeded'?`<a href="/api/jobs/${j.id}/download" download>下载报告</a><a href="/api/jobs/${j.id}/manifest" download>报告说明</a>`:''}</div></article>`).join('')||'<p>当前没有任务</p>';
      signature=snapshot;
      $('#tasks-page').textContent=`第 ${page} / ${pages} 页 · ${data.total} 项`;$('#tasks-prev').disabled=page<=1;$('#tasks-next').disabled=page>=pages;
    }finally{loading=false;}
  }
  async function open(){page=1;await load();$('#tasks-dialog').showModal();clearInterval(timer);timer=setInterval(()=>{if($('#tasks-dialog').open)load().catch((e)=>notify(e.message,true));},1500);}
  async function submit(kind,batchId=null,payload={}){await api('/api/jobs',{kind,batch_id:batchId,payload,dedupe_key:crypto.randomUUID()});await open();notify('任务已进入本机队列');}
  $('#open-tasks').addEventListener('click',()=>action(null,open));$('#tasks-refresh').addEventListener('click',()=>load().catch((e)=>notify(e.message,true)));
  $('#tasks-state').addEventListener('change',()=>{revision++;page=1;load().catch((e)=>notify(e.message,true));});
  $('#tasks-dialog').addEventListener('close',()=>{clearInterval(timer);revision++;});
  $('#queue-reconcile').addEventListener('click',(e)=>action(e.currentTarget,()=>submit('reconcile',state.batch.batch.id)));
  $('#queue-backup').addEventListener('click',(e)=>action(e.currentTarget,()=>submit('backup')));
  $('#queue-report').addEventListener('click',(e)=>action(e.currentTarget,()=>{if(!state.batch?.run)throw new Error('请先执行核对');const params=query(),filters=Object.fromEntries(['group','reason','status','q'].map((key)=>[key,params.get(key)|| (key==='q'?'':'all')]));return submit('report',state.batch.batch.id,{run_id:state.batch.run.id,profile_id:state.reportProfile||null,format:'csv',filters});}));
  $('#tasks-list').addEventListener('click',(event)=>{const cancel=event.target.closest('[data-task-cancel]'),retry=event.target.closest('[data-task-retry]');if(!cancel&&!retry)return;action(event.target,async()=>{const key=cancel?.dataset.taskCancel||retry.dataset.taskRetry;await api(`/api/jobs/${key}/${cancel?'cancel':'retry'}`,{});await load();});});
  for(const [id,delta] of [['#tasks-prev',-1],['#tasks-next',1]])$(id).addEventListener('click',()=>{page+=delta;load().catch((e)=>notify(e.message,true));});
  $('#open-batch-queue').addEventListener('click',(event)=>action(event.currentTarget,async()=>{state.batches=(await api('/api/batches')).batches;$('#queue-batches').replaceChildren();for(const batch of state.batches.filter((b)=>!b.archived)){const label=document.createElement('label');label.className='queue-option';const box=document.createElement('input');box.type='checkbox';box.value=batch.id;label.append(box,document.createTextNode(batch.name));$('#queue-batches').append(label);}$('#batch-queue-dialog').showModal();}));
  $('#submit-batch-queue').addEventListener('click',(event)=>action(event.currentTarget,async()=>{const batch_ids=[...document.querySelectorAll('#queue-batches input:checked')].map((box)=>box.value);const result=await api('/api/jobs/queue',{batch_ids,request_id:crypto.randomUUID()});$('#batch-queue-dialog').close();$('#workspace-dialog').close();await open();notify(`已排队 ${result.count} 个批次`);}));
  return {open};
}};
