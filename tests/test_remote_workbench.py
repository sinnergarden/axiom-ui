from threading import Event, Lock
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from axiom_ui.remote_workbench import WorkbenchRead, _stream_view


class WorkbenchTests(TestCase):
    def test_one_inflight_read_deduplicates_and_has_terminal_failure(self):
        entered, release, done = Event(), Event(), Event()
        catalog = SimpleNamespace(refresh=lambda: None)
        job = WorkbenchRead(catalog, Lock())
        def render(*args, **kwargs):
            entered.set()
            release.wait(3)
            done.set()
            raise ValueError('synthetic invalid binding')
        with patch('axiom_ui.remote_workbench.render_remote_workbench', render):
            status, ident = job.request(selected='a')
            self.assertEqual(status, 202)
            self.assertTrue(entered.wait(1))
            self.assertEqual(job.request(selected='a'), (202, ident))
            self.assertEqual(job.request(selected='b')[0], 409)
            self.assertEqual(job.request(job_id='unknown')[0], 409)
            release.set()
            self.assertTrue(done.wait(1))
            # Acquiring the transaction lock ensures the read has exited; then
            # join the worker via its observable status without a timing sleep.
            import time
            deadline = time.monotonic() + 1
            while job.request(job_id=ident)[0] == 202 and time.monotonic() < deadline:
                Event().wait(.01)
            self.assertEqual(job.request(job_id=ident)[0], 422)

    def test_stream_adapter_keeps_all_saved_rows_and_native_identity(self):
        rows = {key: [{'session': '2026-01-02'}] for key in ('nav', 'positions', 'orders', 'fills')}
        rows['decisions'] = [{'reference_prices': {'unused': 'full universe'},
                              'intents': [{'intent_id': 'saved'}], 'trade_session': '2026-01-02'}]
        saved = SimpleNamespace(rows=rows, profile={'stock_execution_rules': {'unused': 'document'}, 'slippage_bps': '5'},
            wire={'contract_version': 'backtest_run_v8', 'run_id': 'native',
                  'request_manifest': {'scope': {'start_session': '2026-01-02', 'end_session': '2026-01-02'},
                                       'initial_account': {'cash_minor': 100}, 'portfolio_policy': {}}})
        view = _stream_view(saved)
        self.assertEqual(view['run']['contract_version'], 'backtest_run_v8')
        for key in ('nav', 'positions', 'orders', 'fills'):
            self.assertEqual(view['run'][key], rows[key])
        self.assertEqual(view['run']['decisions'][0]['intents'], rows['decisions'][0]['intents'])
        self.assertNotIn('reference_prices', view['run']['decisions'][0])
        self.assertNotIn('stock_execution_rules', view['configuration']['profile'])
        self.assertEqual(view['market']['rows'], [])
