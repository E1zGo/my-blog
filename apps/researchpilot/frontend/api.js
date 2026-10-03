'use strict';
(async()=>{
  const root=document.getElementById('api-list');
  try{
    const response=await fetch('/openapi.json');if(!response.ok)throw new Error('接口规范读取失败');
    const schema=await response.json();root.textContent='';
    for(const [path,methods] of Object.entries(schema.paths))for(const [method,operation] of Object.entries(methods)){
      const section=document.createElement('section');section.className='api-operation';
      const title=document.createElement('h2');title.textContent=method.toUpperCase()+' '+path;section.append(title);
      const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent=operation.summary||'接口详情';details.append(summary);
      const pre=document.createElement('pre');pre.className='source-text';pre.textContent=JSON.stringify(operation,null,2);details.append(pre);section.append(details);root.append(section);
    }
    const models=document.createElement('h2');models.textContent='输入与输出数据模型';root.append(models);
    const pre=document.createElement('pre');pre.className='source-text';pre.textContent=JSON.stringify(schema.components?.schemas||{},null,2);root.append(pre);
  }catch(error){root.textContent=error.message;}
})();
