"use strict";
// This controller owns only the current page. Source evidence is requested by the case dialog.
const LedgerDeskResults={
  initialize({api,notify,escapeHTML,reviewLabels,context,onCase,onRefresh}){
    const find=(selector)=>document.querySelector(selector);
    let page=1,pageSize=50,pages=1,requestRevision=0,searchTimer;
    function query(){
      const current=context();
      const params=new URLSearchParams({group:current?.group||"issues",reason:find("#reason-filter").value,
        status:find("#status-filter").value,q:find("#search").value.trim()});
      if(current?.batch.run)params.set("run_id",current.batch.run.id);
      return params;
    }
    function exports(){
      const current=context();if(!current)return;
      const visible=!!current.batch.run&&!current.batch.stale;
      find("#export-link").hidden=!visible;find("#export-filter-link").hidden=!visible;
      find("#export-link").href=`/api/batches/${current.batch.batch.id}/export?run_id=${encodeURIComponent(current.batch.run?.id||"")}`;
      find("#export-filter-link").href=`/api/batches/${current.batch.batch.id}/export?${query()}`;
    }
    function draw(data){
      page=data.page;pages=data.total_pages;
      find("#results-count").textContent=data.total;
      find("#results-page-label").textContent=`第 ${page} / ${pages} 页 · 共 ${data.total} 项 · 当前 ${data.items.length} 项`;
      find("#results-prev").disabled=page<=1;find("#results-next").disabled=page>=pages;
      document.querySelectorAll("[data-filter]").forEach((button)=>button.classList.toggle("selected",button.dataset.filter===context()?.group));
      find("#results-list").innerHTML=data.items.map((row)=>{
        const matched=row.reasons.length===1&&row.reasons[0]==="matched";
        return `<tr><td><div class="order-id">${escapeHTML(row.order_id)}</div><div class="channel">${escapeHTML(row.channel)}</div></td><td class="number">${row.expected}</td><td class="number">${row.actual}</td><td class="number ${row.difference!=="0.00"?"amount-diff":""}">${row.difference}</td><td><div class="reason-list">${row.reason_labels.map((label)=>`<span class="badge ${matched?"success":"danger"}">${escapeHTML(label)}</span>`).join("")}</div></td><td><span class="badge ${row.review_status==="resolved"?"success":"neutral"}">${matched?"无需处理":reviewLabels[row.review_status]||"未记录"}</span></td><td><button class="text-button" data-case="${row.case_key}">查看 ↗</button></td></tr>`;
      }).join("");
      find("#empty-results").hidden=!!data.items.length;
      find("#empty-results").innerHTML=context()?.batch.run?'<h3>当前筛选下没有记录</h3><p>尝试切换筛选或清除搜索条件。</p>':'<span class="empty-icon">⇄</span><h3>准备好两份文件，就可以开始</h3><p>导入业务单和支付账单，确认映射后点击“执行核对”。</p>';
    }
    async function load(reset=true){
      clearTimeout(searchTimer);
      const current=context();if(!current)return;
      if(reset!==false)page=1;
      const ownRevision=++requestRevision,params=query();
      params.set("page",page);params.set("page_size",pageSize);
      exports();find("#results-page-label").textContent="正在加载…";
      find("#results-prev").disabled=true;find("#results-next").disabled=true;
      try{
        const data=await api(`/api/batches/${current.batch.batch.id}/results?${params}`);
        const active=context();
        if(ownRevision!==requestRevision||!active||active.revision!==current.revision)return;
        active.batch.stale=data.stale;find("#stale-notice").hidden=!data.stale;
        draw(data);exports();
      }catch(error){
        const active=context();if(ownRevision!==requestRevision||!active||active.revision!==current.revision)return;
        find("#results-list").innerHTML="";find("#results-count").textContent="—";
        find("#results-page-label").textContent="无法加载当前页，请刷新结果";
        find("#export-link").hidden=true;find("#export-filter-link").hidden=true;
        notify(error.message,true);
      }
    }
    find("#results-prev").addEventListener("click",()=>{if(page>1){page--;load(false);}});
    find("#results-next").addEventListener("click",()=>{if(page<pages){page++;load(false);}});
    find("#results-page-size").addEventListener("change",()=>{pageSize=Number(find("#results-page-size").value);load();});
    find("#refresh-results").addEventListener("click",()=>onRefresh().catch((error)=>notify(error.message,true)));
    find("#search").addEventListener("input",()=>{requestRevision++;clearTimeout(searchTimer);exports();searchTimer=setTimeout(()=>load(),200);});
    find("#results-list").addEventListener("click",(event)=>{const button=event.target.closest("[data-case]");if(button)onCase(button.dataset.case).catch((error)=>notify(error.message,true));});
    return {load};
  }
};
