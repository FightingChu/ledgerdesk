"use strict";
const LedgerDeskRules={initialize({api,action,notify,state,onRefresh}){
  const $=(s)=>document.querySelector(s);let rules=[];
  async function load(){
    const [list,current]=await Promise.all([api('/api/rules'),api(`/api/batches/${state.batch.batch.id}/rule`)]);rules=list.rules;
    const select=$('#rule-select');select.replaceChildren(new Option('默认精确核对',''));
    for(const rule of rules)select.add(new Option(`${rule.name} · 修订 ${rule.revision} · 容差 ${rule.tolerance_cents} 分`,rule.id));
    select.value=current.id||'';$('#apply-rule').disabled=!!state.batch.batch.archived;
  }
  $('#open-rules').addEventListener('click',()=>action(null,async()=>{if(!state.batch)return;await load();$('#rules-dialog').showModal();}));
  $('#rule-create-form').addEventListener('submit',(event)=>{event.preventDefault();action(event.submitter,async()=>{
    const created=await api('/api/rules',{name:$('#rule-name').value,tolerance_cents:Number($('#rule-tolerance').value)});
    await load();$('#rule-select').value=created.id;notify('规则修订已创建，请明确应用到批次');
  });});
  $('#apply-rule').addEventListener('click',(event)=>action(event.currentTarget,async()=>{
    const id=state.batch.batch.id;await api(`/api/batches/${id}/rule`,{rule_id:$('#rule-select').value||null});
    $('#rules-dialog').close();await onRefresh(id);notify('规则已选择，请重新核对');
  }));
}};
