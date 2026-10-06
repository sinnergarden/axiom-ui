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
V4_PROFILE = ('contract_version', 'lot_size', 'settlement_sessions', 'commission_rate',
              'minimum_commission_minor', 'sell_stamp_tax_rate', 'transfer_fee_rate',
              'slippage_bps', 'participation_rate', 'decision_time_utc', 'execution',
              'approximation', 'unknown_status_policy', 'maximum_order_quantity',
              'price_tick', 'limitation')
V4_METRICS = ('fill_count', 'max_drawdown', 'total_fees_minor', 'total_return',
              'turnover_minor', 'unfilled_order_count')
V4_NAV = ('session', 'cash_minor', 'market_value_minor', 'receivable_minor',
          'nav_minor', 'nav_index', 'committed_sequence')
V4_POSITION = ('session', 'security_id', 'quantity', 'sellable_quantity', 'mark_price',
               'mark_session', 'is_stale', 'market_value_minor', 'committed_sequence',
               'cost_minor', 'mark_source_refs', 'stale_sessions')
V4_ORDER = ('order_id', 'intent_id', 'session', 'security_id', 'side', 'quantity',
            'filled_quantity', 'unfilled_quantity', 'status', 'reason', 'execution',
            'execution_admission', 'execution_evidence_cutoff', 'expected_account_version',
            'field_available_at', 'market_state', 'state_reason', 'committed_sequence',
            'valid_until')
V4_FILL = ('fill_id', 'order_id', 'session', 'security_id', 'side', 'quantity',
           'quantity_unit', 'price', 'gross_minor', 'fee_minor', 'cash_delta_minor',
           'sequence', 'commission_minor', 'stamp_tax_minor', 'transfer_fee_minor',
           'slippage_minor', 'tax_minor', 'realized_pnl_minor', 'reference_open',
           'execution_admission', 'execution_evidence_cutoff', 'field_available_at',
           'market_state', 'state_reason', 'source_refs')
V4_DECISION = ('contract_version', 'expected_account_version', 'feature_session',
               'trade_session', 'status', 'selected_security_id', 'selected_security_ids', 'signal_ref',
               'supported_universe_ref', 'targets', 'top_k', 'trace', 'intents',
               'prediction_clock', 'reference_prices')
V4_INTENT = ('intent_id', 'security_id', 'side', 'quantity', 'valid_until',
             'expected_account_version')
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
V5_PROFILE = (*V4_PROFILE, 'tax_rate', 'price_limit_policy', 'price_grid_policy', 'price_grid_ref')
V5_POSITION = (*V4_POSITION, 'mark_basis_event_id')
V5_PRICE = ('raw_slipped_price', 'price_tick', 'price_grid_ref', 'price_rounding',
            'rounding_delta', 'effective_slippage_bps')
V5_ORDER = (*V4_ORDER, 'announced_suspension_event_ids', *V5_PRICE)
V5_FILL = (*V4_FILL, *V5_PRICE)
V5_APPLICATION = ('event_id', 'security_id', 'session', 'phase', 'status', 'sequence',
                  'record_sequence', 'record_quantity', 'before_quantity', 'after_quantity',
                  'before_sellable_quantity', 'after_sellable_quantity', 'cost_minor',
                  'rounding_extra_fraction', 'original_quote', 'normalized_quote',
                  'before_market_value_minor', 'after_market_value_minor', 'rounding_value_minor',
                  'source_refs')
V5_QUOTE = ('session', 'price', 'available_at', 'source_refs')
V5_ROTATION_POLICY = ('contract_version', 'schedule')
V5_BUY_HOLD_POLICY = ('contract_version', 'security_id', 'entry_session', 'budget',
                      'schedule', 'partial_fill_policy', 'cash_dividend_policy', 'terminal_policy')
V6_RUN_EXTRA = ('stock_execution_rules_ref', 'lifecycle_admission')
V6_PROFILE = ('contract_version', 'settlement_sessions', 'commission_rate',
              'minimum_commission_minor', 'slippage_bps', 'participation_rate',
              'decision_time_utc', 'execution', 'approximation', 'unknown_status_policy',
              'maximum_quantity_policy', 'partial_fill_quantity_unit',
              'stock_execution_rules_ref', 'stock_fee_schedule_ref', 'limitation')
V6_METRICS = (*V4_METRICS, 'unsubmitted_order_count', 'unsubmitted_quantity',
              'incomplete_order_count')
V6_POSITION = (*V4_POSITION, 'stale_reason')
V6_ORDER = (*V4_ORDER, 'requested_quantity', 'submitted_quantity',
            'unsubmitted_quantity', 'submission_reason', 'stock_execution_rules_ref',
            'quantity_rule_effective_from')
V6_FILL = (*V4_FILL, 'stock_execution_rules_ref', 'stock_fee_schedule_ref',
           'quantity_rule_effective_from', 'fee_interval_effective_from')
V6_DECISION = (*V4_DECISION, 'stock_execution_rules_ref')
V6_POLICY = ('budget_basis', 'eligibility_id', 'rebalance', 'top_k',
             'candidate_policy', 'stock_execution_rules_ref')
V6_LIFECYCLE = ('pre_listing_null', 'listed_nonmember_gap', 'member_gap', 'held_gap')
V6_STOPPED = ('session', 'reason', 'committed_sequence')
V6_TRACE = (*TRACE, 'candidate_policy', 'excluded_invalid_member_count',
            'pit_member_count', 'valid_candidate_count', 'top_k')
REVIEW_EVENT = (*EVENT, 'announcement_date', 'implementation_announcement_date', 'cash_dividend_per_unit',
                'ex_date', 'pay_date', 'process_status', 'source_code', 'new_price_basis_basis', 'announcement_precision')
