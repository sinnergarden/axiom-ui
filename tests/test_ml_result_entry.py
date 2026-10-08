"""The empty ML entry has no Owner dependency or fabricated result."""
from contextlib import redirect_stderr
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from axiom_ui import render_empty_stock_ml_entry
from axiom_ui.__main__ import main


ROOT = Path(__file__).resolve().parents[1]


class EmptyStockMLEntryTest(TestCase):
    def test_checked_in_entry_matches_explicit_generator(self):
        html = render_empty_stock_ml_entry()
        self.assertEqual((ROOT / "site/ml-results.html").read_text(), html)
        self.assertIn('id="empty-stock-ml-result"', html)
        self.assertIn("机器学习研究", html)
        self.assertIn("结果准备中", html)
        self.assertNotIn("Research 保存登记", html)
        self.assertNotIn("公共 Reader", html)
        self.assertIn('href="ml-engineering.html"', html)
        self.assertIn('href="ml-results.html"', (ROOT / "site/index.html").read_text())
        self.assertIn('>查看研究结果</a>', (ROOT / "site/index.html").read_text())
        self.assertNotIn("workbench-data", html)
        self.assertNotIn("<script", html)
        manifest = json.loads((ROOT / "site/publication.json").read_text())
        self.assertEqual(manifest["ml_result_entry"]["public_html_sha256"],
                         "sha256:" + sha256(html.encode()).hexdigest())
        self.assertFalse(manifest["ml_result_entry"]["business_execution"])
        self.assertEqual([r["file"] for r in manifest["results"]], ["etf-three-account.html"])

    def test_cli_requires_explicit_absence_and_no_saved_inputs(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / "empty.html"
            with patch.object(sys, "argv", ["axiom-ui", "--workbench", "--empty-stock-ml",
                                            "--output", str(output)]), patch("builtins.print"):
                main()
            self.assertEqual(output.read_text(), render_empty_stock_ml_entry())
            with patch.object(sys, "argv", ["axiom-ui", "--workbench", "--empty-stock-ml",
                                            "--experiment-index", "unread.json", "--output", str(Path(temp) / "wrong.html")]), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main()
            self.assertEqual(error.exception.code, 2)
            self.assertFalse((Path(temp) / "wrong.html").exists())
