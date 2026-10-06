"""Read-only UI coverage using Engine 5d98d70's tiny synthetic v6 save."""
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

from axiom_ui import render_saved_workbench
from axiom_ui.public_share import (project_view, V6_PUBLIC_KEYS,
                                   _V4_PUBLIC_EVALUATION, _schema_field_names)


FIXTURE = Path(__file__).parent / "fixtures" / "stock_v6.synthetic.json"


def saved_view(run):
    runtime = ModuleType("axiom_engine.runtime")
    runtime.load_backtest_run = lambda _path: deepcopy(run)
    with patch.dict(sys.modules, {"axiom_engine.runtime": runtime}):
        html = render_saved_workbench(["synthetic-v6.json"],
                                       synthetic_run_ids=[run["run_id"]])
    match = re.search(r'<script type="application/json" id="workbench-data">(.*?)</script>', html, re.S)
    return json.loads(match[1])["views"][0], html


class StockV6DisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved_run = json.loads(FIXTURE.read_text())

    def test_owner_saved_v6_has_narrow_stock_projection(self):
        view, html = saved_view(self.saved_run)
        self.assertEqual((view["run"]["contract_version"], view["run"]["core_version"],
                          view["run"]["runtime_version"]),
                         ("backtest_run_v6", "axiom.stock_portfolio/3", "axiom.backtest/6"))
        self.assertTrue(view["approximate"])
        self.assertEqual(view["run"]["stock_execution_rules_ref"], self.saved_run["stock_execution_rules_ref"])
        self.assertEqual(view["run"]["lifecycle_admission"]["held_gap"], "0")
        self.assertEqual(view["stock_context"]["schedule_ref"], self.saved_run["signal_ref"])
        self.assertNotIn("stock_execution_rules", view["configuration"]["profile"])
        self.assertNotIn("stock_fee_schedule", view["configuration"]["profile"])
        self.assertNotIn('"quantity_rules"', html)
        self.assertNotIn('"coverage_bundle"', html)

    def test_public_projection_keeps_five_saved_quantities_and_blocks_extra_fields(self):
        view, _ = saved_view(self.saved_run)
        public = project_view(view)
        order = public["run"]["orders"][0]
        fields = ("requested_quantity", "submitted_quantity", "unsubmitted_quantity",
                  "filled_quantity", "unfilled_quantity")
        self.assertEqual(tuple(order[field] for field in fields),
                         tuple(str(self.saved_run["orders"][0][field]) for field in fields))
        self.assertEqual(public["run"]["metrics"]["incomplete_order_count"], "0")
        self.assertEqual(public["run"]["lifecycle_admission"]["pre_listing_null"], "0")
        self.assertEqual(public["configuration"]["profile"]["stock_fee_schedule_ref"],
                         self.saved_run["plan"]["profile"]["stock_fee_schedule_ref"])
        self.assertEqual(public["stock_context"]["portfolio_policy"]["candidate_policy"],
                         "member_valid_finite_v1")
        self.assertNotIn("stock_execution_rules", public["configuration"]["profile"])
        self.assertNotIn("source_evidence", public["market"])
        for container, field, value in (
            (view["run"]["metrics"], "secret_metric", 123),
            (view["run"]["orders"][0], "secret_order", "private"),
            (view["configuration"]["profile"], "stock_execution_rules", {"private": True}),
            (view["run"]["lifecycle_admission"], "private_gap", 1),
        ):
            with self.subTest(field=field):
                container[field] = value
                with self.assertRaises(ValueError):
                    project_view(view)
                del container[field]

    def test_large_native_rules_are_not_embedded_in_display(self):
        run = deepcopy(self.saved_run)
        marker = "SYNTHETIC_PRIVATE_NATIVE_RULES_MUST_NOT_RENDER"
        run["plan"]["profile"]["stock_execution_rules"]["private_marker"] = marker
        run["plan"]["profile"]["stock_fee_schedule"]["private_marker"] = marker
        market_sources = run["plan"]["market_replay"]["source_evidence"]
        market_batch = next(source["batch"] for source in market_sources
                            if source.get("batch", {}).get("context", {}).get("domain") == "market_daily")
        market_batch["field_meta"]["close"]["by_key"][0]["private_marker"] = marker
        view, html = saved_view(run)
        self.assertNotIn(marker, html)
        self.assertEqual(view["market"]["native_chart"]["field_meta"]["close"]["by_key"], [])
        self.assertNotIn(marker, json.dumps(project_view(view)))

    def test_public_blocked_reason_drops_native_gap_details(self):
        view, _ = saved_view(self.saved_run)
        view["run"]["stopped"] = {"session": "2024-01-03",
            "reason": "HELD_MISSING_STOCK_LIFECYCLE_CAPABILITY",
            "committed_sequence": "4", "gaps": [{"factor_source_ref": "private-native-proof"}]}
        view["run"]["status"] = "BLOCKED"
        public = project_view(view)
        self.assertEqual(public["run"]["stopped"]["reason"],
                         "HELD_MISSING_STOCK_LIFECYCLE_CAPABILITY")
        self.assertNotIn("private-native-proof", json.dumps(public))

    def test_v6_export_keeps_v3_evaluation_benchmark_dividend_and_distribution(self):
        self.assertFalse(_schema_field_names(_V4_PUBLIC_EVALUATION) - V6_PUBLIC_KEYS)
        view, _ = saved_view(self.saved_run)
        view["evaluation"] = {
            "contract_version": "evaluation_report_v3",
            "spec": {"benchmark_projection_version": "benchmark_comparison_v2"},
            "benchmark_comparisons": {
                "CSI300": {"projection_version": "benchmark_comparison_v2",
                           "max_drawdown": "-0.2", "series": [
                               {"account_session": "2024-01-02", "benchmark_drawdown": "-0.1",
                                "relative_status": "VALID"}]},
                "SSE_COMPOSITE": {"projection_version": "benchmark_comparison_v2",
                                  "observation_cutoff": "2024-01-03T00:00:00Z",
                                  "observation_pit_policy": "operational_pit_v1",
                                  "observation_purpose": "historical_exploration",
                                  "observation_snapshot_id": "synthetic:snapshot",
                                  "series": []}},
            "episodes": [{"episode_id": "synthetic:episode", "dividends": [
                {"event_id": "synthetic:dividend", "record_session": "2024-01-02",
                 "recognized_minor": "100", "pending_minor": None,
                 "payment_status": "RECOGNIZED"}]}],
            "pnl_distribution": {"bins": [{"lower_minor": "-100", "upper_minor": "0",
                                           "count": "1"}]},
            "return_distribution": {"bins": [{"lower": "-0.1", "upper": "0",
                                              "count": "1"}]},
        }
        public = project_view(view)["evaluation"]
        self.assertEqual(public["spec"]["benchmark_projection_version"],
                         "benchmark_comparison_v2")
        self.assertEqual(public["benchmark_comparisons"]["CSI300"]["series"][0]
                         ["benchmark_drawdown"], "-0.1")
        self.assertEqual(public["benchmark_comparisons"]["SSE_COMPOSITE"]
                         ["observation_snapshot_id"], "synthetic:snapshot")
        self.assertEqual(public["episodes"][0]["dividends"][0]["recognized_minor"], "100")
        self.assertEqual(public["pnl_distribution"]["bins"][0]["upper_minor"], "0")
        self.assertEqual(public["return_distribution"]["bins"][0]["upper"], "0")
        view["evaluation"]["benchmark_comparisons"]["CSI300"]["series"][0]["secret"] = "private"
        with self.assertRaises(ValueError):
            project_view(view)

    def test_v6_with_v2_evaluation_sheds_native_source_payload(self):
        """A handwritten v2 display wire exercises the public reader binding."""
        run = self.saved_run
        marker = "SYNTHETIC_PRIVATE_EVALUATION_NATIVE_PAYLOAD"
        last = run["nav"][-1]
        unavailable = {"cagr": None, "cagr_status": "INSUFFICIENT_SPAN",
                       "cagr_reason": "YEAR_FRACTION_BELOW_ONE"}
        evaluation = {
            "contract_version": "evaluation_report_v2",
            "evaluation_version": "axiom.evaluation/2",
            "evaluation_ref": "synthetic:evaluation-v2", "status": "COMPLETE",
            "input_run_ref": {key: run[key] for key in
                              ("run_id", "content_digest", "committed_sequence")},
            **{key: run[key] for key in ("signal_ref", "market_ref", "profile_ref")},
            "series": [{"session": point["session"], "nav_minor": point["nav_minor"],
                        "nav_index": point["nav_index"],
                        "committed_sequence": point["committed_sequence"],
                        "drawdown": "0"} for point in run["nav"]],
            "monthly_returns": [], "episodes": [],
            "episode_metrics": {"win_rate": None, "mean_net_pnl_minor": None,
                                "mean_episode_return": None},
            "pnl_distribution": {"status": "INSUFFICIENT_SAMPLE",
                                 "metric": "net_pnl_minor", "unit": "CNY fen", "bins": []},
            "benchmark": {"anchor_session": "2024-01-01", "anchor_close": "10",
                          "series": [{"close": "10"}]},
            "period_metrics": {
                "window": {"anchor_session": "2024-01-01", "end_session": last["session"],
                           "elapsed_calendar_days": 7, "day_count": "actual_actual_calendar_year_split",
                           "year_segments": [{"year": 2024, "days": 7, "year_days": 366}],
                           "year_fraction": "0.01912568306010928961748633879781420765027"},
                "account": {**unavailable, "initial_nav_minor": run["initial_nav_minor"],
                            "final_nav_minor": last["nav_minor"],
                            "total_return": run["metrics"]["total_return"],
                            "max_drawdown": run["metrics"]["max_drawdown"]},
                "benchmark": {**unavailable, "anchor_close": "10", "end_close": "10",
                              "total_return": "0", "max_drawdown": "0"}},
            "benchmark_input": {"source_evidence": [{"reference": "synthetic:benchmark",
                "batch": {"records": [{"private": marker}]}}],
                "coverage_bundle": {"payload": marker}},
            "dividend_scope": {"actions": [], "source_evidence": [{"reference": "synthetic:dividend",
                "batch": {"records": [{"private": marker}]}}],
                "coverage": {"private": marker}, "coverage_bundle": {"payload": marker}},
        }
        runtime = ModuleType("axiom_engine.runtime")
        runtime.load_backtest_run = lambda _path: deepcopy(run)
        runtime.load_backtest_evaluation = lambda _path: deepcopy(evaluation)
        with patch.dict(sys.modules, {"axiom_engine.runtime": runtime}):
            html = render_saved_workbench(["synthetic-v6.json"],
                                           evaluation_paths=["synthetic-v2-evaluation.json"])
        view = json.loads(re.search(
            r'<script type="application/json" id="workbench-data">(.*?)</script>',
            html, re.S)[1])["views"][0]
        self.assertEqual(view["evaluation"]["period_metrics"]["account"]["total_return"],
                         run["metrics"]["total_return"])
        self.assertEqual(view["evaluation"]["benchmark_input"]["source_evidence"][0]
                         ["reference"], "synthetic:benchmark")
        self.assertNotIn(marker, html)
        self.assertNotIn("coverage_bundle", view["evaluation"]["dividend_scope"])


if __name__ == "__main__":
    unittest.main()
