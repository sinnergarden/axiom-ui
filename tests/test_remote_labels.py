"""Observed labels remain bound to the configured price display and accounts."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd
from axiom_data import DataBatch, save_review_security_labels
from axiom_ui.remote_display import SavedDisplay


class ObservedLabelsTest(unittest.TestCase):
    def test_public_sidecar_binding_and_changed_display_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            price=root/'block-0000';price.mkdir()
            context=dict(snapshot_id='prices',knowledge_cutoff='2020-01-01T00:00:00Z',anchor_session='2019-12-31',
                         price_source={'query':{'symbols':['S']}})
            payload=json.dumps(dict(contract_version='review_display_v1',context=context)).encode()
            (price/'manifest.json').write_bytes(payload)
            digest=sha256(payload).hexdigest()
            account=dict(run_ref=dict(run_id='r',content_digest='d',committed_sequence=1),
                         market_ref='m',snapshot_id='prices',securities=['S'])
            binding=dict(display_index_sha256='a'*64,accounts=[account['run_ref']])
            row=dict(security_id='S',listing_date='2010-01-01',name='观察名称',source_code='000001.SZ')
            provenance=dict(security_id='S',listing_date='2010-01-01',raw_batch_id='raw',revision_id='revision',
                            first_observed_at='2026-10-14T00:00:00Z',usable_from='2026-10-14T00:00:00Z')
            batch=DataBatch(pd.DataFrame([row]),{f:{'dtype':'string','by_key':[provenance]} for f in ('name','source_code')},
                           dict(contract_version='data_batch_v1',domain='security_master',snapshot_id='names',reader_version='test',
                                query=dict(purpose='historical_exploration',symbols=['S'],fields=['name','source_code'],
                                           cutoff='2026-10-14T01:00:00Z',pit_policy='operational_pit_v1')))
            saved=save_review_security_labels(batch,destination=root/'labels-block-0000',display_manifest=price/'manifest.json',
                                             display_manifest_sha256=digest,run_ref=binding)
            index=dict(contract_version='ui_saved_display_index_v1',accounts=[account],snapshot_id='prices',
                       cutoff=context['knowledge_cutoff'],anchor_session=context['anchor_session'],labels_binding=binding,
                       securities={'S':dict(directory='block-0000',manifest_sha256=digest,
                           labels=dict(directory='labels-block-0000',manifest_sha256=saved['manifest_file_ref']['sha256']))})
            def load(value):
                raw=json.dumps(value).encode();(root/'index.json').write_bytes(raw)
                return SavedDisplay(root/'index.json',sha256(raw).hexdigest())
            display=load(index)
            view=dict(run={**account['run_ref'],'market_ref':'m'},market={'snapshot_id':'prices'})
            display.attach(view)
            self.assertEqual(view['market']['security_labels'],{'S':'观察名称'})
            self.assertEqual(display.labels['S']['observed_at'],'2026-10-14T00:00:00Z')
            changed=deepcopy(index);changed['securities']['S']['manifest_sha256']='f'*64
            with self.assertRaisesRegex(ValueError,'label display binding mismatch'):load(changed)
            changed=deepcopy(index);changed['accounts']=deepcopy(index['accounts']);changed['accounts'][0]['run_ref']['content_digest']='other'
            with self.assertRaisesRegex(ValueError,'label account bindings differ'):load(changed)


if __name__ == '__main__':unittest.main()
