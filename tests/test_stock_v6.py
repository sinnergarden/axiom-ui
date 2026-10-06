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
from axiom_ui.public_share import project_view


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


if __name__ == "__main__":
    unittest.main()
