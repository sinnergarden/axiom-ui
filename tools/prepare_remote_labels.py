"""Explicit Tushare observed names; independent labels beside saved price displays.

Six stock_basic selectors only. Raw responses are retained before validation;
restart reuses receipts. No old Snapshot, account or price package is changed.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import time


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)


def prepare(args):
    from axiom_data import Data, EventQuery, IngestBatch, UpdateRequest, save_review_security_labels
    from axiom_data.live_client import TushareHttpClient
    from axiom_data.provider_local import CONTRACTS, profile_for
    from axiom_data.universe_sources import plan_full_listing_requests, listing_catalogue_evidence
    index_path = Path(args.display_index).resolve(strict=True)
    original = index_path.read_bytes()
    assert sha256(original).hexdigest() == args.display_digest, 'display index digest mismatch'
    index = json.loads(original)
    assert index['contract_version'] == 'ui_saved_display_index_v1'
    identity = json.loads(Path(args.identity).read_text())
    assert identity['contract_version'] == 'stock_execution_identity_v2'
    records = {r['security_id']: r for r in identity['rows']}
    identities = {}
    for security in index['securities']:
        match = re.fullmatch(r'cnstock\.(\d{6})\.(SH|SZ)\.(\d{8})', security)
        assert match and security in records, 'unbound stock identity'
        code, exchange, listing = match.groups()
        row = records[security]
        assert row['listing_date'].replace('-', '') == listing
        assert row['exchange'] == {'SH':'SSE','SZ':'SZSE'}[exchange]
        identities[code+'.'+exchange] = security
    target = index_path.parent / 'observed-labels'
    target.mkdir(exist_ok=True)
    client = None
    observations = []
    responses = {}
    for number, spec in enumerate(plan_full_listing_requests()):
        path = target / f'raw-{number}.json'
        fields = list(spec['fields']) + ['name']
        request = dict(endpoint='stock_basic', params=spec['params'], fields=fields,
                       canonical_symbols=sorted(identities))
        if not path.exists():
            if client is None:
                client = TushareHttpClient()
            response = client.query('stock_basic', fields=','.join(fields), **spec['params'])
            write_new(path, dict(request=request, response=response,
                      observed_at=datetime.now(timezone.utc).isoformat()))
            time.sleep(1.3)
        saved = json.loads(path.read_text())
        assert saved['request'] == request, 'saved request differs'
        table = saved['response']
        assert set(fields) <= set(table['fields']) and len(table['rows']) < 6000
        rows = [dict(zip(table['fields'], row, strict=True)) for row in table['rows']]
        responses[(spec['params']['exchange'],spec['params']['list_status'])] = rows
        observations.append(saved)
    catalogue = listing_catalogue_evidence(responses)['catalogue']
    for code, security in identities.items():
        assert code in catalogue, 'selected identity absent from current catalogue'
        assert catalogue[code]['listing_date'] == records[security]['listing_date'], 'source code listing identity changed'
    contract = deepcopy(CONTRACTS['stock_basic'])
    contract['contract_id'] = 'local.security_master.observed_names.v1'
    contract['fields'].update(name={'dtype':'string','nullable':True}, source_code={'dtype':'string','nullable':False})
    profile = profile_for('stock_basic', identity_map=identities)
    profile['field_map'].update(name='name',source_code='ts_code')
    profile['name_semantics'] = 'observed current label; historical name validity unknown'
    batches = tuple(IngestBatch('security_master', json.dumps(o['response'],ensure_ascii=False).encode(),
                    o['request'], contract, profile, o['observed_at']) for o in observations)
    data = Data(target/'data')
    result = data.update(base_snapshot=None, request=UpdateRequest(batches,'observed-stock-names-v1',{},promote=False))
    cutoff = max(o['observed_at'] for o in observations)
    binding = dict(display_index_sha256=args.display_digest, accounts=[a['run_ref'] for a in index['accounts']])
    blocks = {r['directory']:r['manifest_sha256'] for r in index['securities'].values()}
    coverage = set()
    for block, digest in sorted(blocks.items()):
        symbols = tuple(s for s,r in index['securities'].items() if r['directory'] == block)
        batch = data.events(snapshot=result.snapshot_id,query=EventQuery(domain='security_master',
            fields=('name','source_code'),symbols=symbols,start='1900-01-01',end=cutoff[:10],cutoff=cutoff,
            pit_policy='operational_pit_v1',time_field='listing_date',purpose='historical_exploration'))
        directory = 'labels-'+block
        destination = index_path.parent/directory
        if destination.exists():
            from axiom_data import load_review_security_labels
            manifest_bytes=(destination/'manifest.json').read_bytes()
            digest_label=sha256(manifest_bytes).hexdigest()
            loaded=load_review_security_labels(destination,manifest_sha256=digest_label)
            receipt=loaded['manifest']
            assert receipt['run_ref']==binding and receipt['source_snapshot_id']==result.snapshot_id
            assert receipt['display_ref']['sha256']==digest
        else:
            receipt=save_review_security_labels(batch,destination=destination,
                display_manifest=index_path.parent/block/'manifest.json',display_manifest_sha256=digest,run_ref=binding)
            digest_label=receipt['manifest_file_ref']['sha256']
        coverage.update(s for s in symbols if s not in receipt['missing_name_security_ids'])
        for security in symbols:
            index['securities'][security]['labels']=dict(directory=directory,manifest_sha256=digest_label)
    index['labels_binding']=binding
    index['label_notice']='观察名称（'+cutoff[:10]+'）；历史名称有效期未知'
    path=index_path.parent/'index-observed-names.json'
    write_new(path,index)
    summary=dict(named=len(coverage),securities=len(identities),observed_from=min(o['observed_at'] for o in observations),
        observed_through=cutoff,source_snapshot_id=result.snapshot_id,index=str(path),index_sha256=sha256(path.read_bytes()).hexdigest())
    write_new(target/'receipt.json',summary)
    print(json.dumps(summary,ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('display-index','display-digest','identity'):
        parser.add_argument('--'+name,required=True)
    prepare(parser.parse_args())
