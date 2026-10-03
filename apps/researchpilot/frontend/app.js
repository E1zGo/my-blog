'use strict';
const $ = (selector) => document.querySelector(selector);
const esc = (value = '') => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {paper:'论文',repository:'代码',log:'日志'};
const statuses = {queued:'等待处理',running:'正在研究',completed:'已完成',insufficient_evidence:'证据不足',needs_review:'需要核查',cancelled:'已停止',failed:'任务失败'};
const state = {workspace:null,workspaces:[],sources:[],tasks:[],health:{mode:'offline'},intent:'qa',task:null,poll:null,view:'workbench',generation:0,uploads:[],uploading:false,imports:[],importPoll:null,importError:'',showFinished:true,scope:[],pageRange:null,searchGeneration:0,reader:null};
const activeImports = new Set(['receiving','queued','parsing','indexing']);
let toastTimer;
async function api(path, options={}) {
  const headers = options.body && !(options.body instanceof FormData) ? {'Content-Type':'application/json'} : {};
  let response;
  try {response = await fetch('/api'+path,{...options,headers:{...headers,...(account.csrf?{'X-CSRF-Token':account.csrf}:{}),...options.headers}});}
  catch {throw new Error('无法连接本机服务，请运行项目中的 start.bat 启动服务后重试。');}
  if (response.status===401&&account.user){authExpired();throw new Error('登录已过期，请重新登录。');}
  if (!response.ok) {
    const payload = await response.json().catch(()=>({detail:'服务暂时不可用'}));
    throw new Error(typeof payload.detail === 'string' ? payload.detail : '输入格式不正确，请检查后重试。');
  }
  return response.status === 204 ? null : response.json();
}
function toast(text) {clearTimeout(toastTimer);$('#toast').textContent=text;$('#toast').hidden=false;toastTimer=setTimeout(()=>$('#toast').hidden=true,5500);}
function bind(selector, event, action) {$(selector).addEventListener(event, e=>Promise.resolve(action(e)).catch(err=>toast(err.message)));}
function modal(title, body) {$('#modal').classList.remove('pdf-viewer');$('#modal-title').textContent=title;$('#modal-body').innerHTML=body;if(!$('#modal').open)$('#modal').showModal();}
function date(value) {return new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});}
function sourceRow(s) {
  return `<button class="source-row" data-source="${esc(s.id)}"><span class="file-icon">${s.kind==='repository'?'⌘':s.kind==='log'?'⌁':'▤'}</span><span class="file-info"><strong>${esc(s.name)}</strong><small>${s.chunk_count} 个片段${s.metadata.pages?' · '+s.metadata.pages+' 页':''} · ${esc(s.metadata.demo?'教学示例':s.metadata.retrieval==='hybrid'?'混合检索':'BM25 已索引')}${s.metadata.commit?' · '+esc(s.metadata.commit.slice(0,12)):''}${s.metadata.warnings?.length?' · 有解析提示':''}${readingHint(s)}</small></span><span class="file-tag">${labels[s.kind]}</span><span class="file-chevron">›</span></button>`;
}
function renderSources() {
  $('#paper-count').textContent=state.sources.filter(s=>s.kind==='paper').length;
  $('#repo-count').textContent=state.sources.filter(s=>s.kind==='repository').length;
  $('#task-count').textContent=state.tasks.length;
  $('#source-count').textContent=state.sources.length;
  $('#nav-count').textContent=state.sources.length;
  $('#recent-sources').innerHTML=state.sources.length?state.sources.slice(0,3).map(sourceRow).join(''):'<div class="empty-library">还没有研究资料。导入一篇论文，或试试 TinyRestore 示例，开启第一次探索。</div>';
  renderLibrary();renderHistory();
}
function renderLibrary() {
  const query=$('#source-filter').value.toLowerCase();
  const sources=state.sources.filter(s=>s.name.toLowerCase().includes(query));
  $('#library-summary').textContent=`${state.sources.length} 份资料 / ${state.sources.reduce((n,s)=>n+s.chunk_count,0)} 个片段`;
  $('#library-list').innerHTML=sources.length?sources.map(s=>`<div class="library-item"><input class="source-check" type="checkbox" data-scope="${esc(s.id)}" aria-label="选择 ${esc(s.name)}" ${state.scope.includes(s.id)?'checked':''}>${sourceRow(s)}</div>`).join(''):'<p class="empty-library">暂无匹配资料。上传文件，或从工作台导入示例。</p>';
  renderScope();
}
function renderScope(){
  const label=(state.scope.length?`已选 ${state.scope.length} 份资料`:'全部资料')+(state.pageRange?' · '+pageRangeLabel(state.pageRange):'');
  document.querySelectorAll('[data-edit-page-range]').forEach(b=>b.disabled=!singlePaper());
  document.querySelectorAll('[data-clear-page-range]').forEach(b=>b.hidden=!state.pageRange);
  $('#composer-scope').textContent='研究范围：'+label;$('#library-scope').textContent='检索与提问范围：'+label;
  $('#clear-scope').disabled=!state.scope.length;
}
function saveScope(keepRange=false){
  if(!keepRange&&state.pageRange){state.pageRange=null;$('#prompt').placeholder='你想了解什么？例如：这篇论文使用了什么方法与训练目标？';toast('资料选择已改变，已恢复全文范围。');}
  clientStorage.setItem('researchpilot.page-range.'+state.workspace,JSON.stringify(state.pageRange));
  clientStorage.setItem('researchpilot.scope.'+state.workspace,JSON.stringify(state.scope));
  state.searchGeneration++;$('#search-submit').disabled=false;$('#search-results').innerHTML='';renderLibrary();
}
function renderHistory() {
  $('#history-list').innerHTML=state.tasks.length?state.tasks.map(t=>`<button class="history-card" data-task="${esc(t.id)}"><h3>${esc(t.prompt)}</h3><div><span>${date(t.created_at)}</span><span>${esc(statuses[t.status]||t.status)}</span><span>${t.mode==='offline'?'离线演示':'LLM Agent'}</span>${t.page_range?'<span>'+pageRangeLabel(t.page_range)+'</span>':''}</div></button>`).join(''):'<p class="empty-library">任务记录会保存在这里。先在工作台提出你的第一个问题。</p>';
}
async function refresh() {
  const workspace=state.workspace;
  const [sources,tasks,imports]=await Promise.all([api(`/workspaces/${workspace}/sources`),api(`/workspaces/${workspace}/tasks`),api(`/workspaces/${workspace}/imports`)]);
  if(workspace!==state.workspace)return;
  state.sources=sources;state.tasks=tasks;state.imports=imports;state.importError='';
  const available=new Set(sources.map(s=>s.id));const scope=state.scope.filter(id=>available.has(id));
  if(scope.length!==state.scope.length){state.scope=scope;saveScope();}
  renderSources();renderUploads();scheduleImports();
  if(typeof refreshLogChoices==='function')refreshLogChoices();
}
function scheduleImports(){
  clearTimeout(state.importPoll);
  if(state.uploading||state.imports.some(j=>activeImports.has(j.status))||state.importError){
    const workspace=state.workspace;
    state.importPoll=setTimeout(async()=>{try{await refresh();}catch(err){if(workspace===state.workspace){state.importError=err.message;renderUploads();scheduleImports();}}},state.importError?3000:1000);
  }
}
function switchView(view) {
  state.view=view;
  for(const name of ['workbench','library','history','notebook','experiments'])$(`#${name}-view`).hidden=name!==view;
  document.querySelectorAll('.nav-button').forEach(button=>button.classList.toggle('active',button.dataset.view===view));
  $('#breadcrumb').textContent={workbench:'研究工作台',library:'资料库',history:'任务记录',notebook:'研究笔记',experiments:'实验记录'}[view];
  if(view==='history')refresh().catch(e=>toast(e.message));
  if(view==='notebook')openNotebook().catch(e=>toast(e.message));
  if(view==='experiments')openExperiments().catch(e=>toast(e.message));
}
function home() {state.task=null;clearTimeout(state.poll);state.generation++;$('#task-result').hidden=true;$('#welcome').hidden=false;$('#submit-task').disabled=false;$('#evidence-content').innerHTML=initialEvidence;$('#evidence-count').textContent='0';switchView('workbench');}
async function selectWorkspace(id) {
  home();clearTimeout(state.importPoll);state.workspace=id;clientStorage.setItem('researchpilot.workspace',id);$('#workspace-select').value=id;
  state.sources=[];state.tasks=[];state.imports=[];state.importError='';state.showFinished=true;state.scope=[];state.pageRange=null;
  if(typeof resetNotebook==='function')resetNotebook();
  if(typeof resetExperiments==='function')resetExperiments();
  try{const saved=JSON.parse(clientStorage.getItem('researchpilot.scope.'+id)||'[]');if(Array.isArray(saved))state.scope=saved.filter(v=>typeof v==='string').slice(0,50);}catch{}
  try{const r=JSON.parse(clientStorage.getItem('researchpilot.page-range.'+id)||'null');if(state.scope.length===1&&r&&Number.isInteger(r.start)&&Number.isInteger(r.end)&&r.start>=1&&r.end>=r.start&&r.end<=300)state.pageRange={start:r.start,end:r.end};}catch{}
  if(state.pageRange){state.intent='qa';document.querySelectorAll('.intent').forEach(b=>b.classList.toggle('active',b.dataset.intent==='qa'));$('#prompt').placeholder='仅询问 '+pageRangeLabel(state.pageRange)+' 中的内容…';$('#search-kind').value='paper';}
  state.searchGeneration++;$('#search-submit').disabled=false;$('#search-results').innerHTML='';$('#fulltext-query').value='';$('#source-filter').value='';
  renderSources();renderUploads();await refresh();
}
function renderWorkspaceOptions() {$('#workspace-select').innerHTML=state.workspaces.map(w=>`<option value="${esc(w.id)}">${esc(w.name)}</option>`).join('');}
async function loadDemo(button) {
  button.disabled=true;const old=button.textContent;button.textContent='正在导入…';
  try {await api(`/workspaces/${state.workspace}/demo`,{method:'POST'});await refresh();toast('示例已导入：教学用合成论文、代码片段与错误日志。');$('#prompt').value='这篇论文使用了什么方法与训练目标？';switchView('workbench');}
  finally {button.disabled=false;button.textContent=old;}
}
let uploadKind='paper';
function chooseFiles(kind='paper'){
  if(state.uploading){toast('正在处理上一批文件，请等待完成。');return;}
  if(!state.health.limits){toast('尚未读取上传配置，请确认服务已启动后刷新页面。');return;}
  uploadKind=kind;$('#file-input').accept=kind==='log'?'.log,.txt':'.pdf,.md,.txt,.log';$('#file-input').click();
}
function fileSize(bytes){return bytes < 1024*1024 ? (bytes/1024).toFixed(1)+' KB' : (bytes/1024/1024).toFixed(2)+' MB';}
function renderUploads(){
  const names={receiving:'正在保存',queued:'排队中',sending:'正在上传',processing:'正在保存',parsing:'正在提取文字',indexing:'正在建立索引',completed:'已导入',cancelled:'已取消',failed:'导入失败',error:'上传失败'};
  const transient=state.uploads.filter(u=>u.workspace===state.workspace&&!u.jobId);
  const rows=[...transient,...state.imports],pending=u=>activeImports.has(u.status)||['sending','processing'].includes(u.status);
  $('#upload-panel').hidden=!rows.length;
  $('#upload-summary').textContent=state.importError?'状态刷新中断，将自动重试。'+state.importError:`${rows.filter(pending).length} 份处理中 · ${rows.filter(u=>u.status==='completed').length} 份完成 · ${rows.filter(u=>['failed','error'].includes(u.status)).length} 份失败。已接收的导入任务在后台继续，刷新页面可恢复最近 100 条记录。`;
  $('#clear-uploads').disabled=false;$('#clear-uploads').textContent=state.showFinished?'收起已结束记录':'显示已结束记录';
  $('#upload-items').innerHTML=rows.filter(u=>state.showFinished||pending(u)).map(u=>{
    const warnings=u.result?.metadata?.warnings||[];
    const message=u.error||u.message||'';
    const progress=u.status==='sending'?`<progress max="100" value="${u.progress}" aria-label="${esc(u.name)} 上传进度"></progress>`:u.total_pages&&pending(u)?`<progress max="${u.total_pages}" value="${u.current_page}" aria-label="${esc(u.name)} 解析进度"></progress>`:pending(u)?'<progress aria-label="正在处理文件"></progress>':'';
    return `<div class="upload-item ${['error','failed'].includes(u.status)?'upload-error':''}"><div class="upload-item-title"><strong>${esc(u.name)}</strong><span>${fileSize(u.size_bytes??u.size??0)}</span><b>${u.result?.duplicate?'已存在':names[u.status]||esc(u.status)}</b></div>${progress}<p>${esc(message)}${u.total_pages?` · 已处理 ${u.current_page}/${u.total_pages} 页`:''}</p>${warnings.length?`<details class="import-warnings"><summary>${warnings.length} 条解析提示</summary><p>${warnings.map(esc).join('<br>')}</p></details>`:''}<div class="upload-actions">${['queued','parsing','indexing'].includes(u.status)&&u.id?`<button class="text-button" data-cancel-import="${esc(u.id)}">取消导入</button>`:''}${u.status==='completed'&&state.sources.some(s=>s.id===u.result?.id)?`<button class="text-button" data-source="${esc(u.result.id)}">查看资料与原文 ↗</button>`:''}${u.created_at?`<small>${date(u.created_at)}</small>`:''}</div></div>`;
  }).join('');
}
function uploadFile(workspace,file,kind,item){
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();
    xhr.open('POST',`/api/workspaces/${workspace}/imports`);
    if(account.csrf)xhr.setRequestHeader('X-CSRF-Token',account.csrf);
    xhr.upload.onprogress=event=>{
      if(event.lengthComputable){item.progress=Math.round(event.loaded/event.total*100);item.message=`上传 ${item.progress}% · 目标项目：${item.workspaceName}`;renderUploads();}
    };
    xhr.upload.onload=()=>{item.status='processing';item.message='文件已发送，正在本机保存并创建后台导入任务。';renderUploads();};
    xhr.onerror=()=>reject(new Error('连接本机服务失败或上传中断。请确认 start.bat 正在运行后重试。'));
    xhr.onabort=()=>reject(new Error('上传已中断，请重新选择文件。'));
    xhr.onload=()=>{
      if(xhr.status===401&&account.user){authExpired();reject(new Error('登录已过期。'));return;}
      let payload;try{payload=JSON.parse(xhr.responseText);}catch{reject(new Error(`服务响应异常（HTTP ${xhr.status}），请检查后端运行状态。`));return;}
      if(xhr.status>=200&&xhr.status<300){resolve(payload);return;}
      reject(new Error(typeof payload.detail==='string'?payload.detail:`文件处理失败（HTTP ${xhr.status}），请检查格式或查看服务日志。`));
    };
    const body=new FormData();body.append('file',file);body.append('kind',kind);xhr.send(body);
  });
}
function inline(text) {return esc(text).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\[(E\d+)\]/g,'<button class="cite-button" data-cite="$1">$1 ↗</button>');}
function markdown(text) {
  const lines=text.split('\n');let html='',quote=[],code=[],inCode=false,list=false;
  function closeQuote(){if(quote.length){html+='<blockquote>'+quote.map(inline).join('\n')+'</blockquote>';quote=[];}}
  function closeList(){if(list){html+='</ul>';list=false;}}
  for(const line of lines){
    if(line.startsWith('```')){closeQuote();closeList();if(inCode){html+='<pre><code>'+esc(code.join('\n'))+'</code></pre>';code=[];}inCode=!inCode;continue;}
    if(inCode){code.push(line);continue;}
    if(/^>\s?/.test(line)){closeList();quote.push(line.replace(/^>\s?/,''));continue;}closeQuote();
    const heading=line.match(/^(#{1,6})\s+(.+)/);if(heading){closeList();const level=heading[1].length<3?2:3;html+=`<h${level}>${inline(heading[2])}</h${level}>`;continue;}
    if(/^([-*]|\d+\.)\s+/.test(line)){if(!list){html+='<ul>';list=true;}html+='<li>'+inline(line.replace(/^([-*]|\d+\.)\s+/,''))+'</li>';continue;}closeList();
    if(line.trim())html+='<p>'+inline(line)+'</p>';
  }
  closeQuote();closeList();if(code.length)html+='<pre><code>'+esc(code.join('\n'))+'</code></pre>';return html;
}
function renderTask(task) {
  state.task=task;$('#welcome').hidden=true;$('#task-result').hidden=false;
  $('#task-question').textContent=task.prompt;$('#task-status').textContent=statuses[task.status]||task.status;
  const running=['queued','running'].includes(task.status);$('#submit-task').disabled=running;$('#cancel-task').hidden=!running;
  $('#export-report').hidden=running||!task.answer;$('#export-report').href=`/api/tasks/${task.id}/report`;
  $('#plan-to-experiment').hidden=task.intent!=='plan'||!['completed','needs_review'].includes(task.status)||!task.citations.length;
  const usage=task.usage||{};$('#task-metrics').textContent=[task.mode==='offline'?'离线演示':'LLM Agent',task.source_ids?.length?`限定 ${task.source_ids.length} 份资料`:'全部资料',task.page_range?pageRangeLabel(task.page_range):null,usage.elapsed_ms!==undefined?(usage.elapsed_ms/1000).toFixed(2)+' 秒':null,usage.tool_calls!==undefined?usage.tool_calls+' 次工具调用':null,usage.total_tokens!==undefined?usage.total_tokens+' tokens':null].filter(Boolean).join(' · ');
  $('#trace-count').textContent=task.events.length+' 条事件';
  $('#trace-events').innerHTML=task.events.map(e=>`<div class="trace-event">${esc(e.message)}${e.data.arguments?'<small>'+esc(JSON.stringify(e.data.arguments))+'</small>':''}</div>`).join('');
  $('#answer').innerHTML=task.error?`<div class="error-box">${esc(task.error)}</div>`:task.answer?markdown(task.answer):running?'<p class="loading-copy">正在查找证据，执行过程会持续更新…</p>':'<p class="empty-library">任务已停止。可以调整问题后重新提交。</p>';
  $('#evidence-count').textContent=task.citations.length;
  $('#evidence-content').innerHTML=task.citations.length?task.citations.map(e=>`<button class="evidence-card" data-evidence="${esc(e.label)}" id="citation-${esc(e.label)}"><span class="evidence-label">${esc(e.label)} · ${labels[e.kind]}</span><strong>${esc(e.name)}</strong><p>${esc(e.structure?.type==='visual'?'公式或图表片段，点击查看原版页面。':e.text)}</p><small>${esc(e.locator)} · 查看原文 ↗</small></button>`).join('')+'<p class="evidence-note">引用编号已核对到真实片段。引用存在不等于结论必然正确，请阅读上下文。</p>':initialEvidence;
}
async function openTask(id) {
  clearTimeout(state.poll);const generation=++state.generation;switchView('workbench');
  async function tick(){
    try{const task=await api(`/tasks/${id}`);if(generation!==state.generation)return;renderTask(task);
      if(['queued','running'].includes(task.status))state.poll=setTimeout(tick,900);else await refresh();
    }catch(e){if(generation===state.generation){toast(e.message);$('#submit-task').disabled=false;}}
  }
  await tick();
}
function showEvidence(label){
  const e=state.task?.citations.find(item=>item.label===label);if(!e)return;
  const card=document.getElementById('citation-'+label);if(card){card.classList.add('highlight');setTimeout(()=>card.classList.remove('highlight'),1800);}
  const source=state.sources.find(s=>s.id===e.source_id);
  modal(`${label} · ${e.name}`,`<p class="source-meta">${esc(e.locator)}${e.metadata?.commit?' · Commit '+esc(e.metadata.commit):''}</p>${evidencePresentation(e,source,'',isOriginalPdf(source))}<p class="modal-copy">这是任务执行时保存的证据快照，后续删除资料也不会修改已保存的报告。</p><div class="form-actions"><button class="outline-button" data-bookmark-task="${esc(state.task.id)}" data-bookmark-label="${esc(label)}">☆ 收藏到研究笔记</button>${source?originalLinks(source,e.page):''}${source?`<button class="outline-button" data-source="${esc(e.source_id)}" data-page="${e.page||''}">查看提取文本上下文</button>`:'<span class="modal-copy">来源已移除，证据快照仍可阅读。</span>'}</div>`);
}
function originalLinks(source,page){
  if(!(source.has_original??Boolean(source.metadata?.original_id)))return '';
  const url=`/api/sources/${encodeURIComponent(source.id)}/original`,pdf=/\.pdf$/i.test(source.metadata.filename||source.name);
  return `${pdf?`<button class="outline-button" data-preview-source="${esc(source.id)}" data-preview-page="${Number(page)||1}">查看 PDF 原文${page?' · 第 '+Number(page)+' 页':''} ↗</button>`:''}<a class="outline-button" href="${url}?download=true" download>下载原文件</a>`;
}
async function showPreview(id,page){
  const source=await api(`/sources/${id}`);
  if(!source.has_original)throw new Error('原文件已移除，请重新上传 PDF。');
  const total=source.metadata.pages||1,progress=readingProgress(source);let current=Math.max(1,Math.min(page||progress?.page||1,total));
  modal(source.name+' · 原文',`<div class="pdf-toolbar"><button id="pdf-prev" class="outline-button">← 上一页</button><label>页码 <input id="pdf-page" type="number" min="1" max="${total}" value="${current}"></label><span>/ ${total}</span><button id="pdf-next" class="outline-button">下一页 →</button><select id="pdf-zoom" aria-label="原文缩放"><option value="100">适合宽度</option><option value="150">放大 150%</option><option value="200">放大 200%</option></select><a class="outline-button" href="/api/sources/${encodeURIComponent(id)}/original?download=true" download>下载 PDF</a></div><p id="pdf-status" class="search-hint" role="status"></p><div id="pdf-canvas" class="pdf-canvas" tabindex="0" aria-label="放大原文滚动区域" data-zoom="100"><img id="pdf-image" alt=""></div><div class="form-actions"><button id="pdf-retry" class="text-button" hidden>重新加载本页</button><button id="pdf-text" class="outline-button">查看此页提取文本</button></div>`);
  $('#modal').classList.add('pdf-viewer');
  $('#pdf-zoom').value=['100','150','200'].includes(progress?.zoom)?progress.zoom:'100';
  function render(){
    const zoom=$('#pdf-zoom').value,image=$('#pdf-image');
    saveReadingProgress(source,{page:current,zoom,mode:'original'});
    $('#pdf-page').value=current;$('#pdf-prev').disabled=current===1;$('#pdf-next').disabled=current===total;
    $('#pdf-status').textContent=`正在本机渲染第 ${current} 页…`;$('#pdf-retry').hidden=true;image.hidden=true;
    $('#pdf-canvas').dataset.zoom=zoom;$('#pdf-canvas').scrollTop=0;$('#pdf-canvas').scrollLeft=0;
    image.alt=`${source.name} · PDF 原文第 ${current} 页`;
    image.onload=()=>{if(!image.isConnected)return;image.hidden=false;$('#pdf-status').textContent=`第 ${current}/${total} 页 · 原文件版式预览，文本复制与关键词查找请使用提取文本。`;};
    image.onerror=()=>{if(!image.isConnected)return;$('#pdf-status').textContent='此页预览加载失败，可重新加载或下载 PDF 在本机阅读。';$('#pdf-retry').hidden=false;};
    image.src=`/api/sources/${encodeURIComponent(id)}/pages/${current}?width=${Math.min(2200,Number(zoom)*12)}`;
  }
  bind('#pdf-prev','click',()=>{current--;render();});bind('#pdf-next','click',()=>{current++;render();});
  bind('#pdf-page','change',e=>{current=Math.max(1,Math.min(Math.trunc(Number(e.target.value))||1,total));render();});
  bind('#pdf-zoom','change',render);bind('#pdf-retry','click',render);bind('#pdf-text','click',()=>showSource(id,current,'text'));render();
}
async function showSource(id,page,mode){
  const source=await api(`/sources/${id}`);const meta=source.metadata;
  if(isOriginalPdf(source))return openPaperReader(source,page,mode);
  const link=meta.url&&/^https:\/\/github\.com\//.test(meta.url)?`<a href="${esc(meta.url)}" target="_blank" rel="noopener noreferrer">打开固定版本文件 ↗</a>`:'';
  state.reader={source,offset:0};
  modal(source.name,`<div class="source-meta">${labels[source.kind]} · ${source.chunks.length} 个文本片段${meta.pages?' · '+meta.pages+' 页':''}${meta.size_bytes?' · '+fileSize(meta.size_bytes):''} ${link}<br>${meta.text_pages!==undefined?`可提取文字 ${meta.text_pages}/${meta.pages} 页 · `:''}${meta.characters!==undefined?meta.characters.toLocaleString()+' 字符':''}${esc(meta.notice||'')}${meta.commit?'<br>Commit: '+esc(meta.commit):''}</div><div id="reader-original" class="form-actions">${originalLinks(source,page)}</div>${!source.has_original&&!meta.url?'<p class="modal-copy">此资料没有保存原文件。旧版导入的资料可重新上传同名原文件补齐；教学示例仅提供提取文本。</p>':''}${meta.warnings?.length?`<details class="import-warnings"><summary>${meta.warnings.length} 条解析提示</summary><p>${meta.warnings.map(esc).join('<br>')}</p></details>`:''}<div class="reader-toolbar"><label>页码<input id="reader-page" type="number" min="1" max="${meta.pages||300}" placeholder="全部" value="${Number(page)||''}"></label><label>在提取文本中查找<input id="reader-query" type="search" placeholder="关键词"></label></div><p class="search-hint">以下为可检索的提取文本，版式、图表和公式请打开 PDF 原文核对。</p><div id="reader-content"></div><div class="reader-navigation"><button id="reader-prev" class="outline-button">上一组片段</button><span id="reader-count"></span><button id="reader-next" class="outline-button">下一组片段</button></div><div class="form-actions"><button class="danger-button" data-remove="${esc(source.id)}">移除这份资料</button></div>`);
  bind('#reader-page','input',()=>{state.reader.offset=0;renderReader();});bind('#reader-query','input',()=>{state.reader.offset=0;renderReader();});
  bind('#reader-prev','click',()=>{state.reader.offset=Math.max(0,state.reader.offset-12);renderReader();});bind('#reader-next','click',()=>{state.reader.offset+=12;renderReader();});renderReader();
}
function highlight(text,query){
  // Match literal input before escaping each part; source text never becomes HTML.
  const tokens=(query.match(/[A-Za-z0-9_]+|[\u3400-\u9fff]+/g)||[]).sort((a,b)=>b.length-a.length).slice(0,30);
  if(!tokens.length)return esc(text);
  return text.split(new RegExp('('+tokens.join('|')+')','gi')).map((part,i)=>i%2?'<mark>'+esc(part)+'</mark>':esc(part)).join('');
}
function renderReader(){
  const {source,offset}=state.reader,query=$('#reader-query').value.trim(),page=Number($('#reader-page').value);
  const chunks=source.chunks.filter(c=>(!page||c.page===page)&&(!query||c.text.toLowerCase().includes(query.toLowerCase())));
  $('#reader-original').innerHTML=originalLinks(source,page);
  $('#reader-content').innerHTML=chunks.slice(offset,offset+12).map(c=>`<div class="source-locator">${esc(c.locator)} <button class="text-button" data-bookmark-chunk="${esc(c.id)}">☆ 收藏此段</button></div><pre class="source-text">${highlight(c.text,query)}</pre>`).join('')||'<p class="empty-library">此页或关键词没有匹配的提取文本，可打开原文件检查扫描页或图表。</p>';
  $('#reader-count').textContent=chunks.length?`${offset+1}–${Math.min(offset+12,chunks.length)} / ${chunks.length} 个片段`:'0 个片段';
  $('#reader-prev').disabled=offset===0;$('#reader-next').disabled=offset+12>=chunks.length;
}
async function searchLibrary(){
  const query=$('#fulltext-query').value.trim();if(!query)return;
  const generation=++state.searchGeneration,workspace=state.workspace;
  $('#search-submit').disabled=true;$('#search-results').innerHTML='<p class="loading-copy">正在检索所选范围的原文…</p>';
  try{
    const [results,terms]=await Promise.all([api(`/workspaces/${workspace}/search`,{method:'POST',body:JSON.stringify({query,k:10,kind:$('#search-kind').value,source_ids:state.scope,page_range:state.pageRange})}),api('/query-terms?query='+encodeURIComponent(query))]);
    const expansion=terms.expansion||[];const highlightQuery=query+' '+expansion.flatMap(e=>e.alternatives).join(' ');
    if(generation!==state.searchGeneration||workspace!==state.workspace)return;
    $('#search-results').innerHTML=`<p class="search-summary">${state.pageRange?'精读范围：'+pageRangeLabel(state.pageRange)+'。 ':''}${results.length?`找到 ${results.length} 个相关片段（最多显示 10 个），按相关性排序。`:'未找到相关片段。请检查研究范围，或换用原文中的关键词。'}</p>${expansion.length?`<p class="query-expansion">中文术语对应：${expansion.map(e=>esc(e.term)+' → '+esc(e.alternatives.join(' / '))).join('；')}<br>离线术语检索 · 英文证据保留原文</p>`:''}`+results.map(r=>`<article class="search-hit"><div><strong>${esc(r.name)}</strong><span>${esc(r.locator)}</span></div>${evidencePresentation(r,{id:r.source_id,name:r.name,metadata:r.metadata},highlightQuery,/公式\s*[（(]?\s*\d/.test(query))}<div class="form-actions"><button class="outline-button" data-bookmark-chunk="${esc(r.id)}">☆ 收藏证据</button>${originalLinks({id:r.source_id,name:r.name,metadata:r.metadata},r.page)}<button class="outline-button" data-source="${esc(r.source_id)}" data-page="${r.page||''}">阅读上下文</button></div></article>`).join('');
  }catch(err){if(generation===state.searchGeneration)$('#search-results').innerHTML=`<p class="error-box">${esc(err.message)}</p>`;}
  finally{if(generation===state.searchGeneration)$('#search-submit').disabled=false;}
}
const initialEvidence=$('#evidence-content').innerHTML;
bind('#close-modal','click',()=>$('#modal').close());
bind('#modal','click',e=>{if(e.target===$('#modal')){const r=$('#modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('#modal').close();}});
bind('#workspace-select','change',e=>selectWorkspace(e.target.value));
bind('#new-project','click',()=>{
  modal('创建研究项目','<form id="new-project-form"><label class="form-field">项目名称<input name="name" maxlength="80" required placeholder="例如：扩散模型图像复原" autofocus></label><div class="form-actions"><button class="primary-button" type="submit">创建项目</button></div></form>');
  $('#new-project-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{const workspace=await api('/workspaces',{method:'POST',body:JSON.stringify({name:new FormData(e.target).get('name')})});state.workspaces.unshift(workspace);renderWorkspaceOptions();$('#modal').close();await selectWorkspace(workspace.id);}catch(err){toast(err.message);}finally{button.disabled=false;}});
});
bind('#load-demo','click',e=>loadDemo(e.currentTarget));bind('#load-demo-side','click',e=>loadDemo(e.currentTarget));
bind('#upload-paper','click',()=>chooseFiles());bind('#library-upload','click',()=>chooseFiles());bind('#upload-log','click',()=>chooseFiles('log'));
bind('#file-input','change',async e=>{
  const files=[...e.target.files],workspace=state.workspace,kind=uploadKind;
  e.target.value='';if(!files.length||state.uploading)return;
  const limits=state.health.limits;if(!limits){toast('上传配置未就绪，请刷新页面。');return;}
  const workspaceName=state.workspaces.find(w=>w.id===workspace)?.name||workspace;
  const batch=files.map(file=>({name:file.name,size:file.size,workspace,workspaceName,status:'queued',progress:0,message:'目标项目：'+workspaceName}));
  state.uploads.push(...batch);state.showFinished=true;
  state.uploading=true;renderUploads();scheduleImports();$('#upload-panel').scrollIntoView({block:'start',behavior:'smooth'});
  try{
    for(const [index,file] of files.entries()){
      const item=batch[index];
      if(file.size>limits.max_upload_bytes){item.status='error';item.message=`文件大小 ${fileSize(file.size)}，超过当前 ${limits.max_upload_mb} MB 上限，尚未发送。可在 .env 设置 RP_MAX_UPLOAD_MB 后重启服务并刷新页面。`;renderUploads();continue;}
      item.status='sending';item.message='开始上传…';renderUploads();
      try{
        const result=await uploadFile(workspace,file,kind,item);item.jobId=result.id;
        if(workspace===state.workspace){state.imports=[result,...state.imports.filter(j=>j.id!==result.id)];scheduleImports();}
      }catch(err){item.status='error';item.message=err.message;}
      renderUploads();
    }
  }finally{state.uploading=false;renderUploads();}
  try{await refresh();}catch(err){state.importError=err.message;renderUploads();scheduleImports();}
});
bind('#clear-uploads','click',()=>{state.showFinished=!state.showFinished;renderUploads();});
bind('#clear-scope','click',()=>{state.scope=[];saveScope();});
bind('#search-form','submit',e=>{e.preventDefault();return searchLibrary();});
document.addEventListener('change',e=>{
  const id=e.target.dataset.scope;if(!id)return;
  if(e.target.checked){if(state.scope.length>=50){e.target.checked=false;toast('最多选择 50 份资料。');return;}state.scope.push(id);}else state.scope=state.scope.filter(s=>s!==id);
  saveScope();
});
bind('#import-repo','click',()=>{
  modal('连接 GitHub 仓库','<p class="modal-copy">只读取公开仓库的文本文件，固定默认分支的提交版本。导入需要网络，最多读取 20 个文件；不会执行仓库代码。</p><form id="repo-form"><label class="form-field">仓库地址<input name="url" type="url" placeholder="https://github.com/owner/repository" required></label><div class="form-actions"><button class="primary-button" type="submit">分析并导入</button></div></form>');
  $('#repo-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;button.textContent='正在读取仓库…';try{const result=await api(`/workspaces/${state.workspace}/repository`,{method:'POST',body:JSON.stringify({url:new FormData(e.target).get('url')})});$('#modal').close();await refresh();toast(`导入 ${result.sources.length} 个文件 · ${result.commit.slice(0,8)}。${result.warnings.join('；')}`);}catch(err){toast(err.message);}finally{button.disabled=false;button.textContent='分析并导入';}});
});
bind('#task-form','submit',async e=>{e.preventDefault();const prompt=$('#prompt').value.trim();if(!prompt)return;const workspace=state.workspace;$('#submit-task').disabled=true;try{const result=await api(`/workspaces/${workspace}/tasks`,{method:'POST',body:JSON.stringify({prompt,intent:state.intent,source_ids:state.scope,page_range:state.pageRange})});if(workspace!==state.workspace)return;$('#prompt').value='';await openTask(result.id);}catch(err){$('#submit-task').disabled=false;throw err;}});
bind('#prompt','keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'&&!$('#submit-task').disabled)$('#task-form').requestSubmit();});
bind('#cancel-task','click',async()=>{if(state.task){const task=await api(`/tasks/${state.task.id}/cancel`,{method:'POST'});renderTask(task);await refresh();}});
bind('#back-home','click',home);bind('#source-filter','input',renderLibrary);
bind('#maintenance-nav','click',showMaintenance);
bind('#account-nav','click',showAccount);
bind('#resources-nav','click',showResources);
bind('#settings-button','click',()=>{
  modal('运行配置',`<div class="form-actions"><button id="maintenance-button" class="outline-button">本机自检与完整备份</button></div><div class="config-line"><span>当前模式</span><strong>${state.health.mode==='offline'?'离线演示 / 无 API 调用':'LLM Agent'}</strong></div><div class="config-line"><span>检索方式</span><strong>${esc(state.health.retrieval)}</strong></div><div class="config-line"><span>模型</span><strong>${esc(state.health.model||'未配置')}</strong></div><p class="modal-copy">离线模式使用真实文本解析、BM25 检索和规则诊断，不进行生成式推理。你的资料和任务保存在项目目录 data 中。</p><p class="modal-copy">以后启用模型：复制项目中的 .env.example 为 .env，填写服务地址、模型名称和密钥，再重启服务。密钥仅在服务端读取，不需要填写到网页。</p><pre class="config-code">RP_MODE=llm\nRP_API_BASE=你的兼容接口地址（含 /v1）\nRP_API_KEY=在本机填写\nRP_MODEL=支持工具调用的模型名称\nRP_EMBED_MODEL=可选的向量模型</pre><p class="modal-copy">开启模型后，相关问题和检索片段会发送到你配置的模型服务；启用 Embedding 时，导入资料也会发送给该服务。当前应用仅供本机单用户使用。</p>`);
  bind('#maintenance-button','click',showMaintenance);
});
document.addEventListener('click',async e=>{try{
  const view=e.target.closest('[data-view]');if(view){switchView(view.dataset.view);return;}
  if(e.target.closest('[data-edit-page-range]')){editPageRange();return;}
  if(e.target.closest('[data-clear-page-range]')){clearPageRange();return;}
  const intent=e.target.closest('[data-intent]');if(intent){if(state.pageRange&&intent.dataset.intent!=='qa'){toast('精读页码仅用于问答，请先点击「恢复全文」再切换任务类型。');return;}state.intent=intent.dataset.intent;document.querySelectorAll('.intent').forEach(b=>b.classList.toggle('active',b===intent));$('#prompt').placeholder={qa:'你想了解什么？例如：这篇论文使用了什么方法与训练目标？',plan:'描述复现目标，例如：结合论文和代码，整理环境、数据、权重与验证步骤。',diagnose:'上传运行日志后，描述问题发生时的操作和环境。'}[state.intent];if(state.intent==='plan'&&!$('#prompt').value)$('#prompt').value='结合论文与代码，制定一份有依据的复现计划。';if(state.intent==='diagnose'&&!$('#prompt').value)$('#prompt').value='分析运行日志，列出错误依据、候选原因与排查步骤。';return;}
  const cancelImport=e.target.closest('[data-cancel-import]');if(cancelImport){cancelImport.disabled=true;await api(`/imports/${cancelImport.dataset.cancelImport}/cancel`,{method:'POST'});await refresh();return;}
  const preview=e.target.closest('[data-preview-source]');if(preview){await showPreview(preview.dataset.previewSource,Number(preview.dataset.previewPage)||1);return;}
  const source=e.target.closest('[data-source]');if(source){await showSource(source.dataset.source,Number(source.dataset.page)||null);return;}
  const task=e.target.closest('[data-task]');if(task){await openTask(task.dataset.task);return;}
  const cite=e.target.closest('[data-cite],[data-evidence]');if(cite){showEvidence(cite.dataset.cite||cite.dataset.evidence);return;}
  const remove=e.target.closest('[data-remove]');if(remove){const id=remove.dataset.remove;modal('移除资料','<p class="modal-copy">将从当前资料库和检索索引移除这份资料。已有任务报告中的证据快照会保留。重新上传原文件可恢复到资料库。</p><div class="form-actions"><button id="confirm-remove" class="danger-button">确认移除</button></div>');bind('#confirm-remove','click',async()=>{await api('/sources/'+id,{method:'DELETE'});$('#modal').close();await refresh();toast('已移除资料。');});}
}catch(err){toast(err.message);}});
async function init(){
  try{[state.health,state.workspaces]=await Promise.all([api('/health'),api('/workspaces')]);
    $('#mode-badge').textContent=state.health.mode==='offline'?'◉ 离线演示':'◉ LLM Agent';$('#composer-mode').textContent=state.health.mode==='offline'?'离线证据检索':'模型工具调用';
    $('#upload-limit-label').textContent=state.health.limits?`PDF / Markdown / TXT · 最大 ${state.health.limits.max_upload_mb} MB`:'PDF / Markdown / TXT · 请重启服务更新上传配置';
    if(!state.workspaces.length)state.workspaces=[await api('/workspaces',{method:'POST',body:JSON.stringify({name:'我的科研项目'})})];renderWorkspaceOptions();
    const saved=clientStorage.getItem('researchpilot.workspace');await selectWorkspace(state.workspaces.some(w=>w.id===saved)?saved:state.workspaces[0].id);
  }catch(err){$('#mode-badge').textContent='服务未连接';toast('无法连接后端：'+err.message);$('#submit-task').disabled=true;}
}
startAuth();
