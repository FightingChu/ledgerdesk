"use strict";
const LedgerDeskReports={initialize({api,action,notify,escapeHTML,state,onChange}){
  const $=(s)=>document.querySelector(s);let profiles=[],labels={},order=[],selected=new Set();
  function draw(){
    $('#report-columns').innerHTML=order.map((key,index)=>`<div class="report-column"><label><input type="checkbox" data-report-column="${key}" ${selected.has(key)?'checked':''}> ${escapeHTML(labels[key])}</label><button type="button" class="text-button" data-move-column="${key}" data-delta="-1" ${index===0?'disabled':''} aria-label="上移 ${escapeHTML(labels[key])}">↑</button><button type="button" class="text-button" data-move-column="${key}" data-delta="1" ${index===order.length-1?'disabled':''} aria-label="下移 ${escapeHTML(labels[key])}">↓</button></div>`).join('');
  }
  async function load(){
    const data=await api('/api/report-profiles');profiles=data.profiles;labels=data.columns;
    for(const id of ['#report-profile-filter','#report-profile-select']){const value=$(id).value;$(id).replaceChildren(new Option('默认报告',''));for(const p of profiles)$(id).add(new Option(`${p.name} · 修订 ${p.revision}`,p.id));$(id).value=value;}
  }
  function selectEditor(){
    const profile=profiles.find((p)=>p.id===$('#report-profile-select').value);
    order=profile?[...profile.columns,...Object.keys(labels).filter((key)=>!profile.columns.includes(key))]:Object.keys(labels);
    selected=new Set(profile?.columns||Object.keys(labels).slice(0,12));$('#report-profile-name').value=profile?.name||'';draw();
  }
  $('#manage-report-profiles').addEventListener('click',()=>action(null,async()=>{await load();selectEditor();$('#report-profiles-dialog').showModal();}));
  $('#report-profile-select').addEventListener('change',selectEditor);
  $('#report-columns').addEventListener('change',(event)=>{const key=event.target.dataset.reportColumn;if(key){if(event.target.checked)selected.add(key);else selected.delete(key);}});
  $('#report-columns').addEventListener('click',(event)=>{const button=event.target.closest('[data-move-column]');if(!button)return;const index=order.indexOf(button.dataset.moveColumn),next=index+Number(button.dataset.delta);if(next>=0&&next<order.length){[order[index],order[next]]=[order[next],order[index]];draw();}});
  $('#save-report-profile').addEventListener('click',(event)=>action(event.currentTarget,async()=>{
    const profile=await api('/api/report-profiles',{name:$('#report-profile-name').value,columns:order.filter((key)=>selected.has(key))});
    await load();$('#report-profile-filter').value=profile.id;state.reportProfile=profile.id;onChange();$('#report-profiles-dialog').close();notify('报告修订已保存');
  }));
  $('#report-profile-filter').addEventListener('change',()=>{state.reportProfile=$('#report-profile-filter').value||null;onChange();});
  return {load};
}};
