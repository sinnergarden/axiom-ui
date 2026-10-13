'use strict';
(() => {
  const $ = id => document.getElementById(id), frame = $('workbench');
  const endpoint = new URL(window.AXIOM_RESULTS_ENDPOINT).origin;
  const valid = value => typeof value === 'string' && /^[0-9a-f]{64}:[0-9]{1,9}$/.test(value);
  const preferenceKey = 'axiom.baseline.' + endpoint;
  let token = '', selected = '', compare = '', controller, generation = 0;
  function baseline() { try { const value = localStorage.getItem(preferenceKey); return valid(value) ? value : ''; } catch { return ''; } }
  function clear(message='已退出登录。') {
    generation++; controller?.abort(); token=''; selected=''; compare='';
    frame.removeAttribute('srcdoc'); frame.hidden=true; $('token').value='';
    $('connection').hidden=false; $('refresh').hidden=$('disconnect').hidden=$('clear-baseline').hidden=true;
    $('status').textContent=message;
  }
  async function load(next=selected, comparison=compare) {
    controller?.abort(); const requestController=new AbortController(); controller=requestController; const active=++generation;
    const timeout=setTimeout(()=>requestController.abort(),600000);
    frame.hidden=true; frame.removeAttribute('srcdoc'); $('status').textContent='正在读取所选保存账户…';
    try {
      const url=new URL('/workbench',endpoint);
      if(next)url.searchParams.set('selected',next);
      if(comparison&&comparison!==next)url.searchParams.set('compare',comparison);
      let response=await fetch(url,{headers:{Authorization:'Bearer '+token},signal:requestController.signal,cache:'no-store',credentials:'omit',redirect:'error',referrerPolicy:'no-referrer'});
      while(response.status===202 && active===generation){
        const job=await response.text();
        if(!/^[0-9a-f]{32}$/.test(job))throw new Error('读取任务无效，请重试。');
        $('status').textContent='正在验证所选保存账户，首次读取可能需要一分钟…';
        await new Promise(resolve=>setTimeout(resolve,2000));
        if(active!==generation)return;
        const poll=new URL('/workbench',endpoint);poll.searchParams.set('job',job);
        response=await fetch(poll,{headers:{Authorization:'Bearer '+token},signal:requestController.signal,cache:'no-store',credentials:'omit',redirect:'error',referrerPolicy:'no-referrer'});
      }
      if(active!==generation)return;
      if(response.status===401){clear('登录已失效，请重新登录。');return;}
      if(!response.ok)throw new Error(response.status===409?'账户正在读取或读取已结束，请稍后刷新。':response.status===422?'所选保存结果暂不可用。可刷新重试；若基线已删除，请清除基线偏好。':'结果服务暂不可达，请确认 Mac 在线。');
      const html=await response.text(); if(active!==generation)return;
      selected=next;compare=comparison;frame.srcdoc=html;frame.hidden=false;
      $('connection').hidden=true;$('token').value='';$('refresh').hidden=$('disconnect').hidden=$('clear-baseline').hidden=false;
      $('status').textContent='已连接 · 保存结果只读';
    } catch(error){if(active===generation){$('status').textContent=error.message;$('refresh').hidden=$('disconnect').hidden=$('clear-baseline').hidden=false;}}
    finally {clearTimeout(timeout);}
  }
  $('connect').addEventListener('submit',async event=>{
    event.preventDefault();const password=$('token').value;const active=++generation;
    $('status').textContent='正在登录…';
    try {
      const response=await fetch(new URL('/login',endpoint),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password}),cache:'no-store',credentials:'omit',redirect:'error',referrerPolicy:'no-referrer'});
      if(active!==generation)return;
      if(!response.ok){$('status').textContent=response.status===429?'尝试过多，请一分钟后重试。':response.status===401?'密码不正确，请重试。':response.status===409?'请先在 Mac 完成一次密码设置。':'连接不可达，请确认 Mac 在线。';return;}
      const answer=await response.json();if(active!==generation)return;token=answer.token;compare=baseline();await load('',compare);
    }catch{if(active===generation)$('status').textContent='连接不可达，请确认 Mac 在线。';}
  });
  window.addEventListener('message',event=>{
    if(event.source!==frame.contentWindow||event.origin!=='null'||!token||!event.data)return;
    const message=event.data;
    if(message.type==='axiom-ready'&&valid(message.selected)){selected=message.selected;compare=message.compare || '';}
    if(message.type==='axiom-selection'&&valid(message.selected)&&(!message.compare||valid(message.compare)))load(message.selected,message.compare);
    if(message.type==='axiom-baseline'&&(!message.selection||valid(message.selection))){
      try{if(message.selection)localStorage.setItem(preferenceKey,message.selection);else localStorage.removeItem(preferenceKey);}catch{}
      $('status').textContent=message.selection?'已保存此浏览器的基线偏好；没有修改 Research 收藏。':'已清除基线偏好。';
    }
  });
  $('clear-baseline').addEventListener('click',()=>{try{localStorage.removeItem(preferenceKey);}catch{}compare='';load(selected,'');});
  $('refresh').addEventListener('click',()=>load());
  $('disconnect').addEventListener('click',()=>{
    if(token)fetch(new URL('/logout',endpoint),{method:'POST',headers:{Authorization:'Bearer '+token},cache:'no-store',credentials:'omit',redirect:'error'}).catch(()=>{});
    clear();
  });
  window.addEventListener('pagehide',()=>clear());
})();
