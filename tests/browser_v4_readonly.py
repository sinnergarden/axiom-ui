"""Local Chrome smoke check of a handwritten v4 UI fixture; no Owner execution."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
from urllib.request import urlopen
from types import ModuleType
import json
import os
import socket
import subprocess
import sys
import time

import websocket

from axiom_ui import render_saved_workbench
from test_workbench import SAMPLE, saved_stock_v4_display_case


CHROME = os.environ.get("AXIOM_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def page():
    run, evaluation, _ = saved_stock_v4_display_case(json.loads(SAMPLE.read_text()))
    runtime = ModuleType("axiom_engine.runtime")
    runtime.load_backtest_run = lambda _path: run
    runtime.load_backtest_evaluation = lambda _path: evaluation
    with patch.dict(sys.modules, {"axiom_engine.runtime": runtime}):
        return render_saved_workbench(["synthetic-v4.json"],
                                      evaluation_paths=["synthetic-evaluation.json"],
                                      synthetic_run_ids=[run["run_id"]])


def check():
    with TemporaryDirectory(prefix="axiom-v4-browser-") as temp:
        root = Path(temp)
        (root / "fixture.html").write_text(page())
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
            call("Page.enable")
            call("Page.navigate", {"url": f"http://127.0.0.1:{server.server_port}/fixture.html"})
            for _ in range(100):
                try:
                    if js("document.getElementById('stock-account-refs')?.textContent.includes('synthetic:schedule')"):
                        break
                except Exception:
                    pass
                time.sleep(.1)
            else:
                raise AssertionError("saved v4 context did not render")
            result = js("""(()=>({hidden:document.getElementById('stock-account-context').hidden,
                scope:document.getElementById('stock-account-scope').textContent,
                refs:document.getElementById('stock-account-refs').textContent,
                notice:document.getElementById('notice').textContent}))()""")
            assert result["hidden"] is False, result
            assert "股" in result["scope"] and "元/股" in result["scope"], result
            assert "synthetic:schedule" in result["refs"] and "synthetic:signal-1" in result["refs"], result
            assert "synthetic:signal-2" in result["refs"] and "2024-01-03" in result["refs"], result
            assert "合成验收样例" in result["notice"], result
            assert "private prediction" not in result["refs"] and "parameters" not in result["refs"], result
            return {"status": "PASS", "stock_units": True, "schedule_and_original_folds": True,
                    "synthetic_notice": True}
        finally:
            try:
                if ws is not None:
                    ws.close()
            finally:
                try:
                    if chrome.poll() is None:
                        chrome.terminate()
                        try:
                            chrome.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            chrome.kill()
                            chrome.wait(timeout=5)
                finally:
                    try:
                        server.shutdown()
                    finally:
                        server.server_close()


if __name__ == "__main__":
    print(json.dumps(check(), ensure_ascii=False))
