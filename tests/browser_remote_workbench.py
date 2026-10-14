"""Isolated synthetic browser acceptance; never loads formal data or credentials."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import urlopen
from unittest.mock import patch
import base64
import json
import secrets
import shutil
import socket
import subprocess
import time
import websocket

from axiom_ui.remote_results import build_remote_server
from axiom_ui.remote_password import password_record
from axiom_ui.workbench import render_sample_workbench, _render
from test_workbench import payload
from remote_fixture import fixture, run_fixture

ROOT = Path(__file__).resolve().parents[1]
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


def check(*, decision_only=False, market_only=False):
    sample = json.loads((ROOT / 'examples/synthetic_workbench.json').read_text())
    views = payload(render_sample_workbench(sample))['views']
    # _render serializes saved integers to strings; restore the original render
    # is not needed here: browser acceptance consumes precisely that wire shape.
    for i, view in enumerate(views):
        view['view_id'] = str(i + 1) * 64 + ':0'
        view['remote_selection'] = view['view_id']
        view['research']['question_id'] = 'synthetic-idea-' + str(i)
        view['research']['title'] = '合成验收主题 ' + str(i + 1)
        view['account_title'] = '合成策略 ' + str(i + 1)
    if decision_only:
        d=views[0]['run']['decisions'][0]; sid=d['intents'][0]['security_id']
        d.update(targets={sid:33800},signal_ref='synthetic-signal',strategy_targets={'selected_security_ids':[sid],'target_weights':{sid:'0.2'}},trace=[{'reason':'RANK_BUFFER_KEEP','security_ids':[sid],'keep_rank':10},{'reason':'COMPOSED_STOCK_STRATEGY','score_semantics':'forward_40_session_cs_zscore_prediction'}])
        d['intents'][0].update(side='SELL',quantity=200)
        def score(catalog,selected,day,security):
            assert selected==views[0]['view_id'] and day==d['trade_session'] and security==sid
            return dict(feature_session=d['feature_session'],security_id=sid,signal_ref=d['signal_ref'],score='0.375',score_unit='dimensionless',rank=None,valid=True,member=True)
    if market_only:
        v=views[0];v['market']['display_available']=True
        def market(catalog,selected,security):
            assert selected==v['view_id']
            sessions=[r['session'] for r in v['run']['nav']]
            return dict(run_id=v['run']['run_id'],security_id=security,name='合成证券名称',label_notice='保存观察名称 · 历史名称有效期未知',context={'snapshot_id':'synthetic'},field_meta={},
                records=[dict(security_id=security,session=day,open=10+i,high=12+i,low=9+i,close=11+i,
                    native_open=10+i,native_high=12+i,native_low=9+i,native_close=11+i,
                    volume_shares=1000,volume_units=1000,amount_cny=11000) for i,day in enumerate(sessions)])
    def render(catalog, selected=None, compare=None):
        selected = selected or views[0]['view_id']
        return _render(views, None, remote={'selected': selected, 'compare': compare or ''})
    f = fixture()
    secret = secrets.token_urlsafe(12)
    evidence = {'fixture': 'synthetic; isolated Chrome profile; no private results or credentials persisted'}
    def action():
        with TemporaryDirectory(prefix='axiom-workbench-browser-') as temp:
            site = Path(temp) / 'site'
            shutil.copytree(ROOT / 'site', site)
            class Quiet(SimpleHTTPRequestHandler):
                def log_message(self, *_): pass
            static = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(site)))
            origin = f'http://127.0.0.1:{static.server_port}'
            api = build_remote_server(research_root=f.research, engine_root=f.engine,
                origins=[origin], password_record=password_record(secret))
            (site / 'config.js').write_text(f"window.AXIOM_RESULTS_ENDPOINT = 'http://127.0.0.1:{api.server_port}';")
            for server in (static, api): Thread(target=server.serve_forever, daemon=True).start()
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
            chrome = subprocess.Popen([CHROME, '--headless=new', f'--remote-debugging-port={port}',
                f'--user-data-dir={temp}/profile', '--no-first-run', '--no-default-browser-check', 'about:blank'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ws = None
            try:
                for _ in range(100):
                    try:
                        tabs=json.load(urlopen(f'http://127.0.0.1:{port}/json',timeout=.3))
                        if tabs: break
                    except Exception: time.sleep(.1)
                ws=websocket.create_connection(next(t for t in tabs if t['type']=='page')['webSocketDebuggerUrl'],timeout=20,suppress_origin=True)
                sequence=0; contexts={}; errors=[]; attached={}
                def call(method, params=None, session=None):
                    nonlocal sequence
                    sequence+=1; message={'id':sequence,'method':method,'params':params or {}}
                    if session: message['sessionId']=session
                    ws.send(json.dumps(message))
                    while True:
                        answer=json.loads(ws.recv())
                        if answer.get('method')=='Runtime.executionContextCreated':
                            context=answer['params']['context'];contexts[context['id']]=context
                        if answer.get('method')=='Runtime.executionContextDestroyed':
                            contexts.pop(answer['params']['executionContextId'],None)
                        if answer.get('method')=='Log.entryAdded': print('browser log',answer['params']['entry']['text'][:350],flush=True)
                        if answer.get('method')=='Runtime.exceptionThrown': errors.append(answer['params']['exceptionDetails'].get('exception',{}).get('description',answer['params']['exceptionDetails'].get('text')))
                        if answer.get('id')==sequence:
                            assert 'error' not in answer, answer
                            return answer.get('result',{})
                call('Runtime.enable');call('Page.enable');call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1100,'deviceScaleFactor':1,'mobile':False})
                def js(expression, inside=False):
                    params={'expression':expression,'returnByValue':True}
                    session=None
                    if inside:
                        targets=call('Target.getTargets')['targetInfos']
                        target=next((target for target in targets if target['type']=='iframe'),None)
                        if target:
                            targetid=target['targetId']
                            if targetid not in attached:
                                attached[targetid]=call('Target.attachToTarget',{'targetId':targetid,'flatten':True})['sessionId']
                                call('Runtime.enable',session=attached[targetid]);call('Log.enable',session=attached[targetid])
                            session=attached[targetid]
                        else:
                            frames=call('Page.getFrameTree')['frameTree'].get('childFrames',[])
                            assert frames, 'workbench frame not loaded'
                            frameid=frames[0]['frame']['id']
                            matches=[k for k,c in contexts.items() if c.get('auxData',{}).get('frameId')==frameid and c.get('auxData',{}).get('isDefault')]
                            assert matches, 'frame execution context not ready'
                            params['contextId']=matches[-1]
                    try:
                        result=call('Runtime.evaluate',params,session=session)
                    except AssertionError:
                        if not session:raise
                        attached.pop(targetid,None)
                        return js(expression,inside)
                    assert 'exceptionDetails' not in result, result.get('exceptionDetails')
                    return result['result'].get('value')
                def wait(expression, inside=False):
                    for _ in range(100):
                        try:
                            if js(expression,inside):return
                        except AssertionError:pass
                        time.sleep(.1)
                    print('frame diagnostics',js("JSON.stringify({chart:document.querySelector('#performance-chart')?.outerHTML.slice(0,700),echarts:typeof echarts,body:document.body.innerText.slice(-900)})",True),flush=True)
                    Path('/tmp/axiom-remote-workbench-synthetic-debug.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png'})['data']))
                    raise AssertionError(expression+'; errors='+str(errors))
                call('Page.navigate',{'url':origin+'/'})
                wait("!!document.getElementById('connect')")
                def connect(value):
                    js("document.getElementById('token').value="+json.dumps(value)+";document.getElementById('connect').requestSubmit()")
                connect('incorrect');wait("document.getElementById('status').textContent.includes('不正确')")
                evidence['wrong_password']=True
                connect(secret);wait("document.getElementById('status').textContent.includes('已连接')")
                wait("!!document.getElementById('performance-chart')",True)
                js("document.getElementById('performance-chart').scrollIntoView()",True)
                wait("!!document.querySelector('#performance-chart canvas')",True)
                assert js("document.querySelectorAll('.tabs button').length",True)==3
                assert js("document.querySelectorAll('.question-group').length",True)>=2
                assert js("document.getElementById('token').value")==''
                assert js("document.querySelector('#token').autocomplete")=='current-password'
                assert not js("document.body.innerText.includes('HTTPS 地址')")
                evidence['original_three_tabs_and_echarts']=True
                js("document.querySelector('[data-pane=trade]').click()",True)
                wait("document.getElementById('trade').classList.contains('active')",True)
                assert js("document.querySelectorAll('#event-list button').length",True)>0
                if market_only:
                    wait("document.getElementById('trade-security-title').innerText.includes('合成证券名称')",True)
                    wait("!!echarts.getInstanceByDom(document.getElementById('trade-chart'))",True)
                    assert js("echarts.getInstanceByDom(document.getElementById('trade-chart')).getOption().series[0].type",True)=='candlestick'
                    assert js("echarts.getInstanceByDom(document.getElementById('trade-chart')).getOption().series[0].data.length",True)==len(views[0]['run']['nav'])
                    assert js("document.getElementById('price-basis-select').value",True)=='unadjusted'
                    js("echarts.getInstanceByDom(document.getElementById('trade-chart')).dispatchAction({type:'showTip',seriesIndex:0,dataIndex:1})",True)
                    assert not errors,errors
                    evidence.update(bound_market_channel=True,true_ohlcv_candles=True,observed_name_notice=True,native_default=True,runtime_errors=errors)
                    return
                if decision_only:
                    for _ in range(4):
                        js("document.querySelectorAll('#event-list details').forEach(e=>e.open=true)",True)
                        time.sleep(.1)
                    wait("document.querySelector('#event-list').innerText.includes('读取此证券保存的模型分数')",True)
                    assert js("document.querySelector('#event-list').innerText.includes('保留阈值：前 10 名')",True)
                    assert js("document.querySelector('#event-list').innerText.includes('仍被选中')",True)
                    js("[...document.querySelectorAll('#event-list button')].find(e=>e.textContent==='读取此证券保存的模型分数').click()",True)
                    wait("document.querySelector('#event-list').innerText.includes('0.375')",True)
                    assert js("document.querySelector('#event-list').innerText.includes('未保存精确排名')",True)
                    assert js('sessionStorage.length')==0
                    assert not errors,errors
                    evidence.update(decision_evidence_authenticated_message_channel=True,scoped_keep_sell_chinese=True,stored_score=True,no_invented_rank=True,runtime_errors=errors)
                    return
                js("document.querySelector('[data-pane=statistics]').click()",True)
                wait("document.getElementById('statistics').classList.contains('active')",True)
                assert js("document.getElementById('month-heatmap').children.length",True)>0
                evidence['trade_and_monthly_replay']=True
                js("document.querySelector('[data-pane=performance]').click()",True)
                js("const c=echarts.getInstanceByDom(document.getElementById('performance-chart'));c.dispatchAction({type:'dataZoom',start:20,end:80});c.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:1})",True)
                assert js("!!echarts.getInstanceByDom(document.getElementById('performance-chart'))",True)
                evidence['chart_zoom_tooltip']=True
                other=views[1]['view_id']
                js("document.getElementById('compare-run').value="+json.dumps(other)+";document.getElementById('compare-run').dispatchEvent(new Event('change'))",True)
                wait("document.getElementById('compare-run').value==="+json.dumps(other),True)
                js("document.getElementById('save-baseline').click()",True)
                wait("localStorage.length===1")
                assert js('JSON.stringify(localStorage)') .find(secret)==-1
                evidence['cross_idea_explicit_baseline']=True
                js("document.getElementById('disconnect').click()")
                wait("document.getElementById('workbench').hidden")
                assert js("document.getElementById('workbench').hasAttribute('srcdoc')")==False
                connect(secret);wait("document.getElementById('compare-run').value==="+json.dumps(other),True)
                evidence['baseline_survives_login']=True
                wait("document.getElementById('performance-chart').dataset.chartReady==='true'",True)
                call('Emulation.setDeviceMetricsOverride',{'width':1600,'height':1200,'deviceScaleFactor':1,'mobile':False})
                js('window.scrollTo(0,0)',True)
                (ROOT/'reports'/'remote-workbench-synthetic-desktop.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png'})['data']))
                call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
                assert js('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
                wait('document.documentElement.scrollWidth<=document.documentElement.clientWidth',True)
                evidence['mobile_390_no_overflow']=True
                assert js('sessionStorage.length')==0
                evidence['no_persistent_credentials']=True
                evidence['runtime_errors']=errors
                assert not errors, errors
                (ROOT/'reports'/'remote-workbench-synthetic-mobile.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png'})['data']))
            finally:
                if ws:ws.close()
                chrome.terminate();chrome.wait(timeout=10)
                for server in (static,api):server.shutdown();server.server_close()
    try:
        with patch('axiom_ui.remote_workbench.render_remote_workbench',render):
            if decision_only:
                with patch('axiom_ui.remote_workbench.decision_evidence',score):run_fixture(f,action)
            elif market_only:
                with patch('axiom_ui.remote_workbench.market_display',market):run_fixture(f,action)
            else:run_fixture(f,action)
    finally:f.doCleanups()
    (ROOT/'reports'/('market-display-browser.json' if market_only else 'decision-evidence-browser.json' if decision_only else 'remote-workbench-browser.json')).write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(evidence,ensure_ascii=False))


if __name__=='__main__':
    import sys
    check(decision_only='--decision-only' in sys.argv, market_only='--market-only' in sys.argv)
