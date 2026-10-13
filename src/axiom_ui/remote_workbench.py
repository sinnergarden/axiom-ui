"""Authenticated adaptation of registered saved results to the existing workbench.

Only selected accounts and their registered evaluation leaves are loaded. The
navigation reads manifest/run metadata; it never opens training or market roots.
"""
from copy import deepcopy
from collections import OrderedDict
import re

from .result_catalog import (_require, _relative_file, _engine_nested_artifact,
                             _run_metadata_summary, _strategy_label, _wire)
from .workbench import _run, _evaluation, _comparison_conditions, _render

SELECTION = re.compile(r'([0-9a-f]{64}):([0-9]{1,9})\Z')


def _research(catalog, head):
    question, versions = catalog.questions[head['question_id']]
    version = versions[head['version_ref']]
    return dict(question_id=head['question_id'], title=question.get('title'),
                hypothesis=question.get('hypothesis'), version_id=head['version_ref'],
                version_label=version.get('label'), created_at=head['updated_at'],
                status=head['status'], tags=question.get('tags') or [],
                parameters=version.get('parameters'), changes=version.get('explicit_changes'))


def _stream_view(saved):
    # Keep v7/v8 identity intact. SavedRunProjection has already verified each
    # account part and linkage; this is a display mapping, never a v6 conversion.
    wire, rows = saved.wire, saved.rows
    profile = {key: value for key, value in saved.profile.items()
               if key not in {'stock_execution_rules', 'stock_fee_schedule'}}
    request = wire['request_manifest']
    scope = request['scope']
    configuration = dict(start_session=scope['start_session'], end_session=scope['end_session'],
                         initial_account=request['initial_account'], profile=profile,
                         portfolio_policy=request['portfolio_policy'], price_basis=None)
    run = {key: deepcopy(wire.get(key)) for key in (
        'contract_version', 'run_id', 'account_id', 'status', 'content_digest',
        'committed_sequence', 'signal_ref', 'market_ref', 'profile_ref', 'metrics',
        'core_version', 'runtime_version', 'implementation_ref', 'limitations',
        'initial_nav_minor', 'stopped', 'lifecycle_admission')}
    run.update({key: rows[key] for key in ('nav', 'positions', 'decisions', 'orders', 'fills')})
    run['decisions'] = [{key: value for key, value in row.items()
                         if key != 'reference_prices'} for row in rows['decisions']]
    run.update(quantity_unit='shares', price_unit='CNY/share')
    return dict(run=run, configuration=configuration,
                comparison_conditions=_comparison_conditions(configuration),
                market=dict(rows=[], data_batch=None, source_refs=[],
                            missing_reason='当前尚未接入保存行情的显示读取接口；不从持仓或成交推算 K 线。'),
                evidence_kind='saved_backtest_output', evaluation=None,
                approximate=profile.get('approximation') == 'retrospective_daily_volume_proxy',
                blocked=False, research=None,
                stock_context=dict(portfolio_policy=request['portfolio_policy'],
                                   stock_action_policy=request.get('stock_action_policy')))


