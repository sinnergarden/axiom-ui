"""Small saved-process display bound to explicitly selected stock accounts.

Only saved summaries and role identities are read. This module has no Owner or
Research imports and performs no training, replay, evaluation, or statistics.
"""
from html import escape
import json
from math import isfinite
from pathlib import Path
import re

from .public_share import clean, load_projection, pick


WINDOW = ('first_feature_session', 'last_feature_session', 'session_count', 'training_row_count')
NORMALIZATION = ('normalization_id', 'semantic_version', 'operator', 'operator_version',
                 'maturity', 'eligibility', 'context_mode')
PROFILE = ('contract_version', 'execution', 'commission_rate', 'minimum_commission_minor',
           'sell_stamp_tax_rate', 'tax_rate', 'transfer_fee_rate', 'slippage_bps',
           'participation_rate', 'settlement_sessions', 'lot_size', 'price_tick',
           'maximum_order_quantity', 'unknown_status_policy', 'approximation', 'limitation')
DECISION = ('feature_session', 'trade_session', 'status')
PROFILE_LABELS = {'contract_version': '保存配置版本', 'execution': '成交价格政策',
                  'commission_rate': '佣金率（保存小数）', 'minimum_commission_minor': '最低佣金（分）',
                  'sell_stamp_tax_rate': '卖方印花税率（保存小数）', 'tax_rate': '税率（保存小数）',
                  'transfer_fee_rate': '过户费率（保存小数）', 'slippage_bps': '滑点（基点）',
                  'participation_rate': '全天量容量比例（保存小数）', 'settlement_sessions': '结算交易日数',
                  'lot_size': '委托单位（股）', 'price_tick': '价格最小变动（元每股）',
                  'maximum_order_quantity': '单笔数量上限（股）', 'unknown_status_policy': '市场状态缺证政策',
                  'approximation': '日线执行近似口径', 'limitation': '保存限制说明'}
SIGNAL_LABELS = {'evaluation_cutoff': '评价知识截止', 'evidence_session_count': '评价 session 数',
                 'label_semantics': '前瞻标签口径', 'minimum_pairs': '单日最少配对数',
                 'missing_policy': '缺值政策', 'prediction_row_count': '预测总行数',
                 'prediction_valid_row_count': '有效预测行数', 'prediction_invalid_row_count': '无效预测行数',
                 'valid_pair_count': '有效配对数', 'excluded_pair_count': '排除配对数',
                 'weighting': '汇总权重', 'ic': 'IC 均值 / session 数', 'rank_ic': 'RankIC 均值 / session 数'}


