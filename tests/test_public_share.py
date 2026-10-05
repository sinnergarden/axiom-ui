import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from axiom_ui.public_share import clean, project_view, export_result


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
        value['stock_context']['schedule_ref'] = 'sha256:wrong'
        with self.assertRaisesRegex(ValueError, 'run/schedule identity'):
            project_view(value)
        value['stock_context']['schedule_ref'] = 'sha256:schedule'
        for container, key, private in ((value['run'], 'prediction_schedule', {'rows':['PRIVATE']}),
                                        (value['stock_context'], 'private_prediction', ['PRIVATE']),
                                        (value['stock_context']['folds'][0], 'model', {'parameters':{'private':True}}),
                                        (value['stock_context']['portfolio_policy'], 'private_strategy', 'PRIVATE')):
            container[key] = private
            with self.assertRaisesRegex(ValueError, 'private or unknown v4'):
                project_view(value)
            del container[key]
        value['stock_ml'] = {'model': {'parameters': {'private': True}}}
        with self.assertRaisesRegex(ValueError, 'single-signal model'):
            project_view(value)

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
