import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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


if __name__=='__main__':unittest.main()
