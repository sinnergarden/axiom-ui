"""Local Chrome smoke test of a tiny synthetic saved v6 account."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import urlopen
import json
import os
import socket
import subprocess
import time

import websocket

from test_stock_v6 import FIXTURE, saved_view


CHROME = os.environ.get("AXIOM_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def check():
    run = json.loads(FIXTURE.read_text())
    with TemporaryDirectory(prefix="axiom-v6-browser-") as temp:
        root = Path(temp)
        (root / "fixture.html").write_text(saved_view(run)[1])

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(root), **kwargs)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        Thread(target=server.serve_forever, daemon=True).start()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={port}",
                                   f"--user-data-dir={root / 'chrome'}", "--no-first-run",
                                   "--no-default-browser-check", "about:blank"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws = None
        try:
            for _ in range(100):
                try:
                    tabs = json.load(urlopen(f"http://127.0.0.1:{port}/json", timeout=.3))
                    if tabs:
                        break
                except Exception:
                    time.sleep(.1)
            else:
                raise AssertionError("Chrome CDP did not start")
            ws = websocket.create_connection(next(tab for tab in tabs if tab["type"] == "page")["webSocketDebuggerUrl"],
                                             timeout=20, suppress_origin=True)
            sequence = 0

            def call(method, params=None):
                nonlocal sequence
                sequence += 1
                ws.send(json.dumps({"id": sequence, "method": method, "params": params or {}}))
                while True:
                    answer = json.loads(ws.recv())
                    if answer.get("id") == sequence:
                        assert "error" not in answer, answer
                        return answer.get("result", {})

            def js(expression):
                response = call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
                assert "exceptionDetails" not in response, response
                return response["result"].get("value")

            call("Page.navigate", {"url": f"http://127.0.0.1:{server.server_port}/fixture.html"})
            for _ in range(100):
                try:
                    if js("document.getElementById('stock-account-scope')?.textContent.includes('未提交')"):
                        break
                except Exception:
                    pass
                time.sleep(.1)
            else:
                raise AssertionError("saved v6 context did not render")
            scope = js("document.getElementById('stock-account-scope').textContent")
            notice = js("document.getElementById('notice').textContent")
            refs = js("document.getElementById('stock-account-refs').textContent")
            assert all(label in scope for label in ("股", "未提交", "提交后未成交", "生命周期")), scope
            assert "上市前缺值 0" not in scope, scope
            assert "合成验收样例" in notice and "日线事后近似" in notice, notice
            assert run["stock_execution_rules_ref"] in refs and '"quantity_rules"' not in refs, refs
            js("document.querySelector('[data-pane=trade]').click()")
            for selector in (".chain-year", ".chain-month", ".chain-batch", ".chain-security"):
                js(f"(()=>{{const d=document.querySelector('{selector}');if(d){{d.open=true;d.dispatchEvent(new Event('toggle'));}}}})()")
            chain = js("document.getElementById('event-list').textContent")
            assert all(label in chain for label in ("请求（股）", "已提交（股）", "未提交（股）",
                                               "已成交（股）", "提交后未成交（股）")), chain
            return {"status": "PASS", "synthetic": True, "stock_units": True,
                    "five_saved_quantities": True, "lifecycle": True}
        finally:
            if ws is not None:
                ws.close()
            chrome.terminate()
            chrome.wait(timeout=10)
            server.shutdown()


if __name__ == "__main__":
    print(json.dumps(check(), ensure_ascii=False))
