"""Standard-library public artifact and relative-link checks; no Owner dependencies."""
from html.parser import HTMLParser
from pathlib import Path
from hashlib import sha256
import base64,json,re,sys
from xml.etree import ElementTree

BAD_PATH=re.compile(r'(?:file://)?/(?:Users|tmp|private|var/folders|home)/|[A-Za-z]:\\|\.artifacts/|sediment://')
SECRET=re.compile(r'github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----')
FORBIDDEN={'coverage','coverage_bundle','payload','field_meta','by_key','query','definition','locator','uri','path',
           'root','input_refs','output_refs','stock_ml','research_versions','research_version_comparisons',
           'benchmark_input','dividend_scope','source_evidence','unit_split_source_evidence','raw_batch_id','document_refs',
           'records','environment','parameters','model','trace'}
class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.workbench=[];self.in_workbench=False
    def handle_starttag(self,tag,attrs):
        if tag=='script' and dict(attrs).get('id')=='workbench-data':self.in_workbench=True
        for key,value in attrs:
            if key in ('href','src') and value:self.links.append(value)
    def handle_endtag(self,tag):
        if tag=='script':self.in_workbench=False
    def handle_data(self,data):
        if self.in_workbench:self.workbench.append(data)
def check_json(value,path=()):
    if isinstance(value,dict):
        allowed={'records','field_meta'} if path and path[-1]=='native_chart' else {'records'} if path and path[-1]=='review_display' else {'by_key'} if len(path)>1 and path[-2]=='field_meta' else {'trace'} if path[-2:]==('run','decisions') else set()
        assert not (FORBIDDEN-allowed).intersection(value),(FORBIDDEN-allowed).intersection(value)
        for key in value:assert not BAD_PATH.search(key) and not SECRET.search(key),('private JSON key',key)
        for key,child in value.items():check_json(child,path+(key,))
    elif isinstance(value,list):
        for child in value:check_json(child,path)
    elif isinstance(value,str):
        assert not BAD_PATH.search(value), 'private decoded JSON path'
        assert not SECRET.search(value), 'credential-like decoded JSON content'
def check(root):
    root=Path(root).resolve();assert (root/'index.html').is_file()
    manifest=json.loads((root/'publication.json').read_text())
    assert manifest['authorization']=='explicit_selected_public_results'
    assert manifest['future_results_auto_published'] is False and manifest['Data_roots_current_discovery'] is False
    files=list(root.rglob('*'));count=0
    for p in files:
        assert not p.is_symlink(),p
        if not p.is_file():continue
        assert p.suffix in ('.html','.json') or p.name in {'.nojekyll','echarts.LICENSE.txt','echarts.NOTICE.txt'},p
        text=p.read_text();assert not BAD_PATH.search(text),('private path',p)
        assert not SECRET.search(text),('credential-like content',p)
        if p.suffix=='.json':check_json(json.loads(text))
        if p.suffix=='.html':
            links=Links();links.feed(text)
            for link in links.links:
                if link.startswith(('https://','#','mailto:')):continue
                if p.name=='ml-engineering.html' and link.startswith('data:image/svg+xml;base64,'):continue
                assert not link.startswith(('/', 'http:', 'file:')),link
                target=(p.parent/link.split('#')[0].split('?')[0]).resolve()
                assert target.is_relative_to(root) and target.is_file(),(p,link)
            if p.name in {r['file'] for r in manifest['results']}:assert links.workbench,('missing result projection',p)
            if p.name=='ml-engineering.html':
                assert not links.workbench and '<script' not in text.lower()
                assert text.count('id="section-')>=13 and 'href="index.html"' in text
            if links.workbench:
                wire=json.loads(''.join(links.workbench));check_json(wire)
                declared=next(r for r in manifest['results'] if r['file']==p.name)
                assert {v['run']['run_id'] for v in wire['views']}=={r['run_id'] for r in declared['saved_owner_refs']},('selection mismatch',p)
                for v in wire['views']:
                    assert v['run']['run_id'] and v['public_display_projection']
                    assert v['market'].get('data_batch') is None
                    chart=v['market'].get('native_chart')
                    if chart:
                        assert chart['public_selected_chart'] and chart['display_projection']
                        start,end=v['configuration']['start_session'],v['configuration']['end_session']
                        assert all(start<=row['session']<=end for row in chart['records'])
                        assert all(set(row)<={'security_id','session','open','high','low','close','volume_units','volume_shares'} for row in chart['records'])
                        assert all(meta.get('by_key')==[] and set(meta)<={'unit','dtype','by_key'} for meta in chart['field_meta'].values())
                    display=v['market'].get('review_display')
                    if display:
                        assert display['public_selected_chart'] and display['display_projection']
                        assert display['contract_version']=='review_display_v1'
                        start,end=v['configuration']['start_session'],v['configuration']['end_session']
                        assert all(start<=row['session']<=end for row in display['records'])
                    assert not v.get('registration_history')
                    if v.get('evaluation'):
                        ref=v['evaluation']['input_run_ref']
                        assert all(str(ref[k])==str(v['run'][k]) for k in ('run_id','content_digest','committed_sequence'))
        count+=1
    expected={r['file'] for r in manifest['results']}|{'index.html','publication.json','.nojekyll'}
    for vendor in ('echarts.LICENSE.txt','echarts.NOTICE.txt','echarts.vendor.json'):
        if (root/vendor).exists():expected.add(vendor)
    if (root/'performance.html').exists():expected.add('performance.html')
    if manifest.get('process_refs'):
        assert (root/'process.html').is_file()
        expected.add('process.html')
    if manifest.get('tutorial'):
        tutorial=manifest['tutorial']
        assert tutorial['file']=='ml-engineering.html' and tutorial['diagram_embedded'] is True
        assert tutorial['source_repo']=='sinnergarden/axiom-docs'
        assert re.fullmatch(r'[0-9a-f]{40}',tutorial['source_commit'])
        assert tutorial['source_path']=='notebooks/ml_engineering_tutorial.html'
        assert tutorial['status']=='public_readonly_teaching' and tutorial['business_execution'] is False
        page=(root/tutorial['file']).read_bytes()
        assert tutorial['published_html_sha256']=='sha256:'+sha256(page).hexdigest()
        images=re.findall(rb'src="data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)"',page)
        assert len(images)==1
        svg=base64.b64decode(images[0],validate=True)
        assert tutorial['diagram_sha256']=='sha256:'+sha256(svg).hexdigest()
        decoded=svg.decode('utf-8');assert not BAD_PATH.search(decoded) and not SECRET.search(decoded)
        svg_root=ElementTree.fromstring(decoded)
        assert svg_root.tag.rsplit('}',1)[-1]=='svg'
        assert all(value.strip(' "\'').startswith('#') for value in re.findall(r'url\(([^)]+)\)',decoded,flags=re.I))
        for element in svg_root.iter():
            assert element.tag.rsplit('}',1)[-1].lower() not in {'script','foreignobject'}
            for key,value in element.attrib.items():
                name=key.rsplit('}',1)[-1].lower()
                assert not name.startswith('on') and not (name.endswith('href') and not value.startswith('#'))
        assert re.fullmatch(r'sha256:[0-9a-f]{64}',tutorial['source_html_sha256'])
        assert 'href="ml-engineering.html"' in (root/'index.html').read_text()
        expected.add(tutorial['file'])
    assert {str(p.relative_to(root)) for p in files if p.is_file()}==expected,'unexpected public artifact'
    print('Public site PASS: '+str(count)+' allowlisted files; links, owner refs and disclosure checks passed.')
if __name__=='__main__':check(sys.argv[1])
