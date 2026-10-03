'use strict';

function isOriginalPdf(source){
  return source && (source.has_original??Boolean(source.metadata?.original_id)) && /\.pdf$/i.test(source.metadata?.filename||source.name);
}
function structureLabel(chunk){
  const s=chunk.structure||{};
  return [s.section,s.order?'段落 '+s.order:'',s.continued?'长段续文':'',s.partial?'页内节选，结合上下文阅读':''].filter(Boolean).join(' · ');
}
function paperText(chunk,query=''){
  const s=chunk.structure||{},body=`<div class="paper-prose">${highlight(chunk.text,query)}</div>`;
  if(s.type==='visual')return `<details class="paper-extracted"><summary>公式 / 图表提取文本（可能缺失排版，展开复制）</summary>${body}</details>`;
  return body+(s.math?'<p class="search-hint">含数学符号，分式和上下标请在原版页面中核对。</p>':'');
}
function evidencePresentation(chunk,source,query='',preview=false){
  if(chunk.kind!=='paper' && !chunk.structure?.type)return `<pre class="source-text">${highlight(chunk.text,query)}</pre>`;
  const original=isOriginalPdf(source),page=Number(chunk.page)||1;
  const picture=original&&preview?`<figure class="paper-evidence-original"><figcaption>原版第 ${page} 页 · 公式与图表保留 PDF 排版</figcaption><a href="/api/sources/${encodeURIComponent(source.id)}/original#page=${page}" target="_blank" rel="noopener"><img class="paper-page-image" src="/api/sources/${encodeURIComponent(source.id)}/pages/${page}?width=1600" alt="${esc(source.name)} 第 ${page} 页原版；可使用下方原文按钮放大"></a></figure>`:'';
  const text=picture&&chunk.structure?.math&&chunk.structure?.type!=='visual'?`<details class="paper-extracted"><summary>展开提取文本（用于检索和复制，公式以原版为准）</summary>${paperText(chunk,query)}</details>`:paperText(chunk,query);
  return `<p class="paper-section">${esc(structureLabel(chunk))}</p>${picture}${text}${!original&&chunk.structure?.math?'<p class="search-hint">原文件不可用，请重新上传 PDF 查看公式排版。</p>':''}`;
}

