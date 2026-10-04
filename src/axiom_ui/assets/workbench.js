(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('workbench-data').textContent);
  const views = data.views, byId = new Map(views.map(v => [v.view_id, v]));
  function recent(a,b){
    for(const field of ['last_activity_at','created_at']){
      const left=Date.parse(a.v.research?.[field]),right=Date.parse(b.v.research?.[field]);
      if(Number.isFinite(left)&&Number.isFinite(right)){if(left!==right)return right-left;}
      else {if(Number.isFinite(left))return -1;if(Number.isFinite(right))return 1;}
    }
    return a.i-b.i;
  }
  const initial=views.map((v,i)=>({v,i})).sort(recent)[0].v;
  const state = {runId: initial.view_id, pane: 'performance', compare: '', benchmark: true,
    security: '', session: '', interval: null, fillId: '', eventId: '', kind: 'fills', filter: 'all', status: '', tag: ''};
  const $ = id => document.getElementById(id);
  const current = () => byId.get(state.runId);
  const present = v => v !== null && v !== undefined;
  const saved = v => present(v) ? String(v) : '未提供';
  const short = id => id ? id.replace(/^(sha256:|synthetic:)/, '').slice(0, 10) : '未提供';
  const securityName = id => (String(id || '').match(/\.(\d{6})\./) || [null, id])[1] || '未提供';
  const json = v => JSON.stringify(v, null, 2);
  const eventKey = event => event.fill_id || event.order_id || json(event);
  const numeric = v => present(v) && Number.isFinite(Number(v)) ? Number(v) : null;
  const positive = v => numeric(v) > 0 ? 'positive' : numeric(v) < 0 ? 'negative' : '';
  function decimal(value, shift = 0) {
    if (!present(value)) return '未提供';
    const m = String(value).match(/^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/);
    if (!m) return String(value);
    const exponent = Number(m[4] || 0);
    if (Math.abs(exponent) > 1000) return String(value);
    let digits = m[2] + (m[3] || ''), place = m[2].length + exponent + shift;
    if (place <= 0) digits = '0'.repeat(1-place) + digits, place = 1;
    if (place >= digits.length) digits += '0'.repeat(place-digits.length);
    let integer = digits.slice(0, place).replace(/^0+(?=\d)/, '') || '0';
    let fraction = digits.slice(place).replace(/0+$/, '');
    return (m[1] === '-' ? '-' : '') + integer + (fraction ? '.' + fraction : '');
  }
  function compact(text) {
    const parts=text.split('.');
    if((parts[1] || '').length<=2)return text;
    return (/[1-9]/.test(parts[1].slice(2))?'≈':'')+parts[0]+'.'+parts[1].slice(0,2);
  }
  const percent = v => present(v) ? compact(decimal(v, 2)) + '%' : '未提供';
  function money(v) {
    if (!present(v)) return '未提供';
    let result = decimal(v, -2), parts = result.split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    parts[1] = (parts[1] || '').padEnd(2, '0');
    return compact(parts.join('.'));
  }
  function node(tag, text, cls) {
    const el = document.createElement(tag);
    if (present(text)) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }
  function clear(id) { const el = $(id); el.replaceChildren(); return el; }
  function missing(id, text) { clear(id).append(node('p', text, 'missing')); }
  function option(select, value, label) { const el = node('option', label); el.value = value; select.append(el); }
  const statusOf = v => v.research?.no_version ? '未登记版本' : v.research?.not_run ? '未运行' : v.research?.status || (v.blocked ? '阻断' : v.run.status);
  function selectRun(id) {
    state.runId = id; state.security = ''; state.session = ''; state.interval = null; state.fillId = ''; state.eventId = '';
    if (state.compare === id) state.compare = '';
    render();
  }
  function initializeFilters() {
    const statuses = new Set(views.map(statusOf));
    for (const status of statuses) option($('status-filter'), status, status);
    const tags = new Set(views.flatMap(v => v.research?.tags || []));
    for (const tag of tags) option($('tag-filter'), tag, tag);
  }
  function renderTree() {
    const tree = clear('run-tree');
    let filtered = views.filter(v => (!state.status || statusOf(v) === state.status) &&
      (!state.tag || (v.research?.tags || []).includes(state.tag)) &&
      (state.filter === 'all' || (state.filter === 'favorite' ? v.research?.favorite === true : v.research?.shelved === true)));
    filtered = filtered.map((v,i) => ({v,i})).sort(recent).map(x => x.v);
    const groups = new Map();
    for (const v of filtered) {
      const key = v.research?.question_id || v.research?.experiment_ref || 'unlinked';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(v);
    }
    for (const group of groups.values()) {
      const wrap = node('div', null, 'question-group');
      wrap.append(node('div', group[0].research?.title || '研究问题未提供', 'question-title'));
      const versions=new Map();
      for(const v of group){const key=v.research?.version_id || v.research?.experiment_ref || 'unlinked';if(!versions.has(key))versions.set(key,[]);versions.get(key).push(v);}
      for (const members of versions.values()) {
        const first=members[0];
        wrap.append(node('div', first.research?.version_label || (first.research?.experiment_ref ? '冻结实验 ' + short(first.research.experiment_ref) : '版本说明未提供'), 'version-title'));
        for(const v of members){
        const button = node('button', v.research?.no_version ? '尚未登记版本' : v.research?.not_run ? '尚未运行' : short(v.run.run_id || v.research?.run_record_ref), 'run-item' + (v.view_id === state.runId ? ' selected' : ''));
        button.dataset.runId = v.view_id; button.title = v.run.run_id || v.research?.run_record_ref || v.research?.version_id;
        button.append(node('span', statusOf(v) + (v.evaluation ? ' · 评价 '+short(v.evaluation.evaluation_ref) : '') + (v.research?.favorite ? ' · 收藏' : '') + (v.research?.shelved ? ' · 搁置' : '')));
        button.addEventListener('click', () => selectRun(v.view_id)); wrap.append(button);
        }
      }
      tree.append(wrap);
    }
    if (!filtered.length) tree.append(node('p', '没有匹配的已保存记录。未提供的标记不会当作已收藏或已搁置。', 'small'));
    $('navigation-note').textContent = views.some(v => !v.research?.created_at) ? '部分记录未保存运行时间，保留载入顺序；不以文件时间推断近期。' : '按 Research 保存时间排序。';
    document.querySelectorAll('[data-filter]').forEach(b => b.classList.toggle('active', b.dataset.filter === state.filter));
  }
  function renderHeader(v) {
    const r = v.run, research = v.research;
    $('context-line').textContent = (research?.version_label || '版本说明未提供') + ' / ' + (r.run_id ? 'run ' + short(r.run_id) : research?.not_run ? '尚未运行' : 'record ' + short(research?.run_record_ref)) + (v.evaluation ? ' / eval '+short(v.evaluation.evaluation_ref) : '');
    $('context-line').title = r.run_id || research?.run_record_ref || research?.version_id;
    $('evidence-badge').textContent = v.evidence_kind === 'research_record_only' ? 'Research 记录 · 无已载入账户结果' : v.evidence_kind === 'synthetic_ui_fixture' ? '合成界面样例 · 非回测证据' : v.evidence_kind === 'synthetic_owner_output' ? 'Owner 合成回测' : 'Owner 已保存模拟回测';
    $('run-title').textContent = research?.title || '模拟回测 · ' + short(r.run_id);
    $('hypothesis').textContent = research?.hypothesis || 'Research 尚未保存实验说明。';
    const nav = r.nav || [];
    $('date-range').textContent = saved(v.configuration.start_session || nav[0]?.session) + ' — ' + saved(v.configuration.end_session || nav.at(-1)?.session);
    $('run-status').textContent = statusOf(v) + (r.status ? ' · Engine 原状态 ' + r.status : ' · 无已载入 Engine 结果');
    $('policy-badge').textContent = v.approximate ? 'ETF 日线近似 · 实验假设' : v.blocked ? '市场状态缺证 · 严格阻断' : r.run_id ? '保存的执行假设' : '执行假设未提供';
    $('notice').textContent = v.evidence_kind === 'research_record_only' ? (research?.no_version ? '此问题尚未登记版本。' : research?.not_run ? '本版本尚未登记运行。' : 'Research 保存状态：' + statusOf(v) + '；原因：' + saved(research?.reason)) + ' 未载入的账户结果不可用，缺失不补零。' : v.evidence_kind === 'synthetic_ui_fixture' ? '本页全部为合成界面 fixture；交互通过不构成真实回测或收益验收。' :
      v.evidence_kind === 'synthetic_owner_output' ? '该运行来自 Owner 合成数据，仅验证保存与展示合同，不是真实数据收益验收。' :
      v.blocked ? 'UNKNOWN_MARKET_STATUS：Owner 保存了执行阻断。零成交 / cash-only 不是收益验收，COMPLETE 仅表示处理完成。' :
      v.approximate ? '显式 ETF 日线近似：保留 UNKNOWN 状态，以日线价格、量及限价作模拟假设；不证明开盘流动性或实盘可执行。' : '只读展示 Owner 保存产物；运行处理完成不代表策略有效。';
    if(research?.outcome)$('notice').textContent+=' Research 保存说明：'+research.outcome;
    const metrics = r.metrics || {}, cards = clear('metrics');
    const comparison=byId.get(state.compare),old=comparison?.run.metrics || {};
    const definitions = [['期间收益',metrics.total_return,percent,'Owner 保存比例',old.total_return],['最大回撤',metrics.max_drawdown,percent,'Owner 保存比例',old.max_drawdown],['总费用',metrics.total_fees_minor,money,'CNY 整数分 → 元',old.total_fees_minor],['净资产',nav.at(-1)?.nav_minor,money,'Owner 最后保存水位',comparison?.run.nav?.at(-1)?.nav_minor]];
    for (const [label,value,format,help,oldValue] of definitions) {
      const card = node('div', null, 'metric'); card.append(node('span',label));
      const val = node('strong',format(value),positive(value)); val.title = 'Owner 原值：' + saved(value); card.append(val,node('small',help)); cards.append(card);
      if(comparison){const old=node('span','对照 '+format(oldValue),'comparison-value');old.title='对照 Owner 原值：'+saved(oldValue);card.append(old);}
    }
    $('selection-context').textContent = state.interval ? '定位期间 ' + state.interval.start + ' — ' + state.interval.end + (state.session ? ' / 选中 ' + state.session : '') + '；统计仍为 Owner 保存的原报告。' : '同一运行上下文 · ' + short(r.run_id || research?.run_record_ref || research?.version_id) + (state.session ? ' / ' + state.session : '');
  }
  const NS = 'http://www.w3.org/2000/svg';
  function svgEl(tag, attrs = {}, text) {
    const el = document.createElementNS(NS, tag);
    for (const [key,value] of Object.entries(attrs)) el.setAttribute(key, String(value));
    if (present(text)) el.textContent = text;
    return el;
  }
  function chart(id, width, height, label) {
    const svg = svgEl('svg', {viewBox: `0 0 ${width} ${height}`, role:'img','aria-label':label}); clear(id).append(svg); return svg;
  }
  function bounds(values) {
    const finite = values.map(numeric).filter(present);
    if (!finite.length) return null;
    const lo = Math.min(...finite), hi = Math.max(...finite), pad = (hi-lo)*.12 || Math.abs(hi)*.02 || .02;
    return [lo-pad, hi+pad];
  }
  function scale(range, top, bottom) { return value => bottom-(Number(value)-range[0])/(range[1]-range[0])*(bottom-top); }
  function line(svg, points, sessions, x, y, color, dash = '') {
    let path = '', open = false;
    for (const point of points) {
      const index = sessions.indexOf(point.session), value = numeric(point.value);
      if (index < 0 || value === null) {open = false;continue;}
      path += (open ? ' L' : ' M') + x(index).toFixed(2) + ',' + y(value).toFixed(2); open = true;
    }
    if (path) svg.append(svgEl('path',{d:path,fill:'none',stroke:color,'stroke-width':2,'stroke-dasharray':dash}));
  }
  function axes(svg, sessions, range, y, x, top, bottom, percentAxis = false) {
    for (let i=0;i<4;i++) {
      const value = range[0]+(range[1]-range[0])*i/3, row = y(value);
      svg.append(svgEl('line',{x1:55,x2:930,y1:row,y2:row,stroke:'#e7edf3'}));
      svg.append(svgEl('text',{x:47,y:row+4,'text-anchor':'end',fill:'#607184','font-size':11},percentAxis ? (value*100).toFixed(1)+'%' : value.toFixed(3)));
    }
    for (const index of [...new Set([0,Math.floor((sessions.length-1)/2),sessions.length-1])]) if (index>=0 && sessions[index])
      svg.append(svgEl('text',{x:x(index),y:bottom+19,'text-anchor':index===0?'start':index===sessions.length-1?'end':'middle',fill:'#607184','font-size':11},sessions[index]));
  }
  function renderPerformance(v) {
    const r = v.run, nav = r.nav || [], comparison = byId.get(state.compare);
    const select = $('compare-run'); select.replaceChildren(); option(select,'','添加运行对照');
    for (const view of views) if(view.view_id !== v.view_id && view.run.run_id) option(select,view.view_id,(view.research?.version_label || short(view.run.run_id)) + ' · ' + statusOf(view));
    select.value = state.compare; $('benchmark-toggle').checked = state.benchmark;
    const differences = [];
    if (comparison) for (const key of Object.keys(v.configuration)) {
      if (json(v.configuration[key]) !== json(comparison.configuration[key])) differences.push(key);
    }
    if (comparison) for (const key of ['market_ref','signal_ref','profile_ref','account_id']) {
      if (r[key] !== comparison.run[key]) differences.push(key);
    }
    $('comparison-notice').textContent = !comparison ? '单次运行；添加对照仍使用同一个图和指标区。' : differences.length ? '非同口径 / 变动字段：' + differences.join('、') + '。保留各自完整范围，不裁剪或重新归一化。' : '已载入同口径配置；原始运行身份分别保留。';
    $('configuration-differences').textContent = comparison ? '差异字段：' + (differences.join('、') || '无已知差异') + '；显式版本变动：' + saved(v.research?.changes && json(v.research.changes)) : '显式版本变动：' + saved(v.research?.changes && json(v.research.changes));
    const ownerDiff=v.research?.comparison_left_ref===comparison?.research?.version_id?v.research?.version_comparison:comparison?.research?.comparison_left_ref===v.research?.version_id?comparison.research.version_comparison:null;
    $('configuration-values').textContent = json({current:v.configuration,comparison:comparison?.configuration || null,research_parameters:v.research?.parameters,input_refs:v.research?.input_refs,version_explanation:v.research?.version_explanation,owner_version_comparison:ownerDiff});
    const benchmark = v.evaluation?.benchmark;
    $('benchmark-toggle').disabled=!benchmark || benchmark.status==='MISSING';
    $('benchmark-toggle').checked=state.benchmark && !$('benchmark-toggle').disabled;
    const missingReasons=[...new Set((benchmark?.series || []).map(p=>p.missing_reason).filter(present))];
    $('benchmark-note').textContent = benchmark ? '沪深300 · 状态 '+saved(benchmark.status)+' · ' + saved(benchmark.series_kind) + '；价格指数不含分红，与账户含分红收益有差异。锚点：' + saved(benchmark.anchor_session) + ' / '+saved(benchmark.anchor_close)+' index points。保存收益 '+percent(benchmark.total_return)+' / 最大回撤 '+percent(benchmark.max_drawdown)+'。'+(missingReasons.length?'缺失原因：'+missingReasons.join('、')+'。':'')+'缺值不补零。' : '沪深300不可用：Engine 尚未保存该运行的基准评价。';
    if (!nav.length) {missing('performance-chart','LAYER_UNAVAILABLE · 未保存 NAV。');$('nav-point').textContent='';return;}
    const showBenchmark=state.benchmark && !$('benchmark-toggle').disabled;
    const benchPoints = showBenchmark ? (benchmark?.series || []).map(p=>({session:p.session,value:p.valid === false ? null : p.nav_index})) : [];
    const oldPoints = (comparison?.run.nav || []).map(p=>({session:p.session,value:p.nav_index}));
    const points = nav.map(p=>({session:p.session,value:p.nav_index}));
    const sessions = [...new Set([...points,...oldPoints,...benchPoints].map(p=>p.session))].sort();
    const x = i => 55 + (sessions.length<2 ? 0 : i/(sessions.length-1)*875);
    const range = bounds([...points,...oldPoints,...benchPoints].map(p=>p.value)), y = scale(range,30,210);
    const svg = chart('performance-chart',960,370,'Owner 保存的净值与回撤，同一时间轴');
    axes(svg,sessions,range,y,x,30,210); line(svg,points,sessions,x,y,'#547da3'); line(svg,oldPoints,sessions,x,y,'#866599','5 3'); line(svg,benchPoints,sessions,x,y,'#95753e','5 5');
    const dd = (v.evaluation?.series || []).map(p=>({session:p.session,value:p.drawdown}));
    const oldDd=(comparison?.evaluation?.series || []).map(p=>({session:p.session,value:p.drawdown}));
    const benchDd=showBenchmark?(benchmark?.series || []).map(p=>({session:p.session,value:p.valid===false?null:p.drawdown})):[];
    const ddBounds = bounds([...dd,...oldDd,...benchDd].map(p=>p.value));
    if (ddBounds) {
      const dy = scale(ddBounds,270,335); line(svg,dd,sessions,x,dy,'#428766');line(svg,oldDd,sessions,x,dy,'#866599','5 3');line(svg,benchDd,sessions,x,dy,'#95753e','5 5');
      svg.append(svgEl('text',{x:55,y:256,fill:'#607184','font-size':11},'回撤 · Owner 保存比例'));
      svg.append(svgEl('text',{x:47,y:335,'text-anchor':'end',fill:'#607184','font-size':10},(ddBounds[0]*100).toFixed(1)+'%'));
    } else svg.append(svgEl('text',{x:55,y:278,fill:'#82622e','font-size':12},'回撤序列不可用 · 不从 NAV 计算'));
    for (const point of nav) {
      const circle = svgEl('circle',{cx:x(sessions.indexOf(point.session)),cy:y(point.nav_index),r:6,fill:'transparent',class:'draw-point',tabindex:0,role:'button','aria-label':point.session+' NAV '+point.nav_index});
      const show = () => {$('nav-point').textContent=point.session+' · NAV指数 '+point.nav_index+' · 净资产 '+money(point.nav_minor)+' 元 · 水位 '+point.committed_sequence;};
      const select=()=>{state.session=point.session;state.fillId='';state.eventId='';show();renderHeader(v);renderTrade(v);};
      circle.addEventListener('mouseenter',show); circle.addEventListener('focus',show); circle.addEventListener('click',select);
      circle.addEventListener('keydown',e=>{if(e.key==='Enter')select();}); svg.append(circle);
    }
    $('nav-point').textContent = '选择日期看原值。当前蓝色' + (comparison ? ' / 旧运行紫色' : '') + (benchPoints.length ? ' / 沪深300虚线' : '');
  }
  function pointRow(panel, label, value) {
    const row=node('div',null,'point-row');row.append(node('span',label),node('strong',saved(value)));panel.append(row);
  }
  function renderPoint(v, event = null, kind = state.kind) {
    const panel=clear('trade-point');panel.append(node('h3',event ? (kind==='fills'?'成交原值':kind==='orders'?'委托原值':'决策原值') : '所选行情原值'));
    pointRow(panel,'证券',state.security);pointRow(panel,'交易日',event?.session || event?.trade_session || state.session);
    if (event) {
      if (kind==='fills') {
        pointRow(panel,'原始成交价 / 份额',saved(event.price)+' / '+saved(event.quantity));pointRow(panel,'费用（元）',money(event.fee_minor));pointRow(panel,'原始事件水位',event.sequence);
        const order=(v.run.orders || []).find(o=>o.order_id===event.order_id);
        pointRow(panel,'保存的执行依据',event.execution_admission || order?.execution_admission);
        pointRow(panel,'原始市场状态',event.market_state || order?.market_state);pointRow(panel,'状态来源原因',event.state_reason || order?.state_reason);pointRow(panel,'委托状态 / 原因',saved(order?.status)+' / '+saved(order?.reason));
      } else if(kind==='orders') {
        for(const [key,label] of [['side','方向'],['quantity','委托份额'],['filled_quantity','已成交份额'],['status','状态'],['reason','拒单/未成交原因'],['market_state','原市场状态'],['state_reason','状态来源原因'],['execution_admission','执行依据']]) pointRow(panel,label,event[key]);
      } else {
        pointRow(panel,'信号日',event.feature_session);pointRow(panel,'决策交易日',event.trade_session);pointRow(panel,'决策状态',event.status);pointRow(panel,'已保存 trace',event.trace ? json(event.trace) : null);
      }
      pointRow(panel,'记录身份',event.fill_id || event.order_id || event.intent_id);pointRow(panel,'完整保存记录',json(event));
    } else {
      const rows=v.market.data_batch?.records || v.market.rows;
      const point=rows.find(p=>p.security_id===state.security && p.session===state.session);
      if(point) {for(const key of ['open','high','low','close','volume','volume_units']) if(Object.hasOwn(point,key)) pointRow(panel,key,point[key]);}
      else panel.append(node('p','所选日期未保存行情，不填补。','missing'));
      const positions=(v.run.positions || []).filter(p=>p.security_id===state.security && p.session===state.session);
      for(const position of positions) {pointRow(panel,'持仓 / 可卖份额',saved(position.quantity)+' / '+saved(position.sellable_quantity));pointRow(panel,'估值日 / 是否过期',saved(position.mark_session)+' / '+saved(position.is_stale));pointRow(panel,'账户水位',position.committed_sequence);}
    }
    panel.append(node('p','特征/模型分数/排名 debug 属后续；未保存内容不补理由。','small'));
  }
  function selectEvent(v,event,kind) {
    state.kind=kind;state.session=event.session || event.trade_session;state.security=event.security_id || event.selected_security_id || state.security;
    state.fillId=kind==='fills'?event.fill_id:'';state.eventId=eventKey(event);renderHeader(v);renderTrade(v);renderPoint(v,event,kind);
  }
  function renderTrade(v) {
    const rows=v.market.data_batch?.records || v.market.rows;
    const securities=[...new Set([...rows.map(r=>r.security_id),...(v.run.fills || []).map(r=>r.security_id),...(v.run.orders || []).map(r=>r.security_id)])].sort();
    if(!state.security || !securities.includes(state.security)) state.security=securities[0] || '';
    const select=$('security-select');select.replaceChildren();for(const security of securities) option(select,security,securityName(security));select.value=state.security;
    const points=rows.filter(r=>r.security_id===state.security).sort((a,b)=>a.session.localeCompare(b.session));
    const sessions=points.map(p=>p.session);
    if(!state.session) state.session=sessions.at(-1) || v.run.nav?.at(-1)?.session || '';
    $('session-select').value=state.session;$('session-select').min=sessions[0] || '';$('session-select').max=sessions.at(-1) || '';
    const candle=!!v.market.data_batch;
    $('candle-note').textContent=candle ? 'Data 公共 OHLCV · '+saved(v.market.data_batch.context.snapshot_id)+' · '+saved(v.market.price_basis)+'；成交侧栏保留未复权原价。' : 'K线不可用：当前运行未保存 high/low 图层。下面仅为保存的收盘价 / 全天量；不构造蜡烛。';
    const availablePrices=points.flatMap(p=>candle?[p.high,p.low]:[p.close]);
    if(!points.length || !bounds(availablePrices)) missing('trade-chart','LAYER_UNAVAILABLE · 所选证券无已保存价格。');
    else {
      const svg=chart('trade-chart',760,390,candle?'固定 Data K线、成交量及保存成交点':'保存的收盘价、全天量及成交点（非K线）');
      const fills=(v.run.fills || []).filter(f=>f.security_id===state.security);
      const priceValues=points.flatMap(p=>candle?[p.high,p.low]:[p.close]).concat(fills.map(f=>f.price));
      const range=bounds(priceValues), y=scale(range,35,245), x=i=>50+(sessions.length<2?0:i/(sessions.length-1)*690);
      for(let i=0;i<4;i++){const value=range[0]+(range[1]-range[0])*i/3;svg.append(svgEl('line',{x1:50,x2:740,y1:y(value),y2:y(value),stroke:'#e7edf3'}));svg.append(svgEl('text',{x:43,y:y(value)+4,'text-anchor':'end',fill:'#607184','font-size':11},value.toFixed(3)));}
      for(const episode of v.evaluation?.episodes || []) if(episode.security_id===state.security) {
        let start=sessions.indexOf(episode.entry_session),end=sessions.indexOf(episode.exit_session);
        if(start<0 && episode.left_censored)start=0;if(end<0 && episode.status==='OPEN')end=sessions.length-1;
        if(start>=0 && end>=start)svg.append(svgEl('rect',{x:x(start)-4,y:32,width:Math.max(8,x(end)-x(start)+8),height:215,fill:'#547da3',opacity:.075,'stroke-dasharray':episode.status==='OPEN'?'4 3':''}));
      }
      const volumeValues=points.map(p=>numeric(p.volume ?? p.volume_units)).filter(present), vmax=Math.max(...volumeValues,1);
      const bodyWidth=Math.max(2,Math.min(8,550/points.length));
      if(!candle)line(svg,points.map(p=>({session:p.session,value:p.close})),sessions,x,y,'#547da3');
      points.forEach((p,i)=>{
        const color=numeric(p.close)>=numeric(p.open)?'#c16583':'#428766';
        if(candle && [p.open,p.high,p.low,p.close].every(value=>numeric(value)!==null)){
          svg.append(svgEl('line',{x1:x(i),x2:x(i),y1:y(p.high),y2:y(p.low),stroke:color}));
          svg.append(svgEl('rect',{x:x(i)-bodyWidth/2,y:Math.min(y(p.open),y(p.close)),width:bodyWidth,height:Math.max(1,Math.abs(y(p.open)-y(p.close))),fill:color}));
        }
        const volume=numeric(p.volume ?? p.volume_units);
        if(volume!==null)svg.append(svgEl('rect',{x:x(i)-bodyWidth/2,y:340-volume/vmax*55,width:bodyWidth,height:volume/vmax*55,fill:color,opacity:.8}));
        const hit=svgEl('circle',{cx:x(i),cy:y(p.close ?? range[0]),r:5,fill:'transparent',role:'button',tabindex:0,'aria-label':p.session+' 原价量'});
        const select=()=>{state.session=p.session;state.fillId='';state.eventId='';renderHeader(v);renderTrade(v);};hit.addEventListener('click',select);hit.addEventListener('keydown',e=>{if(e.key==='Enter')select();});svg.append(hit);
      });
      svg.append(svgEl('text',{x:50,y:277,fill:'#607184','font-size':11},'全天成交量 · Owner 原值比例展示'));
      for(const fill of fills) {
        const i=sessions.indexOf(fill.session);if(i<0 || numeric(fill.price)===null)continue;
        const selected=fill.fill_id===state.fillId,color=fill.side==='BUY'?'#c16583':'#428766';
        const g=svgEl('g',{role:'button',tabindex:0,'aria-label':fill.side+' '+fill.session+' '+fill.price,'data-fill-id':fill.fill_id,class:selected?'selected-fill':''});
        g.append(svgEl('circle',{cx:x(i),cy:y(fill.price),r:selected?14:9,fill:'white',stroke:selected?'#24364a':color,'stroke-width':selected?3:2}));
        g.append(svgEl('circle',{cx:x(i),cy:y(fill.price),r:selected?11:7,fill:color}));
        g.append(svgEl('text',{x:x(i),y:y(fill.price)+4,'text-anchor':'middle',fill:'white','font-size':selected?12:10,'font-weight':700},fill.side==='BUY'?'B':'S'));
        g.addEventListener('click',()=>selectEvent(v,fill,'fills'));g.addEventListener('keydown',e=>{if(e.key==='Enter')selectEvent(v,fill,'fills');});svg.append(g);
      }
      for(const index of [...new Set([0,Math.floor((sessions.length-1)/2),sessions.length-1])])svg.append(svgEl('text',{x:x(index),y:372,'text-anchor':index===0?'start':index===sessions.length-1?'end':'middle',fill:'#607184','font-size':10},sessions[index]));
    }
    document.querySelectorAll('[data-event-kind]').forEach(b=>b.classList.toggle('active',b.dataset.eventKind===state.kind));
    const list=clear('event-list'), events=(v.run[state.kind] || []).filter(e=>state.kind==='decisions'?(e.selected_security_id===state.security || (e.intents || []).some(i=>i.security_id===state.security)):e.security_id===state.security);
    if(!events.length)list.append(node('p','Owner 保存的该类记录为空；委托或意图不画成成交点。','small'));
    for(const event of events){
      const day=event.session || event.trade_session,button=node('button',null,'event-item'+(event.fill_id===state.fillId?' selected':''));
      button.dataset.recordId=eventKey(event);const left=node('div',day+' · '+saved(event.side || event.status));
      left.append(node('span',state.kind==='fills'?'模拟成交 · '+saved(event.price)+' / '+saved(event.quantity):saved(event.status)+' · '+saved(event.reason)));
      button.append(left,node('div',state.kind==='fills'?money(event.fee_minor)+' 元费用':saved(event.state_reason),'small'));
      button.addEventListener('click',()=>selectEvent(v,event,state.kind));list.append(button);
    }
    const selected=(v.run[state.kind] || []).find(e=>eventKey(e)===state.eventId);renderPoint(v,selected,state.kind);
  }
  function renderStatistics(v) {
    const evaluation=v.evaluation;
    if(!evaluation){for(const id of ['month-heatmap','episode-chart','episode-metrics','episode-list'])missing(id,'LAYER_UNAVAILABLE · Engine 尚未保存账户评价报告。');$('episode-definition').textContent='未保存定义，不从成交构造完整持仓段。';$('distribution-note').textContent='未保存分布，不从成交或持仓重算。';}
    else {
      const months=evaluation.monthly_returns || [],years=[...new Set(months.map(m=>m.month.slice(0,4)))].sort(),grid=node('div',null,'heat-grid');
      grid.append(node('div',''));for(let month=1;month<=12;month++)grid.append(node('div',String(month).padStart(2,'0'),'month-label'));
      for(const year of years){grid.append(node('div',year,'year-label'));for(let i=1;i<=12;i++){
        const key=year+'-'+String(i).padStart(2,'0'),report=months.find(m=>m.month===key),partial=report?.status==='PARTIAL';
        const value=report?.status==='COMPLETE'?report.return:partial?report.observed_return:null;
        const button=node('button',present(value)?percent(value)+(partial?' *':''):'—','heat-cell '+positive(value)+(partial?' partial':''));
        button.dataset.month=key;button.title=report?json(report):key+' · Owner 未保存该月';button.disabled=!report?.first_session || !report?.last_session;
        button.addEventListener('click',()=>{state.interval={start:report.first_session,end:report.last_session};state.session=report.last_session;state.fillId='';state.eventId='';state.pane='performance';render();});grid.append(button);
      }}clear('month-heatmap').append(grid);if(!months.length)missing('month-heatmap','Owner 月度列表为空。');
      const metrics=evaluation.episode_metrics || {},card=clear('episode-metrics');
      for(const [label,value] of [['闭合段 / 可统计闭合',saved(metrics.closed_count)+' / '+saved(metrics.eligible_closed_count)],['开放 / 左截断 / 已知待分红',saved(metrics.open_count)+' / '+saved(metrics.left_censored_count)+' / '+saved(metrics.income_pending_count)],['盈利 / 亏损 / 平局',saved(metrics.win_count)+' / '+saved(metrics.loss_count)+' / '+saved(metrics.tie_count)],['胜率',percent(metrics.win_rate)],['平均段净盈亏（元）',money(metrics.mean_net_pnl_minor)],['平均段收益率',percent(metrics.mean_episode_return)],['分红范围资格',saved(metrics.dividend_scope_status)]]){
        const row=node('div',null,'episode-stat');row.append(node('span',label),node('strong',value));card.append(row);
      }
      $('episode-definition').textContent=json({spec:evaluation.spec,return_denominator:metrics.return_denominator,weighting:metrics.weighting,owner_metrics:metrics,dividend_scope_status:metrics.dividend_scope_status,limitations:evaluation.limitations});
      const episodes=evaluation.episodes || [],closed=episodes.filter(e=>e.statistics_eligible && e.status==='CLOSED' && present(e.net_pnl_minor));
      const distribution=evaluation.pnl_distribution;
      $('distribution-note').textContent=distribution?.status==='AVAILABLE'?'Owner 保存的固定分箱，单位元；仅纳入可统计闭合段。点击持仓段列表下钻。':'样本不足 10 段或分布未提供；下图逐点保留已保存净盈亏，不称完整分布。';
      if(distribution?.status==='AVAILABLE'){
        const bins=distribution.bins || [],svg=chart('episode-chart',440,200,'Owner 保存的完整持仓段净盈亏桶计数'),maximum=Math.max(1,...bins.map(b=>Number(b.count)));
        bins.forEach((bucket,i)=>{const x=40+i*46,h=Number(bucket.count)/maximum*105;
          const bar=svgEl('rect',{x,y:135-h,width:34,height:h,fill:'#547da3','data-bin-count':bucket.count});
          bar.append(svgEl('title',{},'['+(present(bucket.lower_minor)?money(bucket.lower_minor):'−∞')+', '+(present(bucket.upper_minor)?money(bucket.upper_minor):'+∞')+') 元 · '+bucket.count+' 段'));svg.append(bar);
          svg.append(svgEl('text',{x:x+17,y:126-h,'text-anchor':'middle',fill:'#40536a','font-size':11},bucket.count));
          svg.append(svgEl('text',{x:x+17,y:155,'text-anchor':'middle',fill:'#607184','font-size':10},present(bucket.lower_minor)?money(bucket.lower_minor):'−∞'));
        });
      }
      else if(!closed.length)missing('episode-chart','没有 Owner 标记为可统计的闭合段；缺失不补零。');
      else {
        const svg=chart('episode-chart',440,200,'各可统计闭合持仓段的保存净盈亏，单位元'),range=bounds(closed.map(e=>Number(e.net_pnl_minor)/100)),x=value=>40+(value-range[0])/(range[1]-range[0])*350;
        svg.append(svgEl('line',{x1:40,x2:390,y1:120,y2:120,stroke:'#ccd7e2'}));
        if(range[0]<=0&&range[1]>=0)svg.append(svgEl('line',{x1:x(0),x2:x(0),y1:30,y2:130,stroke:'#607184','stroke-dasharray':'3 3'}));
        closed.forEach((e,i)=>{const circle=svgEl('circle',{cx:x(Number(e.net_pnl_minor)/100),cy:70+(i%3)*16,r:6,fill:Number(e.net_pnl_minor)>0?'#c16583':Number(e.net_pnl_minor)<0?'#428766':'#607184',role:'button',tabindex:0,'data-episode-id':e.episode_id});circle.append(svgEl('title',{},money(e.net_pnl_minor)+' 元 · '+e.episode_id));circle.addEventListener('click',()=>selectEpisode(e));circle.addEventListener('keydown',event=>{if(event.key==='Enter')selectEpisode(e);});svg.append(circle);});
        svg.append(svgEl('text',{x:40,y:155,fill:'#607184','font-size':11},range[0].toFixed(2)));svg.append(svgEl('text',{x:390,y:155,'text-anchor':'end',fill:'#607184','font-size':11},range[1].toFixed(2)+' 元'));
      }
      const list=clear('episode-list');for(const episode of episodes){
        const button=node('button',null,'episode-item');button.dataset.episodeId=episode.episode_id;
        const left=node('div',securityName(episode.security_id)+' · '+episode.status);left.append(node('span',saved(episode.entry_session)+' → '+(episode.status==='OPEN'?'未闭合':saved(episode.exit_session))+' · '+saved(episode.income_status)));
        const right=node('div',present(episode.net_pnl_minor)?money(episode.net_pnl_minor)+' 元净盈亏':'未提供完整净盈亏');right.append(node('span',episode.statistics_eligible?'Owner 标记可统计':'排除原因：'+saved(episode.exclusion_reasons && json(episode.exclusion_reasons))));button.append(left,right);button.addEventListener('click',()=>selectEpisode(episode));list.append(button);
      }
    }
    $('signal-evaluation').textContent=v.research?.signal_evaluation?json(v.research.signal_evaluation):'未保存适用的信号评价；不从账户结果推导 IC/ICIR。';
  }
  function selectEpisode(episode){state.security=episode.security_id;state.interval={start:episode.entry_session,end:episode.exit_session || current().run.nav?.at(-1)?.session};state.session=episode.exit_session || state.interval.end;state.pane='trade';state.kind='fills';state.fillId=episode.fill_refs?.at(-1)?.fill_id || '';state.eventId=state.fillId;render();}
  function renderSources(v) {
    const panel=clear('source-details');
    for(const text of v.run.limitations || [])panel.append(node('p',String(text)));
    for(const text of v.evaluation?.limitations || [])panel.append(node('p',String(text)));
    $('source-refs').textContent=json({run_id:v.run.run_id,account_id:v.run.account_id,content_digest:v.run.content_digest,committed_sequence:v.run.committed_sequence,signal_ref:v.run.signal_ref,market_ref:v.run.market_ref,profile_ref:v.run.profile_ref,core_version:v.run.core_version,runtime_version:v.run.runtime_version,implementation_ref:v.run.implementation_ref,evaluation_ref:v.evaluation?.evaluation_ref,evaluation_content_digest:v.evaluation?.content_digest,benchmark_ref:v.evaluation?.benchmark_ref,benchmark:v.evaluation?.benchmark,data_context:v.market.data_batch?.context,research:v.research});
    $('generated-note').textContent='页面生成于 '+data.generated_at+'；不是数据更新时间。所有业务数值来自保存产物；浏览没有采集、训练、回测或交易调用。';
  }
  function render() {
    const v=current();renderTree();renderHeader(v);renderPerformance(v);renderTrade(v);renderStatistics(v);renderSources(v);
    document.querySelectorAll('.pane').forEach(p=>p.classList.toggle('active',p.id===state.pane));document.querySelectorAll('[data-pane]').forEach(b=>b.classList.toggle('active',b.dataset.pane===state.pane));
  }
  document.querySelectorAll('[data-pane]').forEach(b=>b.addEventListener('click',()=>{state.pane=b.dataset.pane;render();}));
  document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{state.filter=b.dataset.filter;renderTree();}));
  $('status-filter').addEventListener('change',e=>{state.status=e.target.value;renderTree();});$('tag-filter').addEventListener('change',e=>{state.tag=e.target.value;renderTree();});
  $('compare-run').addEventListener('change',e=>{state.compare=e.target.value;renderHeader(current());renderPerformance(current());});$('benchmark-toggle').addEventListener('change',e=>{state.benchmark=e.target.checked;renderPerformance(current());});
  $('security-select').addEventListener('change',e=>{state.security=e.target.value;state.session='';state.fillId='';state.eventId='';renderTrade(current());renderHeader(current());});
  $('session-select').addEventListener('change',e=>{state.session=e.target.value;state.fillId='';state.eventId='';renderTrade(current());renderHeader(current());});
  document.querySelectorAll('[data-event-kind]').forEach(b=>b.addEventListener('click',()=>{state.kind=b.dataset.eventKind;state.fillId='';state.eventId='';renderTrade(current());}));
  $('copy-context').addEventListener('click',async()=>{
    const v=current(),text=json({question_id:v.research?.question_id,version_ref:v.research?.version_id,run_record_ref:v.research?.run_record_ref,run_id:v.run.run_id,content_digest:v.run.content_digest,signal_ref:v.run.signal_ref,market_ref:v.run.market_ref,profile_ref:v.run.profile_ref,evaluation_ref:v.evaluation?.evaluation_ref,security_id:state.security,session:state.session,interval:state.interval,changes:v.research?.changes});
    try {await navigator.clipboard.writeText(text);$('toast').textContent='已复制运行上下文与证据引用。';}catch{const area=node('textarea');area.value=text;document.body.append(area);area.select();const copied=document.execCommand('copy');area.remove();$('toast').textContent=copied?'已复制运行上下文与证据引用。':'浏览器未允许复制；来源详情中保留相同引用。';}
    $('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',2500);
  });
  const mobileNavigation=matchMedia('(max-width:700px)');
  const resizeNavigation=()=>{$('experiment-navigation').open=!mobileNavigation.matches;};
  mobileNavigation.addEventListener('change',resizeNavigation);resizeNavigation();
  initializeFilters();render();
})();
