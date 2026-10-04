from copy import deepcopy
from html import escape
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from axiom_ui import ProjectionError, render_backtest_report, render_sample_report


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "synthetic_run.json"
GENERATED = "2026-10-04T12:00:00Z"


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.run = json.loads(SAMPLE.read_text())

    def render(self):
        return render_sample_report(self.run, generated_at=GENERATED)

    def test_preserves_owner_values_refs_and_input(self):
        original = deepcopy(self.run)
        html = self.render()
        self.assertEqual(self.run, original)
        self.assertIn(escape(json.dumps(self.run, ensure_ascii=False, sort_keys=True,
                                        indent=2, allow_nan=False)), html)
        self.assertIn("synthetic:market", html)
        self.assertIn("10.0000", html)  # Preserve decimal price precision.
        self.assertIn("合成展示样例 · 不是真实回测完成证据", html)
        self.assertIn("T+1", html)
        self.assertIn("不是全部 ETF", html)
        self.assertIn(GENERATED, html)

    def test_formats_integer_cents_without_changing_raw_values(self):
        html = self.render()
        self.assertIn('title="原始整数分：999900">9,999.00', html)
        self.assertIn('title="原始整数分：-100100">-1,001.00', html)
        self.assertIn('title="原始整数分：100">1.00', html)
        self.run["fills"][0]["fee_minor"] = 1.5
        with self.assertRaisesRegex(ProjectionError, "integer CNY"):
            self.render()

    def test_missing_is_not_empty_or_zero(self):
        self.run["fills"] = []
        self.run["positions"] = None
        html = self.render()
        self.assertIn("LAYER_UNAVAILABLE", html)
        self.assertIn("Owner 保存的列表为空", html)
        self.assertIn("未保存标准评估", html)

    def test_rejects_mixed_account_watermarks(self):
        self.render()  # Watermarks may differ across sessions.
        self.run["positions"][1]["committed_sequence"] = 2
        with self.assertRaisesRegex(ProjectionError, "CONTEXT_MISMATCH"):
            self.render()

    def test_escapes_owner_text_and_has_no_active_content(self):
        malicious = '<script>alert("owner")</script><img src="https://example.test">'
        self.run["run_id"] = malicious
        self.run["limitations"].append(malicious)
        self.run["orders"][0]["reason"] = malicious
        html = self.render()
        self.assertNotIn("<script", html)
        self.assertNotIn("<img", html)
        self.assertIn(escape(malicious), html)
        self.assertIn("default-src 'none'", html)

    def test_rejects_unknown_contract_and_malformed_metrics(self):
        self.run["contract_version"] = "future_run"
        with self.assertRaisesRegex(ProjectionError, "unsupported"):
            self.render()
        self.run["contract_version"] = "backtest_run_v1"
        self.run["metrics"] = []
        with self.assertRaisesRegex(ProjectionError, "malformed metrics"):
            self.render()

    def test_unit_run_v2_static_report_separates_application_from_fills(self):
        self.assertNotIn('id="unit_split_applications"', self.render())
        self.run["contract_version"] = "backtest_run_v2"
        self.run["unit_split_applications"] = [{"event_id":"synthetic:unit-event",
            "before_quantity":100, "after_quantity":115, "rounding_value_minor":4610,
            "normalized_quote":{"price":"100.000"}}]
        self.run["positions"][0]["mark_basis_event_id"] = "synthetic:unit-event"
        self.run["orders"][0]["announced_suspension_event_ids"] = ["synthetic:unit-event"]
        original = deepcopy(self.run)
        html = self.render()
        self.assertIn('id="unit_split_applications"', html)
        self.assertIn("账户变化（非成交）", html)
        self.assertIn("估值单位事件依据", html)
        self.assertIn("公告停牌事件来源", html)
        self.assertIn('title="原始整数分：4610">46.10', html)
        self.assertEqual(self.run, original)
        self.run["unit_split_applications"] = None
        with self.assertRaisesRegex(ProjectionError, "malformed saved unit split"):
            self.render()

    def test_raw_mapping_cannot_claim_saved_run_evidence(self):
        with self.assertRaisesRegex(ProjectionError, "Engine Reader"):
            render_backtest_report(self.run)

    def test_shareable_export_omits_raw_inputs_and_retains_results(self):
        self.run["plan"]["private_input_marker"] = "RAW_INPUT_EXCLUDED_FROM_SHARE"
        before = deepcopy(self.run)
        html = render_sample_report(self.run, shareable=True, generated_at=GENERATED)
        self.assertNotIn("RAW_INPUT_EXCLUDED_FROM_SHARE", html)
        self.assertNotIn("展示输入原文 · 完整保存值", html)
        self.assertIn("分享报告省略", html)
        self.assertIn('title="原始整数分：999900">9,999.00', html)
        self.assertIn(self.run["market_ref"], html)
        self.assertEqual(self.run, before)

    def test_unknown_market_status_is_prominent_and_not_return_acceptance(self):
        self.run["orders"][0].update(status="EXPIRED", reason="UNKNOWN_MARKET_STATUS",
                                     market_state="unknown_status", state_reason="status_source_missing")
        self.run["fills"] = []
        original = deepcopy(self.run)
        html = self.render()
        self.assertLess(html.index("执行阻断 · 市场状态缺证"), html.index('<div class="cards">'))
        self.assertIn("零成交结果不构成收益验收", html)
        self.assertIn("EXPIRED", html)
        self.assertIn("status_source_missing", html)
        self.assertEqual(self.run, original)

    def test_daily_approximation_retains_unknown_state_and_saved_profile(self):
        self.run["plan"]["profile"] = {
            "unknown_status_policy": "etf_daily_observed",
            "approximation": "daily_volume_proxy", "lot_size": 100,
            "extra_raw_input": "RAW_PROFILE_INPUT_EXCLUDED",
        }
        self.run["orders"][0].update(
            execution_admission="ETF_OBSERVED_DAILY_ASSUMPTION",
            market_state="unknown_status", state_reason="status_source_missing")
        original = deepcopy(self.run)
        html = render_sample_report(self.run, shareable=True, generated_at=GENERATED)
        self.assertLess(html.index("ETF 日线近似 · 显式实验假设"), html.index('<div class="cards">'))
        self.assertIn("etf_daily_observed", html)
        self.assertIn("ETF_OBSERVED_DAILY_ASSUMPTION", html)
        self.assertIn("unknown_status", html)
        self.assertIn("daily_volume_proxy", html)
        self.assertNotIn("RAW_PROFILE_INPUT_EXCLUDED", html)
        self.assertEqual(self.run, original)

    def test_shareable_profile_rejects_nested_values_and_does_not_infer_policy(self):
        self.run["plan"]["profile"] = {"execution": {"raw_market": [1, 2]}}
        with self.assertRaisesRegex(ProjectionError, "must be scalar"):
            render_sample_report(self.run, shareable=True, generated_at=GENERATED)
        self.run["plan"].pop("profile")
        self.run["orders"][0]["execution_admission"] = "ETF_OBSERVED_DAILY_ASSUMPTION"
        html = render_sample_report(self.run, shareable=True, generated_at=GENERATED)
        self.assertIn("Profile 未匹配", html)
        self.assertNotIn("Owner profile 允许", html)

    def test_cli_keeps_source_bytes_and_refuses_overwrite(self):
        before = SAMPLE.read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "report.html"
            command = [sys.executable, "-m", "axiom_ui", str(SAMPLE), "--sample", "--output", str(output)]
            created = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(created.returncode, 0, created.stderr)
            html = output.read_bytes()
            refused = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(refused.returncode, 2)
            self.assertEqual(output.read_bytes(), html)
        self.assertEqual(SAMPLE.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
