'use strict';
const noteCategories={general:'阅读笔记',method:'方法与创新',setup:'实验设置',result:'结果与局限',question:'待验证问题'};
const notebook={workspace:null,notes:[],draft:null,loading:0,saving:false};
const draftKey=workspace=>'researchpilot.note-draft.'+workspace;
function readNoteDraft(workspace){try{const d=JSON.parse(clientStorage.getItem(draftKey(workspace))||'null');return d&&d.workspace===workspace&&typeof d.title==='string'&&typeof d.body==='string'?d:null;}catch{return null;}}
function resetNotebook(){notebook.workspace=state.workspace;notebook.notes=[];notebook.draft=null;notebook.loading++;$('#note-editor').hidden=true;$('#note-editor').innerHTML='';$('#notes-list').innerHTML='';$('#notes-summary').textContent='';$('#note-filter').value='';$('#note-status-filter').value='active';$('#note-category-filter').value='all';draftBadge();}
function draftBadge(){const has=Boolean(readNoteDraft(state.workspace));$('#restore-draft').hidden=!has;$('#export-notes').href=`/api/workspaces/${state.workspace}/notes/export`;}
async function openNotebook(){
  if(!state.workspace)return;
  if(notebook.workspace!==state.workspace)resetNotebook();
  draftBadge();const workspace=state.workspace,generation=++notebook.loading,archived=$('#note-status-filter').value==='trash';
  const notes=await api(`/workspaces/${workspace}/notes?archived=${archived}`);
  if(workspace!==state.workspace||generation!==notebook.loading)return;
  notebook.notes=notes;renderNotebook();
}
function renderNotebook(){
  const query=$('#note-filter').value.trim().toLowerCase(),category=$('#note-category-filter').value;
  const notes=notebook.notes.filter(n=>(category==='all'||n.category===category)&&[n.title,n.body,n.source_name,n.evidence?.text].some(v=>(v||'').toLowerCase().includes(query)));
  const trash=$('#note-status-filter').value==='trash';
  $('#notes-summary').textContent=`${trash?'回收站':'笔记'} ${notes.length} / ${notebook.notes.length} 条`;
  $('#notes-list').innerHTML=notes.length?notes.map(n=>{
    const source=state.sources.find(s=>s.id===n.source_id),e=n.evidence;
    return `<article class="note-card"><div class="note-heading"><span class="note-category">${noteCategories[n.category]}</span><small>${date(n.updated_at)}</small></div><h2>${esc(n.title)}</h2>${n.source_name?`<p class="source-meta">${esc(n.source_name)}${e?' · '+esc(e.locator):n.source_page?' · 第 '+n.source_page+' 页 · 个人笔记':''}${source?'':' · 来源已移除，记录仍保留'}</p>`:''}${e?`<details><summary>原文证据快照</summary><pre class="source-text">${esc(e.text)}</pre></details>`:''}<p class="note-body">${esc(n.body||'尚未添加个人分析。')}</p><div class="form-actions">${!trash?`<button class="outline-button" data-edit-note="${esc(n.id)}">编辑笔记</button>`:''}${source?originalLinks(source,e?.page||n.source_page):''}${source?`<button class="text-button" data-source="${esc(source.id)}" data-page="${e?.page||n.source_page||''}">阅读上下文</button>`:''}<button class="text-button" data-note-archive="${esc(n.id)}" data-note-revision="${n.revision}" data-note-restore="${trash?'true':'false'}">${trash?'恢复笔记':'移入回收站'}</button></div></article>`;
  }).join(''):`<p class="empty-library">${trash?'回收站为空。移入这里的笔记可以恢复。':'还没有匹配的笔记。可以新建笔记，或在检索结果、提取文本和任务引用中收藏证据。'}</p>`;
}
function categoryOptions(value){return Object.entries(noteCategories).map(([key,label])=>`<option value="${key}" ${key===value?'selected':''}>${label}</option>`).join('');}
function draftFromNote(note){return {workspace:state.workspace,id:note.id,revision:note.revision,title:note.title,body:note.body,category:note.category,source_id:note.source_id,source_name:note.source_name,evidence:note.evidence,source_page:note.source_page};}
function persistDraft(){
  const d=notebook.draft;if(!d||!$('#edit-note-form'))return;
  d.title=$('#note-title').value;d.body=$('#note-body').value;d.category=$('#note-category').value;
  if(!d.id&&!d.source_page)d.source_id=$('#note-source').value||null;
  try{clientStorage.setItem(draftKey(d.workspace),JSON.stringify(d));$('#draft-status').textContent=draftStorageNotice();}catch{$('#draft-status').textContent='浏览器无法保存草稿，请及时点击保存笔记。';}
  draftBadge();
}
function showNoteEditor(draft){
  if(notebook.saving){toast('笔记正在保存，请稍候。');return;}
  notebook.draft=draft;
  $('#note-editor').hidden=false;
  const source=state.sources.find(s=>s.id===draft.source_id),e=draft.evidence;
  $('#note-editor').innerHTML=`<form id="edit-note-form"><h2>${draft.id?'编辑研究笔记':'新建研究笔记'}</h2><label class="form-field">笔记标题<input id="note-title" maxlength="120" required value="${esc(draft.title)}" placeholder="例如：训练目标与复现注意事项"></label><div class="note-editor-fields"><label class="form-field">内容类别<select id="note-category">${categoryOptions(draft.category)}</select></label>${!draft.id?`<label class="form-field">关联资料<select id="note-source" ${draft.source_page?'disabled':''}><option value="">项目综合笔记</option>${state.sources.map(s=>`<option value="${esc(s.id)}" ${s.id===draft.source_id?'selected':''}>${esc(s.name)}</option>`).join('')}</select></label>`:`<p class="source-meta">${esc(draft.source_name||'项目综合笔记')}${source||!draft.source_id?'':' · 来源已移除'}</p>`}</div>${draft.source_page?`<p class="search-hint">本页笔记 · 第 ${draft.source_page} 页 · 关联页码已固定，个人分析由你填写，未自动摘录原文。</p>`:''}${e?`<details open><summary>原文证据（保存时的快照） · ${esc(e.locator)}</summary><pre class="source-text">${esc(e.text)}</pre></details>`:''}<label class="form-field">个人分析与待办<textarea id="note-body" rows="8" maxlength="12000" placeholder="研究问题、方法理解、实验设置、局限与下一步…">${esc(draft.body)}</textarea></label><p id="draft-status" class="search-hint"></p><p id="note-save-error" class="error-box" role="alert" hidden></p><div class="form-actions"><button type="button" id="hide-note-editor" class="text-button">收起并保留草稿</button><button type="button" id="discard-note-draft" class="text-button">放弃草稿</button><button type="submit" id="save-note" class="primary-button">保存笔记</button></div></form>`;
  bind('#edit-note-form','input',persistDraft);bind('#edit-note-form','change',persistDraft);bind('#edit-note-form','submit',saveNote);
  bind('#hide-note-editor','click',()=>{persistDraft();$('#note-editor').hidden=true;});
  bind('#discard-note-draft','click',()=>{
    modal('放弃未保存草稿','<p class="modal-copy">将清除当前项目的本机草稿。已保存到项目中的笔记和原文证据仍然保留。</p><div class="form-actions"><button id="confirm-discard-draft" class="danger-button">放弃草稿</button></div>');
    bind('#confirm-discard-draft','click',()=>{clientStorage.removeItem(draftKey(draft.workspace));notebook.draft=null;$('#note-editor').hidden=true;$('#note-editor').innerHTML='';$('#modal').close();draftBadge();});
  });
  persistDraft();$('#note-editor').scrollIntoView({block:'start',behavior:'smooth'});
}
async function editNote(identifier){
  if(notebook.saving){toast('笔记正在保存，请稍候。');return;}
  const draft=readNoteDraft(state.workspace);
  if(draft){showNoteEditor(draft);toast('已恢复未保存草稿。请先保存或放弃草稿，再编辑其他笔记。');return;}
  const workspace=state.workspace,note=await api(`/workspaces/${workspace}/notes/${identifier}`);
  if(workspace===state.workspace)showNoteEditor(draftFromNote(note));
}
async function saveNote(event){
  event.preventDefault();persistDraft();const draft={...notebook.draft},form=event.target;
  const body={title:draft.title,category:draft.category,body:draft.body};
  if(draft.id)body.revision=draft.revision;else{body.source_id=draft.source_id;if(draft.source_page)body.source_page=draft.source_page;}
  notebook.saving=true;for(const element of form.elements)element.disabled=true;$('#note-save-error').hidden=true;
  try{
    await api(`/workspaces/${draft.workspace}/notes${draft.id?'/'+draft.id:''}`,{method:draft.id?'PATCH':'POST',body:JSON.stringify(body)});
    clientStorage.removeItem(draftKey(draft.workspace));
    if(draft.workspace===state.workspace){notebook.draft=null;$('#note-editor').hidden=true;$('#note-editor').innerHTML='';$('#note-status-filter').value='active';$('#note-category-filter').value='all';$('#note-filter').value='';draftBadge();await openNotebook();toast('笔记已保存到本机研究项目。');}
  }catch(err){if(form.isConnected){$('#note-save-error').hidden=false;$('#note-save-error').textContent=err.message;}}
  finally{notebook.saving=false;for(const element of form.elements)element.disabled=false;if(draft.source_page&&form.isConnected&&$('#note-source'))$('#note-source').disabled=true;}
}
async function bookmark(button){
  const workspace=state.workspace,body=button.dataset.bookmarkChunk?{chunk_id:button.dataset.bookmarkChunk}:{task_id:button.dataset.bookmarkTask,citation_label:button.dataset.bookmarkLabel};
  button.disabled=true;
  try{const note=await api(`/workspaces/${workspace}/notes`,{method:'POST',body:JSON.stringify(body)});toast(note.restored?'已从回收站恢复原有笔记。':note.duplicate?'这段证据已收藏，原有分析已保留。':'证据已收藏，可在「研究笔记」中添加分析。');if(workspace===state.workspace&&state.view==='notebook')await openNotebook();}
  finally{if(button.isConnected)button.disabled=false;}
}
bind('#new-note','click',()=>{
  const existing=readNoteDraft(state.workspace);
  showNoteEditor(existing||{workspace:state.workspace,title:'',body:'',category:'general',source_id:state.scope.length===1?state.scope[0]:null});
  if(existing)toast('已恢复当前项目的未保存草稿。');
});
bind('#restore-draft','click',()=>{const draft=readNoteDraft(state.workspace);if(draft)showNoteEditor(draft);});
bind('#refresh-notes','click',openNotebook);bind('#note-filter','input',renderNotebook);bind('#note-category-filter','change',renderNotebook);bind('#note-status-filter','change',openNotebook);
document.addEventListener('click',async event=>{try{
  const bookmarkButton=event.target.closest('[data-bookmark-chunk],[data-bookmark-task]');if(bookmarkButton){await bookmark(bookmarkButton);return;}
  const edit=event.target.closest('[data-edit-note]');if(edit){await editNote(edit.dataset.editNote);return;}
  const archive=event.target.closest('[data-note-archive]');if(archive){
    const workspace=state.workspace,action=archive.dataset.noteRestore==='true'?'restore':'trash';archive.disabled=true;
    try{await api(`/workspaces/${workspace}/notes/${archive.dataset.noteArchive}/${action}`,{method:'POST',body:JSON.stringify({revision:Number(archive.dataset.noteRevision)})});if(workspace===state.workspace){await openNotebook();toast(action==='trash'?'已移入回收站，随时可以恢复。':'笔记已恢复。');}}
    finally{if(archive.isConnected)archive.disabled=false;}
  }
}catch(err){toast(err.message);}});
