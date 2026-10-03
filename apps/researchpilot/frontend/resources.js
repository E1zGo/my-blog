'use strict';

async function showResources(){
  modal('用量与运行状态','<p role="status">正在读取当前账号的用量…</p>');
  try{
    const usage=await api('/resources');
    const managed=account.mode==='local'||account.user?.role==='admin';
    const runtime=managed?await api('/maintenance/runtime'):null;
    if(!$('#modal').open||$('#modal-title').textContent!=='用量与运行状态')return;
    const card=(label,value,limit,format=n=>n)=>`<div class="resource-card"><strong>${esc(label)}</strong><span>${esc(format(value))} / ${esc(format(limit))}</span><progress max="${limit}" value="${Math.min(value,limit)}" aria-label="${esc(label)}"></progress></div>`;
    $('#modal-body').innerHTML=`<p class="modal-copy">${account.mode==='local'?'本机单人空间':'当前账号：'+esc(account.user.username)} · 达到额度时会显示原因，已有资料仍可阅读。</p><div class="resource-grid">${card('研究项目',usage.projects.length,usage.limits.projects)}${card('原文件空间（含预留）',usage.storage_bytes+usage.reserved_bytes,usage.limits.storage_bytes,fileSize)}${card('研究任务占用',usage.active_tasks,usage.limits.active_tasks)}${card('导入任务占用',usage.active_imports,usage.limits.active_imports)}${card('最近 24 小时研究次数',usage.tasks_last_24h,usage.limits.tasks_daily)}</div><p class="search-hint">已保存原文件 ${fileSize(usage.storage_bytes)}，后台导入预留 ${fileSize(usage.reserved_bytes)}。取消中的任务会在实际停止后释放名额；失败或取消的研究任务也计入 24 小时次数。原文件额度不包含数据库、备份和浏览器草稿。</p><details><summary>各项目资料数量</summary><ul class="maintenance-checks">${usage.projects.map(p=>`<li><strong>${esc(p.name)}</strong><span>${p.sources} / ${usage.limits.sources_per_project} 份资料</span></li>`).join('')||'<li>尚无项目</li>'}</ul></details>${runtime?`<section class="runtime-panel"><h3>服务运行状态 · 管理员可见</h3><p>${runtime.ready?'✓ 服务检查通过':'需要处理：服务检查未通过'}</p><ul class="maintenance-checks"><li><span>本次启动已运行 ${Math.floor(runtime.uptime_seconds/60)} 分钟；当前 ${runtime.active_requests} 个请求。</span></li><li><span>全站后台：${runtime.tasks_in_flight} / 10 个研究任务，${runtime.imports_in_flight} / 8 个导入任务。</span></li><li><span>可用磁盘 ${fileSize(runtime.disk_free_bytes)}；停止新增数据的阈值 ${fileSize(runtime.disk_floor_bytes)}。</span></li><li><span>最近 5 分钟、最多 512 次请求：${runtime.recent_requests} 次，服务器错误 ${runtime.recent_errors} 次，P95 耗时 ${runtime.p95_ms===null?'暂无数据':runtime.p95_ms+' ms'}。</span></li></ul><p class="search-hint">统计仅保留在当前进程，重启清零；这里不会自动向外发送告警。</p></section>`:''}<div class="form-actions"><button id="refresh-resources" class="outline-button">刷新用量</button></div>`;
    bind('#refresh-resources','click',showResources);
  }catch(error){if($('#modal-title').textContent==='用量与运行状态')$('#modal-body').innerHTML=`<p class="error-box">${esc(error.message)}</p>`;}
}
