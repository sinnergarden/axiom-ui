import secrets
import socket
from concurrent.futures import ThreadPoolExecutor
from threading import Condition, Event, Thread
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from axiom_ui.remote_results import build_remote_server, project
from remote_fixture import fixture, run_fixture


class RemoteTests(TestCase):
    def test_auth_routes_refresh_and_projection(self):
        f = fixture()
        self.addCleanup(f.doCleanups)
        token = secrets.token_urlsafe(32)
        origin = 'https://sinnergarden.github.io'
        def action():
            with build_remote_server(research_root=f.research, engine_root=f.engine,
                                     token=token, origins=[origin]) as server:
                worker = Thread(target=server.serve_forever, daemon=True); worker.start()
                base = f'http://127.0.0.1:{server.server_port}'
                def request(path='/', method='GET', auth=token, source=origin, extra=None):
                    headers = {'Origin': source, **(extra or {})}
                    if auth is not None: headers['Authorization'] = 'Bearer ' + auth
                    req = Request(base + path, headers=headers, method=method)
                    try: response = urlopen(req, timeout=3)
                    except HTTPError as error: response = error
                    return response.status, response.headers, response.read().decode()
                try:
                    for path in ['/', '/refresh', '/result/' + f.first['result_id'][7:], '/etc/passwd']:
                        self.assertEqual(request(path, auth=None)[0], 401)
                    self.assertEqual(request(auth='x' * 43)[0], 401)
                    self.assertEqual(request(source='https://foreign.example')[0], 403)
                    status, headers, body = request()
                    self.assertEqual(status, 200); self.assertEqual(headers['Cache-Control'], 'no-store')
                    self.assertEqual(headers['Access-Control-Allow-Origin'], origin)
                    self.assertEqual(f.result_calls, []); self.assertEqual(f.owner_calls, [])
                    self.assertNotIn('/Users/', body); self.assertNotIn('<img', body)
                    self.assertIn('第 1 / 2 页', body)
                    self.assertIn('第 2 / 2 页', request('/?page=2')[2])
                    for path in ['/etc/passwd', '/result/' + f.first['result_id'][7:] + '/full', '/index.json']:
                        self.assertEqual(request(path)[0], 404)
                    for path in ['/?page=1&page=2', '/?path=/etc/passwd', '/?page_size=101']:
                        self.assertEqual(request(path)[0], 422)
                    status, _, detail = request('/result/' + f.first['result_id'][7:])
                    self.assertEqual(status, 200); self.assertIn('25%', detail)
                    for text in ['保存产物与完整引用', 'relative_path', 'secret.json', '/full', '<pre>']:
                        self.assertNotIn(text, detail)
                    self.assertEqual(len(f.result_calls), 1)
                    f.add('appended', 'q2', 'v3', reason='新登记自动发现')
                    self.assertIn('结果 27', request()[2])
                    self.assertEqual(request('/refresh', 'POST')[0], 200)
                    self.assertEqual(request('/', 'OPTIONS', auth=None, extra={
                        'Access-Control-Request-Method': 'GET',
                        'Access-Control-Request-Headers': 'authorization'})[0], 204)
                finally:
                    server.shutdown(); worker.join(3)
        run_fixture(f, action)

    def test_idle_connection_does_not_block_requests_and_expires(self):
        f = fixture()
        self.addCleanup(f.doCleanups)
        token = secrets.token_urlsafe(32)

        def action():
            with build_remote_server(research_root=f.research, engine_root=f.engine,
                                     token=token, origins=['https://example.com']) as server:
                # Keep the production bound long enough to prove responses do
                # not depend on timeout; shorten only the separate expiry check.
                accepted = Event()
                original = server.get_request
                def accept():
                    result = original()
                    accepted.set()
                    return result
                server.get_request = accept
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    with socket.create_connection(server.server_address, timeout=2) as idle:
                        self.assertTrue(accepted.wait(2))
                        base = f'http://127.0.0.1:{server.server_port}'
                        with self.assertRaises(HTTPError) as error:
                            urlopen(base + '/', timeout=2)
                        self.assertEqual(error.exception.code, 401)
                        error.exception.close()
                        with urlopen(Request(base + '/', headers={'Authorization': 'Bearer ' + token}),
                                     timeout=2) as response:
                            self.assertEqual(response.status, 200)
                            self.assertIn('合成验收', response.read().decode())
                    server.request_timeout = 0.2
                    accepted.clear()
                    with socket.create_connection(server.server_address, timeout=2) as idle:
                        self.assertTrue(accepted.wait(2))
                        self.assertEqual(idle.recv(1), b'')
                finally:
                    server.shutdown()
                    worker.join(3)
        run_fixture(f, action)

    def test_refresh_and_all_read_routes_share_one_catalog_transaction(self):
        from axiom_ui.result_catalog import LocalResultCatalog
        f = fixture()
        self.addCleanup(f.doCleanups)
        token = secrets.token_urlsafe(32)

        def action():
            with build_remote_server(research_root=f.research, engine_root=f.engine,
                                     token=token, origins=['https://example.com']) as server:
                refreshed, release, read_entered = Event(), Event(), Event()
                authorized = Condition()
                count = 0
                original_auth = server.RequestHandlerClass._authorize
                def authorize(handler):
                    nonlocal count
                    result = original_auth(handler)
                    with authorized:
                        count += 1
                        authorized.notify_all()
                    return result
                original_refresh = LocalResultCatalog.refresh
                def refresh(catalog):
                    original_refresh(catalog)
                    refreshed.set()
                    if not release.wait(5):
                        raise AssertionError('test did not release refresh')
                def observed(method):
                    def render(catalog, *args, **kwargs):
                        read_entered.set()
                        return method(catalog, *args, **kwargs)
                    return render
                base = f'http://127.0.0.1:{server.server_port}'
                result = '/result/' + f.first['result_id'][7:]
                def request(path, method='GET'):
                    with urlopen(Request(base + path, method=method,
                            headers={'Authorization': 'Bearer ' + token}), timeout=5) as response:
                        return response.status, response.read().decode()
                from contextlib import ExitStack
                with ExitStack() as patches, ThreadPoolExecutor(max_workers=6) as pool:
                    patches.enter_context(patch.object(server.RequestHandlerClass, '_authorize', authorize))
                    patches.enter_context(patch.object(LocalResultCatalog, 'refresh', refresh))
                    for name in ('index_html', 'detail_html', 'signal_html', 'account_html'):
                        patches.enter_context(patch.object(LocalResultCatalog, name,
                            observed(getattr(LocalResultCatalog, name))))
                    worker = Thread(target=server.serve_forever, daemon=True)
                    worker.start()
                    try:
                        first = pool.submit(request, '/refresh', 'POST')
                        self.assertTrue(refreshed.wait(2))
                        paths = ['/', result, result + '/signal/0/0', result + '/account/0']
                        pending = [pool.submit(request, path) for path in paths]
                        with authorized:
                            self.assertTrue(authorized.wait_for(lambda: count == 5, timeout=2))
                        self.assertFalse(read_entered.wait(0.1), 'read overlapped unfinished refresh')
                        release.set()
                        for future in [first, *pending]:
                            self.assertEqual(future.result(timeout=5)[0], 200)
                    finally:
                        release.set()
                        server.shutdown()
                        worker.join(3)
        run_fixture(f, action)

    def test_no_active_markup_or_raw_json(self):
        value = project('<main><script>alert(1)</script><pre>{"secret":1}</pre>'
                        '<p title="/Users/a/b">/etc/passwd C:\\private\\secret.txt</p>'
                        '<a href="https://evil.example">outside</a><svg onload="bad()"><polyline points="1,2"/></svg></main>')
        for forbidden in ['alert', 'secret', '/etc', '/Users', 'onload', 'evil.example', '<pre']:
            self.assertNotIn(forbidden, value)

    def test_weak_token_rejected_before_readers(self):
        with self.assertRaises(ValueError):
            build_remote_server(research_root='absent', engine_root='absent', token='1234', origins=['https://example.com'])

    def test_remote_curve_uses_only_bound_evaluation_leaf(self):
        from unittest.mock import patch
        from axiom_ui.result_catalog import LocalResultCatalog, ResultCatalogError
        f = fixture()
        self.addCleanup(f.doCleanups)
        def action():
            catalog = LocalResultCatalog(research_root=f.research, engine_root=f.engine)
            with patch('axiom_ui.result_catalog._load_account', side_effect=AssertionError('account parts forbidden')):
                html = catalog.account_html(f.first['result_id'], 0, remote=True)
                self.assertIn('评价报告保存净值', html)
                self.assertIn('1800 / 全账户 1800', html)
                self.assertIn('600 / 区间原始点数 1800', html)
                self.assertFalse(catalog.opened_runs)
                for field, bad in [('evaluation_ref', 'bad'), ('content_digest', 'bad'),
                                   ('input_run_ref', {**f.run_ref, 'committed_sequence': 999})]:
                    original = f.eval_wire[field]
                    f.eval_wire[field] = bad
                    with self.assertRaises(ResultCatalogError):
                        catalog.account_html(f.first['result_id'], 0, remote=True)
                    f.eval_wire[field] = original
        run_fixture(f, action)
