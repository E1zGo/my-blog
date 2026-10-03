'use strict';

const account = {mode:'pending',user:null,csrf:null};
const clientStorage = {
  backend(){return account.mode==='accounts'?sessionStorage:localStorage;},
  key(key){return account.mode==='accounts'?`researchpilot.account.${account.user?.id||'signed-out'}.${key}`:key;},
  getItem(key){return this.backend().getItem(this.key(key));},
  setItem(key,value){this.backend().setItem(this.key(key),value);},
  removeItem(key){this.backend().removeItem(this.key(key));}
};
function clearAccountCache(keepUser=null){
  try{for(const key of Object.keys(sessionStorage))if(key.startsWith('researchpilot.account.')&&(!keepUser||!key.startsWith(`researchpilot.account.${keepUser}.`)))sessionStorage.removeItem(key);}catch{}
}
function broadcastAccountChange(){try{localStorage.setItem('researchpilot.auth-event',Date.now()+':'+Math.random());}catch{}}
window.addEventListener('storage',event=>{if(event.key==='researchpilot.auth-event'){clearAccountCache();location.reload();}});
// Revalidate even when the browser restores a previously authenticated page from bfcache.
window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
function authExpired(){account.expired=true;document.body.classList.add('auth-locked');$('#modal').close();location.reload();}
function draftStorageNotice(){return account.mode==='accounts'?'草稿暂存于当前标签页；退出账号或关闭标签页会清除。请点击保存写入项目。':'草稿已保存在本机浏览器，点击保存后写入研究项目。';}
function accountSetupCopy(){
  return `<p>当前为本机单人模式，无需登录。启用账号后，每位成员只能查看自己的项目；现有项目会归属首次创建的管理员。</p><ol><li>先保存草稿并备份，再停止运行中的服务。</li><li>在项目目录的 PowerShell 运行下方命令，输入你自己的管理员密码。</li><li>在 <code>.env</code> 中添加 <code>RP_AUTH_MODE=accounts</code>，再运行 <code>start.bat</code>。</li></ol><pre class="config-code">.\\.venv\\Scripts\\python.exe -m researchpilot.accounts create-admin --username admin</pre><p>密码至少 15 个字符，可使用便于记忆的长句。原有论文、笔记和任务都会保留。账号模式仍运行在本机；网络部署需要另行配置 HTTPS。</p>`;
}
async function authRequest(path,body){
  const response=await fetch('/api/auth/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const payload=await response.json();
  if(!response.ok)throw new Error(typeof payload.detail==='string'?payload.detail:'请检查用户名、密码与邀请码格式。');
  return payload;
}
function loginScreen(register=false){
  $('#auth-content').innerHTML=`<span class="eyebrow">YOUR RESEARCH COMPANION</span><h1>${register?'加入研究工作台':'欢迎回到研究工作台'}</h1><p>登录后继续阅读、检索与记录。研究资料按账号分别保存。</p><form id="auth-form"><label class="form-field">用户名<input id="auth-username" name="username" autocomplete="username" required minlength="3" maxlength="40" placeholder="3–40 位英文字母或数字等"></label><label class="form-field">密码<input id="auth-password" name="password" type="password" autocomplete="${register?'new-password':'current-password'}" required ${register?'minlength="15"':''} maxlength="128" placeholder="${register?'至少 15 个字符':'输入你的密码'}"></label>${register?'<label class="form-field">邀请码<input id="auth-invitation" name="invitation" autocomplete="off" required maxlength="128" placeholder="由管理员提供，仅可使用一次"></label>':''}<p id="auth-error" class="error-box" role="alert" hidden></p><button id="auth-submit" class="primary-button" type="submit">${register?'创建账号并登录':'登录'}</button></form><button id="auth-toggle" class="text-button">${register?'已有账号，返回登录':'有邀请码？创建账号'}</button><p class="auth-footnote">登录有效期为 12 小时。忘记密码请联系本机管理员重置。</p>`;
  $('#auth-toggle').addEventListener('click',()=>loginScreen(!register));
  $('#auth-form').addEventListener('submit',async event=>{
    event.preventDefault();$('#auth-submit').disabled=true;$('#auth-error').hidden=true;
    try{
      const body={username:$('#auth-username').value,password:$('#auth-password').value};
      if(register)body.invitation=$('#auth-invitation').value;
      await authRequest(register?'register':'login',body);
      clearAccountCache();broadcastAccountChange();location.reload();
    }catch(error){$('#auth-error').textContent=error.message;$('#auth-error').hidden=false;$('#auth-submit').disabled=false;}
  });
}
async function startAuth(){
  try{
    const response=await fetch('/api/auth/status');
    if(!response.ok)throw new Error('无法读取登录状态，请检查本机服务后重试。');
    const result=await response.json();account.mode=result.mode;account.user=result.user;account.csrf=result.csrf_token;
    if(result.configuration_error){$('#auth-content').innerHTML='<h1>需要开启账号模式</h1><p>此数据目录已有账号，匿名访问已关闭。请在 .env 中设置 RP_AUTH_MODE=accounts，再重启服务。</p>';return;}
    if(result.setup_required){$('#auth-content').innerHTML='<h1>设置第一个管理员</h1>'+accountSetupCopy().replace('当前为本机单人模式，无需登录。','账号模式已配置，尚未创建管理员。');return;}
    if(account.mode==='accounts'&&!account.user){loginScreen();return;}
    if(account.mode==='accounts')clearAccountCache(account.user.id);
    $('#account-nav-label').textContent=account.user?account.user.username:'账号与权限';
    $('#maintenance-nav').hidden=account.mode==='accounts'&&account.user.role!=='admin';
    $('.profile strong').textContent=account.user?account.user.username:'个人研究空间';
    await init();
    if(!account.expired){$('#auth-screen').hidden=true;document.body.classList.remove('auth-locked');}
  }catch(error){$('#auth-content').innerHTML=`<h1>工作台尚未连接</h1><p role="alert">${esc(error.message)}</p><button id="auth-retry" class="primary-button">重新连接</button>`;$('#auth-retry').addEventListener('click',()=>location.reload());}
}
async function showAccount(){
  if(account.mode==='local'){modal('账号与项目权限',accountSetupCopy());return;}
  modal('账号与项目权限',`<p class="modal-copy"><strong>${esc(account.user.username)}</strong> · ${account.user.role==='admin'?'管理员':'成员'} · 每个账号分别管理自己的项目</p><form id="password-form"><h3>修改密码</h3><label class="form-field">当前密码<input id="current-password" type="password" autocomplete="current-password" maxlength="128" required></label><label class="form-field">新密码<input id="new-password" type="password" autocomplete="new-password" minlength="15" maxlength="128" required></label><button class="outline-button" type="submit">更新密码</button><p class="search-hint">修改后，其他登录会话立即失效。</p></form>${account.user.role==='admin'?'<section class="account-members"><h3>邀请与成员</h3><p class="modal-copy">邀请只能创建普通成员，24 小时内有效且仅可使用一次。管理员可停用成员，并下载包含所有账号资料的完整备份。</p><button id="create-invitation" class="outline-button">生成邀请码</button><div id="invitation-result"></div><div id="account-users" aria-live="polite">正在读取成员…</div></section>':''}<div class="account-signout"><p class="modal-copy">退出会清除浏览器中的账号草稿与阅读进度。请先保存尚未提交的笔记和实验记录；已保存的项目资料会保留。</p><button id="account-logout" class="outline-button">退出登录</button></div>`);
  bind('#password-form','submit',async event=>{
    event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;
    try{const result=await api('/auth/password',{method:'POST',body:JSON.stringify({current_password:$('#current-password').value,new_password:$('#new-password').value})});account.csrf=result.csrf_token;$('#password-form').reset();broadcastAccountChange();toast('密码已更新，其他会话已失效。');}finally{button.disabled=false;}
  });
  bind('#account-logout','click',async()=>{await api('/auth/logout',{method:'POST'});clearAccountCache();broadcastAccountChange();authExpired();});
  if(account.user.role==='admin'){
    bind('#create-invitation','click',async()=>{
      $('#create-invitation').disabled=true;
      try{const result=await api('/admin/invitations',{method:'POST'});$('#invitation-result').innerHTML=`<label class="form-field">邀请码（关闭后不再显示）<input readonly value="${esc(result.invitation)}" aria-label="新生成的邀请码"></label><p class="search-hint">有效期至 ${esc(new Date(result.expires_at*1000).toLocaleString('zh-CN'))}，请自行交给受邀成员。</p>`;}finally{$('#create-invitation').disabled=false;}
    });
    await renderAccountUsers();
  }
}
async function renderAccountUsers(){
  const users=await api('/admin/users');if(!$('#account-users'))return;
  $('#account-users').innerHTML=users.map(user=>`<div class="account-user"><span><strong>${esc(user.username)}</strong><small>${user.role==='admin'?'管理员':user.active?'成员 · 正常':'成员 · 已停用'}</small></span>${user.role==='member'?`<button class="text-button" data-account-id="${esc(user.id)}" data-account-active="${user.active?'false':'true'}">${user.active?'停用':'启用'}</button>`:''}</div>`).join('');
  $('#account-users').querySelectorAll('[data-account-id]').forEach(button=>button.addEventListener('click',async()=>{
    button.disabled=true;
    try{await api('/admin/users/'+encodeURIComponent(button.dataset.accountId),{method:'PATCH',body:JSON.stringify({active:button.dataset.accountActive==='true'})});await renderAccountUsers();}catch(error){toast(error.message);button.disabled=false;}
  }));
}
