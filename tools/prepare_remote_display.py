"""Prepare private, reusable chart packages from saved account scope and Data.

No supplier, training, account execution, Research writes or current mutation.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import time

from axiom_ui.result_catalog import LocalResultCatalog, _relative_file, _wire


def prepare(args):
    from axiom_engine.runtime import load_backtest_evaluation
    from axiom_data import Data, QuerySpec, EventQuery
    target = Path(args.destination)
    target.mkdir(parents=True, exist_ok=True)
    scope_path = target / 'scope.json'
    if scope_path.exists():
        accounts = json.loads(scope_path.read_text())['accounts']
    else:
        catalog = LocalResultCatalog(research_root=args.research_root, engine_root=args.engine_root)
        accounts = []
        for result_id in catalog.heads:
            _, manifest, _ = catalog._manifest(result_id)
            if manifest is None:
                raise ValueError('registered manifest unavailable')
            refs = {r['artifact_key']: r for r in manifest['artifacts']}
            for account in manifest['accounts']:
                evaluation = account['evaluation_refs'][0]
                report = _wire(load_backtest_evaluation(_relative_file(refs[evaluation['artifact_key']], catalog.roots)))
                assert report['input_run_ref'] == evaluation['input_run_ref']
                assert report['content_digest'] == evaluation['content_digest']
                securities = {link['intent']['security_id'] for row in report.get('execution_trace', [])
                              for link in row.get('intent_links', [])}
                securities.update(e['security_id'] for e in report.get('episodes', []) if e.get('security_id'))
                assert securities, 'saved evaluation lacks traded securities'
                run = json.loads(_relative_file(refs[account['backtest_ref']['artifact_key']], catalog.roots).read_text())
                assert all(run[k] == evaluation['input_run_ref'][k] for k in ('run_id', 'content_digest', 'committed_sequence'))
                scope = run['request_manifest']['scope']
                accounts.append(dict(run_ref=evaluation['input_run_ref'], market_ref=run['market_ref'],
                    snapshot_id=run['request_manifest']['market_input']['execution_snapshot_id'],
                    securities=sorted(securities), start=scope['start_session'], end=scope['end_session']))
                print(json.dumps({'phase':'account_scope','accounts':len(accounts),'securities':len(securities)}),flush=True)
        scope_path.write_text(json.dumps({'accounts':accounts}))
    assert len({a['snapshot_id'] for a in accounts}) == 1
    snapshot = accounts[0]['snapshot_id']
    axis = json.loads(Path(args.axis).read_text())
    assert axis['snapshot_id'] == snapshot
    symbols = sorted({s for a in accounts for s in a['securities']})
    start, end = min(a['start'] for a in accounts), max(a['end'] for a in accounts)
    sessions = tuple(s for s in axis['calendar'] if start <= s <= end)
    assert symbols and set(symbols) <= set(axis['execution_universe']) and sessions
    data = Data(args.data_root, cache_bytes=32 * 1024**2, max_readers=1)
    index = dict(contract_version='ui_saved_display_index_v1', snapshot_id=snapshot, accounts=accounts,
                 cutoff=args.cutoff, anchor_session=sessions[-1], securities={})
    began = time.monotonic()
    for offset in range(0, len(symbols), args.block_size):
        selected = tuple(symbols[offset:offset + args.block_size])
        name = 'block-' + str(offset // args.block_size).zfill(4)
        directory = target / name
        query = dict(symbols=selected,sessions=sessions,pit_policy='operational_pit_v1',
                     cutoff_by_session={s:args.cutoff for s in sessions},purpose='historical_exploration')
        if directory.exists():
            raise ValueError('display destination already exists; use a new destination')
        manifest = data.export_review_display(snapshot=snapshot,
            price_query=QuerySpec(domain='market_daily',fields=('open','high','low','close','volume_shares','amount_cny'),**query),
            factor_query=QuerySpec(domain='adjustment_factors',fields=('factor',),**query),
            anchor_session=sessions[-1],destination=directory,reuse_snapshot=offset > 0,
            security_query=EventQuery(domain='security_master',fields=('name','source_code'),symbols=selected,
                start='1900-01-01',end=end,cutoff=args.cutoff,pit_policy='operational_pit_v1',
                time_field='listing_date',purpose='historical_exploration') if not args.without_names else None)
        for security in selected:
            index['securities'][security] = dict(directory=name,manifest_sha256=manifest['manifest_file_ref']['sha256'])
        print(json.dumps({'phase':'display','done':min(offset+args.block_size,len(symbols)),
                          'total':len(symbols),'seconds':round(time.monotonic()-began,1)}),flush=True)
    path=target/'index.json'
    with path.open('x') as stream:json.dump(index,stream,ensure_ascii=False)
    print(json.dumps({'index_sha256':sha256(path.read_bytes()).hexdigest(),'securities':len(symbols),'accounts':len(accounts)}),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('research-root','engine-root','data-root','axis','cutoff','destination'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--without-names',action='store_true',help='Explicitly prepare prices when the bound Snapshot has no name fields')
    parser.add_argument('--block-size',type=int,choices=(8,16,32),default=16)
    prepare(parser.parse_args())