function openPaperReader(source,page,initialMode){
  const total=source.metadata.pages||1,saved=readingProgress(source);
  let current=Math.max(1,Math.min(Number(page)||saved?.page||1,total)),mode=(initialMode||(!page?saved?.mode:null))==='text'?'text':'original';
  const sections=[];
  for(const c of source.chunks){const section=c.structure?.section;if(section&&!sections.some(s=>s.name===section))sections.push({name:section,page:c.page});}
  modal(source.name,`<p class="source-meta">${total} 页 · ${source.chunks.length} 个片段 · ${source.metadata.paper_index_version?'已整理段落与英文断词':'旧版索引，可更新改善片段'} · 原版阅读保留公式、图表和双栏排版</p><div class="paper-reader-tabs" role="group" aria-label="阅读方式"><button id="paper-original-mode" class="outline-button" aria-pressed="true">原版阅读</button><button id="paper-text-mode" class="outline-button" aria-pressed="false">整理文本</button></div><div class="pdf-toolbar"><button id="paper-prev" class="outline-button">← 上一页</button><label>页码 <input id="paper-page" type="number" min="1" max="${total}" value="${current}"></label><span>/ ${total}</span><button id="paper-next" class="outline-button">下一页 →</button><select id="paper-section" aria-label="跳转章节"><option value="">跳转章节</option>${sections.map(s=>`<option value="${s.page}">${esc(s.name)}</option>`).join('')}</select></div><label id="paper-find-label" class="form-field" hidden>在本页整理文本中查找<input id="paper-find" type="search" placeholder="输入原文关键词"></label><div class="paper-reading-actions"><button id="paper-ask-page" class="primary-button">问当前页</button><button id="paper-note-page" class="outline-button">写本页笔记</button><span id="paper-progress-note" class="search-hint"></span></div><div id="paper-content"></div><div id="paper-actions" class="form-actions"></div><p id="paper-index-status" class="search-hint" role="status"></p><div class="form-actions"><button id="paper-reindex" class="outline-button">更新论文索引</button><button class="danger-button" data-remove="${esc(source.id)}">移除这份资料</button></div>`);
  $('#modal').classList.add('pdf-viewer');
  function render(){
    const saved=saveReadingProgress(source,{page:current,mode});$('#paper-progress-note').textContent=`第 ${current} 页 · `+(saved?'阅读位置保存在此浏览器':'浏览器存储不可用，本次阅读位置未保存');
    $('#paper-page').value=current;$('#paper-prev').disabled=current===1;$('#paper-next').disabled=current===total;
    $('#paper-original-mode').setAttribute('aria-pressed',String(mode==='original'));$('#paper-text-mode').setAttribute('aria-pressed',String(mode==='text'));
    $('#paper-actions').innerHTML=originalLinks(source,current);$('#paper-find-label').hidden=mode!=='text';
    if(mode==='original'){
      $('#paper-content').innerHTML=`<p id="paper-page-status" class="search-hint" role="status">正在加载第 ${current} 页原版…</p><div class="paper-page-scroll" tabindex="0" aria-label="原版页面滚动区域"><img id="paper-page-image" class="paper-page-image" alt="${esc(source.name)} 第 ${current} 页原版"></div>`;
      const img=$('#paper-page-image'),status=$('#paper-page-status');
      img.onload=()=>{if(img.isConnected)status.textContent=`第 ${current} / ${total} 页 · 下方「查看 PDF 原文」可放大；切换「整理文本」可复制与收藏。`;};
      img.onerror=()=>{if(img.isConnected)status.textContent='原版加载失败，请切换页码重试或下载原文件。';};
      img.src=`/api/sources/${encodeURIComponent(source.id)}/pages/${current}?width=1600`;
    }else{
      const query=$('#paper-find').value.trim();const chunks=source.chunks.filter(c=>c.page===current&&(!query||c.text.toLowerCase().includes(query.toLowerCase())));
      $('#paper-content').innerHTML='<p class="search-hint">按原文提取顺序排列；英文断行已合并。复杂排版请对照原版，长段续文会单独标记。</p>'+chunks.map(c=>`<article class="paper-paragraph"><div class="source-locator">${esc(c.locator)} · ${esc(structureLabel(c))}<button class="text-button" data-bookmark-chunk="${esc(c.id)}">☆ 收藏此段</button></div>${paperText(c,query)}</article>`).join('')+(chunks.length?'':'<p class="empty-library">本页没有匹配文字，请清空关键词或查看原版。</p>');
    }
  }
  bind('#paper-ask-page','click',()=>activatePageRange(source,{start:current,end:current},true));
  bind('#paper-note-page','click',()=>startPageNote(source,current));
  bind('#paper-find','input',render);
  bind('#paper-original-mode','click',()=>{mode='original';render();});bind('#paper-text-mode','click',()=>{mode='text';render();});
  bind('#paper-prev','click',()=>{current--;render();});bind('#paper-next','click',()=>{current++;render();});
  bind('#paper-page','change',e=>{current=Math.max(1,Math.min(Math.trunc(Number(e.target.value))||1,total));render();});
  bind('#paper-section','change',e=>{if(e.target.value){current=Number(e.target.value);render();}});
  bind('#paper-reindex','click',async e=>{
    const button=e.currentTarget,status=$('#paper-index-status');button.disabled=true;
    try{const job=await api(`/sources/${source.id}/reindex`,{method:'POST'});status.textContent='已加入导入队列。完成后重新打开论文即可使用新索引；历史任务和笔记快照保留。';state.showFinished=true;await refresh();toast(job.message||'正在更新论文索引');}
    catch(err){button.disabled=false;throw err;}
  });
  render();
}
