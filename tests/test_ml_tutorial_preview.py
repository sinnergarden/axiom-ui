import base64
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from prepare_ml_tutorial_preview import prepare, transform  # noqa: E402


COMMIT = "a" * 40
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="2" height="2"/></svg>'


def source(svg=SVG, extra_link=""):
    image = base64.b64encode(svg).decode()
    return ('<!doctype html><html><head><style>body{color:black}</style></head>'
            '<header><a href="researcher_tutorial.html">Researcher</a></header>'
            '<nav><a href="#section-14">Case</a></nav>'
            '<section id="section-14"><img src="data:image/svg+xml;base64,' + image
            + '"><a href="../docs/design/05_axiom_research.md#experiment-records">Docs</a>'
            + extra_link + '</section><script>document.body.dataset.nav=1</script>'
            '</html>').encode()


def digest(data):
    return "sha256:" + sha256(data).hexdigest()


class PreviewTest(unittest.TestCase):
    def test_fixed_source_has_script_free_local_navigation(self):
        raw = source()
        html, diagram = transform(raw, digest(raw), COMMIT)
        text = html.decode()
        self.assertEqual(diagram, digest(SVG))
        self.assertNotIn("<script", text)
        self.assertIn("Content-Security-Policy", text)
        self.assertIn('href="index.html"', text)
        self.assertIn('href="#section-14"', text)
        self.assertIn(COMMIT + "/docs/design/05_axiom_research.md#experiment-records", text)
        self.assertIn(COMMIT + "/notebooks/researcher_tutorial.ipynb", text)

    def test_rejects_changed_source_and_unsafe_content(self):
        raw = source()
        with self.assertRaisesRegex(ValueError, "reviewed digest"):
            transform(raw, digest(b"different"), COMMIT)
        bad_svg = source(b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>')
        with self.assertRaisesRegex(ValueError, "active SVG"):
            transform(bad_svg, digest(bad_svg), COMMIT)
        bad_link = source(extra_link='<a href="/Users/example/private">secret</a>')
        with self.assertRaisesRegex(ValueError, "private path"):
            transform(bad_link, digest(bad_link), COMMIT)
        missing_anchor = raw.replace(b'href="#section-14"', b'href="#missing"')
        with self.assertRaisesRegex(ValueError, "missing tutorial anchor"):
            transform(missing_anchor, digest(missing_anchor), COMMIT)

    def test_preview_preserves_etf_and_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text(
                '<section><details><summary>结果口径与来源</summary></details></section>'
            )
            (site / "etf-three-account.html").write_bytes(b"ETF FIXED")
            (site / "publication.json").write_text('{"published":true}')
            owner = root / "owner.html"
            raw = source()
            owner.write_bytes(raw)
            report = prepare(owner, digest(raw), COMMIT, site, root / "preview")
            copy = root / "preview" / "site"
            self.assertEqual((site / "etf-three-account.html").read_bytes(),
                             (copy / "etf-three-account.html").read_bytes())
            self.assertEqual((site / "publication.json").read_bytes(),
                             (copy / "publication.json").read_bytes())
            self.assertIn('id="ml-engineering-tutorial"',
                          (copy / "index.html").read_text())
            self.assertFalse(report["published"])
            self.assertTrue(json.loads((root / "preview" / "acceptance.json").read_text())
                            ["publication_unchanged"])
            with self.assertRaisesRegex(ValueError, "must be new"):
                prepare(owner, digest(raw), COMMIT, site, root / "preview")


if __name__ == "__main__":
    unittest.main()
