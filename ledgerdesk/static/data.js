"use strict";
// Data management owns its dialog state; the main page supplies session-aware requests.
const LedgerDeskData = {
  initialize({api, action, timeLabel, escapeHTML, notify}) {
    const find=(selector)=>document.querySelector(selector);
    let selectedBackup=null;
    const statusLabel={ok:"校验通过",missing:"数据库不存在",invalid:"数据库无效或损坏",unsupported:"版本不受支持"};
    const sizeLabel=(bytes)=>`${(bytes/1024).toFixed(1)} KiB`;
    function reportText(report){
      const counts=report.counts||{};
      return `${statusLabel[report.status]||report.status} · schema ${report.schema_version??"未知"} · 完整性 ${report.integrity||"未检查"} · 批次 ${counts.batches??"—"} · 源行 ${counts.entries??"—"} · 历史核对 ${counts.runs??"—"} · 处理记录 ${counts.reviews??"—"}`;
    }
    function showError(error){find("#data-errors").textContent=error.message;find("#data-errors").hidden=false;}
    async function refreshBackups(){
      const data=await api("/api/data");
      find("#data-location").textContent=`手动备份目录：${data.backup_directory}；恢复目录：${data.restore_directory}`;
      find("#backups-list").innerHTML=data.backups.length?data.backups.map((backup)=>`<article class="backup-card"><h3>${timeLabel(backup.created_at)} · ${sizeLabel(backup.bytes)}</h3><p class="hint">${escapeHTML(backup.id)}</p><div class="file-actions"><button class="button secondary small" data-verify-backup="${escapeHTML(backup.id)}">校验备份</button><button class="button secondary small" data-restore-backup="${escapeHTML(backup.id)}">恢复到新目录</button></div></article>`).join(""):'<p class="hint">暂无手动备份。可先创建一份经过完整性校验的备份。</p>';
    }
    find("#manage-data").addEventListener("click",(event)=>action(event.currentTarget,async()=>{
      selectedBackup=null;
      for(const id of ["#data-errors","#restore-panel","#restore-result","#database-report","#backup-report"])find(id).hidden=true;
      await refreshBackups();find("#data-dialog").showModal();
    }));
    find("#create-backup").addEventListener("click",(event)=>action(event.currentTarget,async()=>{
      find("#data-errors").hidden=true;
      try{
        const result=await api("/api/data/backup",{});
        await refreshBackups();
        find("#backup-report").textContent=`备份已创建并校验：${result.id} · 批次 ${result.batches} · 源行 ${result.entries} · SHA-256 ${result.sha256}`;
        find("#backup-report").hidden=false;notify("备份已创建并通过校验");
      }catch(error){showError(error);}
    }));
    find("#check-database").addEventListener("click",(event)=>action(event.currentTarget,async()=>{
      find("#data-errors").hidden=true;
      try{const report=await api("/api/data/diagnostics");find("#database-report").textContent=reportText(report);find("#database-report").hidden=false;}
      catch(error){showError(error);}
    }));
    find("#backups-list").addEventListener("click",(event)=>{
      const verify=event.target.closest("[data-verify-backup]"),restore=event.target.closest("[data-restore-backup]");
      if(!verify&&!restore)return;
      const id=verify?.dataset.verifyBackup||restore.dataset.restoreBackup;
      action(verify||restore,async()=>{
        find("#data-errors").hidden=true;
        try{
          const report=await api("/api/data/verify",{id});
          find("#backup-report").textContent=`${reportText(report)} · SHA-256 ${report.sha256}`;
          find("#backup-report").hidden=false;
          if(restore){
            if(report.status!=="ok")throw new Error("备份未通过校验，不能恢复。请使用其他备份。");
            selectedBackup=id;find("#restore-source").textContent=`将恢复：${id}`;
            find("#restore-name").value="restore-"+new Date().toISOString().replace(/[-:]/g,"").slice(0,15).replace("T","-");
            find("#restore-panel").hidden=false;find("#restore-result").hidden=true;
          }
        }catch(error){showError(error);}
      });
    });
    find("#confirm-restore").addEventListener("click",(event)=>{
      const id=selectedBackup,name=find("#restore-name").value.trim();
      if(!id)return;
      if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(name)){notify("请填写有效的新目录名称",true);return;}
      action(event.currentTarget,async()=>{
        find("#data-errors").hidden=true;
        try{
          const result=await api("/api/data/restore",{id,workspace_name:name});
          const currentPort=Number(location.port||80),port=currentPort<65535?currentPort+1:8766;
          const directory="'"+result.data_dir.replaceAll("'","''")+"'";
          find("#restore-command").textContent=`python -m ledgerdesk --data-dir ${directory} --port ${port} --open`;
          find("#restore-result").hidden=false;find("#restore-panel").hidden=true;selectedBackup=null;
          notify("已恢复到新的数据目录，原工作空间保留");
        }catch(error){showError(error);}
      });
    });
  }
};
