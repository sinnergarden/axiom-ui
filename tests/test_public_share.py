import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from axiom_ui.public_share import (clean, project_view, export_result,
    _V4_PUBLIC_EVALUATION, _schema_field_names, V4_PUBLIC_KEYS)


def saved_view():
    return {'view_id':'sha256:run','evidence_kind':'saved_backtest_output','approximate':True,'blocked':False,
            'run':{'contract_version':'backtest_run_v3','run_id':'sha256:run','content_digest':'sha256:owner',
                   'committed_sequence':'7','metrics':{'total_return':'-0.078636','total_fees_minor':'780'},
                   'nav':[{'session':'2024-01-02','nav_minor':'999220','nav_index':'0.99922'}],
                   'positions':[{'security_id':'A','session':'2024-01-02','quantity':'100'}],
                   'fills':[{'security_id':'A','session':'2024-01-02','quantity':'100','price':'10.05',
                             'fee_minor':'780','source_refs':['sha256:source']}],
                   'orders':[],'decisions':[],'limitations':['saved daily approximation'],
                   'quantity_unit':'shares','price_unit':'CNY/share'},
            'configuration':{'start_session':'2024-01-02','end_session':'2024-01-02','profile':{'lot_size':'100'}},
            'market':{'rows':[{'security_id':'A','session':'2024-01-02','close':'10.01','open':'10.02',
                               'volume_shares':'1000'},
                              {'security_id':'UNRELATED','session':'2024-01-02','close':'99','volume_shares':'400'}],
                      'data_batch':{'records':['private raw data']},'native_chart':{'field_meta':{'by_key':['large proof']}},
                      'source_evidence':[{'path':'/Users/example/input.json'}],'price_basis':'unadjusted'},
            'stock_context':{'model_snapshot':'snapshot','execution_snapshot':'snapshot'},
            'research':{'title':'fixed experiment','hypothesis':'saved assumption','output_refs':[{'locator':'file:///Users/example/result'}],
                        'parameters':{'private':'unrelated'},'outcome':'saved at /Users/example/result.json'},
            'stock_ml':{'definition':{'private':'inputs'}},'research_versions':{'version':{'input_refs':[]}},
            'registration_history':[{'record':{'locator':'file:///Users/example/input'}}],
            'comparison_conditions':[{'key':'query.knowledge_time','value':{'cutoff_by_session':{'date':'large'}}},
                                     {'key':'profile.lot_size','value':'100'}],
            'evaluation':{'input_run_ref':{'run_id':'sha256:run','content_digest':'sha256:owner','committed_sequence':'7'},
                          'episode_metrics':{'win_rate':None,'dividend_scope_status':'OBSERVED_RECORDS_ONLY'},
                          'period_metrics':{'account':{'cagr':None,'cagr_status':'INSUFFICIENT_SPAN'}},
                          'benchmark_input':{'source_evidence':['large']},'dividend_scope':{'actions':['raw']}}}


