'use strict';

async function showMaintenance(){
  modal('本机自检与完整备份','<p role="status">正在检查数据库与已保存原文件…</p>');
  try{
    const report=await api('/maintenance/status');
    if(!$('#modal').open||$('#modal-title').textContent!=='本机自检与完整备份')return;
    const counts=report.counts;
    const items=checks=>checks.map(c=>`<li><strong>${c.status==='ok'?'✓':c.status==='warning'?'提示':'待处理'} · ${esc(c.name)}</strong><span>${esc(c.message)}</span></li>`).join('');
    $('#modal-body').innerHTML=`<p class="modal-copy">ResearchPilot ${esc(report.version)} · ${report.mode==='offline'?'离线模式':'模型模式'}</p>${counts?`<p class="modal-copy">${counts.workspaces} 个项目 · ${counts.sources} 份资料 · ${counts.tasks} 条任务 · ${counts.notes} 条笔记 · ${counts.experiments} 条实验记录</p>`:''}<ul class="maintenance-checks">${items(report.checks.filter(c=>c.area!=='environment'))}</ul><details><summary>运行环境详情</summary><ul class="maintenance-checks">${items(report.checks.filter(c=>c.area==='environment'))}</ul></details><div class="form-actions">${report.backup_ready?'<a class="primary-button" href="/api/maintenance/backup" target="_blank" rel="noopener" download>下载完整备份 ZIP</a>':'<span class="search-hint">请处理以上错误或等待任务结束后再备份。</span>'}<button id="refresh-maintenance" class="outline-button">重新检查</button></div><p class="modal-copy">备份包含所有项目的数据库、已保存原文件、任务、笔记和实验记录，包括回收站。生成后开始下载；大资料库需要等待并预留磁盘空间。</p><p class="modal-copy">浏览器中的未保存草稿、阅读进度和本机模型配置不在备份内，请先保存重要笔记。账号模式会包含所有账号的资料与密码哈希，但不保留登录会话和邀请码。恢复后需要重新登录。请将备份存到可信位置。</p><details><summary>如何校验和恢复备份</summary><p class="modal-copy">在项目目录运行下列命令。恢复目标必须是新目录；先检查恢复结果，再停止服务并将 .env 中 RP_DATA_DIR 改为新目录后重启。</p><pre class="config-code">.\\.venv\\Scripts\\python.exe -m researchpilot.maintenance verify "备份文件.zip"\n.\\.venv\\Scripts\\python.exe -m researchpilot.maintenance restore "备份文件.zip" --to "data-restored"\n.\\.venv\\Scripts\\python.exe -m researchpilot.maintenance doctor --data-dir "data-restored"</pre></details>`;
    bind('#refresh-maintenance','click',showMaintenance);
  }catch(error){if($('#modal').open&&$('#modal-title').textContent==='本机自检与完整备份')$('#modal-body').innerHTML=`<p class="error-box">${esc(error.message)}</p>`;}
}
