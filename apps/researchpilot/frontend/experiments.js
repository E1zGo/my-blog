'use strict';
const experimentStatuses={planned:'待开始',running:'进行中',completed:'已结束',blocked:'受阻'};
const experimentChecks=['核对代码版本与运行入口','记录依赖与硬件环境','确认数据划分与权重来源','完成小规模试运行','保存评测协议、指标与日志'];
const journal={workspace:null,rows:[],draft:null,loading:0,comparing:0,saving:false};
const experimentDraftKey=w=>'researchpilot.experiment-draft.'+w;
const experimentPath=(w=state.workspace)=>`/workspaces/${w}/experiments`;
function readExperimentDraft(){
  try{const d=JSON.parse(clientStorage.getItem(experimentDraftKey(state.workspace))||'null');return d?.workspace===state.workspace&&typeof d.name==='string'&&Array.isArray(d.metrics)?d:null;}catch{return null;}
}
function experimentDraftBadge(){$('#restore-experiment-draft').hidden=!readExperimentDraft();}
function resetExperiments(){
  journal.workspace=state.workspace;journal.rows=[];journal.draft=null;journal.loading++;journal.comparing++;
  $('#experiment-editor').hidden=true;$('#experiment-editor').innerHTML='';$('#experiments-list').innerHTML='';$('#experiments-summary').textContent='';
  $('#comparison-result').innerHTML='';$('#experiment-comparison').open=false;$('#experiment-status-filter').value='all';$('#experiment-filter').value='';
  $('#compare-baseline').innerHTML='';$('#compare-candidate').innerHTML='';experimentDraftBadge();
  if(typeof resetLogAnalysis==='function')resetLogAnalysis();
}
async function openExperiments(){
  if(!state.workspace)return;
  if(journal.workspace!==state.workspace)resetExperiments();
  const workspace=state.workspace,generation=++journal.loading,trash=$('#experiment-status-filter').value==='trash';
  const rows=await api(experimentPath(workspace)+`?archived=${trash}`);
  if(workspace!==state.workspace||generation!==journal.loading)return;
  journal.rows=rows;renderExperiments();experimentDraftBadge();journal.comparing++;$('#comparison-result').innerHTML='';
  if(typeof refreshLogChoices==='function')refreshLogChoices();
  $('#experiment-comparison').hidden=trash;
  for(const selector of ['#compare-baseline','#compare-candidate']){
    const previous=$(selector).value;
    $(selector).innerHTML='<option value="">选择实验…</option>'+rows.map(r=>`<option value="${esc(r.id)}">${esc(r.name)}</option>`).join('');
    if(rows.some(r=>r.id===previous))$(selector).value=previous;
  }
}
function renderExperiments(){
  const query=$('#experiment-filter').value.trim().toLowerCase(),status=$('#experiment-status-filter').value,trash=status==='trash';
  const rows=journal.rows.filter(r=>(['all','trash'].includes(status)||r.status===status)&&[r.name,r.dataset,r.code_ref].some(v=>v.toLowerCase().includes(query)));
  $('#experiments-summary').textContent=`${trash?'回收站':'实验'} ${rows.length} / ${journal.rows.length} 条`;
  $('#experiments-list').innerHTML=rows.length?rows.map(r=>`<article class="experiment-card"><div class="note-heading"><span class="note-category">${experimentStatuses[r.status]}</span><small>${date(r.updated_at)}</small></div><h2>${esc(r.name)}</h2><p>数据集：${esc(r.dataset||'待填写')}</p><p>代码版本：${esc(r.code_ref||'待填写')}</p><div class="experiment-metrics">${r.metrics.length?r.metrics.map(m=>`<span>${esc(m.name)} <strong>${m.value}</strong> ${esc(m.unit)}</span>`).join(''):'<span>尚未填写实际指标</span>'}</div><div class="form-actions">${!trash?`<button class="outline-button" data-edit-experiment="${r.id}">查看 / 编辑</button><button class="text-button" data-clone-experiment="${r.id}" data-revision="${r.revision}">复制设置开新实验</button>`:''}<a class="text-button" href="/api${experimentPath()}/${r.id}/export" download>导出 Markdown</a><button class="text-button" data-archive-experiment="${r.id}" data-revision="${r.revision}" data-restore="${trash}">${trash?'恢复记录':'移入回收站'}</button></div></article>`).join(''):`<p class="empty-library">${trash?'回收站为空，移入的记录可以恢复。':'还没有匹配的实验。新建一条记录，或从已生成的复现计划开始。'}</p>`;
}
function newExperiment(plan){
  return {workspace:state.workspace,name:plan?'复现 · '+plan.prompt.slice(0,110):'',status:'planned',objective:plan?.prompt||'',environment:'',dataset:'',code_ref:'',parameters:{},parametersText:'',checklist:experimentChecks.map(label=>({label,done:false})),metrics:[],conclusion:'',log_source_ids:[],logs:[],plan:plan||null,plan_task_id:plan?.id||null};
}
function experimentFieldsFromDOM(){
  const d=journal.draft,form=$('#experiment-form');if(!d||!form)return;
  for(const key of ['name','status','objective','environment','dataset','code_ref','conclusion'])d[key]=$('#experiment-'+key).value;
  d.parametersText=$('#experiment-parameters').value;
  d.checklist=d.checklist.map((c,i)=>({...c,done:form.querySelector(`[data-experiment-check="${i}"]`).checked}));
  d.log_source_ids=Array.from(form.querySelectorAll('[data-experiment-log]:checked')).map(c=>c.dataset.experimentLog);
  d.metrics=Array.from(form.querySelectorAll('.metric-editor')).map((row,i)=>({...Object.fromEntries(['name','value','unit','split','protocol'].map(k=>[k,row.querySelector(`[data-metric-field="${k}"]`).value])),origin:d.metrics[i]?.origin||null,_evidence:d.metrics[i]?._evidence}));
}
function persistExperimentDraft(){
  experimentFieldsFromDOM();const d=journal.draft;if(!d)return;
  try{clientStorage.setItem(experimentDraftKey(d.workspace),JSON.stringify(d));$('#experiment-draft-status').textContent=draftStorageNotice();}
  catch{$('#experiment-draft-status').textContent='浏览器无法保存草稿，请及时保存实验记录。';}
  experimentDraftBadge();
}
function metricEditor(m,index){
  return `<div class="metric-editor" data-metric-index="${index}"><div class="experiment-pair"><label class="form-field">指标名称<input data-metric-field="name" aria-label="指标 ${index+1} 名称" required maxlength="80" value="${esc(m.name)}" placeholder="如 PSNR"></label><label class="form-field">实际数值<input data-metric-field="value" aria-label="指标 ${index+1} 数值" type="number" step="any" min="-1e100" max="1e100" required value="${esc(m.value)}" placeholder="如 28.42"></label></div><div class="experiment-pair"><label class="form-field">单位（无量纲可留空）<input data-metric-field="unit" aria-label="指标 ${index+1} 单位" maxlength="40" value="${esc(m.unit)}" placeholder="如 dB / %"></label><label class="form-field">评测划分<input data-metric-field="split" aria-label="指标 ${index+1} 划分" maxlength="120" value="${esc(m.split)}" placeholder="如 test / validation"></label></div><label class="form-field">评测协议<input data-metric-field="protocol" aria-label="指标 ${index+1} 协议" maxlength="500" value="${esc(m.protocol)}" placeholder="如 RGB，裁边 4px，脚本 eval.py@commit"></label><button type="button" class="text-button" data-remove-metric="${index}">移除此指标</button></div>`;
}
function renderMetricEditors(){
  $('#experiment-metric-rows').innerHTML=journal.draft.metrics.map(metricEditor).join('');
  $('#add-experiment-metric').disabled=journal.draft.metrics.length>=20;
  if(typeof renderMetricOrigins==='function')renderMetricOrigins();
}
function experimentEvidence(d){
  const p=d.plan;
  const plan=p?`<details class="experiment-evidence"><summary>查看复现计划与证据快照 · ${p.mode==='offline'?'离线演示':'LLM'} · 待人工核对</summary><pre class="source-text">${esc(p.answer)}</pre>${(p.citations||[]).map(c=>`<details><summary>${esc(c.label)} · ${esc(c.name)} · ${esc(c.locator)}</summary><pre class="source-text">${esc(c.text)}</pre>${c.metadata?.commit?`<p class="source-meta">代码版本：${esc(c.metadata.commit)}</p>`:''}${state.sources.some(s=>s.id===c.source_id)?`<button type="button" class="text-button" data-source="${esc(c.source_id)}" data-page="${c.page||''}">阅读来源</button>`:'<p class="source-meta">来源已移除，文字快照仍保留。</p>'}</details>`).join('')}</details>`:'';
  const logs=(d.logs||[]).map(l=>`<details class="experiment-evidence"><summary>日志快照 · ${esc(l.name)}${l.truncated?'（前 20000 字符）':''}</summary><pre class="source-text">${esc(l.text)}</pre><p class="source-meta">保存于 ${date(l.saved_at)}${l.truncated?' · 快照已截断，完整内容请查看原资料。':''}</p></details>`).join('');
  return plan+logs;
}
function showExperimentEditor(draft){
  if(journal.saving){toast('实验正在保存，请稍候。');return;}
  journal.draft=draft;
  const liveLogs=state.sources.filter(s=>s.kind==='log'),missing=(draft.logs||[]).filter(l=>!liveLogs.some(s=>s.id===l.id));
  const input=(key,label,placeholder='',max=500)=>`<label class="form-field">${label}<input id="experiment-${key}" maxlength="${max}" ${key==='name'?'required':''} value="${esc(draft[key])}" placeholder="${esc(placeholder)}"></label>`;
  const textarea=(key,label,max,placeholder='')=>`<label class="form-field">${label}<textarea id="experiment-${key}" rows="3" maxlength="${max}" placeholder="${esc(placeholder)}">${esc(draft[key])}</textarea></label>`;
  $('#experiment-editor').hidden=false;
  $('#experiment-editor').innerHTML=`<form id="experiment-form"><h2>${draft.id?'实验详情与记录':'新建实验记录'}</h2>${input('name','实验名称','如：基准复现 / 调整学习率',120)}<div class="experiment-pair"><label class="form-field">执行状态<select id="experiment-status">${Object.entries(experimentStatuses).map(([key,value])=>`<option value="${key}" ${draft.status===key?'selected':''}>${value}</option>`).join('')}</select></label>${input('code_ref','代码版本','仓库名 @ commit 或本地版本')}</div>${textarea('objective','实验目标 / 假设',4000)}${textarea('environment','环境与硬件',8000,'Python / PyTorch / CUDA / GPU / 依赖版本')}${input('dataset','数据集 / 版本','精确名称、版本或清单标识；对比时需一致')}<label class="form-field">参数与权重（每行 名称=值）<textarea id="experiment-parameters" rows="5" placeholder="learning_rate=0.0001&#10;batch_size=8&#10;seed=42&#10;weights=权重文件及校验值">${esc(draft.parametersText??Object.entries(draft.parameters).map(([k,v])=>k+'='+v).join('\n'))}</textarea></label><p class="search-hint">最多 40 项，建议记录随机种子、权重来源、批大小与学习率。</p><h3>复现核对清单</h3>${draft.checklist.map((c,i)=>`<label class="experiment-check"><input type="checkbox" data-experiment-check="${i}" ${c.done?'checked':''}><span>${esc(c.label)}</span></label>`).join('')}<h3>实际指标</h3><p class="search-hint">填写你实际测得的数值；同一次实验的指标名称不能重复。不同划分请使用不同名称。</p><div id="experiment-metric-rows"></div><button id="add-experiment-metric" type="button" class="outline-button">＋ 添加指标</button><h3>关联已导入日志</h3><p class="search-hint">先在工作台「添加日志」导入文件，再刷新记录。保存时留存前 20000 字符的文本快照。</p>${[...liveLogs,...missing].map(l=>`<label class="experiment-check"><input type="checkbox" data-experiment-log="${esc(l.id)}" ${draft.log_source_ids.includes(l.id)?'checked':''}><span>${esc(l.name)}${missing.includes(l)?' · 原资料已移除，保留旧快照':''}</span></label>`).join('')||'<p class="search-hint">当前项目尚无日志。</p>'}${experimentEvidence(draft)}${textarea('conclusion','个人结论 / 下一步',12000,'记录观察到的现象、待验证解释与下一轮调整。')}<p id="experiment-draft-status" class="search-hint"></p><p id="experiment-save-error" class="error-box" role="alert" hidden></p><div id="experiment-save-bar" class="form-actions"><button id="hide-experiment-editor" type="button" class="text-button">收起并保留草稿</button><button id="discard-experiment-draft" type="button" class="text-button">放弃草稿</button><button id="save-experiment" class="primary-button" type="submit">保存实验记录</button></div></form>`;
  renderMetricEditors();
  bind('#experiment-form','input',persistExperimentDraft);bind('#experiment-form','change',persistExperimentDraft);bind('#experiment-form','submit',saveExperiment);
  bind('#add-experiment-metric','click',()=>{experimentFieldsFromDOM();if(journal.draft.metrics.length<20)journal.draft.metrics.push({name:'',value:'',unit:'',split:'',protocol:''});renderMetricEditors();persistExperimentDraft();});
  bind('#hide-experiment-editor','click',()=>{persistExperimentDraft();$('#experiment-editor').hidden=true;});
  bind('#discard-experiment-draft','click',()=>{
    modal('放弃实验草稿','<p class="modal-copy">将清除当前项目的未保存实验草稿。已保存的实验记录保留。</p><div class="form-actions"><button id="confirm-discard-experiment" class="danger-button">放弃草稿</button></div>');
    bind('#confirm-discard-experiment','click',()=>{clientStorage.removeItem(experimentDraftKey(draft.workspace));journal.draft=null;$('#experiment-editor').hidden=true;$('#experiment-editor').innerHTML='';$('#modal').close();experimentDraftBadge();});
  });
  persistExperimentDraft();$('#experiment-editor').scrollIntoView({block:'start',behavior:'smooth'});
}
function resumeExperimentDraft(){
  const existing=readExperimentDraft();
  if(existing){showExperimentEditor(existing);toast('已恢复实验草稿。请先保存或放弃，再开始另一条实验。');return true;}
  return false;
}
async function editExperiment(identifier){
  if(journal.saving||resumeExperimentDraft())return;
  const workspace=state.workspace,record=await api(experimentPath(workspace)+'/'+identifier);
  if(workspace===state.workspace)showExperimentEditor({...record,workspace});
}
function parseExperimentParameters(text){
  const entries=[],seen=new Set();
  for(const line of text.split('\n')){
    if(!line.trim())continue;
    const index=line.indexOf('='),key=line.slice(0,index).trim(),value=line.slice(index+1).trim();
    if(index<1||!key||key.length>80||value.length>1000)throw new Error('参数每行需为「名称=值」，名称不超过 80 字，值不超过 1000 字。');
    if(seen.has(key))throw new Error('参数名称重复：'+key);
    seen.add(key);entries.push([key,value]);
  }
  if(entries.length>40)throw new Error('最多记录 40 项参数。');
  return Object.fromEntries(entries);
}
async function saveExperiment(event){
  event.preventDefault();persistExperimentDraft();
  const d=structuredClone(journal.draft),form=event.target,body={};
  for(const key of ['name','status','objective','environment','dataset','code_ref','checklist','conclusion','log_source_ids'])body[key]=d[key];
  $('#experiment-save-error').hidden=true;
  try{
    body.parameters=parseExperimentParameters(d.parametersText);
    body.metrics=d.metrics.map(m=>{if(String(m.value).trim()===''||!Number.isFinite(Number(m.value)))throw new Error('指标需要填写有效数值。');return {name:m.name,value:Number(m.value),unit:m.unit,split:m.split,protocol:m.protocol,origin:m.origin||null};});
    if(d.id)body.revision=d.revision;else body.plan_task_id=d.plan_task_id||null;
    journal.saving=true;for(const element of form.elements)element.disabled=true;
    await api(experimentPath(d.workspace)+(d.id?'/'+d.id:''),{method:d.id?'PATCH':'POST',body:JSON.stringify(body)});
    clientStorage.removeItem(experimentDraftKey(d.workspace));
    if(d.workspace===state.workspace){journal.draft=null;$('#experiment-editor').hidden=true;$('#experiment-editor').innerHTML='';$('#experiment-status-filter').value='all';$('#experiment-filter').value='';experimentDraftBadge();await openExperiments();toast('实验记录已保存。日志指标的来源行已一并留存。');}
  }catch(err){if(form.isConnected){$('#experiment-save-error').textContent=err.message;$('#experiment-save-error').hidden=false;}}
  finally{journal.saving=false;for(const element of form.elements)element.disabled=false;}
}
async function compareExperiments(){
  const baseline=$('#compare-baseline').value,candidate=$('#compare-candidate').value;
  if(!baseline||!candidate||baseline===candidate){toast('请选择两条不同的实验记录。');return;}
  const workspace=state.workspace,generation=++journal.comparing;$('#compare-experiments').disabled=true;
  try{
    const result=await api(experimentPath(workspace)+'/compare',{method:'POST',body:JSON.stringify({baseline_id:baseline,candidate_id:candidate})});
    if(workspace!==state.workspace||generation!==journal.comparing)return;
    const value=m=>m?`${m.value} ${m.unit||''}`:'未记录';
    const pair=(a,b)=>`<div class="comparison-values"><p><small>基准</small>${esc(a??'未填写')}</p><p><small>对照</small>${esc(b??'未填写')}</p></div>`;
    $('#comparison-result').innerHTML=`<p class="experiment-notice">${esc(result.notice)}</p>${pair(result.baseline.name+' · '+experimentStatuses[result.baseline.status],result.candidate.name+' · '+experimentStatuses[result.candidate.status])}<h3>指标对比</h3>${result.metrics.map(m=>`<div class="comparison-row"><strong>${esc(m.name)}</strong>${pair(value(m.baseline),value(m.candidate))}<div class="${m.comparable?'comparison-delta':'comparison-unavailable'}">${m.comparable?'差值 '+(m.delta>0?'+':'')+Number(m.delta.toPrecision(8))+' '+esc(m.baseline.unit):'不计算差值：'+esc(m.reason)}</div>${pair(m.baseline?'划分：'+(m.baseline.split||'未填')+'；协议：'+(m.baseline.protocol||'未填'):'',m.candidate?'划分：'+(m.candidate.split||'未填')+'；协议：'+(m.candidate.protocol||'未填'):'')}</div>`).join('')||'<p class="search-hint">两侧均未记录指标。</p>'}<h3>设置差异</h3>${result.changes.map(c=>`<div class="comparison-row"><strong>${esc(c.field)}</strong>${pair(c.baseline,c.candidate)}</div>`).join('')||'<p class="search-hint">填写的设置相同；不代表实际运行环境已核验。</p>'}`;
  }finally{$('#compare-experiments').disabled=false;}
}
bind('#new-experiment','click',()=>{if(!journal.saving&&!resumeExperimentDraft())showExperimentEditor(newExperiment());});
bind('#restore-experiment-draft','click',resumeExperimentDraft);
bind('#refresh-experiments','click',async()=>{const workspace=state.workspace;await refresh();if(workspace===state.workspace){await openExperiments();if(journal.draft&&!$('#experiment-editor').hidden){persistExperimentDraft();showExperimentEditor(journal.draft);}}});
bind('#experiment-filter','input',renderExperiments);bind('#experiment-status-filter','change',openExperiments);bind('#compare-experiments','click',compareExperiments);
for(const selector of ['#compare-baseline','#compare-candidate'])bind(selector,'change',()=>{journal.comparing++;$('#comparison-result').innerHTML='';});
bind('#plan-to-experiment','click',()=>{
  const task=state.task;if(!task||journal.saving)return;
  switchView('experiments');if(!resumeExperimentDraft())showExperimentEditor(newExperiment(task));
});
document.addEventListener('click',async event=>{try{
  const remove=event.target.closest('[data-remove-metric]');
  if(remove){experimentFieldsFromDOM();journal.draft.metrics.splice(Number(remove.dataset.removeMetric),1);renderMetricEditors();persistExperimentDraft();return;}
  const edit=event.target.closest('[data-edit-experiment]');if(edit){await editExperiment(edit.dataset.editExperiment);return;}
  const action=event.target.closest('[data-clone-experiment],[data-archive-experiment]');if(!action)return;
  const clone=Boolean(action.dataset.cloneExperiment);if(clone&&(journal.saving||resumeExperimentDraft()))return;
  const workspace=state.workspace,id=action.dataset.cloneExperiment||action.dataset.archiveExperiment,kind=clone?'clone':action.dataset.restore==='true'?'restore':'trash';action.disabled=true;
  try{
    const record=await api(experimentPath(workspace)+'/'+id+'/'+kind,{method:'POST',body:JSON.stringify({revision:Number(action.dataset.revision)})});
    if(workspace!==state.workspace)return;
    await openExperiments();
    if(clone){showExperimentEditor({...record,workspace});toast('新实验已创建：沿用设置与计划，指标、日志和结论留空。');}
    else toast(kind==='trash'?'已移入回收站，可以恢复。':'实验记录已恢复。');
  }finally{if(action.isConnected)action.disabled=false;}
}catch(err){toast(err.message);}});