class PublicProjectionTests(unittest.TestCase):
    def test_etf_v5_selected_policy_split_and_grid_are_narrow(self):
        value = saved_view()
        ref = 'sha256:' + 'a'*64
        run = value['run']
        run.update(contract_version='backtest_run_v5', quantity_unit='fund units',
                   price_unit='CNY/fund unit', signal_ref=ref, portfolio_policy_ref=ref,
                   unit_split_applications=[{'event_id':'split:A','security_id':'A',
                       'session':'2024-01-02','status':'APPLIED','sequence':7,
                       'rounding_extra_fraction':{'numerator':'0','denominator':'1'},
                       'original_quote':{'session':'2024-01-02','price':'10.05',
                                         'source_refs':[ref]},
                       'normalized_quote':{'session':'2024-01-02','price':'2.01',
                                           'source_refs':[ref]}, 'source_refs':[ref]}])
        run['positions'][0]['mark_basis_event_id'] = 'split:A'
        run['fills'][0].update(raw_slipped_price='10.0501', price_tick='0.001',
                               price_grid_ref=ref, price_rounding='HALF_UP',
                               rounding_delta='-0.0001', effective_slippage_bps='5',
                               source_refs=[ref])
        run['orders'] = [{'security_id':'A','session':'2024-01-02',
                          'announced_suspension_event_ids':['split:A'],
                          'raw_slipped_price':'10.0501','price_grid_ref':ref}]
        value['configuration']['portfolio_policy'] = {
            'contract_version':'etf_rotation_policy_v1','schedule':'weekly_first_trading_session'}
        value['configuration']['profile'].update(price_grid_ref=ref,
            price_grid_policy='etf_price_grid_v1', price_limit_policy='require_both', tax_rate='0',
            price_grid={'sources':[{'url':'https://private.example/grid'}]})
        value['comparison_conditions'].append({'key':'profile.extra','provided':True,
            'value':{'price_grid':value['configuration']['profile']['price_grid'],
                     'price_grid_ref':ref}})
        value['market']['unit_splits'] = [
            {'event':{'event_id':'split:A','security_id':'A','event_type':'split',
                      'document_refs':[{'url':'https://private.example/source'}]},
             'source_refs':[ref]},
            {'event':{'event_id':'unrelated','security_id':'UNRELATED'},'source_refs':[ref]}]
        value['market']['source_refs'] = [ref]
        original = deepcopy(value)
        result = project_view(value)
        self.assertEqual(value, original)
        self.assertEqual(result['run']['unit_split_applications'][0]['rounding_extra_fraction'],
                         {'numerator':'0','denominator':'1'})
        self.assertEqual(result['run']['fills'][0]['raw_slipped_price'],'10.0501')
        self.assertEqual(result['market']['unit_splits'][0]['event']['event_id'],'split:A')
        self.assertEqual(len(result['market']['unit_splits']), 1)
        self.assertNotIn('price_grid', result['configuration']['profile'])
        self.assertNotIn('price_grid', result['comparison_conditions'][-1]['value'])
        self.assertNotIn('private.example',json.dumps(result))

        held = deepcopy(value)
        held['run']['signal_ref'] = None
        held['configuration']['portfolio_policy'] = {
            'contract_version':'etf_buy_and_hold_policy_v1','security_id':'A',
            'entry_session':'2024-01-02','budget':'1','schedule':'entry_session_once',
            'partial_fill_policy':'expire_no_retry','cash_dividend_policy':'retain_cash',
            'terminal_policy':'mark_open_position'}
        self.assertIsNone(project_view(held)['run']['signal_ref'])

        for mutation in (
            lambda v: v['run']['metrics'].update(private_marker='secret'),
            lambda v: v['run']['unit_split_applications'][0]['original_quote'].update(path='/Users/secret'),
            lambda v: v['run']['unit_split_applications'][0].update(source_refs=['https://private.example']),
            lambda v: v['configuration']['portfolio_policy'].update(private_marker='secret'),
            lambda v: v['configuration']['profile'].update(private_marker='secret'),
            lambda v: v['run']['fills'][0].update(price_grid_ref={'uri':'file:///Users/secret'}),
            lambda v: v['run']['positions'][0].update(mark_basis_event_id={'event_id':'split:A'}),
            lambda v: v['run']['orders'][0].update(announced_suspension_event_ids=[{'event_id':'split:A'}]),
            lambda v: v['market'].update(source_refs=['https://private.example/source']),
            lambda v: v['market']['unit_splits'][0].update(source_refs=[{'content_digest':ref}]),
            lambda v: v['configuration'].update(unit_split_policy={'private':'value'}),
            lambda v: v['run']['limitations'].append('See https://private.example/source'),
            lambda v: v['comparison_conditions'][-1]['value'].update(price_grid_ref='sha256:wrong'),
        ):
            malformed = deepcopy(value)
            mutation(malformed)
            with self.assertRaises(ValueError):
                project_view(malformed)

    def test_v4_stock_schedule_public_allowlist_and_units(self):
        value = self.chart_view()
        value['run']['contract_version'] = 'backtest_run_v4'
        value['run']['signal_ref'] = 'sha256:schedule'
        value.pop('stock_ml')
        value['stock_context']['portfolio_policy'] = {'top_k': 3}
        value['stock_context'].update(schedule_ref='sha256:schedule', folds=[{
            'fold_ref':'sha256:fold', 'fold_spec_ref':'sha256:spec',
            'signal_run_ref':'sha256:original-signal', 'model_ref':'sha256:model',
            'feature_ref':'sha256:feature', 'fit_session':'2024-01-01',
            'oos_trade_sessions':['2024-01-02']}])
        original = deepcopy(value)
        result = project_view(value)
        self.assertEqual(value, original)
        self.assertEqual(result['stock_context']['schedule_ref'], 'sha256:schedule')
        self.assertEqual(result['stock_context']['folds'][0]['signal_run_ref'], 'sha256:original-signal')
        self.assertEqual(result['stock_context']['folds'][0]['oos_trade_sessions'], ['2024-01-02'])
        self.assertEqual(result['market']['native_chart']['field_meta']['volume_shares']['unit'], 'shares')
        value['market']['review_display'] = {'contract_version':'review_display_v1',
            'field_units':{'close':'CNY/share'},'records':[],'context':{},
            'names_status':'saved_snapshot_labels','events_status':'saved_selected_scope'}
        value['market']['review_display']['context']['pit_policy'] = 'saved_cutoff'
        value['market']['review_events'] = [{'domain':'corporate_actions', 'event':{
            'security_id':'A', 'event_id':'synthetic:event', 'ex_date':'2024-01-02'}}]
        value['run']['fills'][0]['fill_id'] = 'synthetic:fill'
        value['market']['fill_display'] = {
            'contract_version':'fill_display_v1', 'display_ref':'sha256:display',
            'display_result_ref':'sha256:display-result', 'status':'COMPLETE',
            'coordinates':[{'fill_id':'synthetic:fill','security_id':'A',
                            'session':'2024-01-02','display_price':'10.05',
                            'source_unit':'CNY/share','target_unit':'CNY/share'}]}
        public = project_view(value)['market']
        self.assertEqual(public['review_display']['field_units']['close'], 'CNY/share')
        self.assertEqual(public['review_display']['context']['pit_policy'], 'saved_cutoff')
        self.assertEqual(public['review_events'][0]['event']['event_id'], 'synthetic:event')
        self.assertEqual(public['fill_display']['coordinates'][0]['display_price'], '10.05')
        value['market']['review_display']['field_units']['source'] = 'SYNTHETIC_SECRET_SENTINEL'
        with self.assertRaisesRegex(ValueError, 'private or unknown v4'):
            project_view(value)
        del value['market']['review_display']
        value['stock_context']['schedule_ref'] = 'sha256:wrong'
        with self.assertRaisesRegex(ValueError, 'run/schedule identity'):
            project_view(value)
        value['stock_context']['schedule_ref'] = 'sha256:schedule'
        for container, key, private in ((value['run'], 'prediction_schedule', {'rows':['PRIVATE']}),
                                        (value['run'], 'unit_split_applications', [{'event_id':'ETF-only'}]),
                                        (value['run']['metrics'], 'private_marker', 'SYNTHETIC_SECRET_SENTINEL'),
                                        (value['run']['fills'][0], 'private_marker', 'SYNTHETIC_SECRET_SENTINEL'),
                                        (value['configuration']['profile'], 'private_marker', 'SYNTHETIC_SECRET_SENTINEL'),
                                        (value['configuration']['profile'], 'limitation', {'run_id':'SYNTHETIC_SECRET_SENTINEL'}),
                                        (value['stock_context'], 'private_prediction', ['PRIVATE']),
                                        (value['stock_context']['folds'][0], 'model', {'parameters':{'private':True}}),
                                        (value['stock_context']['portfolio_policy'], 'private_strategy', 'PRIVATE')):
            container[key] = private
            with self.assertRaisesRegex(ValueError, 'private or unknown v4'):
                project_view(value)
            del container[key]
        value['comparison_conditions'].append({'key':'profile.private_marker','label':'private',
                                               'provided':True,'value':'SYNTHETIC_SECRET_SENTINEL'})
        with self.assertRaisesRegex(ValueError, 'private or unknown v4'):
            project_view(value)
        value['comparison_conditions'].pop()
        value['comparison_conditions'].append({'key':'initial_account','label':'start',
                                               'provided':True,'value':{'source':'SYNTHETIC_SECRET_SENTINEL'}})
        with self.assertRaisesRegex(ValueError, 'private or unknown v4'):
            project_view(value)
        value['comparison_conditions'].pop()
        value['evaluation']['benchmark'] = {'private_marker':'SYNTHETIC_SECRET_SENTINEL'}
        with self.assertRaisesRegex(ValueError, 'private or unknown v4'):
            project_view(value)
        value['evaluation']['benchmark'] = {'source':'SYNTHETIC_SECRET_SENTINEL'}
        with self.assertRaisesRegex(ValueError, 'private or unknown v4'):
            project_view(value)
        del value['evaluation']['benchmark']
        value['stock_ml'] = {'model': {'parameters': {'private': True}}}
        with self.assertRaisesRegex(ValueError, 'single-signal model'):
            project_view(value)

    def test_v4_saved_benchmark_comparison_v2_keeps_drawdown_and_null_gap(self):
        self.assertFalse(_schema_field_names(_V4_PUBLIC_EVALUATION) - V4_PUBLIC_KEYS)
        value = self.chart_view()
        value['run']['contract_version'] = 'backtest_run_v4'
        value['run']['signal_ref'] = 'sha256:schedule'
        value.pop('stock_ml')
        value['stock_context']['portfolio_policy'] = {'top_k': 3}
        value['stock_context'].update(schedule_ref='sha256:schedule', folds=[{
            'fold_ref':'sha256:fold', 'fold_spec_ref':'sha256:spec',
            'signal_run_ref':'sha256:signal', 'model_ref':'sha256:model',
            'feature_ref':'sha256:feature', 'fit_session':'2024-01-01',
            'oos_trade_sessions':['2024-01-02']}])
        value['evaluation']['benchmark_comparisons'] = {
            'CSI300': {'projection_version':'benchmark_comparison_v2',
                       'max_drawdown':'-0.2', 'series':[
                           {'account_session':'2024-01-02','benchmark_drawdown':'-0.1',
                            'relative_status':'VALID'},
                           {'account_session':'2024-01-03','benchmark_drawdown':None,
                            'relative_status':'MISSING'}]},
            'SSE_COMPOSITE': {'projection_version':'benchmark_comparison_v2',
                              'max_drawdown':None, 'series':[]}}
        value['evaluation']['episodes'] = [{'episode_id':'synthetic:episode',
            'dividends':[{'event_id':'synthetic:dividend','record_session':'2024-01-02',
                'ex_session':'2024-01-03','pay_session':None,'entitlement_quantity':100,
                'recognition_sequence':4,'payment_sequence':None,'recognized_minor':100,
                'pending_minor':None,'payment_status':'RECOGNIZED','tax_convention':'gross'}]}]
        value['evaluation']['pnl_distribution'] = {'bins':[
            {'lower_minor':'-100','upper_minor':'0','count':1}]}
        value['evaluation']['return_distribution'] = {'bins':[
            {'lower':'-0.1','upper':'0','count':1}]}
        public = project_view(value)
        self.assertEqual(public['evaluation']['benchmark_comparisons']['CSI300']['series'][1]
                         ['benchmark_drawdown'], None)
        self.assertEqual(public['evaluation']['benchmark_comparisons']['CSI300']['max_drawdown'], '-0.2')
        self.assertEqual(public['evaluation']['episodes'][0]['dividends'][0]['recognized_minor'], 100)
        self.assertEqual(public['evaluation']['pnl_distribution']['bins'][0]['upper_minor'], '0')
        self.assertEqual(public['evaluation']['return_distribution']['bins'][0]['upper'], '0')
        value['evaluation']['benchmark_comparisons']['CSI300']['series'][0]['private_marker'] = 'SECRET'
        with self.assertRaisesRegex(ValueError, 'private or unknown v4'):
            project_view(value)
        del value['evaluation']['benchmark_comparisons']['CSI300']['series'][0]['private_marker']
        value['evaluation']['benchmark'] = {'record_session':'2024-01-02'}
        with self.assertRaisesRegex(ValueError, 'private or unknown v4'):
            project_view(value)
        del value['evaluation']['benchmark']
        value['evaluation']['episodes'][0]['dividends'][0]['source'] = '/Users/private/secret.csv'
        with self.assertRaisesRegex(ValueError, 'private or unknown v4'):
            project_view(value)

    def test_v4_account_scalar_paths_reject_nested_legal_names(self):
        value = self.chart_view()
        value['run']['contract_version'] = 'backtest_run_v4'
        value['run']['signal_ref'] = 'sha256:schedule'
        value.pop('stock_ml')
        value['stock_context']['portfolio_policy'] = {'top_k': 3}
        value['stock_context'].update(schedule_ref='sha256:schedule', folds=[{
            'fold_ref':'sha256:fold','fold_spec_ref':'sha256:spec',
            'signal_run_ref':'sha256:signal','model_ref':'sha256:model',
            'feature_ref':'sha256:feature','fit_session':'2024-01-01',
            'oos_trade_sessions':['2024-01-02']}])
        value['run']['orders'] = [{'security_id':'A','session':'2024-01-02',
                                   'field_available_at':{'open':'2024-01-02T01:30:00Z'}}]
        value['run']['fills'][0]['field_available_at'] = {'open':'2024-01-02T01:30:00Z'}
        self.assertEqual(project_view(value)['run']['positions'][0]['quantity'], '100')
        for container, key in ((value['run']['positions'][0], 'cost_minor'),
                               (value['run']['metrics'], 'total_return'),
                               (value['run']['nav'][0], 'nav_minor'),
                               (value['run']['orders'][0]['field_available_at'], 'open'),
                               (value['run']['fills'][0], 'price'),
                               (value['market']['rows'][0], 'volume_shares')):
            old = container.get(key)
            container[key] = {'source':'PRIVATE_SENTINEL'}
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, 'private or unknown v4'):
                project_view(value)
            if old is None:
                del container[key]
            else:
                container[key] = old

    def test_account_facts_preserved_and_real_close_not_inferred_from_fill(self):
        source=saved_view();before=deepcopy(source);result=project_view(source)
        self.assertEqual(source,before)
        for field in ('metrics','nav','positions','fills'):
            self.assertEqual(result['run'][field],source['run'][field])
        self.assertEqual(result['market']['rows'],[{'security_id':'A','session':'2024-01-02','close':'10.01','volume_shares':'1000'}])
        self.assertNotEqual(result['market']['rows'][0]['close'],result['run']['fills'][0]['price'])
        self.assertIsNone(result['evaluation']['period_metrics']['account']['cagr'])
        self.assertIsNone(result['evaluation']['episode_metrics']['win_rate'])

    def test_private_material_removed_before_rendering(self):
        result=project_view(saved_view())
        self.assertNotIn('stock_ml',result)
        self.assertNotIn('research_versions',result)
        self.assertNotIn('output_refs',result['research'])
        self.assertNotIn('parameters',result['research'])
        self.assertEqual(result['registration_history'],[])
        self.assertIsNone(result['market']['native_chart'])
        self.assertNotIn('benchmark_input',result['evaluation'])
        self.assertNotIn('dividend_scope',result['evaluation'])
        self.assertIn('[本地路径已隐藏]',result['research']['outcome'])
        self.assertEqual([c['key'] for c in result['comparison_conditions']],['profile.lot_size'])

    def test_public_replay_keeps_narrow_saved_target_reason_and_causal_ids(self):
        value=saved_view()
        value['run']['decisions']=[{'trade_session':'2024-01-02','targets':{'A':'100','UNRELATED':'500'},
                                  'trace':[{'reason':'RAW_TOP5','sizing':'previous_native_close',
                                            'records':['private'],'parameters':{'model':'private'}}],
                                  'intents':[{'intent_id':'saved:intent','security_id':'A','quantity':'100'}]}]
        value['run']['orders']=[{'intent_id':'saved:intent','order_id':'saved:order','security_id':'A',
                                'session':'2024-01-02','quantity':'100'}]
        value['run']['fills'][0]['order_id']='saved:order'
        result=project_view(value);decision=result['run']['decisions'][0]
        self.assertEqual(decision['targets'],{'A':'100'})
        self.assertEqual(decision['trace'],[{'reason':'RAW_TOP5','sizing':'previous_native_close'}])
        self.assertEqual(decision['intents'][0]['intent_id'],result['run']['orders'][0]['intent_id'])
        self.assertEqual(result['run']['orders'][0]['order_id'],result['run']['fills'][0]['order_id'])
        value['run']['decisions'][0]['trace'][0]['sizing']={'payload':'private'}
        with self.assertRaisesRegex(ValueError,'nested public summary'):project_view(value)

    def test_missing_saved_market_point_rejects_instead_of_fabricating(self):
        value=saved_view();value['market']['rows']=[]
        with self.assertRaisesRegex(ValueError,'lacks saved account-related'):project_view(value)

    def test_credentials_nested_paths_and_big_evidence_keys(self):
        self.assertEqual(clean({'path':'private','value':{'coverage':['raw'],'label':'file:///Users/example/proof'}}),
                         {'value':{'label':'[本地路径已隐藏]'}})
        with self.assertRaisesRegex(ValueError,'credential-like'):
            clean({'description':'ghp_'+'a'*30})

    def test_registration_only_is_not_a_public_account(self):
        value=saved_view();value['run']['run_id']=None
        with self.assertRaisesRegex(ValueError,'explicit saved account'):project_view(value)

    def test_nested_private_payloads_removed_and_context_objects_rejected(self):
        value=saved_view()
        value['run']['fills'][0]['trace']={'records':['private'],'parameters':{'x':1}}
        value['evaluation']['benchmark']={'total_return':'0.1','environment':{'private':'env'},'records':['raw']}
        result=project_view(value)
        self.assertNotIn('trace',result['run']['fills'][0])
        self.assertEqual(result['evaluation']['benchmark'],{'total_return':'0.1'})
        value['stock_context']['model_snapshot']={'environment':'private'}
        with self.assertRaisesRegex(ValueError,'nested public summary'):project_view(value)

    def test_only_referenced_unit_events_are_published(self):
        value=saved_view();value['run']['unit_split_applications']=[{'event_id':'selected'}]
        value['market']['unit_splits']=[{'event':{'event_id':'selected','ratio_numerator':'2'}},
                                        {'event':{'event_id':'unrelated','ratio_numerator':'5'}}]
        result=project_view(value)
        self.assertEqual([r['event']['event_id'] for r in result['market']['unit_splits']],['selected'])

    def test_export_requires_exact_explicit_selection(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.json'
            source.write_text(json.dumps({'contract_version':'ui_workbench_projection_v1','views':[saved_view()]}))
            item={'input':str(source),'slug':'saved','title':'test'}
            for run_ids in (None,[],['sha256:run','sha256:run'],['other']):
                with self.assertRaises(ValueError):export_result({**item,'run_ids':run_ids},root,'2026-10-05')
            self.assertFalse((root/'saved.html').exists())

    def chart_view(self):
        value=saved_view();value['configuration']['end_session']='2024-01-03'
        value['market']['data_batch']=None
        value['market']['native_chart']={
            'source_ref':'sha256:original_source','context':{'snapshot_id':'fixed','query':{'price_basis':'unadjusted'},'coverage':['private']},
            'field_meta':{k:{'unit':'shares' if k=='volume_shares' else 'CNY/share','dtype':'saved','by_key':[{'raw_batch_id':'private'}]}
                          for k in ('open','high','low','close','volume_shares')},
            'records':[{'security_id':security,'session':session,'open':'10.01','high':'10.20','low':None,'close':'10.02','volume_shares':'1000'}
                       for security in ('A','UNRELATED') for session in ('2024-01-01','2024-01-02','2024-01-03')]}
        return value

    def test_chart_preserves_continuous_saved_ohlcv_in_selected_window(self):
        value=self.chart_view();result=project_view(value);chart=result['market']['native_chart']
        self.assertEqual(chart['records'],[r for r in value['market']['native_chart']['records']
                                           if r['security_id']=='A' and r['session'] in ('2024-01-02','2024-01-03')])
        self.assertIsNone(chart['records'][0]['low'])
        self.assertEqual(chart['source_ref'],'sha256:original_source')
        self.assertNotIn('query',chart['context']);self.assertNotIn('coverage',chart['context'])
        self.assertNotIn('contract_version',chart['context'])
        self.assertEqual(chart['field_meta']['open'],{'unit':'CNY/share','dtype':'saved','by_key':[]})

    def test_chart_unit_mismatch_rejects_without_rewriting_prices(self):
        value=self.chart_view();value['market']['native_chart']['field_meta']['open']['unit']='CNY/fund unit'
        with self.assertRaisesRegex(ValueError,'unit mismatch'):project_view(value)

    def test_selected_review_layer_keeps_adjusted_native_prices_clock_and_snapshot_names(self):
        value=self.chart_view()
        records=[{'security_id':security,'session':'2024-01-02','close':None,'native_close':'10.02',
                  'display_scale':None,'display_missing_reason':'missing_factor'} for security in ('A','UNRELATED')]
        value['market']['review_display']={'contract_version':'review_display_v1','manifest_sha256':'a'*64,
            'display_projection':True,'context':{'snapshot_id':'fixed','anchor_session':'2024-01-03',
                'knowledge_cutoff':'2024-02-01T00:00:00Z','price_source':{'query':'private'}},
            'records':records,'field_units':{'close':'CNY/share'}}
        value['market']['security_labels']={'A':'保存名称','UNRELATED':'不公开名称'}
        value['market']['review_events']=[{'domain':'corporate_actions','event':{'security_id':security,
            'ex_date':'2024-01-03','cash_dividend_per_unit':'0.1','document_refs':'private'}} for security in ('A','UNRELATED')]
        before=deepcopy(value)
        result=project_view(value)
        self.assertEqual(result['market']['review_display']['records'],records[:1])
        self.assertIsNone(result['market']['review_display']['records'][0]['display_scale'])
        self.assertEqual(result['market']['review_display']['context']['anchor_session'],'2024-01-03')
        self.assertNotIn('price_source',result['market']['review_display']['context'])
        self.assertEqual(result['market']['security_labels'],{'A':'保存名称'})
        self.assertEqual(result['market']['review_events'],[{'domain':'corporate_actions','event':{
            'security_id':'A','ex_date':'2024-01-03','cash_dividend_per_unit':'0.1'}}])
        self.assertEqual(value,before)


if __name__=='__main__':unittest.main()
