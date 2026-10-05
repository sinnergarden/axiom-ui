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
  const state = {runId: initial.view_id, registration: '', pane: 'performance', compare: '', benchmark: true,
    legendVisible: {account:true,comparison:true,benchmark:true}, topicOpen: new Map(), security: '', session: '', interval: null,
    tradeWindow: {mode:'all'}, fillId: '', eventId: '', kind: 'fills', status: '', tag: ''};
  let chartUI;
  const $ = id => document.getElementById(id);
  const current = () => {
    const base=byId.get(state.runId),history=(base.registration_history || []).find(h=>h.record.run_record_ref===state.registration);
    if(!history)return base;
    const record=history.record,version=base.research_versions?.[record.version_ref];
    return {...base,evaluation:history.evaluation,research:{...base.research,
      run_record_ref:record.run_record_ref,created_at:record.created_at,status:record.status,reason:record.reason,
      outcome:record.outcome,output_refs:record.output_refs,backtest_ref:record.backtest_ref,evaluation_ref:record.evaluation_ref,
      version_id:record.version_ref,version_label:version?.label,version_explanation:version?.explanation,
      parameters:version?.parameters,input_refs:version?.input_refs,changes:version?.explicit_changes,
      comparison_left_ref:version?.parent_version_ref || null,
      version_comparison:base.research_version_comparisons?.[record.version_ref] || null}};
  };
  const present = v => v !== null && v !== undefined;
  const saved = v => present(v) ? String(v) : '未提供';
  const stockAccount = v => ['backtest_run_v3','backtest_run_v4'].includes(v.run.contract_version);
  const quantityUnit = v => stockAccount(v) ? '股' : '份';
  const priceUnit = v => stockAccount(v) ? '元/股' : '元/份';
  const slipCaption = v => {
    const raw=v.configuration?.profile?.slippage_bps;
    if(!present(raw) || String(raw).trim()==='' || !Number.isFinite(Number(raw)))return '';
    return Number(raw)===0?'零滑点（'+saved(raw)+' bp）':'非零滑点（'+saved(raw)+' bp）';
  };
  const runCaption = v => (stockAccount(v)?(v.approximate?'股票日线近似':'股票严格对照'):v.approximate?'ETF 日线近似':'保存运行')+' · '+saved(v.configuration.start_session || v.run.nav?.[0]?.session)+' — '+saved(v.configuration.end_session || v.run.nav?.at(-1)?.session)+(slipCaption(v)?' · '+slipCaption(v):'');
  const short = id => id ? id.replace(/^(sha256:|synthetic:)/, '').slice(0, 10) : '未提供';
  const securityName = id => chartUI ? chartUI.securityLabel(current(),id) : saved(id);
  const json = v => JSON.stringify(v, null, 2);
  const eventKey = event => event.fill_id || event.order_id || json(event);
  const statusLabel = value => ({COMPLETE:'已完成',DECISION_COMPLETE:'决策已完成',NO_DECISION:'没有新决策',FILLED:'已成交',EXPIRED:'已过期',REJECTED:'已拒绝',PARTIAL:'部分数据',FAILED:'失败',BLOCKED:'阻断',NEGATIVE:'负收益',CLOSED:'已闭合',OPEN:'未闭合',MISSING:'缺失',OBSERVED_RECORDS_ONLY:'仅已观察记录',COVERAGE_UNKNOWN:'覆盖范围未提供',PENDING_EX:'待除息',RECOGNIZED:'收入已确认',NO_OBSERVED_ENTITLEMENT:'未观察到分红权益',OBSERVED_ONLY:'仅已观察记录',APPLIED:'模型已应用',NO_ENTITLEMENT:'无登记权益',ANNOUNCED_SUSPENSION:'公告全天停牌'})[value] || saved(value);
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
  const ratio = v => present(v) && Number.isFinite(Number(v)) ? Number(v).toFixed(5) : saved(v);
  const cagr = leg => !leg ? '未提供' : leg.cagr_status === 'AVAILABLE' ? percent(leg.cagr) : leg.cagr_status === 'INSUFFICIENT_SPAN' ? '样本不足一年' : '起止值缺失';
  const cagrRaw = leg => leg ? json({cagr:leg.cagr,status:leg.cagr_status,reason:leg.cagr_reason}) : '未提供';
  const periodRange = period => period ? saved(period.window.anchor_session)+' — '+saved(period.window.end_session) : '年化区间未提供';
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
    state.runId = id; state.registration = '';state.episodePage=0;state.chainSecurity='';$('chain-search').value='';$('chain-status').value='';state.security = ''; state.session = ''; state.interval = null;state.tradeWindow={mode:'all'}; state.fillId = ''; state.eventId = '';
    const selected=byId.get(id),topic=selected.research?.question_id || selected.research?.experiment_ref || 'unlinked';
    state.topicOpen.set(topic,true);state.legendVisible={account:true,comparison:true,benchmark:true};
    $('episode-scope').value='window';$('episode-security').value='';$('episode-status').value='';
    if (state.compare === id || !byId.get(id).run.run_id) state.compare = '';
    render();
  }
  function initializeFilters() {
    const statuses = new Set(views.map(statusOf));
    for (const status of statuses) option($('status-filter'), status, statusLabel(status));
    const tags = new Set(views.flatMap(v => v.research?.tags || []));
    for (const tag of tags) option($('tag-filter'), tag, tag);
  }
  function renderTree() {
    const tree = clear('run-tree');
    let filtered = views.filter(v => (!state.status || statusOf(v) === state.status) &&
      (!state.tag || (v.research?.tags || []).includes(state.tag)));
    filtered = filtered.map((v,i) => ({v,i})).sort(recent).map(x => x.v);
    const groups = new Map();
    for (const v of filtered) {
      const key = v.research?.question_id || v.research?.experiment_ref || 'unlinked';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(v);
    }
    for (const [topic,group] of groups) {
      const wrap = node('details', null, 'question-group'),summary=node('summary',group[0].research?.title || '研究问题未提供','question-title'),body=node('div',null,'topic-runs');
      wrap.dataset.questionId=topic;
      wrap.open=state.topicOpen.has(topic)?state.topicOpen.get(topic):group.some(v=>v.view_id===state.runId);
      wrap.addEventListener('toggle',()=>state.topicOpen.set(topic,wrap.open));
      const counts=group[0].research;
      if(present(counts?.saved_backtest_count)&&present(counts?.registration_count))summary.append(node('span',counts.saved_backtest_count+' 份账户回测 · '+counts.registration_count+' 条登记','small'));
      wrap.append(summary,body);
      const versions=new Map();
      for(const v of group){const key=v.research?.version_id || v.research?.experiment_ref || 'unlinked';if(!versions.has(key))versions.set(key,[]);versions.get(key).push(v);}
      for (const members of versions.values()) {
        const first=members[0];
        body.append(node('div', first.research?.version_label || (first.research?.experiment_ref ? '冻结实验 ' + short(first.research.experiment_ref) : '版本说明未提供'), 'version-title'));
        for(const v of members){
        const button = node('button', v.research?.no_version ? '尚未登记版本' : v.research?.not_run ? '尚未运行' : runCaption(v), 'run-item' + (v.view_id === state.runId ? ' selected' : ''));
        button.dataset.runId = v.view_id; button.title = v.run.run_id || v.research?.run_record_ref || v.research?.version_id;
        button.append(node('span', statusLabel(statusOf(v)) + (v.evaluation ? ' · 评价已载入' : '') + (v.research?.favorite ? ' · 收藏' : '') + (v.research?.shelved ? ' · 搁置' : '')));
        button.addEventListener('click', () => selectRun(v.view_id)); body.append(button);
        }
      }
      tree.append(wrap);
    }
    if (!filtered.length) tree.append(node('p', '没有匹配的已保存记录。', 'small'));
    $('navigation-note').textContent = views.some(v => !v.research?.created_at) ? '部分记录未保存时间，按载入顺序显示。' : '按 Research 保存时间排序。';
    if(views.some(v=>v.public_display_projection))$('navigation-note').textContent+=' 本页展示精选运行。';
  }
  function renderHeader(v) {
    const r = v.run, research = v.research,stock=v.stock_ml,withoutAccount=!r.run_id;
    $('context-line').textContent = (research?.version_label || '版本说明未提供')+' / '+(r.run_id?'已保存账户结果':research?.not_run?'尚未运行':'保存研究登记')+(v.evaluation?' / 评价已载入':'');
    $('context-line').title = r.run_id || research?.run_record_ref || research?.version_id;
    $('evidence-badge').textContent = v.evidence_kind === 'research_record_only' ? '实验记录 · 账户结果未载入' : v.evidence_kind === 'synthetic_ui_fixture' ? '合成展示样例' : v.evidence_kind === 'synthetic_owner_output' ? '合成模拟回测' : '模拟回测';
    if(withoutAccount&&stock)$('evidence-badge').textContent='模型与信号 · '+(String(stock.experiment.account_status || '').startsWith('BLOCKED')?'账户未执行':'账户结果未载入');
    $('run-title').textContent = research?.title || '模拟回测 · ' + short(r.run_id);
    $('hypothesis').textContent = research?.hypothesis || '实验说明尚未载入。';
    const nav = r.nav || [];
    $('date-range').textContent = saved(v.configuration.start_session || nav[0]?.session) + ' — ' + saved(v.configuration.end_session || nav.at(-1)?.session);
    $('run-status').textContent = statusLabel(statusOf(v)) + (r.status ? '' : ' · 账户结果未载入');
    $('policy-badge').textContent = stockAccount(v) ? (v.approximate?'股票日线事后近似 · 研究假设':'股票严格状态对照') : v.approximate ? 'ETF 日线近似 · 实验假设' : v.blocked ? '市场状态缺证 · 严格阻断' : r.run_id ? '保存的执行假设' : '执行假设未提供';
    if(stockAccount(v))$('run-status').textContent='账户：'+statusLabel(r.status)+(research?.status?' / 登记：'+statusLabel(research.status):'');
    if(withoutAccount&&stock){
      const sessions=stock.experiment.definition?.config?.prediction_sessions || [],blocked=String(stock.experiment.account_status || '').startsWith('BLOCKED');
      $('date-range').textContent='预测窗口：'+(sessions.length?sessions[0]+' — '+sessions.at(-1):'未提供');
      $('run-status').textContent='研究登记：'+statusLabel(statusOf(v));
      $('policy-badge').textContent=blocked?'股票账户准入阻断':'账户状态见保存说明';
    }
    const history=byId.get(state.runId).registration_history || [],historySelect=$('registration-select');historySelect.replaceChildren();
    $('registration-context').hidden=history.length<2;
    if(history.length){for(const item of history){const ref=item.record.evaluation_ref,version=v.research_versions?.[item.record.version_ref];option(historySelect,item.record.run_record_ref,(version?.label || '版本说明未提供')+' · '+saved(item.record.created_at)+(ref?' / eval '+short(ref.evaluation_ref):' / 未登记评价')+(ref&&!item.evaluation?' · 评价未载入':''));}historySelect.value=state.registration || research?.run_record_ref;}
    $('notice').textContent = v.evidence_kind === 'research_record_only' ? (research?.no_version ? '此问题尚未登记版本。' : research?.not_run ? '本版本尚未登记运行。' : '实验状态：' + statusLabel(statusOf(v)) + '；原因：' + saved(research?.reason)) + ' 未载入的账户结果不可用。' : v.evidence_kind === 'synthetic_ui_fixture' ? '合成展示样例，交互验收不代表真实回测或策略有效。' :
      v.evidence_kind === 'synthetic_owner_output' ? '合成模拟回测，仅验证保存与展示，不代表真实数据收益。' :
      v.blocked ? '市场状态缺证，执行已阻断；没有可评价的策略成交。' :
      v.approximate ? 'ETF 日线近似模拟；实际开盘成交与流动性未获验证。' : '已保存模拟回测。';
    if(stockAccount(v))$('notice').textContent=r.stopped?'股票账户已停止，原因见来源详情。':v.approximate?'股票日线事后近似模拟；实际开盘成交与流动性未获验证。':'股票严格状态对照；未知状态按保存规则拒单。';
    if(stockAccount(v)&&['synthetic_ui_fixture','synthetic_owner_output'].includes(v.evidence_kind))$('notice').textContent='合成验收样例，不代表真实数据或策略收益。'+$('notice').textContent;
    const metrics = r.metrics || {}, cards = clear('metrics');
    cards.hidden=withoutAccount;
    document.querySelector('.tabs').hidden=withoutAccount;
    document.querySelectorAll('.pane').forEach(p=>p.hidden=withoutAccount);
    $('selection-context').hidden=withoutAccount;
    const comparison=byId.get(state.compare),old=comparison?.run.metrics || {};
    const period=v.evaluation?.period_metrics,oldPeriod=comparison?.evaluation?.period_metrics;
    const account=period?.account || metrics,oldAccount=oldPeriod?.account || old;
    cards.classList.toggle('with-cagr',!!(period || oldPeriod));
    const definitions = [['累计收益',account.total_return,percent,'整段回测',oldAccount.total_return],['最大回撤',account.max_drawdown,percent,'整段回测',oldAccount.max_drawdown],['总费用',metrics.total_fees_minor,money,'元 · 整段回测',old.total_fees_minor],['期末净资产',nav.at(-1)?.nav_minor,money,'元',comparison?.run.nav?.at(-1)?.nav_minor]];
    for (const [label,value,format,help,oldValue] of definitions) {
      const card = node('div', null, 'metric'); card.append(node('span',label));
      const val = node('strong',format(value),positive(value)); val.title = 'Owner 原值：' + saved(value); card.append(val,node('small',help)); cards.append(card);
      if(comparison){const old=node('span','对照 '+format(oldValue),'comparison-value');old.title='对照 Owner 原值：'+saved(oldValue);card.append(old);}
    }
    if(period || oldPeriod){
      const card=node('div',null,'metric cagr-metric'),leg=period?.account;
      card.append(node('span','年化收益（CAGR）'));
      const val=node('strong',cagr(leg),leg?.cagr_status==='AVAILABLE'?positive(leg.cagr):'unavailable');
      val.title='Owner 原值：'+cagrRaw(leg);card.append(val,node('small','保存的年化区间'));
      if(comparison){const old=node('span','对照 '+cagr(oldPeriod?.account),'comparison-value');old.title='对照 Owner 原值：'+cagrRaw(oldPeriod?.account);card.append(old);}
      cards.append(card);
    }
    for(const [key,label] of [['sharpe','Sharpe'],['calmar','Calmar']]){
      const value=v.evaluation?.risk_metrics?.[key],oldValue=comparison?.evaluation?.risk_metrics?.[key];
      if(value?.status!=='AVAILABLE'||!present(value.value))continue;
      const card=node('div',null,'metric'),display=node('strong',ratio(value.value));
      display.title='Owner 原值：'+saved(value.value);
      card.append(node('span',label),display,node('small','原回测范围 · 保存值'));
      if(comparison&&oldValue?.status==='AVAILABLE'&&present(oldValue.value)){
        const old=node('span','对照 '+ratio(oldValue.value),'comparison-value');old.title='对照 Owner 原值：'+saved(oldValue.value);card.append(old);
      }
      cards.append(card);
    }
    $('period-note').hidden=!(period || oldPeriod);
    $('period-note').textContent=period || oldPeriod ? '年化按保存报告区间：'+periodRange(period)+(comparison?' / 对照：'+periodRange(oldPeriod):'')+'；缩放不重算。' : '';
    $('period-note').title=json({current:period?.window,comparison:oldPeriod?.window});
    $('selection-context').textContent = state.interval ? '选中期间 ' + state.interval.start + ' — ' + state.interval.end + (state.session ? ' / ' + state.session : '') + '；指标仍为整段回测。' : '指标范围：整段回测' + (state.session ? ' / 选中 ' + state.session : '');
  }
  function renderStockML(v){
    const stock=v.stock_ml,report=stock?.stage_report,panel=$('stock-ml-context'),registered=(v.research?.output_refs || []).some(ref=>ref.artifact_type==='StockMLExperiment');panel.hidden=!stock&&!registered;
    $('stock-saved-report').hidden=!report;
    if(v.run.run_id){if(panel.previousElementSibling!==$('statistics'))$('statistics').after(panel);}
    else if(panel.previousElementSibling!==$('stock-account-context'))$('stock-account-context').after(panel);
    if(!report){clear('stock-report-summary');clear('stock-measurements');$('stock-report-raw').textContent='';$('stock-measurement-note').textContent='';}
    if(!stock){
      if(registered){
        $('stock-account-status').textContent='该登记的阶段产物未载入；账户结果不可用。保留原研究记录，不使用其他版本的模型或信号替代。';
        clear('stock-stage-values');$('stock-stage-config').textContent='阶段原值未载入。';
        $('stock-ic-note').textContent='对应版本的信号证据未载入；IC / RankIC 与覆盖不可用。';
        clear('stock-ic-table');$('stock-stage-refs').textContent=json({run_record_ref:v.research?.run_record_ref,version_ref:v.research?.version_id,output_refs:v.research?.output_refs});
      }
      return;
    }
    const experiment=stock.experiment,model=stock.model,evidence=stock.signal_evidence,config=experiment.definition?.config || {};
    const blocked=String(experiment.account_status || '').startsWith('BLOCKED');
    $('stock-account-status').textContent=v.run.run_id?'已关联股票账户保存结果 · '+saved(v.run.status)+'。当前结果来自该 run 与 Research 登记；模型 manifest 中的旧账户状态仅表示当时研究阶段，原值见来源详情。':(blocked?'股票账户未执行 · ':'账户状态：')+saved(experiment.account_status)+'；'+saved(experiment.account_reason)+'。研究登记完成只表示已保存的研究阶段，不代表账户回测完成。';
    const range=sessions=>sessions?.length?sessions[0]+' — '+sessions.at(-1):'未提供';
    const values=clear('stock-stage-values');
    for(const [label,value] of [['训练 fit cutoff',model.fit_cutoff],['声明 Feature session 窗口',range(config.feature_sessions)],['实际成熟训练样本窗口',report?reportWindow(report.training?.actual):'当前读取输出未提供'],['预测窗口',range(config.prediction_sessions)],['标签评价 cutoff',evidence.evaluation_cutoff],['Feature ID / 语义版本',(model.feature_selection || config.feature_selection || []).map(f=>f.id+' / '+f.semantic_version).join('、') || '未提供'],['特征标准化',model.feature_normalization],['预测目标语义',model.target_semantics || evidence.score_semantics],['标签成熟规则',model.label_normalization?.maturity],['训练 / 预测耗时',report?'见保存阶段测量（按模式和来源区分）':'当前读取输出未提供']]){
      const row=node('div',null,'point-row');row.append(node('span',label),node('strong',saved(value)));values.append(row);
    }
    $('stock-stage-config').textContent=json({fit_cutoff:model.fit_cutoff,feature_normalization:model.feature_normalization,label_normalization:model.label_normalization,score_semantics:evidence.score_semantics,label_semantics:evidence.label_semantics,minimum_pairs:evidence.minimum_pairs,rank_ties:evidence.rank_ties,parameters:model.parameters,num_boost_round:model.num_boost_round,environment:model.environment});
    $('stock-ic-note').textContent='IC、RankIC 和有效/排除配对均为 owner 保存值，不表示账户收益。'+(report?'汇总均值见保存阶段报告；ICIR 未提供，不自行计算。':'均值与 ICIR 未提供，不从逐日值计算。');
    if(report)renderStockReport(report);
    const table=node('table'),head=node('tr'),thead=node('thead'),body=node('tbody');
    for(const label of ['Session','IC','RankIC','有效预测','有效配对','排除配对','原因'])head.append(node('th',label));thead.append(head);table.append(thead,body);
    for(const row of evidence.series || []){const tr=node('tr');tr.dataset.icSession=row.session;tr.title=json(row);for(const key of ['session','ic','rank_ic','prediction_valid_count','valid_pair_count','excluded_pair_count','reason'])tr.append(node('td',saved(row[key])));body.append(tr);}
    clear('stock-ic-table').append(table);
    $('stock-stage-refs').textContent=json({experiment_ref:experiment.experiment_ref,feature_ref:experiment.feature_ref,label_ref:experiment.label_ref,dataset_ref:experiment.dataset_ref,model_ref:experiment.model_ref,signal_run_ref:experiment.signal_run_ref,evidence_ref:experiment.evidence_ref,definition:experiment.definition,signal_evidence:evidence});
  }
  const reportWindow = window => !window ? '未提供' : saved(window.first_feature_session)+' — '+saved(window.last_feature_session)+' · '+saved(window.session_count)+' session'+(Object.hasOwn(window,'training_row_count')?' · '+saved(window.training_row_count)+' 行':'');
  function renderStockReport(report){
    const training=report.training,summary=report.signal_summary,values=clear('stock-report-summary');
    for(const [label,value] of [['训练声明窗口（fit cutoff 内）',reportWindow(training.declared)],['实际成熟训练窗口',reportWindow(training.actual)],['IC 均值 / 有效 session',saved(summary.ic?.mean)+' / '+saved(summary.ic?.session_count)],['RankIC 均值 / 有效 session',saved(summary.rank_ic?.mean)+' / '+saved(summary.rank_ic?.session_count)],['汇总权重 / 缺值规则',saved(summary.weighting)+' / '+saved(summary.missing_policy)],['预测总行 / 有效 / 无效',saved(summary.prediction_row_count)+' / '+saved(summary.prediction_valid_row_count)+' / '+saved(summary.prediction_invalid_row_count)],['有效 / 排除配对',saved(summary.valid_pair_count)+' / '+saved(summary.excluded_pair_count)]]){
      const row=node('div',null,'point-row');row.append(node('span',label),node('strong',value));values.append(row);
    }
    $('stock-measurement-note').textContent='以下 seconds、模式和状态均为 owner 保存值。复用未执行不是零秒冷跑；继承的冷构建只说明早期 Feature/Qlib 来源，不代表当前模型冷训练。build/total 不相加，receipt 整体内存与规模不摊到阶段，不推算吞吐。';
    const table=node('table'),thead=node('thead'),head=node('tr'),body=node('tbody');
    for(const label of ['阶段','模式','状态','Owner 秒数','来源范围'])head.append(node('th',label));thead.append(head);table.append(thead,body);
    for(const measurement of report.measurements){
      const tr=node('tr');tr.title=json(measurement);tr.dataset.measurementStage=measurement.stage;tr.dataset.measurementMode=measurement.mode || '';
      const stage=({feature:'特征',qlib:'Qlib 导出',label_dataset:'标签 / 训练集',train:'训练',predict:'预测',build:'保存构建',total:'总计',cache_load:'缓存读取'})[measurement.stage] || measurement.stage;
      const mode=({saved_input_build:'本次保存构建',cache_reuse:'缓存复用',cold_build:'冷构建'})[measurement.mode] || measurement.mode;
      const status=({MEASURED:'已测量',REUSED_NOT_EXECUTED:'复用，未执行',NOT_PROVIDED:'未提供'})[measurement.status] || measurement.status;
      const scope=!measurement.receipt_file_digest?'测量 receipt 未提供':measurement.inherited_feature_only?'继承早期 Feature/Qlib（非当前模型冷跑）':'当前实验保存 receipt';
      for(const value of [stage,mode,status,measurement.seconds,scope])tr.append(node('td',saved(value)));
      body.append(tr);
    }
    clear('stock-measurements').append(table);$('stock-report-raw').textContent=json(report);
  }
  function renderStockAccount(v){
    const panel=$('stock-account-context');panel.hidden=!stockAccount(v);
    if(panel.hidden){$('stock-account-scope').textContent='';$('stock-account-refs').textContent='';return;}
    const context=v.stock_context,profile=v.configuration.profile;
    $('stock-account-scope').textContent='数量：股；价格：元/股；100 股委托、T+1。范围、税费与容量见展开详情。';
    $('stock-account-refs').textContent=json({run_id:v.run.run_id,content_digest:v.run.content_digest,committed_sequence:v.run.committed_sequence,status:v.run.status,stopped:v.run.stopped,quantity_unit:v.run.quantity_unit,price_unit:v.run.price_unit,admission_ref:v.run.admission_ref,supported_universe_ref:v.run.supported_universe_ref,context,profile,native_source_evidence:v.market.source_evidence,projection_note:'仅显示投影；完整 native DataBatch 身份为 source reference，coverage 与压缩 payload 留在 owner 保存文件，不将此投影重新认定为完整批次。'});
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
    let path = '', open = false;const indices=new Map(sessions.map((s,i)=>[s,i]));
    for (const point of points) {
      const index = indices.get(point.session), value = numeric(point.value);
      if (index === undefined || value === null) {open = false;continue;}
      path += (open ? ' L' : ' M') + x(index).toFixed(2) + ',' + y(value).toFixed(2); open = true;
    }
    if (path) svg.append(svgEl('path',{d:path,fill:'none',stroke:color,'stroke-width':2,'stroke-dasharray':dash}));
  }
  function highlight(svg,sessions,x,top,bottom){
    if(state.interval){const indices=sessions.map((s,i)=>s>=state.interval.start&&s<=state.interval.end?i:-1).filter(i=>i>=0);
      if(indices.length)svg.append(svgEl('rect',{x:x(indices[0])-3,y:top,width:Math.max(6,x(indices.at(-1))-x(indices[0])+6),height:bottom-top,fill:'#dbe8f4',opacity:.55,'data-selected-start':state.interval.start,'data-selected-end':state.interval.end}));}
    const index=sessions.indexOf(state.session);if(index>=0)svg.append(svgEl('line',{x1:x(index),x2:x(index),y1:top,y2:bottom,stroke:'#547da3','stroke-dasharray':'4 3','data-selected-session':state.session}));
  }
  function canonical(value){if(Array.isArray(value))return value.map(canonical);if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])]));return value;}
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
    select.disabled=!r.run_id;
    for (const view of views) if(view.view_id !== v.view_id && view.run.run_id) option(select,view.view_id,(view.research?.version_label || short(view.run.run_id))+' · '+runCaption(view)+' · '+statusOf(view));
    select.value = state.compare; $('benchmark-toggle').checked = state.benchmark;
    const differences=[],unverified=[],oldConditions=new Map((comparison?.comparison_conditions || []).map(f=>[f.key,f]));
    if(comparison)for(const fact of v.comparison_conditions || []){const old=oldConditions.get(fact.key);if(!fact.provided||!old?.provided)unverified.push(fact.label);else if(json(canonical(fact.value))!==json(canonical(old.value)))differences.push(fact.label);}
    if(comparison&&!(v.comparison_conditions || []).length)unverified.push('比较条件');
    $('comparison-notice').textContent = !comparison ? '可添加其他运行，比较保存结果。' : (differences.length?'条件差异：'+differences.join('、')+'。':'已保存条件未发现差异。')+(unverified.length?' 部分条件缺少保存证据，详见配置。':'');
    const changes=[];if(comparison&&r.signal_ref!==comparison.run.signal_ref)changes.push('信号版本');if(comparison&&v.research?.version_id!==comparison.research?.version_id)changes.push('研究版本');
    $('comparison-changes').textContent=comparison?'研究变动：'+(changes.join('、') || '见保存说明')+'；具体参数与声明见展开详情。':'';
    $('configuration-differences').textContent = '本次改了什么：'+(changes.join('、') || '以保存说明为准')+'；声明变动：'+saved(v.research?.changes && json(v.research.changes));
    const ownerDiff=v.research?.comparison_left_ref===comparison?.research?.version_id?v.research?.version_comparison:comparison?.research?.comparison_left_ref===v.research?.version_id?comparison.research.version_comparison:null;

    const benchmark = v.evaluation?.benchmark;
    $('benchmark-toggle').disabled=!benchmark || benchmark.status==='MISSING';
    $('benchmark-toggle').checked=state.benchmark && !$('benchmark-toggle').disabled;
    const missingReasons=[...new Set((benchmark?.series || []).map(p=>p.missing_reason).filter(present))];
    const period=v.evaluation?.period_metrics,benchMetrics=period?.benchmark || benchmark;
    $('benchmark-note').textContent = benchmark ? '沪深300价格指数，不含分红；账户收益含已入账分红。累计收益 '+percent(benchMetrics.total_return)+'，最大回撤 '+percent(benchMetrics.max_drawdown)+(period?'，CAGR '+cagr(period.benchmark):'')+'。' : '';
    $('benchmark-note').title=period?cagrRaw(period.benchmark):'';
    chartUI.summaries(v,comparison,differences,unverified);
    chartUI.performance(v);
  }
  function pointRow(panel, label, value) {
    const row=node('div',null,'point-row');row.append(node('span',label),node('strong',saved(value)));panel.append(row);
  }
  const unitEvents = (v,ids) => (v.market.unit_splits || []).filter(item=>ids.includes(item.event.event_id));
  const unitSources = (v,events) => {const refs=new Set(events.flatMap(item=>item.source_refs || []));return (v.market.unit_split_source_evidence || []).filter(source=>refs.has(source.reference));};
  function renderPoint(v, event = null, kind = state.kind) {
    const panel=clear('trade-point');panel.append(node('h3',event ? (kind==='fills'?'成交原值':kind==='orders'?'委托原值':'决策原值') : '所选行情原值'));
    pointRow(panel,'证券',securityName(state.security));pointRow(panel,'交易日',event?.session || event?.trade_session || state.session);
    if (event) {
      if (kind==='fills') {
        pointRow(panel,'成交价（'+priceUnit(v)+'） / 数量（'+quantityUnit(v)+'）',saved(event.price)+' / '+saved(event.quantity));pointRow(panel,'费用（元）',money(event.fee_minor));
        if(stockAccount(v))for(const [key,label] of [['commission_minor','佣金（元）'],['stamp_tax_minor','印花税（元）'],['transfer_fee_minor','过户费（元）']])pointRow(panel,label,money(event[key]));
        const order=(v.run.orders || []).find(o=>o.order_id===event.order_id);
        pointRow(panel,'方向',event.side==='BUY'?'买入':'卖出');
        const admission=event.execution_admission || order?.execution_admission;
        pointRow(panel,'执行说明',admission==='STOCK_OBSERVED_DAILY_ASSUMPTION'?'股票日线事后近似假设':admission==='ETF_OBSERVED_DAILY_ASSUMPTION'?'ETF 日线近似假设':'保存的模拟成交');
      } else if(kind==='orders') {
        pointRow(panel,'委托 / 成交数量（'+quantityUnit(v)+'）',saved(event.quantity)+' / '+saved(event.filled_quantity));
        pointRow(panel,'委托状态',statusLabel(event.status));pointRow(panel,'未成交原因',event.reason==='UNKNOWN_MARKET_STATUS'?'市场状态缺证':statusLabel(event.reason));
      } else {
        pointRow(panel,'信号日',event.feature_session);pointRow(panel,'决策交易日',event.trade_session);
        pointRow(panel,'决策说明',event.status==='NO_DECISION'?'NO_DECISION：保持原持仓，不隐式清仓':event.trace?'已保存决策依据':'决策依据暂未提供');
      }
      const order=kind==='orders'?event:(v.run.orders || []).find(o=>o.order_id===event.order_id),ids=order?.announced_suspension_event_ids || [];
      if(ids.length)pointRow(panel,'公告停牌事件来源',ids.join('、'));
      const events=unitEvents(v,ids),detail=node('details');detail.append(node('summary','执行依据与原始记录'),node('pre',json({event,order,announced_suspension_events:ids.length?events:undefined,unit_event_sources:ids.length?unitSources(v,events):undefined})));panel.append(detail);
    } else {
      const rows=v.market.data_batch?.records || v.market.native_chart?.records || v.market.rows;
      const point=rows.find(p=>p.security_id===state.security && p.session===state.session);
      const ownerPoint=v.market.rows.find(p=>p.security_id===state.security && p.session===state.session);
      if(point) {
        for(const [key,label] of [['open','开盘（'+priceUnit(v)+'）'],['high','最高（'+priceUnit(v)+'）'],['low','最低（'+priceUnit(v)+'）'],['close','收盘（'+priceUnit(v)+'）'],['volume','全天量'],['volume_units','全天量（份）'],['volume_shares','全天量（股）']]) if(Object.hasOwn(point,key)) pointRow(panel,label,point[key]);
        const marketPoint=ownerPoint || point;
        for(const [key,label] of [['market_state','保存的市场状态'],['state_reason','保存的状态原因']]) if(Object.hasOwn(marketPoint,key)) pointRow(panel,label,marketPoint[key]);
        const chart=v.market.native_chart,provenance=chart?Object.fromEntries(Object.entries(chart.field_meta).map(([field,meta])=>[field,{unit:meta.unit,dtype:meta.dtype,by_key:meta.by_key.find(m=>m.security_id===state.security&&m.session===state.session)}])):undefined;
        const detail=node('details');detail.append(node('summary','行情原值与来源'),node('pre',json({price_point:point,owner_market_point:ownerPoint || null,native_chart_source_ref:chart?.source_ref,native_context:chart?.context,field_meta:provenance,display_projection:chart?.display_projection})));panel.append(detail);
      }
      else panel.append(node('p','所选日期未保存行情，不填补。','missing'));
      const positions=(v.run.positions || []).filter(p=>p.security_id===state.security && p.session===state.session);
      for(const position of positions) {pointRow(panel,'持仓 / 可卖数量（'+quantityUnit(v)+'）',saved(position.quantity)+' / '+saved(position.sellable_quantity));pointRow(panel,'估值日 / 是否过期',saved(position.mark_session)+' / '+saved(position.is_stale));}
      for(const position of positions) if(stockAccount(v)||Object.hasOwn(position,'mark_basis_event_id')){
        pointRow(panel,'账户保存估值价（'+priceUnit(v)+'）',position.mark_price);
        pointRow(panel,'估值单位依据',position.mark_basis_event_id || '原生报价');
        const events=position.mark_basis_event_id?unitEvents(v,[position.mark_basis_event_id]):[],detail=node('details');detail.append(node('summary','保存持仓与单位来源'),node('pre',json({position,unit_event:position.mark_basis_event_id?events:null,unit_event_sources:unitSources(v,events)})));panel.append(detail);
      }
    }
  }
  function selectEvent(v,event,kind) {
    state.kind=kind;state.session=event.session || event.trade_session;state.security=event.security_id || event.selected_security_id || state.security;
    state.fillId=kind==='fills'?event.fill_id:'';state.eventId=eventKey(event);locateDay(v,state.session);renderHeader(v);renderTrade(v);renderPoint(v,event,kind);
  }
  function windowBounds(points){
    const first=points[0]?.session || '',last=points.at(-1)?.session || '',window=state.tradeWindow;
    if(window.mode==='all')return {start:first,end:last};
    if(window.mode==='custom')return {start:window.start || first,end:window.end || last};
    if(!last)return {start:'',end:''};
    const parts=last.split('-').map(Number),date=new Date(Date.UTC(parts[0],parts[1]-1-Number(window.mode),parts[2]));
    return {start:date.toISOString().slice(0,10),end:last};
  }
  function locateDay(v,day){
    const points=(v.market.data_batch?.records || v.market.native_chart?.records || v.market.rows).filter(p=>p.security_id===state.security).sort((a,b)=>a.session.localeCompare(b.session));
    const window=windowBounds(points);if(day>=window.start&&day<=window.end)return;
    const index=points.findIndex(p=>p.session>=day);if(index>=0)state.tradeWindow={mode:'custom',start:points[Math.max(0,index-20)].session,end:points[Math.min(points.length-1,index+20)].session};
  }
  function renderTrade(v) {
    chartUI.trade(v);
    const applications=v.run.unit_split_applications || [],unitList=clear('unit-split-list');
    $('unit-split-context').hidden=!applications.length;
    for(const application of applications){
      const button=node('button',application.session+' · '+statusLabel(application.status)+' · '+saved(application.before_quantity)+' → '+saved(application.after_quantity)+' 份','unit-split-item');
      button.dataset.unitEventId=application.event_id;button.addEventListener('click',()=>{state.session=application.session;chartUI.setWindow(application.session,application.session);chartUI.openRaw('保存账户单位事件',application);});unitList.append(button);
    }
  }
  function renderEpisodeList(v) {
    const list=clear('episode-list'),pager=clear('episode-pager'),summary=$('episode-filter-summary');
    const episodes=v.evaluation?.episodes || [],security=$('episode-security'),selected=security.value;
    security.replaceChildren();option(security,'','全部证券');
    for(const id of [...new Set(episodes.map(e=>e.security_id))].sort())option(security,id,securityName(id));
    security.value=[...security.options].some(o=>o.value===selected)?selected:'';
    const status=$('episode-status').value,scope=$('episode-scope').value;
    const runEnd=v.run.nav?.at(-1)?.session,start=state.interval?.start || v.run.nav?.[0]?.session,end=state.interval?.end || runEnd;
    const matches=episodes.filter(e=>(!security.value||e.security_id===security.value) &&
      (!status||e.status===status) && (scope!=='window'||!start||!end||
        (e.entry_session || start)<=end && (e.exit_session || runEnd || end)>=start))
      .sort((a,b)=>(b.exit_session || runEnd || b.entry_session).localeCompare(a.exit_session || runEnd || a.entry_session) ||
            (b.entry_session || '').localeCompare(a.entry_session || '') || String(a.episode_id).localeCompare(String(b.episode_id)));
    const pageSize=12,total=Math.ceil(matches.length/pageSize);
    state.episodePage=Math.max(0,Math.min(state.episodePage || 0,Math.max(0,total-1)));
    summary.textContent=matches.length+' / '+episodes.length+' 段匹配 · 最近优先，每页最多 '+pageSize+' 段；上方统计仍为原回测全段。';
    if(!matches.length){list.append(node('p','当前筛选没有保存持仓段。','small'));return;}
    for(const episode of matches.slice(state.episodePage*pageSize,(state.episodePage+1)*pageSize)){
      const button=node('button',null,'episode-item');button.dataset.episodeId=episode.episode_id;
      const left=node('div',securityName(episode.security_id)+' · '+statusLabel(episode.status));left.append(node('span',saved(episode.entry_session)+' → '+(episode.status==='OPEN'?'未闭合':saved(episode.exit_session))+' · '+statusLabel(episode.income_status)));
      const right=node('div',present(episode.net_pnl_minor)?money(episode.net_pnl_minor)+' 元净盈亏':episode.status==='OPEN'?'期末仍持有 · 完整净盈亏未提供':'完整净盈亏未提供');right.append(node('span',episode.statistics_eligible?'纳入统计':'未纳入统计 · 原因见定义'));button.title=json(episode);button.append(left,right);button.addEventListener('click',()=>selectEpisode(episode));list.append(button);
    }
    const previous=node('button','上一页'),next=node('button','下一页');previous.disabled=state.episodePage===0;next.disabled=state.episodePage>=total-1;
    previous.addEventListener('click',()=>{state.episodePage--;renderEpisodeList(v);});next.addEventListener('click',()=>{state.episodePage++;renderEpisodeList(v);});
    pager.append(previous,node('span',(state.episodePage+1)+' / '+total+' · 每页 '+pageSize+' 段','small'),next);
  }
  function renderStatistics(v) {
    const evaluation=v.evaluation;
    if(!evaluation){clear('episode-pager');for(const id of ['month-heatmap','legacy-episode-chart','episode-metrics','episode-list'])missing(id,'账户评价数据暂未提供。');$('episode-filter-summary').textContent='持仓段暂未提供。';$('episode-definition').textContent='未保存定义，不从成交构造完整持仓段。';$('distribution-note').textContent='未保存分布，不从成交或持仓重算。';}
    else {
      const months=evaluation.monthly_returns || [],years=[...new Set(months.map(m=>m.month.slice(0,4)))].sort(),grid=node('div',null,'heat-grid');
      grid.append(node('div',''));for(let month=1;month<=12;month++)grid.append(node('div',String(month).padStart(2,'0'),'month-label'));
      for(const year of years){grid.append(node('div',year,'year-label'));for(let i=1;i<=12;i++){
        const key=year+'-'+String(i).padStart(2,'0'),report=months.find(m=>m.month===key),partial=report?.status==='PARTIAL';
        const value=report?.status==='COMPLETE'?report.return:partial?report.observed_return:null;
        const button=node('button',present(value)?percent(value)+(partial?' *':''):'—','heat-cell '+positive(value)+(partial?' partial':''));
        button.dataset.month=key;button.title=report?json(report):key+' · Owner 未保存该月';button.disabled=!report?.first_session || !report?.last_session;
        button.addEventListener('click',()=>{state.interval={start:report.first_session,end:report.last_session};state.tradeWindow={mode:'custom',...state.interval};state.session=report.last_session;state.fillId='';state.eventId='';state.pane='performance';render();});grid.append(button);
      }}clear('month-heatmap').append(grid);if(!months.length)missing('month-heatmap','月度数据暂未提供。');
      const metrics=evaluation.episode_metrics || {},card=clear('episode-metrics');
      for(const [label,value] of [['闭合段 / 可统计闭合',saved(metrics.closed_count)+' / '+saved(metrics.eligible_closed_count)],['开放 / 左截断 / 已知待分红',saved(metrics.open_count)+' / '+saved(metrics.left_censored_count)+' / '+saved(metrics.income_pending_count)],['盈利 / 亏损 / 平局',saved(metrics.win_count)+' / '+saved(metrics.loss_count)+' / '+saved(metrics.tie_count)],['胜率',percent(metrics.win_rate)],['平均段净盈亏（元）',money(metrics.mean_net_pnl_minor)],['平均段收益率',percent(metrics.mean_episode_return)],['分红观察范围',statusLabel(metrics.dividend_scope_status)]]){
        const row=node('div',null,'episode-stat');row.append(node('span',label),node('strong',value));card.append(row);
      }
      $('episode-definition').textContent='完整段从无持仓到清仓；段内加减仓合并，手续费与已确认分红计入。净收益率采用累计买入含费成本作为分母，完整可统计段等权平均。开放、左截断、已知收入待确认单列；分红观察范围：'+statusLabel(metrics.dividend_scope_status)+'。完整原值见来源记录。';
      const episodes=evaluation.episodes || [],closed=episodes.filter(e=>e.statistics_eligible && e.status==='CLOSED' && present(e.net_pnl_minor));
      const distribution=evaluation.pnl_distribution;
      $('distribution-note').textContent=distribution?.status==='AVAILABLE'?'保存的分箱统计，单位元；仅含可统计闭合段。点击持仓段定位。':'样本不足 10 段；展示已保存的逐段净盈亏，尚不足以形成分布。';
      if(distribution?.status==='AVAILABLE'){
        const bins=distribution.bins || [],svg=chart('legacy-episode-chart',440,200,'保存的完整持仓段净盈亏桶计数'),maximum=Math.max(1,...bins.map(b=>Number(b.count)));
        bins.forEach((bucket,i)=>{const x=40+i*46,h=Number(bucket.count)/maximum*105;
          const bar=svgEl('rect',{x,y:135-h,width:34,height:h,fill:'#547da3','data-bin-count':bucket.count});
          bar.append(svgEl('title',{},(!present(bucket.lower_minor)?'低于 '+money(bucket.upper_minor):!present(bucket.upper_minor)?'不低于 '+money(bucket.lower_minor):'['+money(bucket.lower_minor)+', '+money(bucket.upper_minor)+')')+' 元 · '+bucket.count+' 段'));svg.append(bar);
          svg.append(svgEl('text',{x:x+17,y:126-h,'text-anchor':'middle',fill:'#40536a','font-size':11},bucket.count));
          svg.append(svgEl('text',{x:x+17,y:155,'text-anchor':'middle',fill:'#607184','font-size':10},present(bucket.lower_minor)?money(bucket.lower_minor):'低于 '+money(bucket.upper_minor)));
        });
      }
      else if(!closed.length)missing('legacy-episode-chart','暂无可统计的闭合段。');
      else {
        const svg=chart('legacy-episode-chart',440,200,'各可统计闭合持仓段的保存净盈亏，单位元'),range=bounds(closed.map(e=>Number(e.net_pnl_minor)/100)),x=value=>40+(value-range[0])/(range[1]-range[0])*350;
        svg.append(svgEl('line',{x1:40,x2:390,y1:120,y2:120,stroke:'#ccd7e2'}));
        if(range[0]<=0&&range[1]>=0)svg.append(svgEl('line',{x1:x(0),x2:x(0),y1:30,y2:130,stroke:'#607184','stroke-dasharray':'3 3'}));
        closed.forEach((e,i)=>{const circle=svgEl('circle',{cx:x(Number(e.net_pnl_minor)/100),cy:70+(i%3)*16,r:6,fill:Number(e.net_pnl_minor)>0?'#c16583':Number(e.net_pnl_minor)<0?'#428766':'#607184',role:'button',tabindex:0,'data-episode-id':e.episode_id});circle.append(svgEl('title',{},money(e.net_pnl_minor)+' 元 · '+e.episode_id));circle.addEventListener('click',()=>selectEpisode(e));circle.addEventListener('keydown',event=>{if(event.key==='Enter')selectEpisode(e);});svg.append(circle);});
        svg.append(svgEl('text',{x:40,y:155,fill:'#607184','font-size':11},range[0].toFixed(2)));svg.append(svgEl('text',{x:390,y:155,'text-anchor':'end',fill:'#607184','font-size':11},range[1].toFixed(2)+' 元'));
      }
      renderEpisodeList(v);
    }
    chartUI.returnPoints(v);
    $('signal-evaluation').textContent=v.research?.signal_evaluation?json(v.research.signal_evaluation):'未保存适用的信号评价；不从账户结果推导 IC/ICIR。';
  }
  function selectEpisode(episode){const fillId=episode.fill_refs?.at(-1)?.fill_id || '',linkedFill=(current().run.fills || []).find(f=>f.fill_id===fillId);state.security=episode.security_id;state.chainSecurity=episode.security_id;$('chain-search').value='';$('chain-status').value='';state.interval={start:episode.entry_session || current().run.nav?.[0]?.session,end:episode.exit_session || current().run.nav?.at(-1)?.session};state.tradeWindow={mode:'custom',...state.interval};state.session=episode.exit_session || linkedFill?.session || episode.entry_session || state.interval.end;state.pane='trade';state.kind='fills';state.fillId=fillId;state.eventId=fillId;render();requestAnimationFrame(()=>$('trade-chart').scrollIntoView({block:'center'}));}
  function renderSources(v) {
    const panel=clear('source-details'),all=[...(v.run.limitations || []),...(v.evaluation?.limitations || [])];
    if(v.research?.outcome)panel.append(node('p','Research 保存说明：'+v.research.outcome,'small'));
    for(const text of all.slice(0,3))panel.append(node('p',String(text),'small'));
    if(all.length>3)panel.append(node('p','另有 '+(all.length-3)+' 条保存限制，可在原始记录中查看。','small'));
    const refs=clear('source-refs');
    for(const [label,value] of [['账户/评价合同',saved(v.run.contract_version)+' / '+saved(v.evaluation?.contract_version)],['账户最终水位',v.run.committed_sequence],['价格/数量单位',priceUnit(v)+' / '+quantityUnit(v)],['来源与固定版本','原值与身份在独立原始记录入口查看']])pointRow(refs,label,value);
    const display=v.market.review_display;if(display){pointRow(refs,'固定显示锚点 A',display.context.anchor_session);pointRow(refs,'共同截止 C',display.context.knowledge_cutoff);pointRow(refs,'显示范围','原 native 图层的完整运行窗口；缩放不改变 A/C');if(v.market.security_name_scope)pointRow(refs,'名称范围',v.market.security_name_scope);if(v.market.security_label_source){pointRow(refs,'名称独立 Snapshot',v.market.security_label_source.source_snapshot_id);pointRow(refs,'名称观察截止',v.market.security_label_source.label_cutoff);}}
    $('generated-note').textContent='页面生成于 '+data.generated_at+'；不是数据更新时间。指标与交易依据均来自保存产物，浏览没有计算或执行调用。';
  }
  function render() {
    const v=current();document.querySelectorAll('.pane').forEach(p=>p.classList.toggle('active',p.id===state.pane));renderTree();renderHeader(v);renderStockAccount(v);renderStockML(v);renderPerformance(v);renderTrade(v);renderStatistics(v);renderSources(v);chartUI.resize();
    document.querySelectorAll('.pane').forEach(p=>p.classList.toggle('active',p.id===state.pane));document.querySelectorAll('[data-pane]').forEach(b=>b.classList.toggle('active',b.dataset.pane===state.pane));
  }
  document.querySelectorAll('[data-pane]').forEach(b=>b.addEventListener('click',()=>{state.pane=b.dataset.pane;render();}));
  $('status-filter').addEventListener('change',e=>{state.status=e.target.value;renderTree();});$('tag-filter').addEventListener('change',e=>{state.tag=e.target.value;renderTree();});
  $('compare-run').addEventListener('change',e=>{state.compare=e.target.value;state.legendVisible.comparison=true;renderHeader(current());renderPerformance(current());});$('benchmark-toggle').addEventListener('change',e=>{state.benchmark=e.target.checked;if(state.benchmark)state.legendVisible.benchmark=true;renderPerformance(current());});
  $('registration-select').addEventListener('change',e=>{state.registration=e.target.value;state.session='';state.interval=null;state.tradeWindow={mode:'all'};state.fillId='';state.eventId='';render();});
  for(const id of ['episode-scope','episode-security','episode-status'])$(id).addEventListener('change',()=>{state.episodePage=0;renderEpisodeList(current());});
  $('security-select').addEventListener('change',e=>{state.security=e.target.value;state.chainSecurity=e.target.value;state.session='';state.fillId='';state.eventId='';renderTrade(current());renderHeader(current());});
  $('session-select').addEventListener('change',e=>{state.session=e.target.value;state.fillId='';state.eventId='';locateDay(current(),state.session);renderTrade(current());renderHeader(current());renderPerformance(current());});
  $('copy-context').addEventListener('click',async()=>{
    const v=current(),text=json({question_id:v.research?.question_id,version_ref:v.research?.version_id,run_record_ref:v.research?.run_record_ref,run_id:v.run.run_id,content_digest:v.run.content_digest,signal_ref:v.run.signal_ref,market_ref:v.run.market_ref,profile_ref:v.run.profile_ref,evaluation_ref:v.evaluation?.evaluation_ref,security_id:state.security,session:state.session,interval:state.interval,changes:v.research?.changes,stock_experiment_ref:v.stock_ml?.experiment.experiment_ref,model_ref:v.stock_ml?.experiment.model_ref,signal_evidence_ref:v.stock_ml?.experiment.evidence_ref,stage_report_ref:v.stock_ml?.stage_report?.stage_report_ref,stage_report_content_digest:v.stock_ml?.stage_report?.content_digest});
    try {await navigator.clipboard.writeText(text);$('toast').textContent='已复制运行上下文与证据引用。';}catch{const area=node('textarea');area.value=text;document.body.append(area);area.select();const copied=document.execCommand('copy');area.remove();$('toast').textContent=copied?'已复制运行上下文与证据引用。':'浏览器未允许复制；来源详情中保留相同引用。';}
    $('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',2500);
  });
  const mobileNavigation=matchMedia('(max-width:700px)');
  const resizeNavigation=()=>{$('experiment-navigation').open=!mobileNavigation.matches;};
  mobileNavigation.addEventListener('change',resizeNavigation);resizeNavigation();
  const openTradeDay=day=>{state.session=day;state.pane='trade';state.fillId='';state.eventId='';render();};
  chartUI=createAxiomInteractions({state,$,current,byId,node,saved,present,percent,money,priceUnit,quantityUnit,statusLabel,renderHeader,renderPoint,selectEvent,stockAccount,eventKey,selectEpisode,openTradeDay});
  chartUI.bind();initializeFilters();render();
})();
