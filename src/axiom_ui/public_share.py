"""Explicit public display projection over previously validated UI exports.

This module has no Owner imports and cannot collect, train, replay, or evaluate.
Original owner identities describe the saved owner document, not this projection.
"""
from copy import deepcopy
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

from .workbench import ASSETS, _render

PATH = re.compile(r'(?:file://)?/(?:Users|tmp|private|var/folders|home)/[^\s"<>;,]+|[A-Za-z]:\\[^\s"<>;,]+|(?:\.?/?\.artifacts/)[^\s"<>;,]+')
SECRET = re.compile(r'github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----')
DROP = {'source_evidence', 'unit_split_source_evidence', 'coverage', 'coverage_bundle', 'payload',
        'field_meta', 'by_key', 'query', 'definition', 'metadata', 'locator', 'uri', 'path',
        'root', 'input_refs', 'output_refs', 'artifact_path', 'source_path', 'document_refs',
        'raw_batch_id', 'extraction_version', 'revision_id', 'revision_sequence', 'first_observed_at',
        'records', 'environment', 'parameters', 'model', 'trace'}
RUN = ('contract_version', 'run_id', 'account_id', 'status', 'content_digest', 'committed_sequence',
       'signal_ref', 'market_ref', 'profile_ref', 'core_version', 'runtime_version', 'implementation_ref',
       'metrics', 'nav', 'positions', 'orders', 'fills', 'limitations', 'final_account', 'initial_nav_minor',
       'quantity_unit', 'price_unit', 'admission_ref', 'supported_universe_ref', 'stopped', 'unit_split_applications')
EVALUATION = ('benchmark', 'benchmark_ref', 'content_digest', 'contract_version', 'dividend_scope_ref',
              'episode_metrics', 'episodes', 'evaluation_ref', 'evaluation_version', 'implementation_ref',
              'input_run_ref', 'limitations', 'market_ref', 'monthly_returns', 'period_metrics',
              'pnl_distribution', 'profile_ref', 'series', 'signal_ref', 'spec', 'spec_ref', 'status',
              'base_evaluation_ref', 'base_evaluation_content_digest', 'benchmark_refs', 'benchmark_comparisons',
              'risk_metrics', 'drawdown_interval', 'return_distribution', 'analysis_series',
              'execution_summary', 'concentration_series', 'episode_points')
RESEARCH = ('question_id', 'question_ref', 'experiment_ref', 'title', 'hypothesis', 'version_id',
            'version_label', 'version_explanation', 'created_at', 'status', 'reason', 'outcome',
            'run_record_ref', 'saved_run_ref', 'run_kind', 'changes', 'favorite', 'shelved',
            'last_activity_at', 'saved_backtest_count', 'registration_count')
TRACE = ('reason', 'rule', 'budget_basis', 'cash_check', 'eligible_count', 'reference_budget_minor',
         'score_semantics', 'sizing', 'tie_break', 'security_id', 'target_quantity', 'quantity',
         'selected_security_id', 'selected_security_ids', 'feature_session', 'trade_session',
         'threshold', 'signal', 'condition', 'result', 'action')
ROW = ('security_id', 'session', 'close', 'volume', 'volume_units', 'volume_shares', 'market_state',
       'state_reason', 'close_available_at', 'execution_evidence_cutoff', 'source_refs')
EVENT = ('event_id', 'security_id', 'event_type', 'record_date', 'effective_date', 'effective_phase',
         'ratio_numerator', 'ratio_denominator', 'quantity_rounding', 'quantity_rounding_scope',
         'new_price_basis_session', 'suspension_start', 'suspension_end', 'suspension_scope', 'resume_session')
REVIEW_EVENT = (*EVENT, 'announcement_date', 'implementation_announcement_date', 'cash_dividend_per_unit',
                'ex_date', 'pay_date', 'process_status', 'source_code', 'new_price_basis_basis', 'announcement_precision')
SAFE_CONDITIONS = {'start_session', 'end_session', 'initial_account', 'price_basis', 'unit_split_policy',
                   'stock_action_policy'}
NOTE = ('公开分享投影：保留授权账户窗口及相关证券的已保存 OHLCV，供连续 K线与成交复盘；缺值不填补。'
        '不附完整原始 DataBatch、coverage、逐键完整证明或模型输入。图层为展示子集，原 source/file refs 与 content_digest 指向完整保存来源，不是子集身份。')
