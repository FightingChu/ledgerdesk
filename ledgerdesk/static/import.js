"use strict";
const LedgerDeskImport={
  initialize({api,action,notify,escapeHTML,state,fieldLabels,refreshTemplates,onImported}){
    const $=(selector)=>document.querySelector(selector);
    let step=1,revision=0,context=null,upload=null,preview=null,checked=null,validationInput=null;
    async function work(button,operation){
      await action(button,operation);setStep(step);
      if(checked){$("#validation-prev").disabled=checked.page<=1;$("#validation-next").disabled=checked.page>=checked.total_pages;$("#download-import-errors").disabled=!checked.error_count;}
    }
    function error(message=""){$("#import-errors").textContent=message;$("#import-errors").hidden=!message;}
    function setStep(value){
      step=value;
      document.querySelectorAll("[data-import-step]").forEach((section)=>section.hidden=Number(section.dataset.importStep)!==step);
      document.querySelectorAll("[data-step-label]").forEach((label)=>{if(Number(label.dataset.stepLabel)===step)label.setAttribute("aria-current","step");else label.removeAttribute("aria-current");});
      $("#import-back").hidden=step===1;$("#import-next").hidden=step===4;$("#confirm-import").hidden=step!==4;
      $("#import-next").textContent={1:"下一步：字段映射",2:"检查整份文件",3:"下一步：确认导入"}[step]||"";
      $("#import-next").disabled=step===1?!upload:step===3?!checked?.valid:false;
      $("#confirm-import").disabled=step!==4||!checked?.receipt;
    }
    function invalidate(){revision++;checked=null;validationInput=null;$("#mapping-confirm").checked=false;$("#confirm-import").disabled=true;}
    function mapping(){return Object.fromEntries([...$("#mapping-fields").querySelectorAll("select")].map((select)=>[select.name,select.value]));}
    function aliases(){
      const result=Object.create(null),raw=$("#channel-aliases").value.trim();
      if(!raw)return result;
      for(const line of raw.split(/\r?\n/).filter((line)=>line.trim())){
        const parts=line.split("=");
        if(parts.length!==2||!parts[0].trim()||!parts[1].trim())throw new Error("渠道别名每行填写：原渠道 = 统一渠道");
        const source=parts[0].trim();if(Object.hasOwn(result,source))throw new Error("原渠道不能重复");
        result[source]=parts[1].trim();
      }
      return result;
    }
    function templateOptions(){
      const suggestions=new Set((preview?.template_suggestions||[]).map((item)=>item.id));
      $("#template-select").innerHTML='<option value="">不使用模板</option>'+state.templates.filter((item)=>item.side===context.side).map((item)=>`<option value="${item.id}">${suggestions.has(item.id)?"建议：":""}${escapeHTML(item.name)} · 修订 ${item.revision}</option>`).join("");
      $("#template-suggestions").textContent=suggestions.size?`有 ${suggestions.size} 个模板的全部映射列存在于本文件；选择后请逐项确认。`:"没有完整匹配的模板，可手动选择字段后保存。";
    }
    function applyTemplate(){
      invalidate();
      const template=state.templates.find((item)=>item.id===$("#template-select").value&&item.side===context.side);
      const fields=template?JSON.parse(template.mapping):preview.mapping;
      for(const select of $("#mapping-fields").querySelectorAll("select"))select.value=fields[select.name]||"";
      $("#channel-aliases").value=template?Object.entries(JSON.parse(template.channel_aliases||"{}")).map(([a,b])=>`${a} = ${b}`).join("\n"):"";
      $("#template-name").value=template?.name||"";
    }
    function payload(){
      const fields=mapping();
      if(!upload||Object.values(fields).some((name)=>!name)||new Set(Object.values(fields)).size!==Object.keys(fields).length)throw new Error("请为每个字段选择不同的 CSV 列");
      return {...upload,side:context.side,mapping:fields,channel_aliases:aliases(),replace_id:context.replaceId,
        reason:$("#replacement-reason").value,adapter_id:preview.adapter.id,adapter_version:preview.adapter.version};
    }
    function start(side,replaceId=null){
      if(state.busy||!state.batch||state.batch.batch.archived)return;
      const original=state.batch.imports.find((item)=>item.id===replaceId);
      invalidate();upload=null;preview=null;
      context={batchId:state.batch.batch.id,side,replaceId,originalName:original?.filename};
      $("#import-form").reset();error();$("#file-summary").hidden=true;$("#file-preview").hidden=true;
      $("#replacement-reason-field").hidden=!replaceId;
      $("#import-title").textContent=(replaceId?"替换":"导入")+(side==="orders"?"业务单":"支付账单");
      $("#import-help").textContent=original?`将替换 ${original.filename}；原记录保留，确认时先备份再原子切换。`:side==="orders"?"金额为扣除预计退款后的净到账，不扣手续费。":"收款与退款金额均填正数；退款类型使用 refund。";
      $("#template-link").href=`/samples/${side}.csv`;$("#confirm-import").textContent=replaceId?"确认替换":"确认导入";
      setStep(1);$("#import-dialog").showModal();
    }
    async function previewFile(){
      invalidate();upload=null;preview=null;error();setStep(1);$("#file-summary").hidden=true;$("#file-preview").hidden=true;
      const file=$("#csv-file").files[0],own=revision;
      if(!file)return;
      try{
        if(!file.name.toLowerCase().endsWith(".csv")||file.size>5*1024*1024)throw new Error("请选择不超过 5 MiB 的 CSV 文件");
        const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(",")[1]);reader.onerror=()=>reject(new Error("文件读取失败"));reader.readAsDataURL(file);});
        const result=await api("/api/preview",{side:context.side,content});
        if(own!==revision||!$("#import-dialog").open)return;
        preview=result;upload={filename:file.name,content};templateOptions();
        $("#file-summary").textContent=`${file.name} · ${result.adapter.name} v${result.adapter.version} · ${result.encoding} · ${result.row_count} 行 · ${result.headers.length} 列`;
        $("#file-summary").hidden=false;$("#file-preview").hidden=false;
        $("#preview-head").innerHTML=`<tr>${result.headers.map((h)=>`<th>${escapeHTML(h)}</th>`).join("")}</tr>`;
        $("#preview-body").innerHTML=result.rows.map((row)=>`<tr>${result.headers.map((h)=>`<td>${escapeHTML(row[h])}</td>`).join("")}</tr>`).join("");
        $("#mapping-fields").innerHTML=Object.entries(result.mapping).map(([field,column])=>`<label class="field">${fieldLabels[field]}<select name="${field}"><option value="">请选择列</option>${result.headers.map((h)=>`<option value="${escapeHTML(h)}" ${h===column?"selected":""}>${escapeHTML(h)}</option>`).join("")}</select></label>`).join("");
        const warnings=[...Object.entries(result.ambiguous_fields).map(([field,columns])=>`${fieldLabels[field]}有多个候选列（${columns.join("、")}），请手动选择。`),...result.missing_fields.map((field)=>`未识别${fieldLabels[field]}，请手动选择。`)];
        $("#mapping-warning").textContent=warnings.join(" ");$("#mapping-warning").hidden=!warnings.length;
        const c=result.currency;
        $("#currency-summary").textContent=c.defaulted?"没有币种列：按约定默认人民币 CNY，不做汇兑。":`币种列：${c.columns.join("、")}；实际值：${c.values.map((v)=>v||"（空白）").join("、")}。${c.valid?"按人民币 CNY 核对。":`发现 ${c.error_count} 行币种问题，整份校验将列出错误。`}`;
        $("#currency-summary").classList.toggle("warning",!c.valid);setStep(1);
      }catch(e){if(own===revision&&$("#import-dialog").open)error(e.message);}
    }
    async function validate(page=1){
      const own=revision;
      const input=page===1?payload():validationInput;
      if(!input)throw new Error("输入已变化，请返回字段步骤重新校验");
      validationInput=input;checked=null;setStep(3);$("#validation-summary").textContent="正在检查整份文件…";
      $("#validation-errors-list").innerHTML="";$("#validation-prev").disabled=true;$("#validation-next").disabled=true;$("#download-import-errors").disabled=true;
      const result=await api(`/api/batches/${context.batchId}/validate-import`,{...input,page,page_size:25});
      if(own!==revision||!$("#import-dialog").open)return;
      checked=result;setStep(3);
      $("#validation-summary").textContent=result.valid?`整份校验通过：${result.row_count} 行，确认前尚未写入。`:`共 ${result.row_count} 行，${result.valid_rows} 行通过，${result.error_count} 行无效；整份不可导入。`;
      $("#validation-summary").classList.toggle("warning",!result.valid);
      $("#validation-errors-list").innerHTML=result.errors.map((e)=>`<tr><td>${e.line}</td><td>${escapeHTML(e.message)}</td></tr>`).join("");
      $("#validation-page-label").textContent=result.valid?"没有无效行":`第 ${result.page} / ${result.total_pages} 页 · 共 ${result.error_count} 行错误`;
      $("#validation-prev").disabled=result.page<=1;$("#validation-next").disabled=result.page>=result.total_pages;$("#download-import-errors").disabled=!result.error_count;
    }
    $("#csv-file").addEventListener("change",previewFile);
    $("#import-dialog").addEventListener("close",()=>{invalidate();upload=null;preview=null;});
    $("#mapping-fields").addEventListener("change",invalidate);
    for(const id of ["#channel-aliases","#replacement-reason"])$(id).addEventListener("input",invalidate);
    $("#template-select").addEventListener("change",applyTemplate);
    $("#import-back").addEventListener("click",()=>{if(state.busy)return;error();if(step<=3){invalidate();setStep(Math.max(1,step-1));}else setStep(3);});
    $("#import-next").addEventListener("click",(event)=>{
      if(state.busy)return;error();
      if(step===1){if(upload)setStep(2);return;}
      if(step===2){
        if(!$("#mapping-confirm").checked){error("请先确认字段、金额口径和渠道别名");return;}
        work(event.currentTarget,async()=>{try{await validate();}catch(e){error(e.message);setStep(2);}});return;
      }
      if(step===3&&checked?.valid){
        const input=validationInput;
        $("#import-confirmation").innerHTML=`<p>文件：${escapeHTML(input.filename)}</p><p>${context.side==="orders"?"业务单":"支付账单"} · ${checked.row_count} 行 · ${escapeHTML(checked.adapter.name)} v${checked.adapter.version}</p><p>字段：${Object.entries(input.mapping).map(([field,column])=>`${escapeHTML(fieldLabels[field])} → ${escapeHTML(column)}`).join("；")}</p><p>渠道别名：${Object.entries(input.channel_aliases).map(([a,b])=>`${escapeHTML(a)} → ${escapeHTML(b)}`).join("；")||"无"}</p>${context.replaceId?`<p>替换 ${escapeHTML(context.originalName)}；原因：${escapeHTML(input.reason)}</p>`:""}`;
        setStep(4);
      }
    });
    for(const [id,delta] of [["#validation-prev",-1],["#validation-next",1]])$(id).addEventListener("click",(event)=>{
      if(state.busy||!checked)return;const page=checked.page+delta;
      work(event.currentTarget,async()=>{try{await validate(page);}catch(e){error(e.message);}});
    });
    $("#download-import-errors").addEventListener("click",(event)=>work(event.currentTarget,async()=>{
      try{
        const response=await fetch(`/api/batches/${context.batchId}/import-errors`,{method:"POST",headers:{"Content-Type":"application/json","X-LedgerDesk-Token":state.token},body:JSON.stringify(validationInput)});
        if(!response.ok)throw new Error((await response.json()).error||"错误下载失败");
        const url=URL.createObjectURL(await response.blob()),link=document.createElement("a");link.href=url;link.download="LedgerDesk-import-errors.csv";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      }catch(e){error(e.message);}
    }));
    $("#save-template").addEventListener("click",(event)=>work(event.currentTarget,async()=>{
      try{const id=$("#template-select").value;const saved=await api("/api/templates",{name:$("#template-name").value.trim(),side:context.side,mapping:mapping(),channel_aliases:aliases()});await refreshTemplates();templateOptions();$("#template-select").value=saved.id||id;notify(`映射模板已保存，修订 ${saved.revision}`);}catch(e){error(e.message);}
    }));
    $("#import-form").addEventListener("submit",(event)=>{
      event.preventDefault();if(step!==4||!checked?.receipt||!validationInput)return;
      const batchId=context.batchId,input={...validationInput,receipt:checked.receipt};
      work(event.submitter,async()=>{
        let result;
        try{result=await api(`/api/batches/${batchId}/import`,input);}catch(e){error(e.message);if(e.code==="stale_validation"){invalidate();setStep(2);}return;}
        $("#import-dialog").close();
        try{await onImported(batchId);}catch(e){notify(`导入已保存，刷新列表失败：${e.message}`,true);return;}
        notify(result.duplicate?"文件、映射和别名未变，本次未重复入库":`已导入 ${result.row_count} 行，请执行核对`);
      });
    });
    return {start};
  }
};
