"""Small display bindings only; no factor or account acceptance."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest import TestCase
from unittest.mock import patch
import sys

from axiom_ui import ProjectionError
from axiom_ui.saved_layers import (attach_fill_display, attach_review_display, load_consumer_receipt_for_view,
                                   load_review_display_for_view)


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
            "configuration":{"start_session":"2024-01-02","end_session":"2024-01-31"},
            "market":{"native_chart":{"context":{"snapshot_id":"synthetic:snapshot",
                "query":{"symbols":["synthetic:A"],"sessions":["2024-01-02"]}},
                "records":[{"security_id":"synthetic:A","session":"2024-01-02","close":10.2}],
                "field_meta":{"close":{"unit":"CNY/share"},"volume_shares":{"unit":"shares"}}}}}
    binding = {"manifest_sha256":"a"*64,"snapshot_id":context["snapshot_id"],
               "anchor_session":context["anchor_session"],"knowledge_cutoff":context["knowledge_cutoff"],
               "run_ref":{k:view["run"][k] for k in ("run_id","content_digest","committed_sequence")}}
    return view, saved, binding


class SavedLayersTests(TestCase):
    def test_etf_v5_replay_only_display_binding_uses_saved_price_scope(self):
        view, saved, binding = fixture()
        view["run"].update(contract_version="backtest_run_v5",
                           price_unit="CNY/fund unit", quantity_unit="fund units")
        source = view["market"].pop("native_chart")
        view["market"].update(rows=source["records"], source_refs=["synthetic:price"],
            source_evidence=[{"reference":"synthetic:price", "context":{
                **source["context"], "domain":"market_daily"}}])
        for key in ("open", "high", "low", "close", "native_open", "native_high",
                    "native_low", "native_close"):
            saved["ohlcv"]["field_meta"][key]["unit"] = "CNY/fund unit"
        saved["ohlcv"]["field_meta"]["volume_units"] = saved["ohlcv"]["field_meta"].pop("volume_shares")
        saved["ohlcv"]["field_meta"]["volume_units"]["unit"] = "fund units"
        saved["ohlcv"]["records"][0]["volume_units"] = saved["ohlcv"]["records"][0].pop("volume_shares")
        etf_saved = deepcopy(saved)
        attach_review_display(view, saved, **binding)
        self.assertEqual(view["market"]["review_display"]["records"][0]["volume_units"], 1000)
        saved["ohlcv"]["records"][0]["native_close"] = 99
        with self.assertRaisesRegex(ProjectionError, "display/native ETF price or volume"):
            attach_review_display(view, saved, **binding)
        view, _, binding = fixture()
        saved = etf_saved
        view["run"].update(contract_version="backtest_run_v5", price_unit="CNY/fund unit",
                           quantity_unit="fund units")
        view["market"] = {"rows": [{"security_id":"synthetic:wrong", "session":"2024-01-02"}],
            "source_refs": ["synthetic:price"], "source_evidence": [{"reference":"synthetic:price",
            "context":{"domain":"market_daily", "snapshot_id":"synthetic:snapshot"}}]}
        with self.assertRaisesRegex(ProjectionError, "scope keys"):
            attach_review_display(view, saved, **binding)

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

    def test_same_snapshot_different_scope_and_missing_whole_rows_reject(self):
        mutations = [lambda saved: saved["ohlcv"].update(records=[]),
            lambda saved: saved["ohlcv"]["records"][0].update(security_id="synthetic:other"),
            lambda saved: saved["ohlcv"]["records"][0].update(session="2024-01-03"),
            lambda saved: saved["ohlcv"]["records"].append({"security_id":"synthetic:other","session":"2024-01-02"}),
            lambda saved: saved["ohlcv"]["records"].append({"security_id":"synthetic:A","session":"2024-02-01"})]
        for index, mutate in enumerate(mutations):
            view, saved, binding = fixture()
            mutate(saved)
            with self.subTest(case=index), self.assertRaisesRegex(ProjectionError, "scope keys"):
                attach_review_display(view, saved, **binding)
        view, saved, binding = fixture()
        view["market"]["native_chart"]["field_meta"]["close"]["unit"] = "CNY/fund unit"
        with self.assertRaisesRegex(ProjectionError, "original native price"):
            attach_review_display(view, saved, **binding)

    def test_independent_labels_require_fixed_consumer_receipt_and_original_display(self):
        view, display, binding = fixture()
        old_ref = {"run_id":"synthetic:old","content_digest":"synthetic:old-content","committed_sequence":1}
        current_ref = binding["run_ref"]
        labels = {"manifest":{"contract_version":"review_security_labels_v1","usage":"retrospective_label",
            "run_ref":old_ref,"source_snapshot_id":"synthetic:labels-snapshot",
            "label_cutoff":"2024-02-03T00:00:00Z","security_ids":["synthetic:A"],
            "display_ref":{"sha256":binding["manifest_sha256"],"snapshot_id":binding["snapshot_id"],
                "anchor_session":binding["anchor_session"],"knowledge_cutoff":binding["knowledge_cutoff"]}},
            "securities":{"name_kind":"observed_label","name_valid_from":None,"name_valid_to":None,
                "batch":{"context":{"snapshot_id":"synthetic:labels-snapshot",
                    "query":{"cutoff":"2024-02-03T00:00:00Z"}},
                    "records":[{"security_id":"synthetic:A","name":"今时名称"}]}}}
        receipt = {"contract_version":"review_display_consumer_receipt_v1",
            "status":"PASSED_ACTUAL_SAVED_INPUT_EQUALITY", "current_run_ref":current_ref,
            "original_bound_run_ref":old_ref,
            "display_binding":{"directory":"fixed-display",**binding},
            "independent_labels_binding":{"directory":"fixed-labels","manifest_sha256":"b"*64,
                "original_run_ref":old_ref,"current_run_ref":current_ref,
                "source_snapshot_id":"synthetic:labels-snapshot","label_cutoff":"2024-02-03T00:00:00Z"}}
        calls, data = [], ModuleType("axiom_data")
        data.load_review_display = lambda directory, **kw:calls.append("display") or display
        data.load_review_security_labels = lambda directory, **kw:calls.append("labels") or labels
        data.Reader = lambda *a, **k:self.fail("no Data query")
        with TemporaryDirectory() as directory:
            path = Path(directory)/"receipt.json"
            def write():
                raw = json.dumps(receipt).encode()
                path.write_bytes(raw)
                return sha256(raw).hexdigest()
            digest = write()
            with patch.dict(sys.modules, {"axiom_data":data}):
                with self.assertRaisesRegex(ProjectionError, "external byte reference"):
                    load_consumer_receipt_for_view(view,receipt_path=path,receipt_sha256="0"*64)
                self.assertEqual(calls, [])
                load_consumer_receipt_for_view(view,receipt_path=path,receipt_sha256=digest)
                self.assertEqual(calls,["display","labels"])
                self.assertEqual(view["market"]["security_labels"],{"synthetic:A":"今时名称"})
                self.assertIn("historical name validity unknown",view["market"]["security_name_scope"])
                receipt["current_run_ref"]={**current_ref,"run_id":"synthetic:another"}
                with self.assertRaisesRegex(ProjectionError,"receipt/run identity"):
                    load_consumer_receipt_for_view(view,receipt_path=path,receipt_sha256=write())
                self.assertEqual(calls,["display","labels"])
                receipt["current_run_ref"]=current_ref
                labels["manifest"]["display_ref"]["sha256"]="c"*64
                with self.assertRaisesRegex(ProjectionError,"labels/original price display"):
                    load_consumer_receipt_for_view(view,receipt_path=path,receipt_sha256=write())

    def test_saved_fill_coordinates_bind_exact_original_fills_and_display(self):
        view, display, binding = fixture()
        attach_review_display(view, display, **binding)
        fill={"fill_id":"synthetic:fill","order_id":"synthetic:order","security_id":"synthetic:A",
              "session":"2024-01-02","side":"BUY","quantity":100,"price":"10.2",
              "fee_minor":5,"sequence":1}
        view["run"]["fills"]=[fill]
        report={"contract_version":"fill_display_report_v1","input_run_ref":binding["run_ref"],
                "display_ref":"sha256:"+binding["manifest_sha256"],"display_result_ref":"synthetic:result",
                "content_digest":"synthetic:digest","status":"COMPLETE","fills":[deepcopy(fill)],
                "coordinates":[{"fill_id":"synthetic:fill","security_id":"synthetic:A",
                    "session":"2024-01-02","status":"AVAILABLE","reason":None,
                    "display_price":"20.4","source_unit":"CNY/share","target_unit":"CNY/share"}]}
        attach_fill_display(view, report)
        self.assertEqual(view["market"]["fill_display"]["coordinates"][0]["display_price"],"20.4")
        self.assertEqual(view["run"]["fills"][0]["price"],"10.2")
        for key,value,reason in (("display_ref","sha256:wrong","Data display"),
                                 ("input_run_ref",{"run_id":"synthetic:wrong"},"run identity")):
            altered=deepcopy(report);altered[key]=value
            with self.assertRaisesRegex(ProjectionError,reason):attach_fill_display(view,altered)
        altered=deepcopy(report);altered["fills"][0]["price"]="999"
        with self.assertRaisesRegex(ProjectionError,"original fill link"):
            attach_fill_display(view,altered)
