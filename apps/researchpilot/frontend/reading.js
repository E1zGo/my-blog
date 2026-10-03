'use strict';

function pageRangeLabel(range){return range?(range.start===range.end?`第 ${range.start} 页`:`第 ${range.start}–${range.end} 页`):'全文';}
function readingKey(source){return 'researchpilot.reading.'+source.workspace_id+'.'+source.id;}
function readingProgress(source){
  try{const p=JSON.parse(clientStorage.getItem(readingKey(source))||'null');
    return p&&Number.isInteger(p.page)&&p.page>=1&&p.page<=(source.metadata?.pages||300)?p:null;
  }catch{return null;}
}
function saveReadingProgress(source,values){
  try{clientStorage.setItem(readingKey(source),JSON.stringify({...readingProgress(source),...values}));return true;}catch{return false;}
}
function readingHint(source){const p=readingProgress(source);return p?` · 上次读到第 ${p.page} 页`:'';}
function singlePaper(){return state.scope.length===1?state.sources.find(s=>s.id===state.scope[0]&&s.kind==='paper'):null;}
function activatePageRange(source,range,ask=false){
  if(source.workspace_id!==state.workspace)throw new Error('研究项目已切换，请重新打开论文。');
  if(ask&&['queued','running'].includes(state.task?.status))throw new Error('请等待当前任务完成，或先停止当前任务。');
  state.scope=[source.id];state.pageRange=range;state.intent='qa';
  document.querySelectorAll('.intent').forEach(b=>b.classList.toggle('active',b.dataset.intent==='qa'));
  $('#prompt').placeholder=`仅询问 ${source.name} ${pageRangeLabel(range)} 中的内容…`;
  $('#search-kind').value='paper';saveScope(true);
  if(ask){$('#modal').close();home();$('#prompt').focus();}
}
function editPageRange(){
  const source=singlePaper();if(!source)throw new Error('先在资料库中只选择一篇论文。');
  const range=state.pageRange||{start:1,end:source.metadata.pages||1},workspace=state.workspace;
  modal('限定论文页码',`<p class="modal-copy">${esc(source.name)} · 按 PDF 文件页序计数。检索与新问答仅使用选中页，跨页公式请包括其前后页。</p><form id="page-range-form"><div class="page-range-inputs"><label class="form-field">起始页<input name="start" type="number" min="1" max="${source.metadata.pages||300}" value="${range.start}" required></label><label class="form-field">结束页<input name="end" type="number" min="1" max="${source.metadata.pages||300}" value="${range.end}" required></label></div><p id="page-range-error" class="error-box" hidden></p><div class="form-actions"><button class="primary-button" type="submit">应用页码范围</button></div></form>`);
  bind('#page-range-form','submit',e=>{
    e.preventDefault();const form=new FormData(e.target),start=Number(form.get('start')),end=Number(form.get('end'));
    if(workspace!==state.workspace)throw new Error('项目已切换，请重新选择范围。');
    if(!Number.isInteger(start)||!Number.isInteger(end)||start<1||end<start||end>(source.metadata.pages||300)){$('#page-range-error').textContent='请输入有效的起止页码，起始页不能大于结束页。';$('#page-range-error').hidden=false;return;}
    activatePageRange(source,{start,end});$('#modal').close();toast('已限定 '+pageRangeLabel(state.pageRange)+'；检索和下一次问答均使用此范围。');
  });
}
function clearPageRange(){state.pageRange=null;saveScope(true);$('#prompt').placeholder='你想了解什么？例如：这篇论文使用了什么方法与训练目标？';}
function startPageNote(source,page){
  if(source.workspace_id!==state.workspace)throw new Error('项目已切换，请重新打开论文。');
  if(notebook.saving)throw new Error('笔记正在保存，请稍候。');
  const existing=readNoteDraft(state.workspace);
  $('#modal').close();switchView('notebook');
  if(existing){showNoteEditor(existing);toast('已有未保存草稿，请先保存或放弃，再创建本页笔记。');return;}
  showNoteEditor({workspace:state.workspace,title:(source.name+` · 第 ${page} 页`).slice(0,120),body:'',category:'general',source_id:source.id,source_name:source.name,source_page:page});
}
