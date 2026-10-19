"use strict";
const LedgerDeskBackupPolicy={initialize({api,action,notify}){
  const $=(s)=>document.querySelector(s);let revision=0;
  $('#open-backup-policy').addEventListener('click',()=>action(null,async()=>{const data=await api('/api/backup-policy');revision=data.revision;$('#backup-startup').checked=data.payload.startup;$('#backup-retain').value=data.payload.retain_count;$('#backup-age').value=data.payload.max_age_days;$('#backup-policy-result').hidden=true;$('#backup-policy-dialog').showModal();}));
  $('#backup-policy-form').addEventListener('submit',(event)=>{event.preventDefault();action(event.submitter,async()=>{const data=await api('/api/backup-policy',{expected_revision:revision,payload:{startup:$('#backup-startup').checked,retain_count:Number($('#backup-retain').value),max_age_days:Number($('#backup-age').value)}});revision=data.revision;notify('备份策略已保存');});});
  $('#prune-backups').addEventListener('click',(event)=>action(event.currentTarget,async()=>{const data=await api('/api/backup-policy/prune',{});$('#backup-policy-result').textContent=`已删除 ${data.removed.length} 份，保留 ${data.retained.length} 份，跳过 ${data.skipped.length} 份；未登记文件保留。`;$('#backup-policy-result').hidden=false;}));
}};