def _selected(catalog, manifest, account):
    refs = {ref['artifact_key']: ref for ref in manifest['artifacts']}
    binding = account['backtest_ref']
    ref = refs[binding['artifact_key']]
    _require(ref['owner'] == 'Engine' and ref['artifact_type'] == 'BacktestRun', 'not an Engine account')
    path = _relative_file(ref, catalog.roots)
    if ref['artifact_contract_version'] in {'backtest_run_v7', 'backtest_run_v8'}:
        from axiom_engine.runtime import load_stock_backtest_projection
        saved = load_stock_backtest_projection(path, artifact_reader=lambda item:
            _engine_nested_artifact(item, catalog.roots['engine']), limits=catalog.engine_limits)
        view = _stream_view(saved)
    else:
        from axiom_engine.runtime import load_backtest_run
        view = _run(_wire(load_backtest_run(path)), 'saved_backtest_output')
    run = view['run']
    _require(run['contract_version'] == ref['artifact_contract_version'] and
             run['run_id'] == ref['artifact_id'] == binding['run_id'] and
             run['content_digest'] == ref['content_digest'] == binding['content_digest'] and
             run['committed_sequence'] == binding['committed_sequence'], 'account binding mismatch')
    evaluations = account.get('evaluation_refs') or []
    if evaluations:
        # Preserve registered order. Do not infer a newest/best evaluation.
        er = evaluations[0]
        report_ref = refs[er['artifact_key']]
        _require(report_ref['owner'] == 'Engine' and report_ref['artifact_type'] == 'BacktestEvaluation',
                 'not an Engine evaluation')
        from axiom_engine.runtime import load_backtest_evaluation
        report = _wire(load_backtest_evaluation(_relative_file(report_ref, catalog.roots)))
        _require(report['contract_version'] == report_ref['artifact_contract_version'] and
                 report['evaluation_ref'] == er['evaluation_ref'] == report_ref['artifact_id'] and
                 report['content_digest'] == er['content_digest'] == report_ref['content_digest'] and
                 report['input_run_ref'] == er['input_run_ref'], 'evaluation registration mismatch')
        evaluation = _evaluation(report, run)
        view['evaluation'] = {key: value for key, value in evaluation.items()
                              if key not in {'base_evaluation', 'execution_trace', 'benchmark_inputs',
                                             'benchmark_input', 'dividend_scope'}}
    # Market data is accepted only through already registered, bound Owner
    # inputs. No Data query, ancestral loader, or synthetic candle is issued.
    return view


def render_remote_workbench(catalog, *, selected=None, compare=None):
    views, entries = [], {}
    if not hasattr(catalog, '_workbench_metadata'):
        catalog._workbench_metadata = OrderedDict()
        catalog._workbench_views = OrderedDict()
    for result_id, head in catalog.heads.items():
        _, manifest, error = catalog._manifest(result_id)
        if manifest is None:
            continue
        refs = {ref['artifact_key']: ref for ref in manifest['artifacts']}
        for index, account in enumerate(manifest.get('accounts') or []):
            binding = account.get('backtest_ref')
            if not binding:
                continue
            key = result_id[7:] + ':' + str(index)
            ref = refs[binding['artifact_key']]
            digest = ref['content_digest']
            if digest not in catalog._workbench_metadata:
                catalog._workbench_metadata[digest] = _run_metadata_summary(ref, catalog.roots)
                if len(catalog._workbench_metadata) > 128:
                    catalog._workbench_metadata.popitem(last=False)
            metadata = catalog._workbench_metadata[digest]
            title = _strategy_label(metadata.get('strategy_spec'), account.get('strategy_ref'))
            view = dict(view_id=key, remote_selection=key, account_title=title,
                        run=dict(run_id=binding['run_id'], status=account['status']),
                        configuration={}, market=dict(rows=[], data_batch=None),
                        comparison_conditions=[], evidence_kind='research_record_only',
                        evaluation=None, approximate=False, blocked=False,
                        research=_research(catalog, head))
            views.append(view)
            entries[key] = (manifest, account, view)
    _require(bool(views), 'no registered account is available')
    selected = selected or views[0]['view_id']
    _require(selected in entries and (not compare or compare in entries), 'unknown account selection')
    if compare == selected:
        compare = None
    for key in dict.fromkeys([selected] + ([compare] if compare else [])):
        manifest, account, placeholder = entries[key]
        cache_key = (key, manifest['content_digest'], account['backtest_ref']['content_digest'],
                     tuple(e['content_digest'] for e in account.get('evaluation_refs') or []))
        if cache_key not in catalog._workbench_views:
            catalog._workbench_views[cache_key] = _selected(catalog, manifest, account)
            if len(catalog._workbench_views) > 2:
                catalog._workbench_views.popitem(last=False)
        catalog._workbench_views.move_to_end(cache_key)
        loaded = dict(catalog._workbench_views[cache_key])
        loaded.update({name: placeholder[name] for name in ('view_id', 'remote_selection', 'account_title', 'research')})
        placeholder.update(loaded)
    return _render(views, catalog.generated_at,
                   remote=dict(selected=selected, compare=compare or ''))


