"""Explicit private display bindings; only Data's saved display loader reads prices."""
from hashlib import sha256
import json
from pathlib import Path
import re

from .result_catalog import _require


class SavedDisplay:
    def __init__(self, index_path, digest):
        self.path = Path(index_path).resolve(strict=True)
        raw = self.path.read_bytes()
        _require(sha256(raw).hexdigest() == digest, 'display index digest mismatch')
        self.index = json.loads(raw)
        _require(self.index['contract_version'] == 'ui_saved_display_index_v1', 'invalid display index')
        self.digest = digest

    def binding(self, view):
        run = view['run']
        matches = [a for a in self.index['accounts'] if all(a['run_ref'][k] == run[k]
                   for k in ('run_id', 'content_digest', 'committed_sequence'))]
        _require(len(matches) == 1, 'display account binding unavailable')
        account = matches[0]
        _require(account['market_ref'] == run['market_ref'] and
                 account['snapshot_id'] == view['market']['snapshot_id'] == self.index['snapshot_id'],
                 'display market binding mismatch')
        return account

    def attach(self, view):
        if not any(all(a['run_ref'][k] == view['run'][k] for k in
                   ('run_id', 'content_digest', 'committed_sequence')) for a in self.index['accounts']):
            view['market']['missing_reason'] = '该账户版本尚未绑定保存行情显示包。'
            return
        account = self.binding(view)
        view['market'].update(display_available=True,
            display_securities=[s for s in account['securities'] if s in self.index['securities']],
            security_labels={},
            label_notice=self.index.get('label_notice', '名称显示输入尚未保存'))

    def read(self, view, security):
        account = self.binding(view)
        _require(security in account['securities'] and security in self.index['securities'],
                 'security not in bound display')
        ref = self.index['securities'][security]
        _require(re.fullmatch(r'block-\d{4}', ref['directory']) is not None, 'invalid display locator')
        directory = (self.path.parent / ref['directory']).resolve(strict=True)
        _require(directory.is_relative_to(self.path.parent), 'display escaped configured root')
        from axiom_data import load_review_display
        saved = load_review_display(directory, manifest_sha256=ref['manifest_sha256'])
        layer = saved['ohlcv']; context = layer['context']; meta = layer['field_meta']
        _require(context['snapshot_id'] == account['snapshot_id'] and
                 context['anchor_session'] == self.index['anchor_session'] and
                 context['knowledge_cutoff'] == self.index['cutoff'] and
                 context['usage'] == 'retrospective_review' and context['native_price_basis'] == 'unadjusted',
                 'display clock mismatch')
        _require(all(meta['native_'+k]['unit'] == 'CNY/share' for k in ('open','high','low','close')) and
                 meta['volume_shares']['unit'] == 'shares', 'display units mismatch')
        rows = [r for r in layer['records'] if r['security_id'] == security and account['start'] <= r['session'] <= account['end']]
        _require(rows and len({r['session'] for r in rows}) == len(rows), 'missing or duplicate display records')
        names = (saved.get('securities') or {}).get('batch', {}).get('records', [])
        labels = [row for row in names if row.get('security_id') == security and row.get('name')]
        _require(len(labels) <= 1, 'ambiguous observed name')
        notice = '保存观察名称；历史名称有效期未知' if labels else '该保存 Snapshot 未提供证券名称'
        return dict(security_id=security, run_id=view['run']['run_id'], records=rows,
                    context=dict(snapshot_id=context['snapshot_id'], anchor_session=context['anchor_session'],
                        knowledge_cutoff=context['knowledge_cutoff'], native_price_basis='unadjusted',
                        manifest_sha256=ref['manifest_sha256'], usage='retrospective_review'),
                    field_meta={k:{f:v for f,v in item.items() if f != 'by_key'} for k,item in meta.items()},
                    name=labels[0]['name'] if labels else None, label_notice=notice)