# Names from the frozen v4 stock display and evaluation v2/v3 public contract.
# Unknown nested names fail closed even when an outer object is allowlisted.
V4_PUBLIC_EXTRA = frozenset((
    'CSI300 NASDAQ100 SSE_COMPOSITE account account_cumulative_return account_relative_wealth '
    'account_session adjustment_anchor admission_status anchor anchor_close anchor_session '
    'annual_effective_rate annualization annualization_factor approximate available_at benchmark_alignment '
    'benchmark_cumulative_return benchmark_keys benchmark_security_id benchmark_series_kind bins blocked '
    'boundary_session buy_cost_minor by_key cagr cagr_reason cagr_status calmar clock_scope closed_count '
    'comparison_conditions configuration context cross_currency_relative_policy cross_market_clock currency '
    'daily_return data_batch day_count days decisions display_projection dividend_income_minor '
    'dividend_recognition dividend_scope_status dividends domain drawdown drawdown_peak edges edges_minor '
    'elapsed_calendar_days eligibility_id eligible_closed_count end_anchor end_close end_nav_minor '
    'end_session entry_sequence entry_session episode_definition episode_id evaluation evidence_kind '
    'exclusion_reasons execution_snapshot execution_universe exit_sequence exit_session external_cash_flows '
    'feature_ref fee_ratio fees_minor field_meta fill_refs final_nav_minor final_quantity first_session '
    'fit_session fold_ref fold_spec_ref folds frequency gross_traded_minor high holding_calendar_days '
    'identity_note included_episode_count income_pending_count income_status initial_account '
    'initial_quantity input_ref interval key label last_session left_censored left_censored_count limit_down '
    'limit_up loss_count low marked_pnl_minor market maximum_single_security_weight mean_episode_return '
    'mean_nav_minor mean_net_pnl_minor method metric minimum_episodes minimum_year_fraction missing_policy '
    'missing_reason model_ref model_snapshot month monthly_partial_policy native_calendar native_chart '
    'native_series native_session net_pnl_minor net_return normalized_index observations observed_return '
    'omitted oos_trade_sessions open open_count original_saved_batch_file_ref '
    'original_saved_replay_source_refs payment_unknown_count peak_is_initial_anchor peak_nav_minor '
    'peak_session pending_dividend_minor portfolio_policy prediction_universe price_basis profile provided '
    'public_display_projection public_selected_chart reader_version rebalance records recovery_session '
    'recovery_status registration_history relative_status research return return_basis return_denominator '
    'return_denominator_minor risk_free rolling_return_20 rolling_status rolling_volatility_20 '
    'rolling_window_sessions rows run schedule_ref selected_end_session selected_start_session '
    'sell_proceeds_minor series_kind sharpe signal_run_ref snapshot_id source source_ref start_anchor '
    'start_nav_minor start_session statistics_eligible stock_action_policy stock_context tie_count timezone '
    'trough_nav_minor trough_session turnover_status two_sided_turnover unavailable_reason unit valid value '
    'view_id weighting win_count win_rate window year year_days year_fraction year_segments '
).split())
V4_PUBLIC_KEYS = frozenset().union(RUN, EVALUATION, RESEARCH, TRACE, ROW, EVENT, REVIEW_EVENT,
                                   V4_PROFILE, V4_METRICS, V4_NAV, V4_POSITION, V4_ORDER,
                                   V4_FILL, V4_DECISION, V4_INTENT, V4_PUBLIC_EXTRA,
                                   ('native_open', 'native_high', 'native_low', 'native_close',
                                    'native_pre_close', 'amount_cny', 'display_scale',
                                    'display_missing_reason', 'security_labels', 'security_name_scope',
                                    'security_label_source', 'review_display', 'review_events',
                                    'fill_display', 'coordinates', 'source_snapshot_id',
                                    'label_cutoff', 'original_display_manifest_sha256',
                                    'manifest_sha256', 'knowledge_cutoff', 'default_price_basis',
                                    'native_price_basis', 'usage', 'dtype', 'description',
                                    'contract_id', 'source_profile_id', 'field_units',
                                    'names_status', 'events_status', 'event', 'display_ref',
                                    'display_result_ref', 'display_price', 'source_unit',
                                    'target_unit', 'pit_policy'))
V6_PUBLIC_KEYS = V4_PUBLIC_KEYS.union(V6_RUN_EXTRA, V6_PROFILE, V6_METRICS,
    V6_POSITION, V6_ORDER, V6_FILL, V6_DECISION, V6_POLICY, V6_LIFECYCLE,
    V6_STOPPED, V6_TRACE)


def _public_object(fields, **nested):
    return {**dict.fromkeys(fields.split()), **nested}


_EVAL_POINT = _public_object('session close daily_return drawdown missing_reason nav_index valid',
                            source_refs=(None,))
_BENCHMARK = _public_object('anchor_close anchor_session max_drawdown security_id series_kind status total_return unit',
                            series=(_EVAL_POINT,))
_COMPARISON_POINT = _public_object('account_session native_session close available_at normalized_index '
    'benchmark_cumulative_return account_relative_wealth relative_status benchmark_drawdown', source_refs=(None,))
_NATIVE_POINT = _public_object('native_session close available_at normalized_index '
    'benchmark_cumulative_return benchmark_drawdown', source_refs=(None,))
_COMPARISON = _public_object('anchor_close anchor_session clock_scope currency input_ref return_basis '
    'security_id status timezone unavailable_reason projection_version max_drawdown',
    native_calendar=(None,), native_series=(_NATIVE_POINT,), series=(_COMPARISON_POINT,))
_DIVIDEND = _public_object('event_id record_session ex_session pay_session entitlement_quantity '
    'recognition_sequence payment_sequence recognized_minor pending_minor receivable_minor payment_status '
    'tax_convention', source_refs=(None,))
_EPISODE = _public_object('buy_cost_minor dividend_income_minor entry_sequence entry_session episode_id '
    'exit_sequence exit_session fees_minor final_quantity income_status initial_quantity left_censored '
    'marked_pnl_minor net_pnl_minor net_return pending_dividend_minor receivable_minor '
    'return_denominator_minor security_id sell_proceeds_minor statistics_eligible status',
    dividends=(_DIVIDEND,), exclusion_reasons=(None,),
    fill_refs=(_public_object('fill_id sequence'),))
_SPEC = _public_object('anchor benchmark_alignment benchmark_security_id benchmark_series_kind description '
    'contract_version cross_currency_relative_policy cross_market_clock dividend_recognition '
    'drawdown_peak episode_definition external_cash_flows frequency missing_policy '
    'monthly_partial_policy return_denominator rolling_window_sessions weighting',
    benchmark_keys=(None,),
    annualization=_public_object('day_count end_anchor interval method minimum_year_fraction start_anchor'),
    pnl_distribution=_public_object('interval metric minimum_episodes unit', edges_minor=(None,)),
    return_distribution=_public_object('interval metric minimum_episodes unit', edges=(None,)),
    risk_free=_public_object('annual_effective_rate currency source'))