class WorkbenchRead:
    """One in-flight, authenticated read; no queue, persistence, or scheduled work."""
    def __init__(self, catalog, catalog_lock):
        from threading import Lock
        self.catalog, self.catalog_lock = catalog, catalog_lock
        self.lock = Lock()
        self.job = None

    def request(self, *, selected=None, compare=None, job_id=None):
        from secrets import token_hex
        from threading import Thread
        from time import monotonic
        with self.lock:
            if job_id is not None:
                if self.job is None or self.job['id'] != job_id or monotonic() > self.job['expires']:
                    return 409, '读取已结束，请重新刷新。'
                return self.job['status'], self.job['body']
            if self.job is not None and self.job['status'] == 202:
                if self.job['selection'] == (selected, compare):
                    return 202, self.job['body']
                return 409, '另一账户正在读取，请稍后再选。'
            ident = token_hex(16)
            self.job = dict(id=ident, selection=(selected, compare), status=202,
                            body=ident, expires=monotonic() + 600)
            def read():
                try:
                    # Capture one freshly validated index and hold its complete
                    # render transaction. A later refresh starts a new job.
                    with self.catalog_lock:
                        self.catalog.refresh()
                        html = render_remote_workbench(self.catalog, selected=selected, compare=compare)
                    status, body = 200, html
                except Exception:
                    status, body = 422, '保存账户读取失败；请刷新后重试。'
                with self.lock:
                    self.job.update(status=status, body=body, expires=monotonic() + 600)
            Thread(target=read, daemon=True).start()
            return 202, ident


def decision_evidence(catalog, *, selected, day, security):
    """Read one registered prediction leaf for one already admitted decision."""
    match = SELECTION.fullmatch(selected)
    _require(match is not None and re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) is not None,
             'invalid decision selection')
    _, manifest, error = catalog._manifest('sha256:' + match[1])
    _require(manifest is not None, 'result unavailable')
    account = manifest['accounts'][int(match[2])]
    key = (selected, manifest['content_digest'], account['backtest_ref']['content_digest'],
           tuple(e['content_digest'] for e in account.get('evaluation_refs') or []))
    view = getattr(catalog, '_workbench_views', {}).get(key)
    _require(view is not None, 'reload the selected account')
    decisions = [d for d in view['run']['decisions'] if d.get('trade_session') == day]
    _require(len(decisions) == 1, 'ambiguous decision')
    decision = decisions[0]
    _require(security in decision.get('targets', {}) or
             any(i.get('security_id') == security for i in decision.get('intents', [])),
             'security not in decision')
    refs = [r for r in manifest['artifacts'] if r['owner'] == 'Research' and
            r['artifact_type'] == 'StockPredictionRun' and
            r['artifact_id'] == decision.get('signal_ref')]
    _require(len(refs) == 1, 'prediction leaf not registered')
    ref = refs[0]
    from axiom_research import load_stock_prediction_projection
    saved = load_stock_prediction_projection(_relative_file(ref, catalog.roots), research_root=catalog.roots['research'])
    wire = _wire(saved)
    _require(saved.content_digest == ref['content_digest'] and
             wire['signal_run_ref'] == decision['signal_ref'] and
             wire['contract_version'] == ref['artifact_contract_version'], 'prediction binding mismatch')
    rows = [r for r in wire['rows'] if r.get('session') == decision['feature_session'] and
            r.get('security_id') == security]
    _require(len(rows) == 1, 'prediction row unavailable')
    row = rows[0]
    return dict(feature_session=decision['feature_session'], security_id=security,
                signal_ref=decision['signal_ref'], score_semantics=wire['score_semantics'],
                score_unit=wire['score_unit'], **{k: row.get(k) for k in
                ('score', 'rank', 'valid', 'member', 'invalid_reason')})