DESIGN = 'https://github.com/sinnergarden/axiom-docs/blob/main/README.md'


def clean(value):
    if isinstance(value, str):
        if SECRET.search(value):
            raise ValueError('credential-like content is forbidden in public output')
        return PATH.sub('[本地路径已隐藏]', value)
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k not in DROP and not PATH.search(k)}
    return deepcopy(value)


def pick(value, keys):
    return clean({k: value[k] for k in keys if k in value})


def scalars(value, keys):
    selected = pick(value, keys)
    if any(isinstance(v, (dict, list)) for v in selected.values()):
        raise ValueError('unexpected nested public summary field')
    return selected


def related_securities(run):
    ids = {r.get('security_id') for name in ('positions', 'fills', 'orders', 'unit_split_applications')
           for r in run.get(name) or []}
    for decision in run.get('decisions') or []:
        ids.add(decision.get('selected_security_id'))
        ids.update(decision.get('selected_security_ids') or [])
        ids.update(i.get('security_id') for i in decision.get('intents') or [])
    return {i for i in ids if isinstance(i, str) and i}


def chart_projection(view, securities, start, end):
    market = view['market']
    source = market.get('native_chart') or market.get('data_batch')
    if not source:
        return None
    stock = view['run'].get('contract_version') == 'backtest_run_v3'
    volume = 'volume_shares' if stock else 'volume_units'
    fields = ('open', 'high', 'low', 'close', volume)
    metadata = source.get('field_meta') or {}
    if not all(field in metadata for field in fields):
        return None
    price_unit, volume_unit = ('CNY/share', 'shares') if stock else ('CNY/fund unit', 'fund units')
    if any(metadata[k].get('unit') != price_unit for k in fields[:4]) or metadata[volume].get('unit') != volume_unit:
        raise ValueError('saved chart unit mismatch')
    source_context = source.get('context') or {}
    basis = (source_context.get('query') or {}).get('price_basis')
    if basis != market.get('price_basis'):
        raise ValueError('saved chart price basis mismatch')
    rows = [scalars(row, ('security_id', 'session', *fields)) for row in source.get('records') or []
            if row.get('security_id') in securities and start <= row.get('session', '') <= end]
    context = scalars(source_context, ('snapshot_id', 'domain', 'reader_version', 'contract_id', 'source_profile_id'))
    context.update(price_basis=basis, adjustment_anchor=clean((source_context.get('query') or {}).get('adjustment_anchor')),
                   selected_start_session=start, selected_end_session=end,
                   original_saved_batch_file_ref=clean(market.get('data_batch_file_digest')),
                   original_saved_replay_source_refs=clean(market.get('source_refs')),
                   identity_note='Original refs identify saved full sources; this is a selected display projection, not a complete DataBatch.')
    return {'display_projection': True, 'public_selected_chart': True, 'context': context,
            'source_ref': clean(source.get('source_ref')), 'records': rows,
            'field_meta': {k: {**scalars(metadata[k], ('unit', 'dtype')), 'by_key': []} for k in fields},
            'omitted': ['full DataBatch', 'query', 'coverage', 'full per-key provenance', 'unselected securities and dates']}


