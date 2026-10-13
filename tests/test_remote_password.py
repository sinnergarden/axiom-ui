from threading import Thread
from unittest import TestCase
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json

from axiom_ui.remote_password import PasswordLogin, password_record
from axiom_ui.remote_results import build_remote_server
from remote_fixture import fixture, run_fixture


class PasswordTests(TestCase):
    def test_login_limit_session_and_logout(self):
        login = PasswordLogin(password_record('synthetic-pass'))
        status, token = login.login('synthetic-pass')
        self.assertEqual(status, 200)
        self.assertTrue(login.authorized(token))
        login.logout(token)
        self.assertFalse(login.authorized(token))
        for _ in range(5):
            self.assertEqual(login.login('wrong-pass')[0], 401)
        self.assertEqual(login.login('synthetic-pass')[0], 429)
        login.failures.clear()
        status, token = login.login('synthetic-pass')
        login.sessions[token] = 0
        self.assertFalse(login.authorized(token))

    def test_http_login_origin_and_session(self):
        f = fixture()
        self.addCleanup(f.doCleanups)
        def action():
            with build_remote_server(research_root=f.research, engine_root=f.engine,
                    origins=['https://example.com'], password_record=password_record('synthetic-pass')) as server:
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                base = f'http://127.0.0.1:{server.server_port}'
                def request(path, password=None, token=None, origin='https://example.com'):
                    headers = {'Origin': origin}
                    if token: headers['Authorization'] = 'Bearer ' + token
                    data = json.dumps({'password': password}).encode() if password else None
                    method = 'POST' if password or path == '/logout' else 'GET'
                    try:
                        response = urlopen(Request(base + path, data=data, headers=headers, method=method), timeout=3)
                    except HTTPError as error:
                        response = error
                    with response:
                        return response.status, response.read()
                try:
                    self.assertEqual(request('/login', 'synthetic-pass', origin='https://foreign.example')[0], 403)
                    self.assertEqual(request('/login', 'wrong-pass')[0], 401)
                    status, body = request('/login', 'synthetic-pass')
                    self.assertEqual(status, 200)
                    token = json.loads(body)['token']
                    self.assertNotIn(b'synthetic-pass', body)
                    self.assertEqual(request('/', token=token)[0], 200)
                    self.assertEqual(request('/logout', token=token)[0], 204)
                    self.assertEqual(request('/', token=token)[0], 401)
                finally:
                    server.shutdown()
                    worker.join(3)
        run_fixture(f, action)
