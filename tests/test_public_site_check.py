import importlib.util
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from axiom_ui import render_empty_stock_ml_entry

spec=importlib.util.spec_from_file_location('public_site_check',Path(__file__).parents[1]/'tools/check_public_site.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


class PublicSiteCheckTests(unittest.TestCase):
    def bundle(self,root,wire,opening="<script id='workbench-data' type='application/json'>"):
        root=Path(root)
        manifest={'authorization':'explicit_selected_public_results','future_results_auto_published':False,
                  'Data_roots_current_discovery':False,'results':[{'file':'result.html','saved_owner_refs':[{'run_id':'saved'}]}]}
        (root/'publication.json').write_text(json.dumps(manifest))
        (root/'.nojekyll').write_text('')
        (root/'index.html').write_text('<a href="result.html">Saved account</a>')
        (root/'result.html').write_text(opening+json.dumps(wire)+'</script>')

    def wire(self):
        return {'views':[{'run':{'run_id':'saved'},'public_display_projection':True,
                         'market':{'data_batch':None,'native_chart':None},'registration_history':[]}]}

    def test_script_attribute_variations_are_checked(self):
        with TemporaryDirectory() as root:
            self.bundle(root,self.wire());checker.check(root)
            value=self.wire();value['views'][0]['stock_ml']={'definition':'private'}
            self.bundle(root,value)
            with self.assertRaises(AssertionError):checker.check(root)

    def test_missing_result_payload_rejects(self):
        with TemporaryDirectory() as root:
            self.bundle(root,self.wire(),'<script type="application/json">')
            with self.assertRaises(AssertionError):checker.check(root)

    def test_escaped_json_paths_and_credentials_reject(self):
        for private in ('/Users/example/private.json','ghp_'+'a'*30):
            with TemporaryDirectory() as root:
                value=self.wire();value['views'][0]['run']['description']=private
                self.bundle(root,value)
                p=Path(root)/'result.html'
                text=p.read_text().replace(private,''.join('\\u'+format(ord(c),'04x') for c in private))
                p.write_text(text)
                with self.assertRaises(AssertionError):checker.check(root)

    def test_tutorial_requires_exact_declared_static_page(self):
        with TemporaryDirectory() as root:
            self.bundle(root,self.wire())
            page='<main><h1>机器学习研究</h1><p>未执行</p></main>'.encode()
            (Path(root)/'ml-engineering.html').write_bytes(page)
            publication=Path(root)/'publication.json'
            manifest=json.loads(publication.read_text())
            manifest['tutorial']={
                'file':'ml-engineering.html','status':'public_unexecuted_semantic_preview',
                'business_execution':False,'source_commit':'a'*40,
                'source_html_sha256':'sha256:'+'b'*64,
                'public_html_sha256':'sha256:'+sha256(page).hexdigest(),
                'excerpt':'current_progress_workflow_and_case_c_a_b_only',
            }
            publication.write_text(json.dumps(manifest))
            checker.check(root)
            (Path(root)/'ml-engineering.html').write_bytes(page+b'<script>run()</script>')
            with self.assertRaises(AssertionError):checker.check(root)

    def test_empty_ml_entry_is_explicit_and_digest_bound(self):
        with TemporaryDirectory() as root:
            self.bundle(root,self.wire())
            root=Path(root)
            tutorial='<main><h1>机器学习研究</h1></main>'.encode()
            (root/'ml-engineering.html').write_bytes(tutorial)
            empty=render_empty_stock_ml_entry().encode()
            (root/'ml-results.html').write_bytes(empty)
            (root/'index.html').write_text('<a href="result.html">Saved account</a><a href="ml-results.html">ML result</a>')
            manifest=json.loads((root/'publication.json').read_text())
            manifest['tutorial']={'file':'ml-engineering.html','status':'public_unexecuted_semantic_preview',
                'business_execution':False,'source_commit':'a'*40,'source_html_sha256':'sha256:'+'b'*64,
                'public_html_sha256':'sha256:'+sha256(tutorial).hexdigest(),
                'excerpt':'current_progress_workflow_and_case_c_a_b_only'}
            manifest['ml_result_entry']={'file':'ml-results.html','status':'NO_SAVED_RESEARCH_REGISTRATION',
                'public_html_sha256':'sha256:'+sha256(empty).hexdigest(),
                'research_index_bound':False,'business_execution':False}
            (root/'publication.json').write_text(json.dumps(manifest))
            checker.check(root)
            (root/'ml-results.html').write_bytes(empty+b'<script>run()</script>')
            with self.assertRaises(AssertionError):checker.check(root)


if __name__=='__main__':unittest.main()
