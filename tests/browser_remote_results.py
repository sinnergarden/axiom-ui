"""Real Chrome/CDP cross-origin shell acceptance using tiny synthetic owners."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import urlopen
import base64
import json
import secrets
import socket
import subprocess
import time
import websocket

from axiom_ui.remote_results import build_remote_server
from remote_fixture import fixture, run_fixture

ROOT = Path(__file__).resolve().parents[1]
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


def check():
    f = fixture()
    token = secrets.token_urlsafe(32)
    evidence = {'fixture': 'synthetic; no owner data, credentials or network configuration persisted'}
    def action():
        class Quiet(SimpleHTTPRequestHandler):
            def log_message(self, *_args): pass
        static = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(ROOT / 'site')))
        origin = f'http://127.0.0.1:{static.server_port}'
        api = build_remote_server(research_root=f.research, engine_root=f.engine, token=token, origins=[origin])
        for server in (static, api): Thread(target=server.serve_forever, daemon=True).start()
        with TemporaryDirectory(prefix='axiom-remote-browser-') as temp:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
            chrome = subprocess.Popen([CHROME, '--headless=new', f'--remote-debugging-port={port}',
                f'--user-data-dir={temp}/profile', '--no-first-run', '--no-default-browser-check', 'about:blank'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ws = None
            try:
                for _ in range(100):
                    try:
                        tabs = json.load(urlopen(f'http://127.0.0.1:{port}/json', timeout=.3))
                        if tabs: break
                    except Exception: time.sleep(.1)
                ws = websocket.create_connection(next(t for t in tabs if t['type'] == 'page')['webSocketDebuggerUrl'],
                                                  timeout=15, suppress_origin=True)
                sequence = 0
                def call(method, params=None):
                    nonlocal sequence
                    sequence += 1; ws.send(json.dumps({'id':sequence, 'method':method, 'params':params or {}}))
                    while True:
                        answer = json.loads(ws.recv())
                        if answer.get('id') == sequence:
                            assert 'error' not in answer, answer
                            return answer.get('result', {})
                def js(expression):
                    result = call('Runtime.evaluate', {'expression':expression, 'returnByValue':True})
                    assert 'exceptionDetails' not in result, result
                    return result['result'].get('value')
                def wait(expression):
                    for _ in range(100):
                        if js(expression): return
                        time.sleep(.1)
                    raise AssertionError(expression + ': ' + str(js('document.body.innerText')))
                def connected(): wait("document.getElementById('status').textContent.includes('已连接')")
                def connect(value):
                    js("document.getElementById('endpoint').value=" + json.dumps(f'http://127.0.0.1:{api.server_port}') +
                       ";document.getElementById('token').value=" + json.dumps(value) +
                       ";document.getElementById('connect').requestSubmit()")
                def click(text):
                    js("Array.from(document.querySelectorAll('#results a')).find(a=>a.textContent.includes(" + json.dumps(text) + ")).click()")
                call('Page.navigate', {'url':origin + '/'})
                wait("!!document.getElementById('connect')")
                connect('x' * 43); wait("document.getElementById('status').textContent.includes('未授权')")
                assert js("document.getElementById('results').textContent") == ''
                evidence['unauthorized'] = True
                connect(token); connected()
                assert js("document.getElementById('token').value") == ''
                assert js("document.querySelectorAll('#results section').length") == 25
                click('下一页'); connected(); wait("document.getElementById('results').textContent.includes('第 2 / 2 页')")
                evidence['pagination'] = True
                js("document.getElementById('home').click()"); connected()
                # First result is selected through a real rendered link after paging to its location.
                while not js("!!document.querySelector('#results a[href=\"/result/" + f.first['result_id'][7:] + "\"]')"):
                    click('下一页'); connected()
                js("document.querySelector('#results a[href=\"/result/" + f.first['result_id'][7:] + "\"]').click()")
                connected(); wait("document.getElementById('results').textContent.includes('25%')")
                assert '/Users/' not in js("document.getElementById('results').textContent")
                click('账户曲线'); connected(); wait("!!document.querySelector('#results svg polyline')")
                text = js("document.getElementById('results').textContent")
                assert '1800 / 全账户 1800' in text and '600 / 区间原始点数 1800' in text, text
                evidence['full_range_curve'] = True
                (ROOT / 'reports' / 'remote-results-desktop.png').write_bytes(base64.b64decode(
                    call('Page.captureScreenshot', {'format':'png'})['data']))
                js("document.querySelector('#results input[name=start]').value='2019-02-01';document.querySelector('#results input[name=end]').value='2019-02-10';document.querySelector('#results form').requestSubmit()")
                connected(); wait("document.getElementById('results').textContent.includes('10 / 全账户 1800')")
                click('返回结果'); connected()
                js("Array.from(document.querySelectorAll('#results summary')).find(x=>x.textContent.includes('保存 Signal')).click()")
                click('信号评价'); connected(); wait("document.getElementById('results').textContent.includes('平均 IC')")
                assert '0.03' in js("document.getElementById('results').textContent")
                evidence['signal_table'] = True
                js("document.getElementById('home').click()"); connected()
                while not js("!!document.querySelector('#results a[href=\"/result/" + f.second['result_id'][7:] + "\"]')"):
                    click('下一页'); connected()
                js("document.querySelector('#results a[href=\"/result/" + f.second['result_id'][7:] + "\"]').click()")
                connected(); wait("document.getElementById('results').textContent.includes('第二个实验')")
                evidence['switch_experiment'] = True
                f.add('fresh-registration', 'q2', 'v3', reason='浏览器新增登记')
                js("document.getElementById('refresh').click()"); connected()
                wait("document.getElementById('results').textContent.includes('结果 27')")
                evidence['new_registration_refresh'] = True
                call('Emulation.setDeviceMetricsOverride', {'width':390, 'height':844, 'deviceScaleFactor':1, 'mobile':True})
                assert js('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), 'mobile overflow'
                output = ROOT / 'reports' / 'remote-results-mobile.png'
                output.write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format':'png'})['data']))
                evidence['mobile_width'] = 390
                api.shutdown(); api.server_close()
                js("document.getElementById('refresh').click()")
                wait("document.getElementById('status').textContent.includes('离线')")
                assert js("document.getElementById('results').textContent") == ''
                evidence['offline_clears_results'] = True
                evidence['no_persistent_browser_storage'] = js('localStorage.length === 0 && sessionStorage.length === 0')
            finally:
                if ws: ws.close()
                chrome.terminate(); chrome.wait(timeout=10)
                for server in (static, api): server.shutdown(); server.server_close()
    try: run_fixture(f, action)
    finally: f.doCleanups()
    (ROOT / 'reports' / 'remote-results-browser.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence))


if __name__ == '__main__': check()
