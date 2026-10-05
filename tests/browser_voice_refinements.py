"""Bounded Chrome review of a handwritten UI fixture; no Owner run is executed.

Run from the repository root with PYTHONPATH=src python tests/browser_voice_refinements.py.
Requires the local Mac Chrome and the already available websocket-client package.
"""

from contextlib import closing
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import urlopen
import json
import os
import re
import socket
import subprocess
import time

import websocket

from axiom_ui import render_sample_workbench
from axiom_ui.workbench import _render


ROOT = Path(__file__).resolve().parents[1]
CHROME = os.environ.get("AXIOM_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def synthetic_page():
    sample = json.loads((ROOT / "examples/synthetic_workbench.json").read_text())
    html = render_sample_workbench(sample, generated_at="2026-10-05T00:00:00Z")
    wire = json.loads(re.search(r'<script type="application/json" id="workbench-data">(.*?)</script>', html, re.S)[1])
    baseline, comparison = wire["views"][:2]
    baseline["research"].update(version_label="零滑点基线", created_at="2026-10-05T00:00:00Z")
    comparison["research"].update(question_id="synthetic:other-question", title="合成对照主题",
                                  version_label="非零滑点对照", created_at="2026-10-04T00:00:00Z")
    for view, slippage, commission in ((baseline, "0", "0.0003"), (comparison, "5", "0.0005")):
        view["configuration"]["profile"].update(slippage_bps=slippage, commission_rate=commission,
                                                    minimum_commission_minor="500")
    baseline["evaluation"]["risk_metrics"] = {
        "sharpe": {"status": "AVAILABLE", "value": "0.73462", "risk_free": {
            "annual_effective_rate": "0", "currency": "CNY", "source": "EXPLICIT_ZERO_ASSUMPTION"}},
        "calmar": {"status": "AVAILABLE", "value": "0.56123"},
    }
    comparison["evaluation"]["risk_metrics"] = {
        "sharpe": {"status": "INSUFFICIENT_SPAN", "value": None, "risk_free": {
            "annual_effective_rate": "0", "currency": "CNY", "source": "EXPLICIT_ZERO_ASSUMPTION"}},
        "calmar": {"status": "INSUFFICIENT_SPAN", "value": None},
    }
    for view in (baseline, comparison):
        points = view["evaluation"]["benchmark"]["series"]
        view["evaluation"]["benchmark_comparisons"] = {
            "CSI300": {"status": "COMPLETE", "currency": "CNY", "return_basis": "price_index_excluding_dividends",
                       "series": [{"account_session": p["session"], "normalized_index": p["nav_index"],
                                   "benchmark_cumulative_return": "0.01", "account_relative_wealth": "0.01"}
                                  for p in points]},
            "SSE_COMPOSITE": {"status": "COMPLETE", "currency": "CNY", "return_basis": "price_index_excluding_dividends",
                              "series": [{"account_session": p["session"], "normalized_index": p["nav_index"],
                                          "benchmark_cumulative_return": "0.02", "account_relative_wealth": "0.02",
                                          "drawdown": "-0.5"} for p in points]},
        }
    return _render([baseline, comparison], wire["generated_at"])


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def review(output):
    with TemporaryDirectory(prefix="axiom-voice-browser-") as temp:
        folder = Path(temp)
        (folder / "fixture.html").write_text(synthetic_page())
        handler = lambda *args, **kwargs: Handler(*args, directory=str(folder), **kwargs)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        Thread(target=server.serve_forever, daemon=True).start()
        with closing(socket.socket()) as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            debug_port = port_socket.getsockname()[1]
        chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={debug_port}",
                                   f"--user-data-dir={folder / 'chrome'}", "--no-first-run",
                                   "--no-default-browser-check", "about:blank"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws = None
        try:
            for _ in range(100):
                try:
                    tabs = json.load(urlopen(f"http://127.0.0.1:{debug_port}/json", timeout=.3))
                    if tabs:
                        break
                except Exception:
                    time.sleep(.1)
            else:
                raise AssertionError("Chrome CDP did not start")
            ws = websocket.create_connection(next(tab for tab in tabs if tab["type"] == "page")["webSocketDebuggerUrl"],
                                             timeout=20, suppress_origin=True)
            request_id = 0
            events = []

            def call(method, params=None):
                nonlocal request_id
                request_id += 1
                ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
                while True:
                    message = json.loads(ws.recv())
                    if message.get("id") == request_id:
                        assert "error" not in message, (method, message["error"])
                        return message.get("result", {})
                    events.append(message)

            def js(expression):
                result = call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
                assert "exceptionDetails" not in result, result.get("exceptionDetails")
                return result["result"].get("value")

            def check_group(return_id, drawdown_id, label):
                result = js("""(()=>{const c=echarts.getInstanceByDom(document.getElementById('performance-chart'));
                    const pair=c.getOption().series.filter(s=>['%s','%s'].includes(s.id));
                    const name=pair[0].name;c.dispatchAction({type:'legendToggleSelect',name});
                    return {ids:pair.map(s=>s.id),names:pair.map(s=>s.name),selected:c.getOption().legend[0].selected[name],
                        tooltip:c.getOption().tooltip[0].formatter([{axisValue:'2026-03-30'}])};})()""" % (return_id, drawdown_id))
                assert result["ids"] == [return_id, drawdown_id], result
                assert len(set(result["names"])) == 1 and result["selected"] is False, result
                assert label not in result["tooltip"], result
                return result

            call("Page.enable")
            call("Runtime.enable")
            call("Network.enable")
            call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1000,
                                                       "deviceScaleFactor": 1, "mobile": False})
            call("Page.navigate", {"url": f"http://127.0.0.1:{server.server_port}/fixture.html"})
            for _ in range(100):
                try:
                    if js("document.getElementById('performance-chart')?.dataset.chartReady==='true'"):
                        break
                except Exception:
                    pass
                time.sleep(.1)
            else:
                raise AssertionError("synthetic workbench did not render")
            initial = js("""({topics:[...document.querySelectorAll('#run-tree details.question-group')].map(x=>x.open),
                config:document.getElementById('configuration-summary').innerText,
                metrics:document.getElementById('metrics').innerText,
                options:[...document.querySelectorAll('#compare-run option')].map(x=>x.textContent)})""")
            assert initial["topics"] == [True, False], initial
            assert "未启用 · 0 bp" in initial["config"] and "0.03%" in initial["config"], initial
            assert "0.73462" in initial["metrics"] and "0.56123" in initial["metrics"], initial
            assert any("非零滑点对照" in item and "5 bp" in item for item in initial["options"]), initial
            account = check_group("account", "drawdown", "策略")
            benchmark = check_group("benchmark", "benchmark-dd", "沪深300")
            comparison = js("""(()=>{const s=document.getElementById('compare-run');s.value='synthetic:run-v1';
                s.dispatchEvent(new Event('change',{bubbles:true}));return s.value})()""")
            assert comparison == "synthetic:run-v1"
            compared = check_group("comparison", "comparison-dd", "对照")
            comparison_reset = js("""(()=>{const s=document.getElementById('compare-run');s.value='';
                s.dispatchEvent(new Event('change',{bubbles:true}));s.value='synthetic:run-v1';
                s.dispatchEvent(new Event('change',{bubbles:true}));const c=echarts.getInstanceByDom(document.getElementById('performance-chart'));
                return c.getOption().legend[0].selected[c.getOption().series.find(x=>x.id==='comparison').name]})()""")
            assert comparison_reset is True
            sse = js("""(()=>{const s=document.getElementById('benchmark-select');s.value='SSE_COMPOSITE';
                s.dispatchEvent(new Event('change',{bubbles:true}));const c=echarts.getInstanceByDom(document.getElementById('performance-chart'));
                return {selected:s.value,series:c.getOption().series.filter(x=>x.id.startsWith('benchmark')).map(x=>x.id),
                    visible:c.getOption().legend[0].selected[c.getOption().series.find(x=>x.id==='benchmark').name],
                    note:document.getElementById('benchmark-source-note').textContent};})()""")
            assert sse["selected"] == "SSE_COMPOSITE" and sse["series"] == ["benchmark"], sse
            assert sse["visible"] is True and "尚无正式可读序列" in sse["note"], sse
            switched = js("""(()=>{const group=[...document.querySelectorAll('#run-tree details.question-group')][1];
                group.querySelector('summary').click();group.querySelector('.run-item').click();
                const c=echarts.getInstanceByDom(document.getElementById('performance-chart'));
                return {topics:[...document.querySelectorAll('#run-tree details.question-group')].map(x=>x.open),
                    config:document.getElementById('configuration-summary').innerText,
                    metrics:[...document.querySelectorAll('#metrics .metric span:first-child')].map(x=>x.innerText),
                    legend:c.getOption().legend[0].selected,compare:document.getElementById('compare-run').value};})()""")
            assert switched["topics"][1] is True and switched["compare"] == "", switched
            assert "已启用 · 5 bp" in switched["config"] and "0.05%" in switched["config"], switched
            assert "Sharpe" not in switched["metrics"] and "Calmar" not in switched["metrics"], switched
            assert all(value is True for value in switched["legend"].values()), switched
            errors = [event for event in events if event.get("method") == "Runtime.exceptionThrown"]
            requests = [event.get("params", {}).get("request", {}).get("url", "") for event in events
                        if event.get("method") == "Network.requestWillBeSent"]
            external = [url for url in requests if not url.startswith((f"http://127.0.0.1:{server.server_port}/", "about:", "data:"))]
            assert not errors and not external, {"errors": errors, "external": external}
            output.mkdir(parents=True, exist_ok=True)
            js("document.getElementById('configuration-summary').scrollIntoView({block:'center'})")
            shots = []
            for name in ("synthetic-nonzero-config.png",):
                import base64
                target = output / name
                target.write_bytes(base64.b64decode(call("Page.captureScreenshot", {"format": "png"})["data"]))
                shots.append(str(target))
            report = {"status": "PASS", "fixture": "handwritten synthetic UI only", "groups_hidden": ["account", "benchmark", "comparison"],
                      "topic_switch": True, "zero_and_nonzero_config": True, "risk_available_and_insufficient": True,
                      "sse_drawdown_contract_not_assumed": True, "runtime_exceptions": len(errors),
                      "external_requests": len(external), "screenshots": shots}
            (output / "browser-voice-refinements.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            return report
        finally:
            try:
                if ws:
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
                    server.shutdown()
                    server.server_close()


if __name__ == "__main__":
    print(json.dumps(review(Path("/tmp/axiom-ui-voice-delta-20261005")), ensure_ascii=False))
