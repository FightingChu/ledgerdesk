"use strict";
const LedgerDeskPresets={initialize({api,action,notify,state,query,onApply}){
  const $=(s)=>document.querySelector(s);let presets=[];
  async function load(){const data=await api('/api/filters');presets=data.filters;const value=$('#saved-filter-select').value;$('#saved-filter-select').replaceChildren(new Option('当前条件',''));for(const p of presets)$('#saved-filter-select').add(new Option(p.name,p.id));$('#saved-filter-select').value=value;}
  $('#saved-filter-select').addEventListener('change',()=>{const p=presets.find((p)=>p.id===$('#saved-filter-select').value);if(!p)return;$('#saved-filter-name').value=p.name;onApply(p.payload);});
  $('#save-filter').addEventListener('click',(event)=>action(event.currentTarget,async()=>{const name=$('#saved-filter-name').value.trim(),old=presets.find((p)=>p.name===name),params=query();const payload=Object.fromEntries(['group','reason','status','q'].map((key)=>[key,params.get(key)|| (key==='q'?'':'all')]));await api('/api/filters',{name,payload,expected_revision:old?.revision||0});await load();notify('常用筛选已保存');}));
  $('#delete-filter').addEventListener('click',(event)=>action(event.currentTarget,async()=>{const p=presets.find((p)=>p.id===$('#saved-filter-select').value);if(!p)throw new Error('请先选择已保存筛选');await api('/api/filters/delete',{id:p.id,revision:p.revision});await load();$('#saved-filter-name').value='';notify('常用筛选已删除');}));
  return {load};
}};
