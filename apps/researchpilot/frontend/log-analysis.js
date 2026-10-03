'use strict';
const logView={generation:0,result:null,series:null,point:null};
function resetLogAnalysis(){logView.generation++;logView.result=null;logView.series=null;logView.point=null;$('#log-analysis-result').innerHTML='';$('#analysis-log-source').innerHTML='';$('#log-analysis-panel').open=false;$('#analyze-log').disabled=false;}
function refreshLogChoices(){
  const previous=$('#analysis-log-source').value,logs=state.sources.filter(s=>s.kind==='log');
  $('#analysis-log-source').innerHTML='<option value="">选择日志…</option>'+logs.map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');
  if(logs.some(s=>s.id===previous))$('#analysis-log-source').value=previous;
  else if(logs.length===1)$('#analysis-log-source').value=logs[0].id;
  if(logView.result&&!logs.some(s=>s.id===logView.result.source_id)){logView.generation++;logView.result=null;$('#log-analysis-result').innerHTML='<p class="log-warning">原日志已移除。已保存到实验中的指标来源快照仍保留。</p>';}
}
async function analyzeSelectedLog(){
  const source=$('#analysis-log-source').value,workspace=state.workspace,generation=++logView.generation;
  if(!source){toast('请先选择已导入的日志。');return;}
  logView.result=null;$('#analyze-log').disabled=true;$('#log-analysis-result').innerHTML='<p class="search-hint">正在读取完整日志并提取指标…</p>';
  try{
    const result=await api(`/workspaces/${workspace}/logs/${source}/analysis`,{method:'POST'});
    if(workspace!==state.workspace||generation!==logView.generation)return;
    logView.result=result;
    const findings=result.findings.map(f=>`<article><h3>${esc(f.title)} · L${f.line}</h3><p>${esc(f.matched)}</p><p>${esc(f.advice)}</p><small>${esc(f.certainty)}</small></article>`).join('');
    $('#log-analysis-result').innerHTML=`<div class="log-statistics"><span>已读 ${result.scanned_lines} / ${result.total_lines} 行</span><span>${result.point_count} 个指标点</span><span>${result.series.length} 组序列</span></div>${result.warnings.map(w=>`<p class="log-warning">${esc(w)}</p>`).join('')}${result.series.length?`<div class="log-controls"><label for="log-series">指标序列</label><select id="log-series" aria-label="指标序列">${result.series.map(s=>`<option value="${s.id}">${esc([s.split||'未标注划分',s.name,s.unit||'未标注单位'].join(' · '))}（${s.count} 点）</option>`).join('')}</select></div><div id="log-series-content"></div>`:'<p class="empty-library">未识别到受支持的数值指标。可以参考上方格式示例，或继续手动填写实验结果。</p>'}<details class="log-diagnostics" ${findings?'open':''}><summary>日志错误线索 · ${result.findings.length} 项</summary>${findings||'<p>没有匹配内置报错规则；这不代表运行一定成功。</p>'}</details>`;
    if(result.series.length){bind('#log-series','change',showLogSeries);showLogSeries();}
  }catch(err){if(workspace===state.workspace&&generation===logView.generation)$('#log-analysis-result').innerHTML=`<p class="error-box" role="alert">${esc(err.message)}</p>`;}
  finally{if(generation===logView.generation)$('#analyze-log').disabled=false;}
}
function numberLabel(value){return Number(value.toPrecision(6)).toString();}
function logChart(series,selected){
  const points=series.points,axis=series.axis,xs=points.map(p=>p[axis]),ys=points.map(p=>p.value);
  let xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys);
  if(xmin===xmax){xmin-=.5;xmax+=.5;}
  const pad=(ymax-ymin)*.08||Math.max(Math.abs(ymax)*.05,1e-6);ymin-=pad;ymax+=pad;
  const x=v=>64+(v-xmin)/(xmax-xmin)*540,y=v=>224-(v-ymin)/(ymax-ymin)*190;
  let paths=[],segment=[];
  points.forEach((p,i)=>{if(i&&p[axis]<=points[i-1][axis]){paths.push(segment);segment=[];}segment.push(p);});paths.push(segment);
  const grids=Array.from({length:5},(_,i)=>{const v=ymin+(ymax-ymin)*i/4;return `<line class="log-grid" x1="64" y1="${y(v)}" x2="604" y2="${y(v)}"/><text x="56" y="${y(v)+4}" text-anchor="end">${numberLabel(v)}</text>`;}).join('');
  const pathMarkup=paths.map(ps=>ps.length===1?`<circle class="log-dot" cx="${x(ps[0][axis])}" cy="${y(ps[0].value)}" r="3"/>`:`<polyline class="log-line" points="${ps.map(p=>`${x(p[axis])},${y(p.value)}`).join(' ')}"/>`).join('');
  return `<svg viewBox="0 0 640 280" role="img" aria-label="${esc(series.name)} 随 ${axis} 的变化曲线；所选点位于日志第 ${selected.line} 行"><title>${esc(series.name)} · 原始顺序，无平滑或插值</title>${grids}${pathMarkup}<circle class="log-selected" cx="${x(selected[axis])}" cy="${y(selected.value)}" r="6"/><text x="64" y="248">${numberLabel(xmin)}</text><text x="604" y="248" text-anchor="end">${numberLabel(xmax)}</text><text x="334" y="269" text-anchor="middle">${axis==='line'?'日志行号':axis}</text></svg>`;
}
function showLogSeries(){
  logView.series=logView.result.series.find(s=>s.id===$('#log-series').value);const s=logView.series;
  logView.point=s.points.at(-1);
  $('#log-series-content').innerHTML=`<p class="search-hint">横轴：${s.axis==='line'?'日志行号（坐标未全部填写）':s.axis}；${s.breaks?'重复或回退处断线。':'按日志原始顺序连接。'} 最小/最大只描述数值，不代表最佳结果。</p><div id="log-chart" class="log-chart"></div><div class="log-controls"><label for="log-point-choice">选择原始记录点</label><select id="log-point-choice" aria-label="选择原始记录点">${s.points.map(p=>`<option value="${p.id}" ${p.id===s.last?'selected':''}>L${p.line} · ${s.axis}=${p[s.axis]} · ${p.value} ${esc(s.unit)}</option>`).join('')}</select></div><div class="log-picks"><button type="button" class="text-button" data-log-pick="last">最后记录</button><button type="button" class="text-button" data-log-pick="minimum">最小值</button><button type="button" class="text-button" data-log-pick="maximum">最大值</button></div><div id="log-point-detail"></div>`;
  bind('#log-point-choice','change',showLogPoint);showLogPoint();
}
function showLogPoint(){
  const s=logView.series,p=s.points.find(p=>p.id===$('#log-point-choice').value);logView.point=p;
  $('#log-chart').innerHTML=logChart(s,p);
  $('#log-point-detail').innerHTML=`<div class="log-point"><h3>${esc(s.name)} = ${p.value} ${esc(s.unit)}</h3><p>${esc(logView.result.source_name)} · L${p.line}${p.epoch===null?'':` · epoch=${p.epoch}`}${p.step===null?'':` · step=${p.step}`}</p><pre class="source-text">${esc(logView.result.lines[String(p.line)])}</pre><p>请核对单位、数据划分和评测协议；日志中的数值不代表系统已验证实验。</p><div class="form-actions"><button id="adopt-log-point" type="button" class="primary-button">确认此值，加入实验草稿</button></div></div>`;
  bind('#adopt-log-point','click',adoptLogPoint);
}
function adoptLogPoint(){
  if(journal.saving){toast('实验正在保存，请稍候。');return;}
  if(journal.draft&&$('#experiment-form'))persistExperimentDraft();
  const draft=journal.draft||readExperimentDraft()||newExperiment(),s=logView.series,p=logView.point,result=logView.result;
  const name=[s.split,s.name].filter(Boolean).join('/');
  if(draft.metrics.length>=20){toast('每次实验最多 20 个指标。');return;}
  if(draft.metrics.some(m=>m.name.trim().toLowerCase()===name.toLowerCase())){toast(`草稿中已有 ${name}。请先重命名或移除旧指标，再加入该记录点。`);return;}
  const origin={source_id:result.source_id,checksum:result.checksum,point_id:p.id};
  draft.metrics.push({name,value:p.value,unit:s.unit,split:s.split,protocol:'',origin,_evidence:{...origin,source_name:result.source_name,line:p.line,text:result.lines[String(p.line)]}});
  showExperimentEditor(draft);toast('所选数值已加入实验草稿。补充评测协议后点击「保存实验记录」正式保存。');
}
function renderMetricOrigins(){
  document.querySelectorAll('.metric-editor').forEach((row,i)=>{
    const m=journal.draft.metrics[i];if(!m.origin)return;
    const snapshot=m._evidence||Object.values(journal.draft.metric_evidence||{}).find(e=>e.point_id===m.origin.point_id&&e.source_id===m.origin.source_id&&e.checksum===m.origin.checksum);
    row.querySelector('[data-metric-field="value"]').readOnly=true;
    row.insertAdjacentHTML('afterbegin',`<div class="metric-origin">日志确认值${snapshot?` · ${esc(snapshot.source_name)}:L${snapshot.line}<details><summary>查看原始记录行</summary><pre class="source-text">${esc(snapshot.text)}</pre></details>`:''}<button type="button" class="text-button" data-manual-metric="${i}">改为手动记录</button></div>`);
  });
}
bind('#analyze-log','click',analyzeSelectedLog);bind('#analysis-upload','click',()=>chooseFiles('log'));
bind('#analysis-log-source','change',()=>{logView.generation++;logView.result=null;$('#analyze-log').disabled=false;$('#log-analysis-result').innerHTML='';});
bind('#analysis-demo','click',async()=>{
  const workspace=state.workspace,button=$('#analysis-demo');button.disabled=true;
  try{const source=await api(`/workspaces/${workspace}/logs/demo`,{method:'POST'});if(workspace!==state.workspace)return;await refresh();if(workspace!==state.workspace)return;refreshLogChoices();$('#analysis-log-source').value=source.id;await analyzeSelectedLog();}
  finally{button.disabled=false;}
});
document.addEventListener('click',event=>{
  const pick=event.target.closest('[data-log-pick]');if(pick&&logView.series){$('#log-point-choice').value=logView.series[pick.dataset.logPick];showLogPoint();}
  const manual=event.target.closest('[data-manual-metric]');if(manual&&!journal.saving){experimentFieldsFromDOM();const m=journal.draft.metrics[Number(manual.dataset.manualMetric)];m.origin=null;delete m._evidence;renderMetricEditors();persistExperimentDraft();}
});
