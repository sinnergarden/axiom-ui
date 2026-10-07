from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from prepare_ml_tutorial_preview import prepare, transform  # noqa: E402


COMMIT = "a" * 40


def digest(data):
    return "sha256:" + sha256(data).hexdigest()


def source(case_extra=""):
    return (
        '<!doctype html><html><head><style>body{color:black}</style></head><body>'
        '<nav><a href="#section-1">old result</a></nav><main>'
        '<section id="section-1">Feb5 37.72 s Top3/Top5 private result</section>'
        '<section id="section-14" class="markdown">'
        '<h2>14. 三个小用例：从正式输入到保存结果</h2>'
        '<p>第 1–13 节的历史回执无须加载。</p>'
        '<a href="../docs/design/04_axiom_trade.md#stock-bounded-v7-proposal">Trade</a>'
        '<a href="../docs/design/04_axiom_trade.md#long-history-evaluation">Evaluate</a>'
        + case_extra + '</section>'
        '<section id="cell-20">generic inputs/config.json</section>'
        '<section id="cell-22"><h3>14.1 CaseC：四折</h3></section>'
        '<section id="cell-33"><h3>14.2 CaseA：配置</h3></section>'
        '<section id="cell-34"><h3>14.3 CaseB：组合</h3></section>'
        '<section id="cell-35"><h3>14.4 结果记录</h3>'
        '<p>未执行，无新增结果。</p>'
        '<p>小例之后沿同一实现做 M1 多年计划。</p></section>'
        '</main><script>old navigation</script></body></html>'
    ).encode()


class PreviewTest(unittest.TestCase):
    def test_excerpt_excludes_historical_results_and_old_navigation(self):
        raw = source()
        text = transform(raw, digest(raw), COMMIT).decode()
        self.assertIn('id="progress"', text)
        self.assertIn('id="case-c"', text)
        self.assertIn('id="case-a"', text)
        self.assertIn('id="case-b"', text)
        self.assertIn("505 交易日 Feature", text)
        self.assertIn("29.43%", text)
        self.assertIn("未执行，无新增结果", text)
        self.assertNotIn("Feb5", text)
        self.assertNotIn("37.72 s", text)
        self.assertNotIn("Top3/Top5", text)
        self.assertNotIn("小例之后", text)
        self.assertNotIn("<script", text)
        self.assertNotIn("#section-1", text)
        self.assertNotIn("notebooks/", text)
        self.assertIn(COMMIT + "/docs/design/04_axiom_trade.md", text)

    def test_rejects_changed_source_and_private_case_material(self):
        raw = source()
        with self.assertRaisesRegex(ValueError, "reviewed digest"):
            transform(raw, digest(b"different"), COMMIT)
        private = source(case_extra='<p>/Users/example/private/run.json</p>')
        with self.assertRaisesRegex(ValueError, "private path"):
            transform(private, digest(private), COMMIT)
        old_result = source(case_extra='<p>Feb19 real fold result</p>')
        with self.assertRaisesRegex(ValueError, "historical result"):
            transform(old_result, digest(old_result), COMMIT)

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
            self.assertIn('>机器学习研究</h2>', (copy / "index.html").read_text())
            self.assertIn('>查看流程、用例与当前进展。</p>',
                          (copy / "index.html").read_text())
            self.assertFalse(report["published"])
            self.assertTrue(json.loads((root / "preview" / "acceptance.json").read_text())
                            ["publication_unchanged"])
            with self.assertRaisesRegex(ValueError, "must be new"):
                prepare(owner, digest(raw), COMMIT, site, root / "preview")


if __name__ == "__main__":
    unittest.main()
