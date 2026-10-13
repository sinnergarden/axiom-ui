"""Local real-reader Chrome acceptance; roots supplied privately by environment.

Writes only outcome booleans/counts. Never writes a screenshot, result HTML,
credentials or local owner paths into the repository.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import urlopen
import json
import os
import secrets
import socket
import subprocess
import time
import websocket

from axiom_ui.remote_results import build_remote_server

ROOT = Path(__file__).resolve().parents[1]


def check():
    token = secrets.token_urlsafe(32)
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *_args): pass
    static = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(ROOT / 'site')))
    origin = f'http://127.0.0.1:{static.server_port}'
    api = build_remote_server(research_root=os.environ['AXIOM_RESEARCH_ROOT'],
        engine_root=os.environ['AXIOM_ENGINE_ROOT'], token=token, origins=[origin])
    for server in (static, api): Thread(target=server.serve_forever, daemon=True).start()
    evidence = {'scope': 'local Chrome cross-origin shell with formal read-only owner Readers; not deployed Pages'}
    with TemporaryDirectory(prefix='axiom-formal-browser-') as temp:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
        chrome = subprocess.Popen(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '--headless=new', f'--remote-debugging-port={port}', f'--user-data-dir={temp}/profile',
            '--no-first-run', '--no-default-browser-check', 'about:blank'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws = None
        try:
            for _ in range(100):
                try:
                    tabs = json.load(urlopen(f'http://127.0.0.1:{port}/json', timeout=.3))
                    if tabs: break
                except Exception: time.sleep(.1)
            ws = websocket.create_connection(next(t for t in tabs if t['type'] == 'page')['webSocketDebuggerUrl'],
                                              timeout=30, suppress_origin=True)
            sequence = 0
            def call(method, params=None):
                nonlocal sequence
                sequence += 1; ws.send(json.dumps({'id':sequence, 'method':method, 'params':params or {}}))
                while True:
                    answer = json.loads(ws.recv())
                    if answer.get('id') == sequence:
                        assert 'error' not in answer, 'CDP command failed'
                        return answer.get('result', {})
            def js(expression):
                result = call('Runtime.evaluate', {'expression':expression, 'returnByValue':True})
                assert 'exceptionDetails' not in result, 'browser expression failed'
                return result['result'].get('value')
            def wait(expression):
                for _ in range(300):
                    if js(expression): return
                    time.sleep(.1)
                raise AssertionError('expected browser state not reached: ' + expression)
            def connected(): wait("document.getElementById('status').textContent.includes('已连接')")
            call('Page.navigate', {'url':origin + '/'})
            wait("!!document.getElementById('connect')")
            js("document.getElementById('endpoint').value=" + json.dumps(f'http://127.0.0.1:{api.server_port}') +
               ";document.getElementById('token').value=" + json.dumps(token) +
               ";document.getElementById('connect').requestSubmit()")
            connected()
            evidence['formal_result_count'] = js("document.querySelectorAll('#results section').length")
            links = js("Array.from(document.querySelectorAll('#results section')).filter(s=>s.textContent.includes('COMPLETE')).map(s=>s.querySelector('a').getAttribute('href'))")
            account_counts = []
            for link in links:
                js("document.querySelector('#results a[href=\"" + link + "\"]').click()")
                connected(); wait("document.querySelector('#results h2')?.textContent.includes('策略账户')")
                text = js("document.getElementById('results').textContent")
                assert '/Users/' not in text and '指标暂不展示' not in text
                assert '保存产物与完整引用' not in text
                count = js("document.querySelectorAll('#results a[href*=\"/account/\"]').length")
                account_counts.append(count)
                if count == 5:
                    assert 'Top 10' in text and '保留前 20' in text
                    evidence['top10_keep20_visible'] = True
                    js("document.querySelector('#results a[href*=\"/account/\"]').click()")
                    connected(); wait("!!document.querySelector('#results svg polyline')")
                    curve = js("document.getElementById('results').textContent")
                    assert '评价报告保存净值' in curve and '1699 / 全账户 1699' in curve
                    evidence['formal_curve_points'] = 1699
                    evidence['curve_reads_evaluation_leaf_only'] = True
                    js("document.querySelector('#results a').click()"); connected()
                    js("Array.from(document.querySelectorAll('#results summary')).find(x=>x.textContent.includes('保存 Signal')).click()")
                    js("document.querySelector('#results a[href*=\"/signal/\"]').click()")
                    connected(); wait("document.getElementById('results').textContent.includes('平均 IC')")
                    assert '摘要不可用' not in js("document.getElementById('results').textContent")
                    evidence['formal_signal_metrics'] = True
                js("document.getElementById('home').click()"); connected()
            evidence['formal_complete_account_counts'] = sorted(account_counts)
            evidence['no_persistent_browser_storage'] = js('localStorage.length === 0 && sessionStorage.length === 0')
            js("document.getElementById('disconnect').click()")
            evidence['disconnect_clears_results'] = js("document.getElementById('results').textContent === ''")
        finally:
            if ws: ws.close()
            chrome.terminate(); chrome.wait(timeout=10)
            for server in (static, api): server.shutdown(); server.server_close()
    (ROOT / 'reports' / 'remote-results-formal-browser.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence))


if __name__ == '__main__': check()
