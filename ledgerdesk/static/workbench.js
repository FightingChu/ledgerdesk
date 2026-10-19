"use strict";
const LedgerDeskWorkbench={initialize({api,action,notify,escapeHTML,state,query,onOpen}){
  const $=(s)=>document.querySelector(s);let workspacePage=1,workspacePages=1,channelPage=1,channelPages=1;
  async function workspace(){
    const data=await api(`/api/workspace?page=${workspacePage}&page_size=25`);workspacePage=data.page;workspacePages=data.total_pages;
    $('#workspace-list').innerHTML=data.items.map((b)=>`<article class="workspace-card"><button class="text-button" data-workspace-batch="${b.batch_id}">${escapeHTML(b.name)}</button><p>${b.summary?`${b.summary.groups} 组 · ${b.summary.issues} 项差异 · 预计 ${b.summary.expected_total} · 实际 ${b.summary.actual_total}`:'尚未核对'}${b.stale?' · 等待重新核对':''}</p></article>`).join('')||'<p>暂无进行中批次</p>';
    $('#workspace-page').textContent=`第 ${data.page} / ${data.total_pages} 页 · ${data.total} 个批次`;
    $('#workspace-prev').disabled=data.page<=1;$('#workspace-next').disabled=data.page>=data.total_pages;
  }
  async function channels(){
    if(!state.batch?.run)throw new Error('请先执行核对');
    const params=query();params.set('page',channelPage);params.set('page_size',25);
    const data=await api(`/api/batches/${state.batch.batch.id}/statistics?${params}`);channelPage=data.channels.page;channelPages=data.channels.total_pages;
    const t=data.totals;$('#statistics-totals').textContent=`${t.groups} 组 · ${t.matched} 金额一致 · ${t.issues} 差异 · 预计 ${t.expected} · 实际 ${t.actual} · 差额 ${t.difference}${data.stale?'（输入已过期）':''}`;
    $('#channel-statistics').innerHTML=data.channels.items.map((row)=>`<article class="channel-card"><strong>${escapeHTML(row.channel)}</strong><p>${row.groups} 组 · ${row.issues} 差异 · 预计 ${row.expected} · 实际 ${row.actual} · 差额 ${row.difference}</p><meter min="0" max="${Math.max(1,row.groups)}" value="${row.issues}" aria-label="差异数占订单分组">${row.issues}</meter></article>`).join('')||'<p>当前筛选没有记录</p>';
    $('#statistics-page').textContent=`第 ${data.channels.page} / ${data.channels.total_pages} 页 · ${data.channels.total} 渠道`;
    $('#statistics-prev').disabled=channelPage<=1;$('#statistics-next').disabled=channelPage>=channelPages;
  }
  $('#open-workbench').addEventListener('click',()=>action(null,async()=>{workspacePage=1;await workspace();$('#workspace-dialog').showModal();}));
  $('#workspace-list').addEventListener('click',(event)=>{const button=event.target.closest('[data-workspace-batch]');if(button)action(button,async()=>{$('#workspace-dialog').close();await onOpen(button.dataset.workspaceBatch);});});
  $('#open-statistics').addEventListener('click',()=>action(null,async()=>{channelPage=1;await channels();$('#statistics-dialog').showModal();}));
  for(const [selector,delta,type] of [['#workspace-prev',-1,'workspace'],['#workspace-next',1,'workspace'],['#statistics-prev',-1,'channels'],['#statistics-next',1,'channels']])$(selector).addEventListener('click',(event)=>action(event.currentTarget,async()=>{if(type==='workspace'){workspacePage+=delta;await workspace();}else{channelPage+=delta;await channels();}}));
}};
