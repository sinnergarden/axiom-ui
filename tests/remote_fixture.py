"""Tiny synthetic registered results shared by HTTP and Chrome tests."""
from datetime import date, timedelta
import test_result_catalog as fixtures


def fixture():
    f = fixtures.CatalogTest()
    f.setUp()
    run = f.artifact('run-a', 'BacktestRun', f.run_id, f.run_digest, 'run.json', 'backtest_run_v8')
    report = f.artifact('eval-a', 'BacktestEvaluation', f.eval_id, f.eval_digest, 'eval.json', 'evaluation_report_v3')
    f.eval_wire['period_metrics']['account'].update(total_return='0.25', final_nav_minor=125000)
    signal = {'artifact_key': 'signal-eval', 'owner': 'Research', 'artifact_type': 'StockSignalEvaluation',
              'artifact_id': f.signal_eval_id, 'content_digest': f.signal_eval_digest,
              'artifact_contract_version': 'stock_signal_evidence_v8', 'root_id': 'research',
              'relative_path': 'signal-eval.json'}
    (f.research / 'signal-eval.json').write_text('{}')
    account = {'strategy_ref': fixtures.digest('strategy'), 'signal_run_ref': f.shared_signal,
               'status': 'COMPLETE', 'reason': None, 'backtest_ref': {'artifact_key': 'run-a', **f.run_ref},
               'evaluation_refs': [{'artifact_key': 'eval-a', 'evaluation_ref': f.eval_id,
                                   'content_digest': f.eval_digest, 'input_run_ref': f.run_ref}]}
    f.first = f.add('remote-first', 'q1', 'v1', accounts=[account], artifacts=[run, report, signal],
                   signals=[{'signal_run_ref': f.shared_signal, 'status': 'COMPLETE',
                             'evaluation_artifact_keys': ['signal-eval']}])
    f.second = f.add('remote-second', 'q2', 'v3', status='BLOCKED', reason='第二个实验')
    for i in range(24):
        f.add('extra-' + str(i), 'q1', 'v2')
    # Deliberately populated path/HTML must never reach the remote DOM.
    f.first['reason'] = '/Users/example/private/secret.json <img src=x onerror=alert(1)>'
    f.manifests[f.first['result_id']]['reason'] = f.first['reason']
    f.nav = [{'session': (date(2019, 1, 1) + timedelta(days=i)).isoformat(),
              'nav_minor': 100000 + i * 10} for i in range(1800)]
    f.eval_wire['series'] = f.nav
    f.run_wire['request_manifest'] = {}
    f.signal_eval_wire.update(input_signal_refs=[f.shared_signal], label_ref=fixtures.digest('label'),
        audit_scope='report_and_bindings', ancestors_audited=False,
        label_spec={'horizon_sessions': 40}, coverage={'valid_pair_count': 99}, limitations=[])
    return f


def run_fixture(f, action):
    from unittest.mock import patch
    def wrapped():
        import axiom_research
        original_index = axiom_research.ExperimentReader.index
        def synthetic_index(reader):
            value = original_index(reader)
            for question in value['questions']:
                question['question']['title'] = '合成验收 · ' + question['question']['title']
            return value
        with patch.object(axiom_research.ExperimentReader, 'index', synthetic_index), \
             patch('axiom_ui.result_catalog._run_metadata_summary', return_value={
                'availability': 'NOT_OPENED', 'artifact_type': 'BacktestRun', 'artifact_id': f.run_id}), \
             patch('axiom_ui.result_catalog._load_account', return_value=(f.run_wire, f.nav)), \
             patch.object(axiom_research, 'load_stock_signal_evaluation_summary',
                          return_value=f.signal_eval_wire, create=True):
            return action()
    return f.refresh(action=wrapped)