_V4_PUBLIC_EVALUATION = _public_object('benchmark_ref content_digest contract_version dividend_scope_ref '
    'evaluation_ref evaluation_version implementation_ref market_ref profile_ref signal_ref spec_ref status '
    'base_evaluation_ref base_evaluation_content_digest',
    input_run_ref=_public_object('run_id content_digest committed_sequence'),
    limitations=(None,), benchmark=_BENCHMARK,
    series=(_public_object('session nav_minor nav_index peak_nav_minor drawdown committed_sequence'),),
    monthly_returns=(_public_object('month status first_session last_session boundary_session start_nav_minor '
                                    'end_nav_minor return observed_return reason committed_sequence'),),
    episodes=(_EPISODE,),
    episode_metrics=_public_object('closed_count eligible_closed_count open_count left_censored_count '
        'income_pending_count payment_unknown_count win_count loss_count tie_count win_rate '
        'mean_net_pnl_minor mean_episode_return dividend_scope_status return_denominator weighting'),
    pnl_distribution=_public_object('status metric unit included_episode_count minimum_episodes',
        bins=(_public_object('lower_minor upper_minor count'),)),
    period_metrics=_public_object('',
        account=_public_object('cagr cagr_reason cagr_status final_nav_minor initial_nav_minor '
                              'max_drawdown total_return'),
        benchmark=_public_object('anchor_close cagr cagr_reason cagr_status end_close max_drawdown total_return'),
        window=_public_object('anchor_session day_count elapsed_calendar_days end_session year_fraction',
                              year_segments=(_public_object('days year year_days'),))),
    benchmark_refs=_public_object('CSI300 NASDAQ100 SSE_COMPOSITE'),
    benchmark_comparisons={'CSI300': _COMPARISON, 'NASDAQ100': _COMPARISON,
                           'SSE_COMPOSITE': _COMPARISON},
    risk_metrics={'sharpe': _public_object('annualization_factor observations status value year_fraction',
                                         risk_free=_public_object('annual_effective_rate currency source')),
                  'calmar': _public_object('status value')},
    drawdown_interval=_public_object('drawdown elapsed_calendar_days peak_is_initial_anchor peak_nav_minor '
        'peak_session recovery_session recovery_status status trough_nav_minor trough_session'),
    return_distribution=_public_object('included_episode_count interval metric minimum_episodes status unit',
        edges=(None,), bins=(_public_object('lower upper count'),)),
    analysis_series=(_public_object('account_cumulative_return committed_sequence rolling_return_20 '
                                    'rolling_status rolling_volatility_20 session'),),
    execution_summary=_public_object('fee_ratio fees_minor gross_traded_minor initial_nav_minor '
                                      'mean_nav_minor turnover_status two_sided_turnover'),
    concentration_series=(_public_object('committed_sequence maximum_single_security_weight security_id '
                                          'session status'),),
    episode_points=(_public_object('entry_session episode_id exit_session holding_calendar_days net_return'),),
    spec=_SPEC)


def _schema_field_names(schema):
    """Keep the global v4 output-name gate aligned with its stricter evaluation paths."""
    if isinstance(schema, tuple):
        return _schema_field_names(schema[0])
    if not isinstance(schema, dict):
        return frozenset()
    return frozenset(schema).union(*(_schema_field_names(child) for child in schema.values()))


# Engine evaluation v3 is independent of the account contract version.
# Keep one strict evaluation path schema for both stock v4 and ETF v5.
_SSE_COMPARISON = {**_COMPARISON, **dict.fromkeys((
    'observation_cutoff', 'observation_pit_policy', 'observation_purpose',
    'observation_snapshot_id'))}
_V4_PUBLIC_EVALUATION = {**_V4_PUBLIC_EVALUATION,
    'spec': {**_SPEC, 'benchmark_projection_version': None},
    'benchmark_comparisons': {**_V4_PUBLIC_EVALUATION['benchmark_comparisons'],
                              'SSE_COMPOSITE': _SSE_COMPARISON}}
V4_PUBLIC_KEYS = V4_PUBLIC_KEYS | _schema_field_names(_V4_PUBLIC_EVALUATION)
V5_PUBLIC_KEYS = (V4_PUBLIC_KEYS | frozenset((*V5_PROFILE, *V5_POSITION, *V5_ORDER,
    *V5_FILL, *V5_APPLICATION, *V5_QUOTE, *V5_BUY_HOLD_POLICY, 'portfolio_policy_ref',
    'phase', 'numerator', 'denominator', 'unit_split_policy', 'unit_splits')))


def reject_public_shape(value, schema, label):
    if value is None:
        return
    if schema is None:
        if isinstance(value, (dict, list)):
            raise ValueError('unexpected private or unknown v4 ' + label)
    elif isinstance(schema, tuple):
        if not isinstance(value, list):
            raise ValueError('unexpected private or unknown v4 ' + label)
        for row in value:
            reject_public_shape(row, schema[0], label + ' item')
    else:
        if not isinstance(value, dict) or set(value) - set(schema):
            raise ValueError('unexpected private or unknown v4 ' + label)
        for key, child in value.items():
            reject_public_shape(child, schema[key], label + '.' + key)
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


def reject_extra(value, keys, label):
    if not isinstance(value, dict) or set(value) - set(keys):
        raise ValueError('unexpected private or unknown v4 ' + label)


def validated_public_outer(view, run):
    """Validate envelope scalars before copying them into an HTML data script."""
    outer = {}
    for name in ('view_id', 'evidence_kind'):
        value = view.get(name)
        if not isinstance(value, str) or not value:
            raise ValueError('invalid public ' + name)
        cleaned = clean(value)
        if cleaned != value:
            raise ValueError('local path in public ' + name)
        outer[name] = cleaned
    for name in ('approximate', 'blocked'):
        value = view.get(name)
        if type(value) is not bool:
            raise ValueError('invalid public ' + name)
        outer[name] = value
    limitations = run.get('limitations', [])
    if not isinstance(limitations, list) or any(not isinstance(item, str) for item in limitations):
        raise ValueError('saved run limitations must be a list of strings')
    conditions = view.get('comparison_conditions', [])
    if not isinstance(conditions, list):
        raise ValueError('comparison conditions must be a list')
    for condition in conditions:
        reject_extra(condition, ('key', 'label', 'provided', 'value'), 'comparison condition')
        key = condition.get('key')
        if not isinstance(key, str) or not key or clean(key) != key:
            raise ValueError('invalid public comparison key')
        if 'label' in condition and not isinstance(condition['label'], str):
            raise ValueError('invalid public comparison label')
        if 'provided' in condition and type(condition['provided']) is not bool:
            raise ValueError('invalid public comparison provided flag')
    return outer


