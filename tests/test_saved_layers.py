"""Small display bindings only; no factor or account acceptance."""
from copy import deepcopy
from types import ModuleType
from unittest import TestCase
from unittest.mock import patch
import sys

from axiom_ui import ProjectionError
from axiom_ui.saved_layers import attach_review_display, load_review_display_for_view


def fixture():
    context = {"usage":"retrospective_review","snapshot_id":"synthetic:snapshot",
        "anchor_session":"2024-01-31","knowledge_cutoff":"2024-02-01T00:00:00Z"}
    fields = ("open","high","low","close","native_open","native_high","native_low","native_close")
    metadata = {k:{"unit":"CNY/share"} for k in fields}
    metadata["volume_shares"] = {"unit":"shares"}
    metadata["display_scale"] = {"unit":"dimensionless","by_key":[{"security_id":"synthetic:A",
        "session":"2024-01-02","missing_reason":"missing_factor"}]}
    row = {"security_id":"synthetic:A","session":"2024-01-02","open":None,"high":None,"low":None,
           "close":None,"native_open":10.1,"native_high":10.3,"native_low":10.0,"native_close":10.2,
           "volume_shares":1000,"display_scale":None}
    saved = {"manifest":{"context":context,"names_status":"saved_snapshot_labels","events_status":"saved_selected_scope"},
        "ohlcv":{"contract_version":"review_display_v1","context":context,"records":[row],"field_meta":metadata},
        "securities":{"name_kind":"snapshot_label","name_validity":"unknown",
            "batch":{"records":[{"security_id":"synthetic:A","name":"合成示例","source_code":"000001.SZ"}]}},
        "events":{"corporate_actions":{"records":[{"security_id":"synthetic:A","event_id":"synthetic:event",
            "ex_date":"2024-01-03","cash_dividend_per_share":"0.1","process_status":"implemented"}]}}}
    view = {"run":{"contract_version":"backtest_run_v3","run_id":"synthetic:run","content_digest":"synthetic:content",
                   "committed_sequence":1,"nav":[{"nav_minor":1000000}]},
            "market":{"native_chart":{"context":{"snapshot_id":"synthetic:snapshot"}}}}
    binding = {"manifest_sha256":"a"*64,"snapshot_id":context["snapshot_id"],
               "anchor_session":context["anchor_session"],"knowledge_cutoff":context["knowledge_cutoff"],
               "run_ref":{k:view["run"][k] for k in ("run_id","content_digest","committed_sequence")}}
    return view, saved, binding


class SavedLayersTests(TestCase):
    def test_native_nulls_names_events_and_fixed_clock_without_adjustment(self):
        view, saved, binding = fixture()
        binding["run_ref"]["run_id"] = "another:account"
        with self.assertRaisesRegex(ProjectionError, "consumer/run"):
            attach_review_display(view, saved, **binding)
        view, saved, binding = fixture()
        original, run = deepcopy(saved), deepcopy(view["run"])
        attach_review_display(view, saved, **binding)
        layer = view["market"]["review_display"]
        self.assertIsNone(layer["records"][0]["close"])
        self.assertIsNone(layer["records"][0]["display_scale"])
        self.assertEqual(layer["records"][0]["native_close"], 10.2)
        self.assertEqual(layer["records"][0]["display_missing_reason"], "missing_factor")
        self.assertEqual(view["market"]["security_labels"], {"synthetic:A":"合成示例"})
        self.assertIn("historical name validity unknown", view["market"]["security_name_scope"])
        self.assertEqual(view["market"]["review_events"][0]["event"], original["events"]["corporate_actions"]["records"][0])
        self.assertEqual(saved, original)
        self.assertEqual(view["run"], run)

    def test_context_unit_and_ambiguous_name_reject(self):
        for field in ("snapshot_id", "anchor_session", "knowledge_cutoff"):
            view, saved, binding = fixture()
            binding[field] = "wrong"
            with self.subTest(field=field), self.assertRaisesRegex(ProjectionError, "CONTEXT_MISMATCH"):
                attach_review_display(view, saved, **binding)
        view, saved, binding = fixture()
        saved["ohlcv"]["field_meta"]["native_close"]["unit"] = "CNY/fund unit"
        with self.assertRaisesRegex(ProjectionError, "unit"):
            attach_review_display(view, saved, **binding)
        view, saved, binding = fixture()
        saved["securities"]["batch"]["records"].append({"security_id":"synthetic:A","name":"另一名称"})
        with self.assertRaisesRegex(ProjectionError, "ambiguous"):
            attach_review_display(view, saved, **binding)

    def test_public_saved_loader_only(self):
        view, saved, binding = fixture()
        calls, data = [], ModuleType("axiom_data")
        data.load_review_display = lambda directory, **kw:calls.append((directory, kw)) or saved
        def forbidden(*args, **kwargs):
            self.fail("UI must not query or adjust Data")
        data.Reader = data.export_review_display = data.adjust_prices = forbidden
        with patch.dict(sys.modules, {"axiom_data":data}):
            load_review_display_for_view(view, directory="explicit-saved-directory", **binding)
        self.assertEqual(calls, [("explicit-saved-directory", {"manifest_sha256":"a"*64})])