def _ref(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', value):
        raise ValueError('missing saved process identity: ' + name)
    return value


def _equal(values, name):
    if any(value is None or isinstance(value, (dict, list, tuple)) for value in values) or len(set(values)) != 1:
        raise ValueError('saved process binding mismatch: ' + name)
    return values[0]


def _scalar(value):
    if value is not None and type(value) not in (str, int, float, bool):
        raise ValueError('unexpected nested saved process field')
    if type(value) is float and not isfinite(value):
        raise ValueError('nonfinite saved process field')
    return clean(value)


def _scalars(value, keys):
    selected = pick(value or {}, keys)
    return {key: _scalar(v) for key, v in selected.items()}


def _source_summary(stock, signal):
    experiment, model = stock.get('experiment') or {}, stock.get('model') or {}
    report, evidence = stock.get('stage_report') or {}, stock.get('signal_evidence') or {}
    refs = report.get('input_refs') or {}
    _equal((signal, experiment.get('signal_run_ref'), refs.get('signal_run_ref'),
            evidence.get('signal_ref')), 'signal')
    identity = {}
    for key in ('model_ref', 'feature_ref', 'dataset_ref'):
        identity[key] = _ref(_equal((experiment.get(key), model.get(key), refs.get(key)), key), key)
    identity['experiment_ref'] = _ref(_equal((experiment.get('experiment_ref'),
                                             refs.get('experiment_ref')), 'experiment_ref'), 'experiment_ref')
    identity['evidence_ref'] = _ref(_equal((experiment.get('evidence_ref'), refs.get('evidence_ref'),
                                           evidence.get('evidence_ref')), 'evidence_ref'), 'evidence_ref')
    identity['stage_report_ref'] = _ref(report.get('stage_report_ref'), 'stage_report_ref')
    identity['stage_report_content_digest'] = _ref(report.get('content_digest'), 'stage_report_content_digest')
    training = report.get('training') or {}
    fit_cutoff = _equal((model.get('fit_cutoff'), training.get('fit_cutoff'),
                        (experiment.get('definition') or {}).get('config', {}).get('fit_cutoff')), 'fit_cutoff')
    target = _equal((model.get('target_semantics'),
                     (experiment.get('definition') or {}).get('target_semantics'),
                     evidence.get('score_semantics'),
                     (report.get('signal_summary') or {}).get('score_semantics')), 'target_semantics')
    selected_training = _scalars(training, ('fit_cutoff', 'declared_rule', 'actual_source'))
    for key in ('declared', 'actual'):
        selected_training[key] = _scalars(training.get(key), WINDOW)
        if not all(name in selected_training[key] for name in WINDOW[:3]):
            raise ValueError('missing saved training window: ' + key)
    if 'training_row_count' not in selected_training['actual']:
        raise ValueError('missing saved mature training row count')
    selected_training['excluded'] = _scalars(training.get('excluded'),
                                             ('NOT_MEMBER', 'missing_end_close', 'missing_start_open'))
    feature_selection = [_scalars(item, ('id', 'semantic_version'))
                         for item in model.get('feature_selection') or []]
    if not feature_selection or any(not item.get('id') for item in feature_selection):
        raise ValueError('missing saved process feature identities')
    model_summary = {'fit_cutoff': _scalar(fit_cutoff), 'target_semantics': _scalar(target),
                     'feature_normalization': _scalar(model.get('feature_normalization')),
                     'label_normalization': _scalars(model.get('label_normalization'), NORMALIZATION),
                     'feature_selection': feature_selection}
    # Label identities have different saved normalization/materialization roles.
    # They are deliberately not compared or relabeled as one common label input.
    signal_summary = _scalars(report.get('signal_summary'),
                               ('evaluation_cutoff', 'evidence_session_count', 'label_semantics',
                                'minimum_pairs', 'missing_policy', 'prediction_row_count',
                                'prediction_valid_row_count', 'prediction_invalid_row_count',
                                'valid_pair_count', 'excluded_pair_count', 'weighting'))
    for key in ('ic', 'rank_ic'):
        if key in (report.get('signal_summary') or {}):
            signal_summary[key] = _scalars(report['signal_summary'][key], ('mean', 'session_count'))
    return identity, selected_training, model_summary, signal_summary


def _display(value):
    if value is None:
        return '未保存'
    return escape(str(value))


def _table(rows):
    return '<table><tbody>' + ''.join('<tr><th>' + escape(label) + '</th><td>' +
                                      _display(value) + '</td></tr>' for label, value in rows) + '</tbody></table>'


def export_process(source_path, target_path, output):
    """Write process.html using a saved source with the target's exact signal."""
    source, source_file_ref = load_projection(source_path)
    target, target_file_ref = load_projection(target_path)
    targets = [view for view in target['views'] if (view.get('run') or {}).get('run_id') and
               view['run'].get('contract_version') == 'backtest_run_v3']
    if not targets:
        raise ValueError('process target requires an explicit saved stock account')
    signal = _ref(_equal(tuple(view['run'].get('signal_ref') for view in targets), 'target signals'), 'signal_ref')
    candidates = [view['stock_ml'] for view in source['views'] if view.get('stock_ml') and
                  (view['stock_ml'].get('experiment') or {}).get('signal_run_ref') == signal]
    if not candidates:
        raise ValueError('no saved process source matches the selected account signal')
    summaries = [_source_summary(stock, signal) for stock in candidates]
    identity, training, model_summary, signal_summary = summaries[0]
    if any(summary != summaries[0] for summary in summaries[1:]):
        raise ValueError('ambiguous saved process source for selected signal')
    target_refs, accounts = [], []
    for view in targets:
        if type(view.get('approximate')) is not bool or type(view.get('blocked')) is not bool:
            raise ValueError('missing saved account approximation or blocking flag')
        run, context = view['run'], view.get('stock_context') or {}
        signal_inputs = context.get('signal_inputs') or {}
        for key in ('model_ref', 'feature_ref'):
            if signal_inputs.get(key) is not None:
                _equal((signal_inputs[key], identity[key]), 'target ' + key)
        evaluation = view.get('evaluation') or {}
        if evaluation:
            binding = evaluation.get('input_run_ref') or {}
            for key in ('run_id', 'content_digest', 'committed_sequence'):
                _equal((str(binding.get(key)), str(run.get(key))), 'target evaluation ' + key)
        decisions = []
        for decision in run.get('decisions') or []:
            _equal((signal, decision.get('signal_ref')), 'target decision signal')
            decisions.append(_scalars(decision, DECISION))
        if not decisions:
            raise ValueError('selected account has no saved signal/trade-day process records')
        target_refs.append({'run_id': _ref(run.get('run_id'), 'target run_id'),
                            'content_digest': _ref(run.get('content_digest'), 'target content_digest'),
                            'committed_sequence': _scalar(run.get('committed_sequence')),
                            'signal_ref': signal,
                            'evaluation_ref': _ref(evaluation['evaluation_ref'], 'target evaluation_ref')
                            if evaluation.get('evaluation_ref') is not None else None})
        limits = list(run.get('limitations') or []) + list(evaluation.get('limitations') or [])
        action_limits = [clean(text) for text in limits if isinstance(text, str) and
                         any(word in text.lower() for word in ('action', 'dividend', 'corporate', 'pay', 'tax', '分红', '行动'))]
        accounts.append({'status': _scalar(run.get('status')), 'approximate': view.get('approximate'),
                         'blocked': view.get('blocked'),
                         'range': _scalars(view.get('configuration'), ('start_session', 'end_session')),
                         'decisions': decisions,
                         'fee_profile': _scalars((view.get('configuration') or {}).get('profile'), PROFILE),
                         'dividend_scope_status': _scalar((evaluation.get('episode_metrics') or {}).get('dividend_scope_status')),
                         'action_limitations': action_limits})
    provenance = {'contract_version': 'public_saved_process_v1', 'signal_ref': signal, **identity,
                  'source_projection_file_ref': source_file_ref,
                  'target_projection_file_ref': target_file_ref,
                  'target_run_ref': target_refs[0], 'target_run_refs': target_refs,
                  'training': training, 'model_summary': model_summary, 'signal_summary': signal_summary}
    provenance = clean(provenance)
    declared, actual = training['declared'], training['actual']
    training_rows = [('拟合截止', training['fit_cutoff']),
                     ('声明特征日窗口', declared['first_feature_session'] + ' — ' + declared['last_feature_session']),
                     ('声明 session 数', declared['session_count']),
                     ('实际成熟训练特征日窗口', actual['first_feature_session'] + ' — ' + actual['last_feature_session']),
                     ('实际成熟 session 数 / 训练行数', str(actual['session_count']) + ' / ' + str(actual['training_row_count'])),
                     ('声明窗口规则', training.get('declared_rule')),
                     ('成熟标签规则', model_summary['label_normalization'].get('maturity')),
                     ('目标语义', model_summary['target_semantics']),
                     ('特征归一化', model_summary['feature_normalization']),
                     ('标签归一化', model_summary['label_normalization'].get('normalization_id')),
                     ('特征 ID（保存语义版本）', '、'.join(str(item['id']) + ' (' + str(item.get('semantic_version', '未保存')) + ')' for item in model_summary['feature_selection']))]
    sections = '<section><h2>训练成熟度</h2><p>声明窗口与实际成熟窗口分别来自保存报告；截止之后才成熟的标签不回填训练。本页不重读训练键或计算成熟度。</p>' + _table(training_rows) + '</section>'
    for number, account in enumerate(accounts, 1):
        kind = '股票日线近似' if account['approximate'] else '股票严格对照'
        rows = ''.join('<tr><td>' + _display(d.get('feature_session')) + '</td><td>' +
                       _display(d.get('trade_session')) + '</td><td>' + _display(d.get('status')) +
                       '</td></tr>' for d in account['decisions'])
        sections += '<section><h2>账户 ' + str(number) + ' · ' + kind + '</h2>' + _table([
            ('保存范围', str(account['range'].get('start_session')) + ' — ' + str(account['range'].get('end_session'))),
            ('保存账户状态 / 拒单阻断标记', str(account['status']) + ' / ' + str(account['blocked'])),
            ('数量 / 价格单位', '股 / 元每股'),
            ('分红观察范围', account['dividend_scope_status'])]) + '<h3>信号日与委托交易日</h3><p>下面是账户保存的决策记录；委托交易日不表示每笔都已成交，实际成交与拒单见股票结果。</p><table><thead><tr><th>特征 / 信号日</th><th>委托交易日</th><th>保存状态</th></tr></thead><tbody>' + rows + '</tbody></table><h3>冻结费用与执行假设</h3>' + _table([(PROFILE_LABELS[key], value) for key, value in account['fee_profile'].items()]) + '<details><summary>保存的现金行动、分红及覆盖限制</summary>' + ''.join('<p>' + escape(text) + '</p>' for text in account['action_limitations']) + '</details></section>'
    sections += '<section><h2>保存的信号评价摘要</h2><p>以下为保存的前瞻标签配对摘要，与账户收益口径不同，不表示策略有效或置信结论。模型评分是标准化目标的预测值，不是收益百分比。</p>' + _table([(SIGNAL_LABELS[key], str(value.get('mean')) + ' / ' + str(value.get('session_count')) if isinstance(value, dict) else value) for key, value in signal_summary.items()]) + '</section>'
    details = escape(json.dumps(provenance, ensure_ascii=False, indent=2, allow_nan=False))
    html = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Axiom · 保存过程验收</title><style>body{margin:0;background:#f3f6fa;color:#25374d;font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1000px;margin:32px auto;padding:0 22px}section{background:white;border:1px solid #dce5ef;border-radius:12px;padding:22px;margin:18px 0}a{color:#416e99}h1{font-size:30px}h2{font-size:21px}h3{font-size:17px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;border-bottom:1px solid #e4ebf2;padding:9px;vertical-align:top;overflow-wrap:anywhere}th{font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}.small{font-size:13px;color:#52677e}nav{display:flex;gap:16px;flex-wrap:wrap}</style></head><body><main><nav><a href="index.html">← 公开结果入口</a><a href="index.html">股票保存结果入口</a><a href="performance.html">性能实测</a><a href="https://github.com/sinnergarden/axiom-docs/blob/main/README.md">统一设计导航</a></nav><p class="small">AXIOM · SAVED PROCESS · 公开只读</p><h1>关键中间过程验收</h1><p>训练报告通过同一保存信号身份绑定到本页账户。所有日期、数量、语义及评价值均来自保存产物；本页没有采集、训练、回测、交易或业务指标计算。较早模型记录的账户准入状态不作为本次账户状态。</p>''' + sections + '<section><details><summary>保存身份与公开投影来源</summary><p>原身份引用指向完整保存产物；公开摘要不是完整输入或证明。不同标签角色保留原语义，不强行合并身份。</p><pre>' + details + '</pre></details></section></main></body></html>'
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'process.html').write_text(clean(html))
    return provenance