def validate_public_condition_values(conditions):
    """Selected conditions have a fixed scalar value or one known narrow object."""
    for condition in conditions:
        key = condition['key']
        value = condition.get('value')
        if key == 'initial_account':
            reject_public_shape(value, _public_object('cash_minor', positions=_public_object('')),
                                'public initial account condition')
        elif key == 'profile.extra':
            if not isinstance(value, dict):
                raise ValueError('unexpected nested public profile condition')
            reject_public_shape(value, dict.fromkeys(value), 'public profile condition')
        else:
            reject_public_shape(value, None, 'public comparison condition')


def reject_unknown_public_v4(value, *, v5=False, v6=False, security_keys=frozenset()):
    allowed = V5_PUBLIC_KEYS if v5 else V6_PUBLIC_KEYS if v6 else V4_PUBLIC_KEYS
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or (key not in allowed and key not in security_keys and
                not re.fullmatch(r'cnstock\.(?:000|002|003)\d{3}\.SZ\.\d{8}', key)):
                raise ValueError('unexpected private or unknown v4 public field: ' + str(key))
            reject_unknown_public_v4(child, v5=v5, v6=v6, security_keys=security_keys)
    elif isinstance(value, list):
        for child in value:
            reject_unknown_public_v4(child, v5=v5, v6=v6, security_keys=security_keys)


def validate_v4_public_account(run, securities, *, v5=False, v6=False):
    """Account scalar fields cannot carry arbitrary objects under legal key names."""
    containers = {'metrics', 'nav', 'positions', 'orders', 'fills', 'limitations', 'final_account'}
    reject_public_shape({k: v for k, v in run.items() if k not in containers | {'decisions', 'unit_split_applications', 'lifecycle_admission'} | ({'stopped'} if v6 else set())},
                        dict.fromkeys((set(RUN) - containers - {'unit_split_applications'}) |
                                      ({'portfolio_policy_ref'} if v5 else set()) |
                                      ({'stock_execution_rules_ref'} if v6 else set())), 'run')
    if v6:
        reject_public_shape(run.get('stopped'), _public_object(' '.join(V6_STOPPED)), 'stopped stock account')
        reject_public_shape(run.get('lifecycle_admission'), _public_object(' '.join(V6_LIFECYCLE)), 'lifecycle admission')
        if set(run.get('lifecycle_admission') or {}) != set(V6_LIFECYCLE) or any(
            (type(value) is not int or value < 0) and
            (type(value) is not str or not re.fullmatch(r'\d+', value))
            for value in run['lifecycle_admission'].values()):
            raise ValueError('invalid public v6 lifecycle admission')
        _digest_ref(run.get('stock_execution_rules_ref'), 'stock rules identity')
    reject_public_shape(run.get('metrics'), _public_object(' '.join(V6_METRICS if v6 else V4_METRICS)), 'metrics')
    for name, fields, sequences in (
        ('nav', V4_NAV, ()), ('positions', V5_POSITION if v5 else V6_POSITION if v6 else V4_POSITION, ('mark_source_refs',)),
        ('orders', V5_ORDER if v5 else V6_ORDER if v6 else V4_ORDER, ('announced_suspension_event_ids',) if v5 else ()),
        ('fills', V5_FILL if v5 else V6_FILL if v6 else V4_FILL, ('source_refs',))):
        clock = {'field_available_at'} if name in {'orders', 'fills'} else set()
        schema = _public_object(' '.join(k for k in fields if k not in set(sequences) | clock),
            **{k: (None,) for k in sequences},
            **({'field_available_at': _public_object(
                'close limit_down limit_up market_state open volume_shares')} if clock else {}))
        reject_public_shape(run.get(name), (schema,), name)
    reject_public_shape(run.get('limitations'), (None,), 'limitations')
    if v5:
        quote = _public_object('session price available_at', source_refs=(None,))
        application = _public_object(' '.join(k for k in V5_APPLICATION
            if k not in {'original_quote', 'normalized_quote', 'source_refs',
                         'rounding_extra_fraction'}),
            original_quote=quote, normalized_quote=quote, source_refs=(None,),
            rounding_extra_fraction=_public_object('numerator denominator'))
        reject_public_shape(run.get('unit_split_applications'), (application,), 'unit split applications')
    for decision in run.get('decisions') or []:
        nested = {'selected_security_ids', 'targets', 'trace', 'intents'}
        reject_public_shape({k: v for k, v in decision.items() if k not in nested},
                            _public_object(' '.join(k for k in (V6_DECISION if v6 else V4_DECISION) if k not in nested)), 'decision')
        reject_public_shape(decision.get('selected_security_ids'), (None,), 'selected securities')
        reject_public_shape(decision.get('trace'), (_public_object(' '.join(V6_TRACE if v6 else TRACE)),), 'decision trace')
        reject_public_shape(decision.get('intents'), (_public_object(' '.join((*V4_INTENT,
            'quantity_unit', 'reason', 'session'))),), 'decision intents')
        targets = decision.get('targets')
        if targets is not None:
            if not isinstance(targets, dict) or set(targets) - securities:
                raise ValueError('unexpected private or unknown v4 decision targets')
            reject_public_shape(targets, dict.fromkeys(targets), 'decision targets')
    final = run.get('final_account')
    if final is not None:
        reject_extra(final, ('cash_minor', 'receivable_minor', 'positions', 'committed_sequence'), 'final account')
        reject_public_shape({k: v for k, v in final.items() if k != 'positions'},
                            _public_object('cash_minor receivable_minor committed_sequence'), 'final account')
        positions = final.get('positions') or {}
        if not isinstance(positions, dict):
            raise ValueError('unexpected private or unknown v4 final positions')
        for security_id, position in positions.items():
            if security_id not in securities:
                raise ValueError('unexpected private or unknown v4 final security')
            reject_public_shape(position, _public_object('quantity sellable_quantity cost_minor'),
                                'final account position')


def _digest_refs(refs, label):
    if not isinstance(refs, list) or any(not isinstance(ref, str) or
            not re.fullmatch(r'sha256:[0-9a-f]{64}', ref) for ref in refs):
        raise ValueError('unexpected private or unknown v5 ' + label)


