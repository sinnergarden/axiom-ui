'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let endpoint = '', token = '', currentPath = '/', controller, generation = 0;
  const route = path => path === '/' || /^\/result\/[0-9a-f]{64}(?:\/signal\/[0-9]{1,9}\/[0-9]{1,9}|\/account\/[0-9]{1,9})?$/.test(path);
  function clearResults() { $('results').replaceChildren(); }
  function disconnect(message = '已断开连接；访问码和结果已清除。') {
    generation++; controller?.abort(); token = ''; endpoint = ''; currentPath = '/';
    $('token').value = ''; clearResults(); $('connection').hidden = false;
    $('disconnect').hidden = $('navigation').hidden = true; $('status').textContent = message;
  }
  async function load(path = '/', method = 'GET') {
    const url = new URL(path, endpoint);
    if (url.origin !== endpoint || !(route(url.pathname) || method === 'POST' && url.pathname === '/refresh')) return;
    controller?.abort(); const requestController = new AbortController(); controller = requestController; const active = ++generation;
    const timeout = setTimeout(() => requestController.abort(), 60000);
    clearResults(); $('status').textContent = '正在读取保存结果…';
    try {
      const response = await fetch(url.href, {method, headers: {Authorization: `Bearer ${token}`},
        signal: requestController.signal, cache: 'no-store', credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer'});
      if (active !== generation) return;
      if (response.status === 401) { disconnect('未授权：访问码缺失、错误或已失效，请重新连接。'); return; }
      if (response.status === 403) { disconnect('访问被拒绝：服务未允许此页面来源，请检查连接配置。'); return; }
      if (!response.ok) throw new Error(`保存结果暂不可用（${response.status}），请刷新索引后重试。`);
      const markup = await response.text();
      if (active !== generation) return;
      // The backend emits an inert allowlisted projection. No scripts are evaluated.
      const template = document.createElement('template'); template.innerHTML = markup;
      $('results').replaceChildren(template.content); currentPath = method === 'POST' ? '/' : path;
      $('connection').hidden = true; $('navigation').hidden = $('disconnect').hidden = false;
      $('status').textContent = '已连接 · 保存结果只读';
      window.scrollTo(0, 0);
    } catch (error) {
      if (active !== generation) return;
      clearResults(); $('status').textContent = error.message.startsWith('保存结果') ? error.message :
        '连接离线或不可达：请确认 Mac 在线、HTTPS 连接可用且允许此页面来源，然后重试。';
      $('navigation').hidden = false; $('disconnect').hidden = false;
    } finally { clearTimeout(timeout); }
  }
  if (typeof window.AXIOM_RESULTS_ENDPOINT === 'string') $('endpoint').value = window.AXIOM_RESULTS_ENDPOINT;
  $('connect').addEventListener('submit', event => {
    event.preventDefault();
    try {
      const url = new URL($('endpoint').value.trim());
      const local = ['127.0.0.1', 'localhost'].includes(location.hostname) && ['127.0.0.1', 'localhost'].includes(url.hostname);
      if (url.protocol !== 'https:' && !(local && url.protocol === 'http:') || url.username || url.password || url.search || url.hash || url.pathname !== '/') throw new Error();
      if (!/^[A-Za-z0-9_-]{43,128}$/.test($('token').value)) throw new Error();
      endpoint = url.origin; token = $('token').value; $('token').value = ''; load('/');
    } catch { $('status').textContent = '请输入不含路径、查询或凭据的 HTTPS 服务地址，以及有效访问码。'; }
  });
  $('results').addEventListener('click', event => {
    const anchor = event.target.closest('a'); if (!anchor) return;
    event.preventDefault(); const path = anchor.getAttribute('href'); if (path) load(path);
  });
  $('results').addEventListener('submit', event => {
    event.preventDefault(); const form = event.target;
    if (form.getAttribute('method')?.toLowerCase() === 'post') load('/refresh', 'POST');
    else load(currentPath.split('?')[0] + '?' + new URLSearchParams(new FormData(form)));
  });
  $('home').addEventListener('click', () => load('/'));
  $('refresh').addEventListener('click', () => load('/refresh', 'POST'));
  $('disconnect').addEventListener('click', () => disconnect());
  window.addEventListener('pagehide', () => disconnect());
})();