def project_view(view):
    run = view.get('run') or {}
    if not run.get('run_id'):
        raise ValueError('public results require an explicit saved account')
    result = {'view_id': view['view_id'], 'run': pick(run, RUN),
              'configuration': pick(view['configuration'], ('start_session', 'end_session', 'initial_account',
                                                           'profile', 'price_basis', 'unit_split_policy')),
              'evidence_kind': view['evidence_kind'], 'approximate': view['approximate'], 'blocked': view['blocked'],
              'research': pick(view['research'], RESEARCH) if view.get('research') else None,
              'evaluation': pick(view['evaluation'], EVALUATION) if view.get('evaluation') else None,
              'comparison_conditions': [clean(c) for c in view.get('comparison_conditions', [])
                                        if c['key'] in SAFE_CONDITIONS or c['key'].startswith('profile.')],
              'registration_history': []}
    result['run']['decisions'] = [pick(d, ('contract_version', 'feature_session', 'trade_session', 'status',
                                         'selected_security_id', 'selected_security_ids', 'signal_ref',
                                         'expected_account_version', 'intents', 'reason', 'top_k')) for d in run.get('decisions') or []]
    securities = related_securities(run)
    for d, original in zip(result['run']['decisions'], run.get('decisions') or []):
        # These narrow saved facts are required for public trade replay. Keep
        # generic clean() stripping arbitrary trace/payloads everywhere else.
        if original.get('targets') is not None:
            targets = {k: v for k, v in original['targets'].items() if k in securities}
            if any(isinstance(v, (dict, list)) for v in targets.values()):
                raise ValueError('unexpected nested public target quantity')
            d['targets'] = clean(targets)
        if original.get('trace') is not None:
            if not isinstance(original['trace'], list) or not all(isinstance(row, dict) for row in original['trace']):
                raise ValueError('unexpected public decision trace')
            d['trace'] = [scalars(row, TRACE) for row in original['trace']]
        if 'intents' in d:
            d['intents'] = [pick(i, ('intent_id', 'security_id', 'side', 'quantity', 'quantity_unit', 'reason',
                                   'session', 'valid_until')) for i in d['intents']]
    required = {(r['security_id'], r['session']) for name in ('positions', 'fills', 'orders')
                for r in run.get(name) or [] if r.get('security_id') and r.get('session')}
    market = view['market']
    start, end = view['configuration']['start_session'], view['configuration']['end_session']
    rows = [pick(r, ROW) for r in market.get('rows') or []
            if r.get('security_id') in securities and start <= r.get('session', '') <= end]
    present = {(r['security_id'], r['session']) for r in rows}
    if required - present:
        raise ValueError('public close/volume projection lacks saved account-related market points')
    result['market'] = {'rows': rows, 'price_basis': market.get('price_basis'),
                        'source_refs': clean(market.get('source_refs')), 'data_batch': None,
                        'native_chart': chart_projection(view, securities, start, end)}
    display = market.get('review_display')
    if display is not None:
        fields = ('security_id', 'session', 'open', 'high', 'low', 'close', 'native_open', 'native_high',
                  'native_low', 'native_close', 'native_pre_close', 'volume_shares', 'volume_units',
                  'amount_cny', 'display_scale', 'display_missing_reason')
        result['market']['review_display'] = {
            **scalars(display, ('contract_version', 'manifest_sha256', 'display_projection', 'names_status', 'events_status')),
            'public_selected_chart': True,
            'context': pick(display.get('context') or {}, ('usage', 'snapshot_id', 'anchor_session', 'knowledge_cutoff',
                                                         'pit_policy', 'default_price_basis', 'native_price_basis', 'limitations')),
            'field_units': clean(display.get('field_units') or {}),
            'records': [scalars(row, fields) for row in display.get('records') or []
                        if row.get('security_id') in securities and start <= row.get('session', '') <= end]}
        result['market']['security_labels'] = clean({key:value for key,value in (market.get('security_labels') or {}).items()
                                                     if key in securities})
        result['market']['security_name_scope'] = clean(market.get('security_name_scope'))
        result['market']['review_events'] = [
            {'domain': clean(item['domain']), 'event': pick(item['event'], REVIEW_EVENT)}
            for item in market.get('review_events') or [] if item['event'].get('security_id') in securities]
    if market.get('unit_splits') is not None:
        referenced_events = {r.get('event_id') for r in run.get('unit_split_applications') or []}
        referenced_events.update(r.get('mark_basis_event_id') for r in run.get('positions') or [])
        referenced_events.update(i for r in run.get('orders') or [] for i in r.get('announced_suspension_event_ids') or [])
        result['market']['unit_splits'] = [{'event': pick(item['event'], EVENT),
                                          'source_refs': clean(item.get('source_refs'))}
                                         for item in market['unit_splits'] if item['event'].get('event_id') in referenced_events]
    if run.get('contract_version') == 'backtest_run_v3':
        context = view.get('stock_context') or {}
        result['stock_context'] = scalars(context, ('stock_action_policy', 'model_snapshot', 'execution_snapshot', 'admission_status'))
        for key in ('prediction_universe', 'execution_universe'):
            rows = context.get(key) or []
            if not isinstance(rows, list) or not all(isinstance(row, str) for row in rows):
                raise ValueError('unexpected nested public universe')
            result['stock_context'][key] = clean(rows)
        result['stock_context']['portfolio_policy'] = scalars(context.get('portfolio_policy') or {},
                                                             ('budget_basis', 'eligibility_id', 'rebalance', 'top_k'))
        result['stock_context']['signal_inputs'] = scalars(context.get('signal_inputs') or {},
                                                         ('feature_ref', 'model_ref', 'score_semantics', 'score_unit'))
    result['run']['limitations'] = list(result['run'].get('limitations') or []) + [NOTE]
    result['public_display_projection'] = True
    return result