def _digest_ref(ref, label):
    if not isinstance(ref, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', ref):
        raise ValueError('unexpected private or unknown v5 ' + label)


def _v5_applications(rows):
    if not isinstance(rows, list):
        raise ValueError('unexpected private or unknown v5 unit split applications')
    result = []
    for row in rows:
        reject_extra(row, V5_APPLICATION, 'v5 unit split application')
        projected = pick(row, V5_APPLICATION)
        if row.get('rounding_extra_fraction') is not None:
            reject_public_shape(row['rounding_extra_fraction'],
                _public_object('numerator denominator'), 'v5 split fraction')
        for key in ('original_quote', 'normalized_quote'):
            if row.get(key) is not None:
                reject_extra(row[key], V5_QUOTE, 'v5 unit split quote')
                projected[key] = pick(row[key], V5_QUOTE)
                _digest_refs(projected[key].get('source_refs'), 'quote source refs')
        _digest_refs(projected.get('source_refs'), 'application source refs')
        result.append(projected)
    return result


def validate_v5_public_input(view, run):
    """Accept only the selected ETF owner paths; never export a native plan/grid."""
    reject_extra(run, (*RUN, 'portfolio_policy_ref', 'decisions'), 'v5 run field')
    configuration = view.get('configuration') or {}
    reject_extra(configuration, ('start_session', 'end_session', 'initial_account',
                                 'profile', 'price_basis', 'unit_split_policy',
                                 'portfolio_policy'), 'v5 configuration field')
    for name in ('start_session', 'end_session', 'price_basis', 'unit_split_policy'):
        reject_public_shape(configuration.get(name), None, 'v5 configuration.' + name)
    profile = configuration.get('profile') or {}
    reject_extra(profile, (*V5_PROFILE, 'price_grid'), 'v5 profile field')
    if any(isinstance(value, (dict, list)) for key, value in profile.items() if key != 'price_grid'):
        raise ValueError('unexpected private or unknown v5 nested profile field')
    _digest_ref(profile.get('price_grid_ref'), 'price grid identity')
    _digest_ref(run.get('portfolio_policy_ref'), 'portfolio policy identity')
    initial = configuration.get('initial_account') or {}
    reject_public_shape(initial, _public_object('cash_minor', positions=_public_object('')),
                        'v5 initial account')
    policy = configuration.get('portfolio_policy') or {}
    if not isinstance(policy, dict):
        raise ValueError('unexpected private or unknown v5 portfolio policy')
    kind = policy.get('contract_version')
    if kind == 'etf_rotation_policy_v1':
        reject_extra(policy, V5_ROTATION_POLICY, 'v5 rotation policy')
        if run.get('signal_ref') is None:
            raise ValueError('missing v5 rotation signal')
    elif kind == 'etf_buy_and_hold_policy_v1':
        reject_extra(policy, V5_BUY_HOLD_POLICY, 'v5 buy and hold policy')
        if run.get('signal_ref') is not None:
            raise ValueError('unexpected v5 buy and hold signal')
    else:
        raise ValueError('unexpected private or unknown v5 portfolio policy')
    reject_public_shape(policy, _public_object(' '.join(policy)), 'v5 portfolio policy')
    for name, allowed in (('metrics', V4_METRICS), ('nav', V4_NAV), ('positions', V5_POSITION),
                          ('orders', V5_ORDER), ('fills', V5_FILL),
                          ('decisions', (*V4_DECISION, 'reference_session', 'portfolio_policy_ref'))):
        rows = run.get(name) or ([] if name != 'metrics' else {})
        for row in rows if name != 'metrics' else [rows]:
            reject_extra(row, allowed, 'v5 ' + name)
    for row in run.get('positions') or []:
        reject_public_shape(row.get('mark_basis_event_id'), None, 'v5 mark basis event')
        if row.get('mark_source_refs') is not None:
            _digest_refs(row['mark_source_refs'], 'position mark source refs')
    for row in run.get('orders') or []:
        reject_public_shape(row.get('announced_suspension_event_ids'), (None,),
                            'v5 announced suspension events')
        if row.get('price_grid_ref') is not None:
            _digest_ref(row['price_grid_ref'], 'order price grid identity')
    for row in run.get('fills') or []:
        if row.get('source_refs') is not None:
            _digest_refs(row['source_refs'], 'fill source refs')
        if row.get('price_grid_ref') is not None:
            _digest_ref(row['price_grid_ref'], 'fill price grid identity')
    for condition in view.get('comparison_conditions') or []:
        reject_extra(condition, ('key', 'label', 'provided', 'value'), 'v5 condition')
        key = condition.get('key')
        if key == 'profile.extra':
            extra = condition.get('value') or {}
            reject_extra(extra, (*V5_PROFILE, 'price_grid'), 'v5 profile extra')
            if any(profile.get(name) != value for name, value in extra.items()):
                raise ValueError('v5 profile condition mismatch')
        elif isinstance(key, str) and key.startswith('profile.'):
            name = key[8:]
            if name not in V5_PROFILE or condition.get('value') != profile.get(name):
                raise ValueError('unexpected private or unknown v5 profile condition')
        elif key in SAFE_CONDITIONS and condition.get('value') != configuration.get(key):
            raise ValueError('v5 condition mismatch')
    for row in run.get('decisions') or []:
        for intent in row.get('intents') or []:
            reject_extra(intent, (*V4_INTENT, 'quantity_unit', 'reason', 'session'), 'v5 intent')
        for trace in row.get('trace') or []:
            reject_extra(trace, (*TRACE, 'count', 'top_k', 'detail', 'reference_nav_minor'), 'v5 trace')
    if run.get('final_account') is not None:
        final = run['final_account']
        reject_extra(final, ('cash_minor', 'receivable_minor', 'positions', 'committed_sequence'),
                     'v5 final account')
        if not isinstance(final.get('positions'), dict):
            raise ValueError('unexpected private or unknown v5 final positions')
        for position in final['positions'].values():
            reject_extra(position, ('quantity', 'sellable_quantity', 'cost_minor'),
                         'v5 final position')


def validate_v5_public_market(market, securities):
    """Validate each exported market path after selecting rows and dropping native proofs."""
    reject_extra(market, ('rows', 'price_basis', 'source_refs', 'data_batch', 'native_chart',
                          'review_display', 'security_labels', 'security_name_scope',
                          'security_label_source', 'review_events', 'fill_display', 'unit_splits'),
                 'v5 market')
    reject_public_shape(market.get('price_basis'), None, 'v5 price basis')
    if market.get('data_batch') is not None:
        raise ValueError('native DataBatch cannot enter public v5 market')
    _digest_refs(market.get('source_refs'), 'market source refs')
    reject_public_shape(market.get('rows'),
        (_public_object(' '.join(k for k in ROW if k not in {'source_refs', 'volume_shares'}),
                        source_refs=(None,)),), 'v5 market rows')
    for row in market.get('rows') or []:
        if row.get('source_refs') is not None:
            _digest_refs(row['source_refs'], 'market row source refs')
    labels = market.get('security_labels') or {}
    if not isinstance(labels, dict) or set(labels) - securities:
        raise ValueError('unexpected private or unknown v5 security label')
    reject_public_shape(labels, dict.fromkeys(labels), 'v5 security labels')
    reject_public_shape(market.get('security_name_scope'), None, 'v5 security name scope')
    reject_public_shape(market.get('security_label_source'), _public_object(
        'manifest_sha256 source_snapshot_id label_cutoff original_display_manifest_sha256'),
        'v5 security label source')
    display = market.get('review_display')
    if display is not None:
        fields = ('security_id', 'session', 'open', 'high', 'low', 'close', 'native_open',
                  'native_high', 'native_low', 'native_close', 'native_pre_close',
                  'volume_units', 'amount_cny', 'display_scale',
                  'display_missing_reason')
        reject_public_shape(display, _public_object(
            'contract_version manifest_sha256 display_projection names_status events_status '
            'public_selected_chart',
            context=_public_object('usage snapshot_id anchor_session knowledge_cutoff pit_policy '
                                   'default_price_basis native_price_basis', limitations=(None,)),
            field_units=_public_object(' '.join(fields[2:])),
            records=(_public_object(' '.join(fields)),)), 'v5 review display')
    reject_public_shape(market.get('review_events'),
        (_public_object('domain', event=_public_object(' '.join(REVIEW_EVENT))),),
        'v5 review events')
    reject_public_shape(market.get('fill_display'), _public_object(
        'contract_version content_digest display_result_ref display_ref status display_projection',
        coordinates=(_public_object('fill_id security_id session status reason display_price '
                                    'source_unit target_unit'),)), 'v5 fill display')
    native = market.get('native_chart')
    if native is not None:
        volume = 'volume_units'
        fields = ('open', 'high', 'low', 'close', volume)
        reject_public_shape(native, _public_object('display_projection public_selected_chart source_ref',
            context=_public_object('snapshot_id domain reader_version contract_id source_profile_id '
                'price_basis adjustment_anchor selected_start_session selected_end_session '
                'original_saved_batch_file_ref identity_note',
                original_saved_replay_source_refs=(None,)),
            records=(_public_object('security_id session ' + ' '.join(fields)),),
            field_meta={name: _public_object('unit dtype', by_key=(None,)) for name in fields},
            omitted=(None,)), 'v5 native chart')
        _digest_ref(native.get('source_ref'), 'selected chart source identity')
    reject_public_shape(market.get('unit_splits'),
        (_public_object('', event=_public_object(' '.join(EVENT)), source_refs=(None,)),),
        'v5 unit splits')


def reject_v5_source_urls(value):
    if isinstance(value, str) and re.search(r'\b(?:https?|file)://', value, re.I):
        raise ValueError('source URL is forbidden in public v5 projection')
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {'source_refs', 'original_saved_replay_source_refs'} and child is not None:
                _digest_refs(child, key)
            reject_v5_source_urls(child)
    elif isinstance(value, list):
        for child in value:
            reject_v5_source_urls(child)


def validate_v4_public_input(view, run, *, v6=False):
    """Fail closed on native v4 account/config fields exported as whole objects."""
    reject_extra(run, (*[key for key in RUN if key != 'unit_split_applications'], 'decisions',
                       *(V6_RUN_EXTRA if v6 else ())), 'run field')
    if v6:
        reject_extra(run.get('lifecycle_admission'), V6_LIFECYCLE, 'lifecycle admission')
        if run.get('stopped') is not None:
            reject_extra(run['stopped'], (*V6_STOPPED, 'gaps', 'blocks'), 'stopped account')
    configuration = view.get('configuration') or {}
    reject_extra(configuration, ('start_session', 'end_session', 'initial_account',
                                 'profile', 'price_basis'), 'configuration field')
    profile = configuration.get('profile') or {}
    reject_extra(profile, V6_PROFILE if v6 else V4_PROFILE, 'profile field')
    if any(isinstance(value, (dict, list)) for value in profile.values()):
        raise ValueError('unexpected private or unknown v4 nested profile field')
    initial = configuration.get('initial_account') or {}
    reject_extra(initial, ('cash_minor', 'positions'), 'initial account field')
    if initial.get('positions') not in ({}, None):
        raise ValueError('unexpected private or unknown v4 initial positions')
    reject_public_shape(initial, _public_object('cash_minor', positions=_public_object('')),
                        'initial account')
    for condition in view.get('comparison_conditions') or []:
        reject_extra(condition, ('key', 'label', 'provided', 'value'), 'condition field')
        key = condition.get('key')
        if key in SAFE_CONDITIONS:
            expected = (configuration if key != 'stock_action_policy' else
                        view.get('stock_context') or {}).get(key)
            if condition.get('value') != expected:
                raise ValueError('unexpected private or unknown v4 condition value')
        if key == 'profile.extra':
            extra = condition.get('value') or {}
            reject_extra(extra, V6_PROFILE if v6 else V4_PROFILE, 'profile condition')
            if any(profile.get(name) != value for name, value in extra.items()):
                raise ValueError('unexpected private or unknown v4 profile condition')
        if isinstance(key, str) and key.startswith('profile.') and key != 'profile.extra':
            name = key[8:]
            absent = condition.get('value') is None and condition.get('provided') is False
            if name not in (V6_PROFILE if v6 else V4_PROFILE) and not (absent and (v6 or name == 'tax_rate')):
                raise ValueError('unexpected private or unknown v4 profile condition')
            if name in (V6_PROFILE if v6 else V4_PROFILE) and condition.get('value') != profile.get(name):
                raise ValueError('unexpected private or unknown v4 profile condition')
    if run.get('metrics') is not None:
        reject_extra(run['metrics'], V6_METRICS if v6 else V4_METRICS, 'metrics field')
    for name, allowed in (('nav', V4_NAV), ('positions', V6_POSITION if v6 else V4_POSITION),
                          ('orders', V6_ORDER if v6 else V4_ORDER),
                          ('fills', V6_FILL if v6 else V4_FILL),
                          ('decisions', V6_DECISION if v6 else V4_DECISION)):
        for row in run.get(name) or []:
            reject_extra(row, allowed, name + ' field')
    for decision in run.get('decisions') or []:
        for intent in decision.get('intents') or []:
            reject_extra(intent, V4_INTENT, 'intent field')
        for trace in decision.get('trace') or []:
            reject_extra(trace, (*V6_TRACE, 'excluded_invalid_members') if v6 else (*TRACE, 'count', 'top_k'), 'trace field')
    if run.get('final_account') is not None:
        reject_extra(run['final_account'], ('cash_minor', 'receivable_minor',
                                            'positions', 'committed_sequence'), 'final account field')
        positions = run['final_account'].get('positions') or {}
        if not isinstance(positions, dict):
            raise ValueError('unexpected private or unknown v4 final positions')
        for security_id, position in positions.items():
            pattern = r'cnstock\.\d{6}\.(?:SH|SZ)\.\d{8}' if v6 else r'cnstock\.(?:000|002|003)\d{3}\.SZ\.\d{8}'
            if not isinstance(security_id, str) or not re.fullmatch(pattern, security_id):
                raise ValueError('unexpected private or unknown v4 final security')
            reject_extra(position, ('quantity', 'sellable_quantity', 'cost_minor'), 'final position field')


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
    stock = view['run'].get('contract_version') in ('backtest_run_v3', 'backtest_run_v4', 'backtest_run_v6')
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
    if not isinstance(view, dict):
        raise ValueError('public view must be an object')
    run = view.get('run') or {}
    if not isinstance(run, dict):
        raise ValueError('public run must be an object')
    if not run.get('run_id'):
        raise ValueError('public results require an explicit saved account')
    outer = validated_public_outer(view, run)
    v5 = run.get('contract_version') == 'backtest_run_v5'
    v6 = run.get('contract_version') == 'backtest_run_v6'
    if v5:
        validate_v5_public_input(view, run)
    v4 = run.get('contract_version') == 'backtest_run_v4'
    if v4 or v6:
        validate_v4_public_input(view, run, v6=v6)
        if view.get('stock_ml') is not None:
            raise ValueError('unexpected private or unknown v4 single-signal model')
    result = {**outer, 'run': pick(run, RUN),
              'configuration': pick(view['configuration'], ('start_session', 'end_session', 'initial_account',
                                                           'profile', 'price_basis', 'unit_split_policy',
                                                           'portfolio_policy')),
              'research': pick(view['research'], RESEARCH) if view.get('research') and not v5 else None,
              'evaluation': pick(view['evaluation'], EVALUATION) if view.get('evaluation') else None,
              'comparison_conditions': [clean(c) for c in view.get('comparison_conditions', [])
                                        if c['key'] in SAFE_CONDITIONS or c['key'].startswith('profile.')],
              'registration_history': []}
    if v5:
        result['run']['portfolio_policy_ref'] = clean(run['portfolio_policy_ref'])
        result['run']['unit_split_applications'] = _v5_applications(run.get('unit_split_applications') or [])
        result['configuration']['profile'] = pick(view['configuration']['profile'], V5_PROFILE)
        conditions = []
        for condition in result['comparison_conditions']:
            if condition['key'] == 'profile.extra':
                condition['value'] = pick(condition['value'], V5_PROFILE)
            conditions.append(condition)
        result['comparison_conditions'] = conditions
    if v6:
        _digest_ref(run.get('stock_execution_rules_ref'), 'stock rules identity')
        result['run']['stock_execution_rules_ref'] = clean(run['stock_execution_rules_ref'])
        result['run']['lifecycle_admission'] = pick(run['lifecycle_admission'], V6_LIFECYCLE)
        if run.get('stopped') is not None:
            result['run']['stopped'] = pick(run['stopped'], V6_STOPPED)
        result['configuration']['profile'] = pick(view['configuration']['profile'], V6_PROFILE)
        if result['configuration']['profile'].get('stock_execution_rules_ref') != run['stock_execution_rules_ref']:
            raise ValueError('public v6 stock rule identity mismatch')
        for key in ('stock_fee_schedule_ref',):
            _digest_ref(result['configuration']['profile'].get(key), key)
        policy = (view.get('stock_context') or {}).get('portfolio_policy') or {}
        if policy.get('stock_execution_rules_ref') != run['stock_execution_rules_ref']:
            raise ValueError('public v6 portfolio stock rule identity mismatch')
        for name in ('decisions', 'orders', 'fills'):
            if any(row.get('stock_execution_rules_ref') != run['stock_execution_rules_ref']
                   for row in run.get(name) or []):
                raise ValueError('public v6 saved stock rule identity mismatch')
    validate_public_condition_values(result['comparison_conditions'])
    result['run']['decisions'] = [pick(d, ('contract_version', 'feature_session', 'trade_session', 'status',
                                         'selected_security_id', 'selected_security_ids', 'signal_ref',
                                         'expected_account_version', 'intents', 'reason', 'top_k',
                                         *(('stock_execution_rules_ref',) if v6 else ()))) for d in run.get('decisions') or []]
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
            d['trace'] = [scalars(row, V6_TRACE if v6 else TRACE) for row in original['trace']]
        if 'intents' in d:
            d['intents'] = [pick(i, ('intent_id', 'security_id', 'side', 'quantity', 'quantity_unit', 'reason',
                                   'session', 'valid_until')) for i in d['intents']]
    required = {(r['security_id'], r['session']) for name in ('positions', 'fills', 'orders')
                for r in run.get(name) or [] if r.get('security_id') and r.get('session')}
    market = view['market']
    start, end = view['configuration']['start_session'], view['configuration']['end_session']
    row_fields = tuple(k for k in ROW if k != 'volume_shares') if v5 else ROW
    rows = [pick(r, row_fields) for r in market.get('rows') or []
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
        if v5:
            fields = tuple(k for k in fields if k != 'volume_shares')
        if v4 or v5 or v6:
            units = display.get('field_units') or {}
            reject_extra(units, fields[2:], 'display unit field')
            if any(value is not None and not isinstance(value, str) for value in units.values()):
                raise ValueError('unexpected private or unknown v4 display unit')
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
        if market.get('security_label_source'):
            result['market']['security_label_source'] = pick(market['security_label_source'],
                ('manifest_sha256', 'source_snapshot_id', 'label_cutoff', 'original_display_manifest_sha256'))
        result['market']['review_events'] = [
            {'domain': clean(item['domain']), 'event': pick(item['event'], REVIEW_EVENT)}
            for item in market.get('review_events') or [] if item['event'].get('security_id') in securities]
        if market.get('fill_display'):
            owner = market['fill_display']
            selected_fills = {item['fill_id'] for item in run.get('fills') or []}
            result['market']['fill_display'] = {
                **pick(owner, ('contract_version', 'content_digest', 'display_result_ref', 'display_ref',
                                'status', 'display_projection')),
                'coordinates': [pick(point, ('fill_id', 'security_id', 'session', 'status', 'reason',
                                             'display_price', 'source_unit', 'target_unit'))
                                for point in owner.get('coordinates') or []
                                if point.get('fill_id') in selected_fills and point.get('security_id') in securities]}
    if market.get('unit_splits') is not None:
        referenced_events = {r.get('event_id') for r in run.get('unit_split_applications') or []}
        referenced_events.update(r.get('mark_basis_event_id') for r in run.get('positions') or [])
        referenced_events.update(i for r in run.get('orders') or [] for i in r.get('announced_suspension_event_ids') or [])
        result['market']['unit_splits'] = [{'event': pick(item['event'], EVENT),
                                          'source_refs': clean(item.get('source_refs'))}
                                         for item in market['unit_splits'] if item['event'].get('event_id') in referenced_events]
        if v5:
            for item in result['market']['unit_splits']:
                reject_public_shape(item, _public_object('',
                    event=_public_object(' '.join(EVENT)), source_refs=(None,)), 'v5 unit split event')
                _digest_refs(item['source_refs'], 'event source refs')
    if run.get('contract_version') in ('backtest_run_v3', 'backtest_run_v4', 'backtest_run_v6'):
        context = view.get('stock_context') or {}
        result['stock_context'] = scalars(context, ('stock_action_policy', 'model_snapshot', 'execution_snapshot', 'admission_status'))
        for key in ('prediction_universe', 'execution_universe'):
            rows = context.get(key) or []
            if not isinstance(rows, list) or not all(isinstance(row, str) for row in rows):
                raise ValueError('unexpected nested public universe')
            result['stock_context'][key] = clean(rows)
        result['stock_context']['portfolio_policy'] = scalars(context.get('portfolio_policy') or {},
                                                             V6_POLICY if v6 else ('budget_basis', 'eligibility_id', 'rebalance', 'top_k'))
        if v4 or v6:
            reject_extra(context, ('stock_action_policy', 'model_snapshot', 'execution_snapshot',
                                   'admission_status', 'prediction_universe', 'execution_universe',
                                   'portfolio_policy', 'schedule_ref', 'folds'), 'schedule field')
            reject_extra(context.get('portfolio_policy') or {},
                         V6_POLICY if v6 else ('budget_basis', 'eligibility_id', 'rebalance', 'top_k'), 'portfolio policy')
            if context.get('schedule_ref') != run.get('signal_ref'):
                raise ValueError('saved run/schedule identity mismatch')
            result['stock_context']['schedule_ref'] = scalars(context, ('schedule_ref',))['schedule_ref']
            folds = context.get('folds')
            if not isinstance(folds, list) or not folds:
                raise ValueError('missing saved fold summary')
            result['stock_context']['folds'] = []
            for fold in folds:
                reject_extra(fold, ('fold_ref', 'fold_spec_ref', 'signal_run_ref', 'model_ref',
                                    'feature_ref', 'fit_session', 'oos_trade_sessions'), 'fold field')
                selected = scalars(fold, ('fold_ref', 'fold_spec_ref', 'signal_run_ref', 'model_ref',
                                          'feature_ref', 'fit_session'))
                days = fold.get('oos_trade_sessions')
                if not isinstance(days, list) or not days or not all(isinstance(day, str) for day in days):
                    raise ValueError('malformed saved fold sessions')
                selected['oos_trade_sessions'] = clean(days)
                result['stock_context']['folds'].append(selected)
        else:
            result['stock_context']['signal_inputs'] = scalars(context.get('signal_inputs') or {},
                                                             ('feature_ref', 'model_ref', 'score_semantics', 'score_unit'))
    result['run']['limitations'] = list(result['run'].get('limitations') or []) + [NOTE]
    result['public_display_projection'] = True
    if v4 or v5 or v6:
        validate_v4_public_account(result['run'], securities, v5=v5, v6=v6)
        reject_public_shape(result['market'].get('rows'),
            (_public_object(' '.join(k for k in ROW if k != 'source_refs'), source_refs=(None,)),),
            'market rows')
        reject_public_shape(result['evaluation'], _V4_PUBLIC_EVALUATION, 'evaluation')
        if v5:
            if result['run'].get('quantity_unit') != 'fund units' or result['run'].get('price_unit') != 'CNY/fund unit':
                raise ValueError('unexpected v5 ETF saved units')
            if result['run'].get('portfolio_policy_ref') is None:
                raise ValueError('missing saved v5 policy identity')
            validate_v5_public_market(result['market'], securities)
            reject_v5_source_urls(result)
        reject_unknown_public_v4(result, v5=v5, v6=v6, security_keys=securities if v5 or v6 else frozenset())
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
    banner = '<nav style="padding:8px 20px;background:#eef3f8;font-size:12px"><a href="index.html">← 实验结果入口</a> · 保存的模拟回测</nav>'
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
    links = ''.join('<section class="result-card"><h2>'+escape(r['title'])+'</h2><a href="'+r['file']+'">打开实验结果</a></section>' for r in results)
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
        (output/'performance.html').write_text(clean(text));performance='<p class="small secondary-link"><a href="performance.html">性能验收与发布证据</a> · Mac 本地有界实测，范围见详情。</p>'
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
        process = '<p class="small secondary-link"><a href="process.html">查看保存的关键中间过程</a> · 训练、信号与交易日期及执行范围。</p>'
    index='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Axiom · 研究工作台</title><style>body{margin:0;background:#f3f6fa;color:#25374d;font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1000px;margin:40px auto;padding:0 22px}section{background:white;border:1px solid #dce5ef;border-radius:12px;padding:22px;margin:18px 0}.result-card{border-left:4px solid #547da3}.secondary-link{margin:12px 2px}a{color:#416e99}h1{font-size:30px;margin-bottom:0}.subhead{font-size:17px;color:#416e99;margin:0 0 18px}.small{font-size:13px;color:#52677e}summary{cursor:pointer;color:#416e99}</style><main><p class="small">AXIOM · 授权选定保存结果 · 公开只读</p><h1>Axiom 研究工作台</h1><p class="subhead">实验结果入口</p><p>打开已保存实验，查看收益风险、交易复盘与统计。结果为模拟回测，执行假设和费用见各运行。</p>'''+links+process+performance+'''<section><details><summary>结果口径与来源</summary><p>ETF 与股票分别按基金份额与股显示；保存的日线执行近似不验证实际开盘流动性或实盘成交。沪深300和上证综指是价格指数，不含分红；账户收益含已入账分红。数据与分红仅覆盖已保存来源，不补缺值。</p><p>分享版仅包含授权选定的回测窗口与相关证券行情。完整 DataBatch、coverage、模型输入和未选结果不随页面公开；来源引用保留在各报告中。</p></details><p><a href="publication.json">公开发布记录</a> · <a href="'''+DESIGN+'''">统一设计文档</a> · <a href="https://github.com/sinnergarden/axiom-ui">源码与更新流程</a></p></section></main></html>'''
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