def load_projection(path):
    raw = Path(path).read_bytes()
    text = raw.decode('utf-8')
    match = re.search(r'id="workbench-data">(.*?)</script>', text, re.S)
    wire = json.loads(match.group(1) if match else text)
    if wire.get('contract_version') != 'ui_workbench_projection_v1':
        raise ValueError('selection must be an existing validated UI workbench projection')
    return wire, 'sha256:' + sha256(raw).hexdigest()


def export_result(item, output, generated_at):
    slug = item['slug']
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,60}', slug):
        raise ValueError('unsafe public slug')
    run_ids = item.get('run_ids')
    if not isinstance(run_ids, list) or not run_ids or not all(isinstance(r, str) and r for r in run_ids):
        raise ValueError('public results require explicit nonempty run_ids')
    if len(set(run_ids)) != len(run_ids):
        raise ValueError('duplicate selected run identity')
    wire, source_ref = load_projection(item['input'])
    views = [project_view(v) for v in wire['views'] if (v.get('run') or {}).get('run_id') and
             v['run']['run_id'] in run_ids]
    if not views:
        raise ValueError('no explicitly selected saved results')
    if {v['run']['run_id'] for v in views} != set(run_ids):
        raise ValueError('selected run identity not present')
    html = _render(views, generated_at)
    banner = '<nav style="padding:8px 20px;background:#eef3f8;font-size:12px"><a href="index.html">← 公开结果入口</a> · 授权选定的保存结果 · 日线近似/单位/基准限制见页面 · 分享投影不是完整原始数据</nav>'
    html = html.replace('<body>', '<body>'+banner, 1)
    (output/(slug+'.html')).write_text(html)
    return {'slug': slug, 'title': clean(item['title']), 'file': slug+'.html',
            'source_projection_file_ref': source_ref, 'public_projection': True,
            'saved_owner_refs': [{'run_id': v['run']['run_id'], 'content_digest': v['run']['content_digest'],
                                  'committed_sequence': v['run']['committed_sequence'],
                                  'implementation_ref': v['run'].get('implementation_ref'),
                                  'evaluation_ref': (v.get('evaluation') or {}).get('evaluation_ref'),
                                  'evaluation_content_digest': (v.get('evaluation') or {}).get('content_digest')}
                                 for v in views]}


def export_site(selection_path, output):
    selection = json.loads(Path(selection_path).read_text())
    if selection.get('authorization') != 'explicit_selected_public_results':
        raise ValueError('public export requires explicit selection authorization')
    output = Path(output)
    if output.is_symlink():
        raise ValueError('public output cannot be a symlink')
    if len({r['slug'] for r in selection['results']}) != len(selection['results']):
        raise ValueError('duplicate public selection slug')
    output.mkdir(parents=True, exist_ok=True)
    results = [export_result(item, output, selection['generated_at']) for item in selection['results']]
    links = ''.join('<section><h2>'+escape(r['title'])+'</h2><a href="'+r['file']+'">打开保存结果</a></section>' for r in results)
    performance = ''
    if selection.get('performance_html'):
        text = Path(selection['performance_html']).read_text()
        text = re.sub(r'<section><details id="evidence-details">.*?</details></section>',
                      '<section><p>实测来源引用见 <a href="publication.json">公开发布记录</a>；完整输入及本地性能证明不随网站公开。</p></section>', text, flags=re.S)
        text = text.replace('← 11:30 本地真实验收入口', '← 公开结果入口')
        text = text.replace('已保存的实测 · 只读 · 2026-10-05', 'Mac 本地已保存实测 · 公开只读摘要 · 2026-10-05')
        text = text.replace('原 ETF、股票账户页面保持原样。本页没有运行 Data、训练、账户或评价计算；Library 保持暂停，未上传或部署。',
                            '本页展示 Mac 本地保存的性能观测；133 / 105 毫秒不是 GitHub Pages 访客的在线速度。网站部署不运行采集、训练、账户或评价。')
        update = selection.get('performance_update')
        if update:
            values = scalars(update, ('generation_seconds', 'run_read_seconds', 'evaluation_read_seconds', 'scope'))
            added = '<tr><td>本次新 Jan 结果读取</td><td>'+escape(str(values['run_read_seconds']))+' ＋ '+escape(str(values['evaluation_read_seconds']))+' 秒</td><td>新账户与评价各一次公共 Reader 读取；UI 业务计算为 0。</td></tr>'
            added += '<tr><td>本次新 Jan 页面生成</td><td>'+escape(str(values['generation_seconds']))+' 秒</td><td>'+escape(str(values['scope']))+'</td></tr>'
            text = text.replace('<tr><td>Reader 前后对照</td>', added+'<tr><td>Reader 前后对照</td>', 1)
        (output/'performance.html').write_text(clean(text));performance='<section><h2>性能验收</h2><p>Mac 本地已保存的有界实测，完整历史尚未实跑。</p><a href="performance.html">查看性能摘要</a></section>'
    process_refs = None;process = ''
    if selection.get('process'):
        from .public_process import export_process
        p = selection['process']
        target, _ = load_projection(p['target'])
        selected = {ref['run_id'] for r in results for ref in r['saved_owner_refs']}
        targets = {(v.get('run') or {}).get('run_id') for v in target['views'] if (v.get('run') or {}).get('run_id')}
        if not targets or not targets.issubset(selected):
            raise ValueError('process target contains an unselected saved account')
        process_refs = export_process(p['source'], p['target'], output)
        process = '<section><h2>关键中间过程</h2><p>保存的训练成熟度、信号与交易日期、冻结费用和现金行动范围。</p><a href="process.html">查看过程验收</a></section>'
    index='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Axiom · 公开保存结果</title><style>body{margin:0;background:#f3f6fa;color:#25374d;font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1000px;margin:40px auto;padding:0 22px}section{background:white;border:1px solid #dce5ef;border-radius:12px;padding:22px;margin:18px 0}a{color:#416e99}h1{font-size:30px}.small{font-size:13px;color:#52677e}</style><main><p class="small">AXIOM · 授权选定保存结果 · 公开只读</p><h1>回测结果与性能验收</h1><p><a href="'''+DESIGN+'''">统一设计文档</a></p><p>真实固定输入的模拟回测，保留日线执行近似。处理完成不证明策略有效、开盘流动性或实盘成交。页面指标由 owner 保存，浏览不重算收益或交易。</p>'''+links+process+performance+'''<section><h2>展示范围</h2><p>ETF 与股票的数量单位分别为基金份额与股；费用及执行假设见对应报告。沪深300为不含分红的价格指数，账户含已观测分红，两者口径不同。分红范围为已观测记录，不代表供应完整。</p><p>分享版保留选定回测窗口、相关证券的已保存 OHLCV 与连续复盘；缺值不填补。完整 DataBatch、coverage、模型输入和未选结果不随页面公开。图层是展示子集，来源引用指向原完整保存文件。</p><a href="publication.json">公开发布记录</a> · <a href="https://github.com/sinnergarden/axiom-ui">源码与更新流程</a></section></main></html>'''
    (output/'index.html').write_text(index)
    manifest={'contract_version':'public_static_site_v1','generated_at':selection['generated_at'],
              'authorization':'explicit_selected_public_results','selection_note':clean(selection.get('selection_note')),
              'results':results,'performance_refs':clean(selection.get('performance_refs') or {}),
              'performance_update':clean(selection.get('performance_update')),
              'process_refs':process_refs,
              'owner_digest_note':'Saved owner content_digest identifies the original complete owner result, not public HTML.',
              'future_results_auto_published':False,'Data_roots_current_discovery':False}
    (output/'publication.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    for name in ('echarts.LICENSE.txt', 'echarts.NOTICE.txt', 'echarts.vendor.json'):
        (output/name).write_bytes((ASSETS/name).read_bytes())
    index = (output/'index.html').read_text().replace('</main>',
        '<p class="small">图表：Apache ECharts 6.1.0 · '
        '<a href="echarts.LICENSE.txt">Apache-2.0</a> · '
        '<a href="echarts.NOTICE.txt">NOTICE</a> · '
        '<a href="echarts.vendor.json">固定来源与摘要</a></p></main>')
    (output/'index.html').write_text(index)
    (output/'.nojekyll').write_text('')
    return manifest
