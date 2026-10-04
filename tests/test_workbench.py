from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from axiom_ui import ProjectionError, render_sample_workbench, render_saved_workbench
from axiom_ui.projection import _digest

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "synthetic_workbench.json"
GENERATED = "2026-10-04T12:00:00Z"


def payload(html):
    return json.loads(re.search(r'<script type="application/json" id="workbench-data">(.*?)</script>', html, re.S)[1])


def saved_v2(entry):
    """Handwritten UI shape fixture, not an Engine evaluation or return proof."""
    run, evaluation = entry["run"], entry["evaluation"]
    run["initial_nav_minor"] = 1000000
    evaluation.update(contract_version="evaluation_report_v2", evaluation_version="axiom.evaluation/2")
    evaluation["period_metrics"] = {
        "window": {"anchor_session": "2026-03-27", "end_session": "2026-04-30",
                   "elapsed_calendar_days": 34, "day_count": "actual_actual_calendar_year_split",
                   "year_segments": [{"year": 2026, "days": 34, "year_days": 365}],
                   "year_fraction": "0.09315068493150684931506849315068493150685"},
        "account": {"cagr_status": "INSUFFICIENT_SPAN", "cagr": None,
                    "cagr_reason": "YEAR_FRACTION_BELOW_ONE", "initial_nav_minor": 1000000,
                    "final_nav_minor": run["nav"][-1]["nav_minor"],
                    "total_return": run["metrics"]["total_return"],
                    "max_drawdown": run["metrics"]["max_drawdown"]},
        "benchmark": {"cagr_status": "INSUFFICIENT_SPAN", "cagr": None,
                      "cagr_reason": "YEAR_FRACTION_BELOW_ONE", "anchor_close": "4000",
                      "end_close": "4040", "total_return": "0.01", "max_drawdown": "-0.00744"},
    }
    return evaluation


def saved_unit_run(entry):
    """Handwritten UI event-link fixture; never an Engine accounting test."""
    run = entry["run"]
    security, event_id = run["fills"][0]["security_id"], "synthetic:unit-event"
    application_session = run["positions"][-1]["session"]
    run["contract_version"] = "backtest_run_v2"
    run["plan"]["unit_split_policy"] = "etf_settled_holder_eod_v1"
    run["plan"]["market_replay"]["unit_splits"] = [{
        "event": {"event_id": event_id, "security_id": security, "effective_date": application_session,
                  "process_status": "planned", "effective_phase": "not_stated", "document_refs": "synthetic-plan"},
        "available_at": "2026-03-27T00:00:00Z", "source_refs": ["synthetic:unit-source"]}]
    run["plan"]["market_replay"].setdefault("source_evidence", []).append({
        "reference": "synthetic:unit-source", "batch": {
            "context": {"domain": "fund_share_conversions", "snapshot_id": "s_synthetic_unit",
                        "query": {"cutoff": "2026-03-27T00:00:00Z", "pit_policy": "synthetic_saved"}},
            "records": [deepcopy(run["plan"]["market_replay"]["unit_splits"][0]["event"])],
            "field_meta": {"ratio_numerator": {"by_key": [{"event_id": event_id, "status": "synthetic_saved"}]}}}})
    run["unit_split_applications"] = [{"event_id": event_id, "security_id": security,
        "session": application_session, "phase": "EOD_AFTER_CLOSE_BEFORE_NAV", "status": "APPLIED",
        "before_quantity": 100, "after_quantity": 500, "rounding_value_minor": 0,
        "original_quote": {"price": "10.0000"}, "normalized_quote": {"price": "2.0000"},
        "rounding_extra_fraction": {"numerator": 0, "denominator": 1}}]
    for position in run["positions"]:
        position["mark_basis_event_id"] = event_id if position["session"] == application_session else None
    for order in run["orders"]:
        order["announced_suspension_event_ids"] = []
    blocked = deepcopy(run["orders"][0])
    blocked.update(order_id="synthetic:announced-order", session="2026-04-01", status="EXPIRED",
                   filled_quantity=0, reason="ANNOUNCED_SUSPENSION", market_state="unknown_status",
                   state_reason="status_source_missing", announced_suspension_event_ids=[event_id])
    run["orders"].append(blocked)
    return run


def saved_stock_case(sample):
    """Handwritten stock display fixture, never a strategy or account execution."""
    entry = deepcopy(sample["runs"][0])
    run, evaluation, native = entry["run"], entry["evaluation"], entry["data_batch"]
    run.update(contract_version="backtest_run_v3", runtime_version="axiom.backtest/3",
               core_version="axiom.stock_portfolio/1", quantity_unit="shares", price_unit="CNY/share",
               admission_ref="synthetic:admission", supported_universe_ref="synthetic:supported", stopped=None)
    run["plan"].update(contract_version="backtest_request_v3", prediction_universe=["synthetic:prediction"],
                       execution_universe=["synthetic:execution"], portfolio_policy={"eligibility_id":"sz_main_a_000_002_003_v1"},
                       stock_action_policy="observed_implemented_only",
                       signal_frame={"model_ref":"synthetic:model", "feature_ref":"synthetic:feature", "score_unit":"dimensionless"},
                       admission_evidence={"model":{"snapshot":"synthetic:model-snapshot"},
                                           "execution":{"snapshot":"synthetic:execution-snapshot"}, "status":"SYNTHETIC"})
    run["plan"]["profile"].update(contract_version="stock_daily_open_profile_v1", unknown_status_policy="stock_daily_observed",
                                lot_size=100, settlement_sessions=1)
    for fill in run["fills"]:
        fill.update(quantity_unit="shares", commission_minor=fill["fee_minor"], stamp_tax_minor=0, transfer_fee_minor=0,
                    execution_admission="STOCK_OBSERVED_DAILY_ASSUMPTION")
    for row in native["records"]:
        row["volume_shares"] = row.pop("volume_units")
    native["field_meta"]["volume_shares"] = native["field_meta"].pop("volume_units")
    for key in ("open","high","low","close","volume_shares"):
        native["field_meta"][key]["unit"] = "shares" if key == "volume_shares" else "CNY/share"
    native["context"]["domain"] = "market_daily"
    native["context"]["coverage"] = {"large_table":"SYNTHETIC_HEAVY_COVERAGE"}
    source = {"reference":_digest(native), "batch":native}
    market = run["plan"]["market_replay"]
    market.update(source_refs=[source["reference"]], source_evidence=[source],
                  coverage_bundle=[{"payload":"SYNTHETIC_COMPRESSED_PAYLOAD"}])
    evaluation["benchmark_input"] = {"source_refs":[source["reference"]],"source_evidence":[source]}
    evaluation["dividend_scope"] = {"actions":[],"source_refs":[source["reference"]],"source_evidence":[source],
                                    "coverage":{"table":"SYNTHETIC_HEAVY_COVERAGE"},
                                    "coverage_bundle":[{"payload":"SYNTHETIC_COMPRESSED_PAYLOAD"}]}
    return run, evaluation, native


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.sample = json.loads(SAMPLE.read_text())

    def render(self):
        return render_sample_workbench(self.sample, generated_at=GENERATED)

    def test_precision_null_and_input_are_preserved(self):
        self.sample["runs"][0]["run"]["metrics"]["total_fees_minor"] = 9007199254740993
        before = deepcopy(self.sample)
        wire = payload(self.render())["views"][0]
        self.assertEqual(wire["run"]["metrics"]["total_fees_minor"], "9007199254740993")
        self.assertIsNone(wire["evaluation"]["monthly_returns"][0]["return"])
        self.assertIsNone(wire["evaluation"]["episodes"][1]["pending_dividend_minor"])
        self.assertEqual(wire["run"]["fills"][0]["price"], "10.00")
        self.assertIs(wire["evaluation"]["episodes"][0]["statistics_eligible"], True)
        self.assertEqual(self.sample, before)

    def test_v1_and_v2_preserve_saved_periods_null_and_independent_status(self):
        self.assertNotIn("period_metrics", payload(self.render())["views"][0]["evaluation"])
        evaluation = saved_v2(self.sample["runs"][0])
        evaluation["status"] = "COMPLETE"
        before = deepcopy(self.sample)
        projected = payload(self.render())["views"][0]["evaluation"]
        self.assertIsNone(projected["period_metrics"]["account"]["cagr"])
        self.assertEqual(projected["period_metrics"]["account"]["cagr_reason"], "YEAR_FRACTION_BELOW_ONE")
        self.assertEqual(projected["period_metrics"]["window"]["elapsed_calendar_days"], "34")
        self.assertEqual(self.sample, before)
        # Display qualification is the saved owner status, independent of PARTIAL
        # monthly/top-level output; no calculation or threshold inference in UI.
        evaluation["status"] = "PARTIAL"
        evaluation["period_metrics"]["account"].update(
            cagr_status="AVAILABLE", cagr="0.12345678901234567890123456789", cagr_reason=None)
        projected = payload(self.render())["views"][0]["evaluation"]
        self.assertEqual(projected["period_metrics"]["account"]["cagr"], "0.12345678901234567890123456789")
        self.assertIsNone(projected["period_metrics"]["benchmark"]["cagr"])

    def test_v2_rejects_malformed_periods_and_wrong_saved_endpoints(self):
        evaluation = saved_v2(self.sample["runs"][0])
        baseline = deepcopy(evaluation)
        mutations = [
            lambda e: e.pop("period_metrics"),
            lambda e: e.update(evaluation_version="axiom.evaluation/1"),
            lambda e: e["period_metrics"]["window"].update(end_session="wrong"),
            lambda e: e["period_metrics"]["account"].update(initial_nav_minor=1),
            lambda e: e["period_metrics"]["account"].update(final_nav_minor=1),
            lambda e: e["period_metrics"]["benchmark"].update(end_close="99"),
            lambda e: e["period_metrics"]["benchmark"].pop("anchor_close"),
            lambda e: e["period_metrics"]["account"].update(cagr="0"),
            lambda e: e["period_metrics"]["account"].update(cagr_status="AVAILABLE", cagr=None),
        ]
        for i, mutate in enumerate(mutations):
            with self.subTest(case=i):
                self.sample["runs"][0]["evaluation"] = deepcopy(baseline)
                mutate(self.sample["runs"][0]["evaluation"])
                with self.assertRaises(ProjectionError):
                    self.render()
        self.sample["runs"][0]["evaluation"] = deepcopy(baseline)
        e = self.sample["runs"][0]["evaluation"]
        e["benchmark"]["series"][-1].update(close=None, valid=False, missing_reason="missing close")
        e["period_metrics"]["benchmark"].update(end_close=None, cagr_status="MISSING_BOUNDARY", cagr_reason="END_CLOSE_MISSING")
        projected = payload(self.render())["views"][0]["evaluation"]
        self.assertIsNone(projected["period_metrics"]["benchmark"]["end_close"])
        self.assertEqual(projected["period_metrics"]["benchmark"]["cagr_reason"], "END_CLOSE_MISSING")
        e["contract_version"] = "evaluation_report_v1"
        with self.assertRaisesRegex(ProjectionError, "v1 must not acquire"):
            self.render()

    def test_v2_uses_same_public_loaders_without_computing_or_mutating(self):
        entry = self.sample["runs"][0]
        saved_v2(entry)
        baseline = deepcopy(entry)
        calls, runtime = [], ModuleType("axiom_engine.runtime")
        runtime.load_backtest_run = lambda path: calls.append(("load_run", str(path))) or entry["run"]
        runtime.load_backtest_evaluation = lambda path: calls.append(("load_evaluation", str(path))) or entry["evaluation"]
        def forbidden(*args, **kwargs):
            self.fail("UI must not execute or save owner computation")
        runtime.run_backtest = runtime.evaluate_backtest_run = runtime.save_backtest_evaluation = forbidden
        with patch.dict(sys.modules, {"axiom_engine.runtime": runtime}):
            html = render_saved_workbench(["run.json"], evaluation_paths=["v2.json"], generated_at=GENERATED)
        self.assertEqual(calls, [("load_run", "run.json"), ("load_evaluation", "v2.json")])
        self.assertEqual(entry, baseline)
        self.assertEqual(payload(html)["views"][0]["evaluation"]["contract_version"], "evaluation_report_v2")

    def test_unit_run_v2_preserves_saved_events_positions_orders_without_new_fills(self):
        entry = self.sample["runs"][0]
        run = saved_unit_run(entry)
        before = deepcopy(self.sample)
        projected = payload(self.render())["views"][0]
        self.assertEqual(projected["run"]["unit_split_applications"][0]["after_quantity"], "500")
        self.assertEqual(projected["run"]["unit_split_applications"][0]["normalized_quote"]["price"], "2.0000")
        self.assertEqual(projected["market"]["unit_splits"][0]["event"]["process_status"], "planned")
        self.assertEqual(projected["market"]["unit_splits"][0]["event"]["effective_phase"], "not_stated")
        evidence = projected["market"]["unit_split_source_evidence"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["batch"]["context"]["snapshot_id"], "s_synthetic_unit")
        self.assertEqual(evidence[0]["batch"]["field_meta"]["ratio_numerator"]["by_key"][0]["status"], "synthetic_saved")
        self.assertEqual(len(projected["run"]["fills"]), len(run["fills"]))
        self.assertEqual(projected["run"]["orders"][-1]["market_state"], "unknown_status")
        self.assertEqual(projected["run"]["orders"][-1]["announced_suspension_event_ids"], ["synthetic:unit-event"])
        self.assertTrue(any(p["mark_basis_event_id"] == "synthetic:unit-event" for p in projected["run"]["positions"]))
        self.assertEqual(self.sample, before)
        self.assertNotIn("unit_split_applications", payload(self.render())["views"][1]["run"])

    def test_unit_run_v2_sources_use_saved_context_and_exclude_unrelated_batches(self):
        run = saved_unit_run(self.sample["runs"][0])
        native = run["plan"]["market_replay"]["source_evidence"][-1]
        unrelated = deepcopy(native)
        unrelated["reference"] = "synthetic:unrelated-unit-source"
        run["plan"]["market_replay"]["source_evidence"].append(unrelated)
        before = deepcopy(self.sample)
        view = payload(self.render())["views"][0]
        self.assertEqual([s["reference"] for s in view["market"]["unit_split_source_evidence"]], [native["reference"]])
        facts = {f["key"]: f for f in view["comparison_conditions"]}
        self.assertIn("s_synthetic_unit", facts["snapshot_id"]["value"])
        self.assertIn({"cutoff":"2026-03-27T00:00:00Z"}, facts["query.knowledge_time"]["value"])
        self.assertEqual(self.sample, before)

    def test_unit_run_v2_rejects_unbound_event_links_and_missing_layer(self):
        run = saved_unit_run(self.sample["runs"][0])
        original = deepcopy(run)
        for field in ("unit_split_applications", "mark_basis_event_id", "announced_suspension_event_ids"):
            with self.subTest(field=field):
                self.sample["runs"][0]["run"] = deepcopy(original)
                r = self.sample["runs"][0]["run"]
                if field == "unit_split_applications":r[field][0]["event_id"] = "unbound"
                elif field == "mark_basis_event_id":r["positions"][0][field] = "unbound"
                else:r["orders"][-1][field] = ["unbound"]
                with self.assertRaisesRegex(ProjectionError, "CONTEXT_MISMATCH"):
                    self.render()
        self.sample["runs"][0]["run"] = deepcopy(original)
        del self.sample["runs"][0]["run"]["unit_split_applications"]
        with self.assertRaisesRegex(ProjectionError, "unit split applications"):
            self.render()

    def test_unit_run_v2_uses_public_loader_and_retains_v1_compatibility(self):
        v2 = saved_unit_run(self.sample["runs"][0])
        v1 = self.sample["runs"][1]["run"]
        runtime, calls = ModuleType("axiom_engine.runtime"), []
        runtime.load_backtest_run = lambda path: calls.append(str(path)) or (v2 if path == "v2.json" else v1)
        with patch.dict(sys.modules, {"axiom_engine.runtime": runtime}):
            html = render_saved_workbench(["v2.json", "v1.json"], generated_at=GENERATED)
        views = payload(html)["views"]
        self.assertEqual(calls, ["v2.json", "v1.json"])
        self.assertEqual(views[0]["run"]["contract_version"], "backtest_run_v2")
        self.assertNotIn("unit_split_applications", views[1]["run"])

    def test_json_is_inert_and_template_text_is_not_executed(self):
        text = '{{SCRIPT}}</script><script>alert("owner")</script>&'
        self.sample["runs"][0]["research"]["hypothesis"] = text
        html = self.render()
        self.assertEqual(payload(html)["views"][0]["research"]["hypothesis"], text)
        self.assertNotIn('<script>alert("owner")', html)
        self.assertEqual(html.count("<script"), 2)
        self.assertIn("connect-src 'none'", html)

    def test_evaluation_requires_exact_run_identity_refs_and_daily_watermarks(self):
        entry = self.sample["runs"][0]
        for field in ("run_id", "content_digest", "committed_sequence"):
            with self.subTest(field=field):
                changed = deepcopy(entry["evaluation"])
                entry["evaluation"]["input_run_ref"][field] = "wrong"
                with self.assertRaisesRegex(ProjectionError, "CONTEXT_MISMATCH"):
                    self.render()
                entry["evaluation"] = changed
        entry["evaluation"]["series"][0]["committed_sequence"] = 3
        with self.assertRaisesRegex(ProjectionError, "series/NAV"):
            self.render()

    def test_episode_fill_and_distribution_qualification_are_not_guessed(self):
        evaluation = self.sample["runs"][0]["evaluation"]
        evaluation["episodes"][0]["fill_refs"][0]["sequence"] = 42
        with self.assertRaisesRegex(ProjectionError, "episode/fill"):
            self.render()
        evaluation["episodes"][0]["fill_refs"][0]["sequence"] = 1
        evaluation["episodes"][0]["statistics_eligible"] = "false"
        with self.assertRaisesRegex(ProjectionError, "booleans"):
            self.render()
        evaluation["episodes"][0]["statistics_eligible"] = True
        evaluation["pnl_distribution"]["bins"] = [{"lower_minor": None, "upper_minor": 0, "count": 1}]
        with self.assertRaisesRegex(ProjectionError, "insufficient sample"):
            self.render()

    def test_data_requires_saved_query_and_common_provenance_digest(self):
        entry = self.sample["runs"][0]
        for change in (
            lambda b: b["context"]["query"].update(pit_policy="wrong"),
            lambda b: b["context"].update(reader_version="wrong"),
            lambda b: b["field_meta"]["close"]["by_key"][0].update(evidence_ref="wrong"),
            lambda b: b["records"][0].update(close="99"),
        ):
            original = deepcopy(entry["data_batch"])
            change(entry["data_batch"])
            with self.assertRaisesRegex(ProjectionError, "CONTEXT_MISMATCH"):
                self.render()
            entry["data_batch"] = original
        entry["data_batch"]["field_meta"]["high"]["unit"] = "shares"
        with self.assertRaisesRegex(ProjectionError, "unit"):
            self.render()

    def test_real_entry_rejects_raw_mappings_before_loading(self):
        with self.assertRaisesRegex(ProjectionError, "explicit paths via owner Reader"):
            render_saved_workbench([self.sample["runs"][0]["run"]])

    def test_stock_v3_public_readers_preserve_units_fees_and_project_native_evidence(self):
        run, evaluation, native = saved_stock_case(self.sample)
        before = deepcopy((run,evaluation,native));calls=[]
        runtime=ModuleType("axiom_engine.runtime")
        runtime.load_backtest_run=lambda path:calls.append(("run",str(path))) or deepcopy(run)
        runtime.load_backtest_evaluation=lambda path:calls.append(("evaluation",str(path))) or deepcopy(evaluation)
        with patch.dict(sys.modules,{"axiom_engine.runtime":runtime,"axiom_data":None}):
            html=render_saved_workbench(["stock.json"],evaluation_paths=["stock-evaluation.json"])
            view=payload(html)["views"][0]
            self.assertEqual(calls,[("run","stock.json"),("evaluation","stock-evaluation.json")])
            self.assertEqual(view["run"]["quantity_unit"],"shares")
            self.assertEqual(view["run"]["price_unit"],"CNY/share")
            self.assertEqual(view["run"]["fills"][0]["commission_minor"],str(run["fills"][0]["commission_minor"]))
            self.assertEqual(view["stock_context"]["model_snapshot"],"synthetic:model-snapshot")
            self.assertEqual(view["stock_context"]["execution_snapshot"],"synthetic:execution-snapshot")
            self.assertEqual(view["market"]["native_chart"]["source_ref"],_digest(native))
            self.assertEqual(view["market"]["native_chart"]["records"][0]["high"],native["records"][0]["high"])
            self.assertEqual(view["market"]["native_chart"]["field_meta"]["open"],native["field_meta"]["open"])
            self.assertEqual(view["evaluation"]["content_digest"],evaluation["content_digest"])
            self.assertEqual(view["evaluation"]["benchmark_input"]["source_evidence"][0]["reference"],_digest(native))
            self.assertTrue(view["evaluation"]["dividend_scope"]["display_projection"])
            self.assertNotIn("SYNTHETIC_HEAVY_COVERAGE",html)
            self.assertNotIn("SYNTHETIC_COMPRESSED_PAYLOAD",html)
            self.assertEqual((run,evaluation,native),before)
            matched=payload(render_saved_workbench(["stock.json"],data_batches={run["run_id"]:native}))["views"][0]
            self.assertTrue(matched["market"]["native_chart"]["explicit_saved_batch_matched"])
            wrong=deepcopy(native);wrong["records"][0]["high"]="synthetic:wrong-price"
            with self.assertRaisesRegex(ProjectionError,"stock saved DataBatch/native source"):
                render_saved_workbench(["stock.json"],data_batches={run["run_id"]:wrong})
            for key,value in (("quantity_unit","fund units"),("price_unit","CNY/fund unit"),("core_version","axiom.rotation/1")):
                with self.subTest(stock_tuple=key):
                    run[key]=value
                    with self.assertRaisesRegex(ProjectionError,"stock version or units"):
                        render_saved_workbench(["stock.json"])
                    run[key]=before[0][key]
            native["field_meta"]["volume_shares"]["unit"]="fund units"
            with self.assertRaisesRegex(ProjectionError,"stock OHLCV unit"):
                render_saved_workbench(["stock.json"])

    def test_stock_v3_without_high_low_keeps_saved_close_volume_fallback(self):
        run, _, native = saved_stock_case(self.sample)
        for field in ("high", "low"):
            del native["field_meta"][field]
            for row in native["records"]:
                del row[field]
        native["context"]["query"]["fields"]=["open","close","volume_shares"]
        market=run["plan"]["market_replay"]
        market["source_evidence"][0]["reference"]=_digest(native)
        market["source_refs"]=[_digest(native)]
        market["rows"]=[{k:row[k] for k in ("security_id","session","open","close","volume_shares")}
                        for row in native["records"]]
        before=deepcopy(run)
        runtime=ModuleType("axiom_engine.runtime")
        runtime.load_backtest_run=lambda path:deepcopy(run)
        with patch.dict(sys.modules,{"axiom_engine.runtime":runtime,"axiom_data":None}):
            html=render_saved_workbench(["stock-close-volume.json"])
            view=payload(html)["views"][0]
            self.assertIsNone(view["market"]["native_chart"])
            self.assertIsNone(view["market"]["data_batch"])
            self.assertEqual(view["market"]["rows"][0]["close"],native["records"][0]["close"])
            self.assertEqual(view["market"]["rows"][0]["volume_shares"],str(native["records"][0]["volume_shares"]))
            self.assertEqual(view["run"]["nav"][-1]["nav_minor"],str(run["nav"][-1]["nav_minor"]))
            self.assertIn("K线暂未提供，当前仅显示保存的收盘价与全天量。",html)
            self.assertNotIn("high",view["market"]["rows"][0])
            self.assertNotIn("low",view["market"]["rows"][0])
            self.assertEqual(run,before)
            matched=payload(render_saved_workbench(["stock-close-volume.json"],data_batches={run["run_id"]:native}))["views"][0]
            self.assertTrue(matched["market"]["explicit_saved_batch_matched"])
            self.assertIsNone(matched["market"]["native_chart"])
            wrong=deepcopy(native);wrong["records"][0]["close"]="synthetic:changed"
            with self.assertRaisesRegex(ProjectionError,"stock saved DataBatch/native source identity"):
                render_saved_workbench(["stock-close-volume.json"],data_batches={run["run_id"]:wrong})
            # A missing optional field must not excuse wrong units on provided fields.
            for field in ("open","close","volume_shares","high"):
                with self.subTest(provided_field=field):
                    original=deepcopy(native["field_meta"].get(field))
                    native["field_meta"][field]={"unit":"fund units"}
                    with self.assertRaisesRegex(ProjectionError,"stock OHLCV unit"):
                        render_saved_workbench(["stock-close-volume.json"])
                    if original is None:
                        del native["field_meta"][field]
                    else:
                        native["field_meta"][field]=original

    def test_stock_ml_public_readers_bind_registration_without_account_outputs(self):
        experiment = {"contract_version":"stock_ml_experiment_v1", "account_status":"BLOCKED_PENDING_STOCK_RUNTIME_ADMISSION",
                      "account_reason":"synthetic owner reason", "definition":{"config":{"prediction_sessions":["2026-01-02","2026-01-05"]}}}
        keys = {"StockMLExperiment":"experiment_ref", "FeatureBuild":"feature_ref", "LabelBuild":"label_ref",
                "TrainingDataset":"dataset_ref", "ModelRelease":"model_ref", "SignalRun":"signal_run_ref", "SignalEvidence":"evidence_ref"}
        experiment.update({key:"synthetic:"+key for key in keys.values()})
        model = {"contract_version":"stock_model_release_v1", "model_ref":experiment["model_ref"],
                 "fit_cutoff":"2025-12-31T12:30:00Z", "ordered_features":["synthetic:feature"],
                 "label_normalization":{"params":{"ddof":0,"clip":None}}}
        evidence = {"contract_version":"stock_signal_evidence_v1", "evidence_ref":experiment["evidence_ref"],
                    "signal_ref":experiment["signal_run_ref"], "series":[{"session":"2026-01-02","ic":-0.125,
                    "rank_ic":None,"valid_pair_count":20,"reason":None}]}
        record = {"run_record_ref":"synthetic:stock-record", "question_id":"stock-q", "version_ref":"stock-v", "status":"COMPLETE",
                  "backtest_ref":None,"evaluation_ref":None,"run_kind":"REGISTRATION_ONLY",
                  "output_refs":[{"artifact_type":kind,"artifact_id":experiment[key]} for kind,key in keys.items()]}
        projection = {"contract_version":"experiment_projection_v1", "questions":[{
            "question":{"question_id":"stock-q","title":"Synthetic stock study"}, "organization":{},
            "saved_backtest_count":0,"registration_count":1,
            "versions":[{"question_id":"stock-q","version_ref":"stock-v"}],"runs":[record]}]}
        before = deepcopy((experiment,model,evidence,projection));calls=[]
        class Reader:
            def __init__(self,path):calls.append(("index",str(path)))
            def index(self):return deepcopy(projection)
        class Saved:
            def to_dict(self):return deepcopy(experiment)
            def evidence(self):calls.append(("evidence",));return deepcopy(evidence)
        research=ModuleType("axiom_research");research.ExperimentReader=Reader
        research.load_stock_ml_experiment=lambda path:calls.append(("stock",str(path))) or Saved()
        research.load_stock_model=lambda path:calls.append(("model",str(path))) or deepcopy(model)
        with patch.dict(sys.modules,{"axiom_research":research,"axiom_engine.runtime":None}):
            html=render_saved_workbench([],experiment_index_path="stock-index.json",stock_ml_paths=["stock-dir"],generated_at=GENERATED)
            view=payload(html)["views"][0]
            self.assertIsNone(view["run"]["run_id"])
            self.assertIsNone(view["run"]["nav"])
            self.assertIsNone(view["run"]["fills"])
            self.assertIsNone(view["run"]["metrics"])
            self.assertEqual(view["stock_ml"]["experiment"]["account_status"],experiment["account_status"])
            self.assertEqual(view["stock_ml"]["signal_evidence"]["series"][0]["ic"],-0.125)
            self.assertIsNone(view["stock_ml"]["signal_evidence"]["series"][0]["rank_ic"])
            self.assertEqual(view["research"]["saved_backtest_count"],"0")
            self.assertEqual((experiment,model,evidence,projection),before)
            self.assertEqual(calls,[("index","stock-index.json"),("stock","stock-dir"),("model","stock-dir"),("evidence",)])
            report = {"contract_version":"stock_stage_report_v1", "report_version":"axiom.stock_stage_report/1",
                      "stage_report_ref":"synthetic:report", "content_digest":"synthetic:report-content",
                      "input_refs":{key:experiment[key] for key in keys.values() if key != "label_ref"},
                      "training":{"declared":{"session_count":2},"actual":{"first_feature_session":"2025-12-29",
                                  "last_feature_session":"2025-12-29","session_count":1,"training_row_count":20}},
                      "signal_summary":{"ic":{"session_count":0,"mean":None},"rank_ic":{"session_count":1,"mean":-0.2}},
                      "measurements":[{"stage":"feature","mode":"saved_input_build","status":"REUSED_NOT_EXECUTED",
                                       "seconds":None,"reported_seconds":0,"inherited_feature_only":False},
                                      {"stage":"total","mode":"saved_input_build","status":"NOT_PROVIDED",
                                       "seconds":None,"reported_seconds":None,"receipt_file_digest":None,
                                       "observation":None,"inherited_feature_only":False}]}
            report_before=deepcopy(report)
            research.load_stock_stage_report=lambda path:calls.append(("stage-report",str(path))) or deepcopy(report)
            kwargs={"experiment_index_path":"stock-index.json","stock_ml_paths":["stock-dir"],"stock_stage_report_paths":["report.json"],"generated_at":GENERATED}
            attached=payload(render_saved_workbench([],**kwargs))["views"][0]["stock_ml"]["stage_report"]
            self.assertIsNone(attached["signal_summary"]["ic"]["mean"])
            self.assertEqual(attached["signal_summary"]["rank_ic"]["mean"],-0.2)
            self.assertEqual(attached["training"]["actual"]["training_row_count"],"20")
            self.assertIsNone(attached["measurements"][0]["seconds"])
            self.assertEqual(attached["measurements"][0]["reported_seconds"],"0")
            self.assertIsNone(attached["measurements"][1]["receipt_file_digest"])
            self.assertIsNone(attached["measurements"][1]["observation"])
            self.assertEqual(report,report_before)
            for key in report["input_refs"]:
                with self.subTest(stage_input=key):
                    report["input_refs"][key]="synthetic:wrong"
                    with self.assertRaisesRegex(ProjectionError,"CONTEXT_MISMATCH"):
                        render_saved_workbench([],**kwargs)
                    report["input_refs"][key]=report_before["input_refs"][key]
            with self.assertRaisesRegex(ProjectionError,"duplicate stock stage report"):
                render_saved_workbench([],**{**kwargs,"stock_stage_report_paths":["report.json","report.json"]})
            with self.assertRaisesRegex(ProjectionError,"explicitly loaded stock ML"):
                render_saved_workbench([],experiment_index_path="stock-index.json",stock_stage_report_paths=["report.json"])
            from axiom_ui.__main__ import main
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/"stock.html"
                args=["axiom-ui","--workbench","--experiment-index","stock-index.json","--stock-ml","stock-dir","--stock-stage-report","report.json","--output",str(output)]
                with patch.object(sys,"argv",args),patch("builtins.print"):
                    main()
                self.assertEqual(payload(output.read_text())["views"][0]["stock_ml"]["stage_report"]["stage_report_ref"],report["stage_report_ref"])
            stock_run, _, _ = saved_stock_case(self.sample)
            stock_run["signal_ref"] = experiment["signal_run_ref"]
            stock_run["plan"]["signal_frame"].update(
                feature_ref=experiment["feature_ref"], model_ref=experiment["model_ref"])
            record["backtest_ref"] = {k:stock_run[k] for k in ("run_id","content_digest","signal_ref","committed_sequence")}
            record["run_kind"] = "SAVED_BACKTEST"
            runtime = ModuleType("axiom_engine.runtime")
            runtime.load_backtest_run = lambda path:deepcopy(stock_run)
            with patch.dict(sys.modules,{"axiom_engine.runtime":runtime}):
                actual=payload(render_saved_workbench(["stock-run.json"],**kwargs))["views"][0]
                self.assertEqual(actual["run"]["status"],stock_run["status"])
                self.assertEqual(actual["stock_ml"]["experiment"]["account_status"],experiment["account_status"])
                for key in ("feature_ref","model_ref"):
                    with self.subTest(account_input=key):
                        stock_run["plan"]["signal_frame"][key]="synthetic:wrong"
                        with self.assertRaisesRegex(ProjectionError,"stock account/model inputs"):
                            render_saved_workbench(["stock-run.json"],**kwargs)
                        stock_run["plan"]["signal_frame"][key]=experiment[key]
                stock_run["signal_ref"]="synthetic:wrong-signal"
                record["backtest_ref"]["signal_ref"]=stock_run["signal_ref"]
                with self.assertRaisesRegex(ProjectionError,"stock account/model inputs"):
                    render_saved_workbench(["stock-run.json"],**kwargs)
            record["backtest_ref"]=None
            record["run_kind"]="REGISTRATION_ONLY"
            record["output_refs"][3]["artifact_id"]="wrong"
            with self.assertRaisesRegex(ProjectionError,"stock ML registration"):
                render_saved_workbench([],experiment_index_path="stock-index.json",stock_ml_paths=["stock-dir"])
            record["output_refs"]=[]
            with self.assertRaisesRegex(ProjectionError,"without registered"):
                render_saved_workbench([],experiment_index_path="stock-index.json",stock_ml_paths=["stock-dir"])
        with self.assertRaisesRegex(ProjectionError,"explicit Research index"):
            render_saved_workbench([],stock_ml_paths=["stock-dir"])

    def test_public_readers_bind_catalog_failed_unrun_and_parent_diff(self):
        run = deepcopy(self.sample["runs"][0]["run"])
        evaluation = deepcopy(self.sample["runs"][0]["evaluation"])
        runtime = ModuleType("axiom_engine.runtime")
        calls = []
        runtime.load_backtest_run = lambda path: (calls.append(("run", str(path))) or run)
        runtime.load_backtest_evaluation = lambda path: (calls.append(("evaluation", str(path))) or evaluation)
        question = {"question_id":"q", "question_ref":"qref", "title":"saved title", "hypothesis":"saved hypothesis"}
        versions = [{"question_id":"q", "version_ref":ref, "label":ref, "parent_version_ref":parent,
                     "parameters":{}, "input_refs":{}, "explicit_changes":[ref], "created_at":"2026-10-04T00:00:00Z"}
                    for ref, parent in [("v1",None),("v2","v1"),("v3","v2")]]
        records = [{"run_record_ref":"record1", "question_id":"q", "version_ref":"v1", "status":"COMPLETE",
                    "organization":{"revision":1,"favorite":False,"shelved":True},
                    "evaluation_ref":{"evaluation_ref":evaluation["evaluation_ref"],"evaluation_content_digest":evaluation["content_digest"],"input_run_ref":evaluation["input_run_ref"]},
                    "backtest_ref":{k:run[k] for k in ("run_id","content_digest","signal_ref","committed_sequence")}},
                   {"run_record_ref":"record2", "question_id":"q", "version_ref":"v2", "status":"FAILED", "reason":"saved failure", "organization":{"revision":1,"favorite":True,"shelved":False}}]
        catalog = {"contract_version":"experiment_projection_v1", "store_revision":1, "content_digest":"index_digest",
                   "questions":[{"question":question,"organization":{"revision":0,"tags":["ETF"],"favorite":True,"shelved":False},"versions":versions,"runs":records}]}
        class Reader:
            def __init__(self, path): calls.append(("index", str(path)))
            def index(self): return deepcopy(catalog)
            def compare_versions(self, left, right):
                calls.append(("compare",left,right))
                return {"left_ref":left,"right_ref":right,"explicit_changes":["saved"]}
        research = ModuleType("axiom_research")
        research.ExperimentReader = Reader
        with patch.dict(sys.modules, {"axiom_engine.runtime":runtime,"axiom_research":research}):
            html = render_saved_workbench(["run.json"], evaluation_paths=["evaluation.json"], experiment_index_path="index.json", generated_at=GENERATED)
            views = payload(html)["views"]
            self.assertEqual(len(views), 3)
            self.assertEqual(views[0]["run"]["run_id"], run["run_id"])
            self.assertIsNone(views[1]["run"]["run_id"])
            self.assertIsNone(views[1]["run"]["metrics"])
            self.assertEqual(views[1]["research"]["reason"], "saved failure")
            self.assertFalse(views[0]["research"]["favorite"])
            self.assertTrue(views[0]["research"]["shelved"])
            self.assertTrue(views[1]["research"]["favorite"])
            self.assertTrue(views[2]["research"]["not_run"])
            self.assertEqual(views[1]["research"]["version_comparison"]["explicit_changes"], ["saved"])
            self.assertIn(("compare","v1","v2"), calls)
            records[0]["evaluation_ref"]["evaluation_ref"] = "not-loaded-historical-evaluation"
            historical = payload(render_saved_workbench(["run.json"], evaluation_paths=["evaluation.json"], experiment_index_path="index.json"))["views"]
            self.assertIsNone(historical[0]["evaluation"])
            self.assertEqual(historical[-1]["evaluation"]["evaluation_ref"], evaluation["evaluation_ref"])
            records[0]["evaluation_ref"]["evaluation_ref"] = evaluation["evaluation_ref"]
            records[0]["evaluation_ref"]["evaluation_content_digest"] = "wrong"
            with self.assertRaisesRegex(ProjectionError, "evaluation reference"):
                render_saved_workbench(["run.json"], evaluation_paths=["evaluation.json"], experiment_index_path="index.json")
            records[0]["evaluation_ref"]["evaluation_content_digest"] = evaluation["content_digest"]
            batch = deepcopy(self.sample["runs"][0]["data_batch"])
            records[0]["output_refs"] = [{"artifact_type":"DataBatch","artifact_id":_digest(batch)}]
            matching = payload(render_saved_workbench(["run.json"], experiment_index_path="index.json", data_batches={run["run_id"]:batch}))["views"]
            self.assertEqual(matching[0]["market"]["data_batch"]["records"][0]["high"], "10.10")
            batch["records"][0]["high"] = "99.00"
            with self.assertRaisesRegex(ProjectionError, "Research/DataBatch identity"):
                render_saved_workbench(["run.json"], experiment_index_path="index.json", data_batches={run["run_id"]:batch})
            records[0]["output_refs"] = []
            records[0]["backtest_ref"]["content_digest"] = "wrong"
            with self.assertRaisesRegex(ProjectionError, "Research/Engine"):
                render_saved_workbench(["run.json"], experiment_index_path="index.json")
            with self.assertRaisesRegex(ProjectionError, "unknown synthetic"):
                render_saved_workbench(["run.json"], synthetic_run_ids=["unknown"])

    def test_cli_refuses_overwrite_and_keeps_source_bytes(self):
        before = SAMPLE.read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "workbench.html"
            command = [sys.executable,"-m","axiom_ui",str(SAMPLE),"--sample","--workbench","--output",str(output)]
            first = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            saved = output.read_bytes()
            self.assertEqual(subprocess.run(command,capture_output=True).returncode, 2)
            self.assertEqual(output.read_bytes(), saved)
        self.assertEqual(SAMPLE.read_bytes(), before)

    def test_grouped_saved_run_keeps_registration_history_separate(self):
        run = deepcopy(self.sample["runs"][0]["run"])
        old = deepcopy(self.sample["runs"][0]["evaluation"])
        new = deepcopy(old)
        new.update(evaluation_ref="synthetic:new-evaluation", content_digest="synthetic:new-digest")
        runtime = ModuleType("axiom_engine.runtime")
        runtime.load_backtest_run = lambda path: run
        runtime.load_backtest_evaluation = lambda path: new if path == "new.json" else old
        ref = {k:run[k] for k in ("run_id","content_digest","signal_ref","committed_sequence")}
        def registration(name, evaluation):
            return {"run_record_ref":name,"question_id":"q","version_ref":"v1","status":"COMPLETE",
                    "backtest_ref":ref,"created_at":"2026-10-04T00:00:00Z","output_refs":[],
                    "evaluation_ref":{"evaluation_ref":evaluation["evaluation_ref"],"evaluation_content_digest":evaluation["content_digest"],"input_run_ref":evaluation["input_run_ref"]}}
        before = registration("old-registration",old)
        after = registration("new-registration",new)
        after["version_ref"] = "v2"
        group = {**after,"saved_run_ref":"synthetic:saved-run","run_kind":"SAVED_BACKTEST",
                 "registration_history":[before,after],"organization":{"revision":2,"favorite":True,"shelved":False}}
        item = {"question":{"question_id":"q","created_at":"2026-10-04T00:00:00Z"},
                "organization":{},"last_activity_at":"2026-10-04T00:00:00Z","saved_backtest_count":1,"registration_count":2,
                "versions":[{"question_id":"q","version_ref":"v1","label":"original"},
                            {"question_id":"q","version_ref":"v2","label":"revision","parent_version_ref":"v1"}],"runs":[group]}
        class Reader:
            def __init__(self, path): pass
            def index(self): return {"contract_version":"experiment_projection_v1","questions":[deepcopy(item)]}
            def compare_versions(self, left, right): return {"left_version_ref":left,"right_version_ref":right,"explicit_changes":["saved explanation"]}
        research = ModuleType("axiom_research")
        research.ExperimentReader = Reader
        with patch.dict(sys.modules,{"axiom_engine.runtime":runtime,"axiom_research":research}):
            views = payload(render_saved_workbench(["run.json"],evaluation_paths=["new.json","old.json"],experiment_index_path="index.json"))["views"]
            self.assertEqual(len(views),1)
            self.assertFalse(views[0]["research"]["not_run"])
            self.assertEqual(views[0]["research"]["version_id"],"v2")
            self.assertIsNone(views[0]["research_version_comparisons"]["v1"])
            self.assertEqual(views[0]["research_version_comparisons"]["v2"]["right_version_ref"],"v2")
            self.assertEqual(views[0]["research"]["saved_backtest_count"],"1")
            self.assertEqual(views[0]["research"]["registration_count"],"2")
            self.assertEqual(views[0]["evaluation"]["evaluation_ref"],new["evaluation_ref"])
            self.assertEqual([h["evaluation"]["evaluation_ref"] for h in views[0]["registration_history"]],[old["evaluation_ref"],new["evaluation_ref"]])
            before["evaluation_ref"]["evaluation_content_digest"] = "wrong"
            with self.assertRaisesRegex(ProjectionError,"history/evaluation"):
                render_saved_workbench(["run.json"],evaluation_paths=["new.json","old.json"],experiment_index_path="index.json")
            item["versions"],item["runs"] = [],[]
            empty = payload(render_saved_workbench([],experiment_index_path="index.json"))["views"]
            self.assertTrue(empty[0]["research"]["no_version"])
            self.assertIsNone(empty[0]["run"]["run_id"])

    def test_comparison_conditions_exclude_identities_and_retain_missing_policies(self):
        from axiom_ui.workbench import _run
        original = deepcopy(self.sample["runs"][0]["run"])
        changed = deepcopy(original)
        changed.update(signal_ref="synthetic:other-strategy",account_id="other-account",profile_ref="other-profile-identity")
        before = _run(original,"synthetic_ui_fixture")["comparison_conditions"]
        after = _run(changed,"synthetic_ui_fixture")["comparison_conditions"]
        self.assertEqual(before,after)
        changed["plan"]["profile"]["lot_size"] = 1
        after = _run(changed,"synthetic_ui_fixture")["comparison_conditions"]
        self.assertEqual([a["label"] for a,b in zip(before,after) if a!=b],["委托单位"])
        missing = next(a for a in before if a["key"]=="profile.commission_rate")
        self.assertFalse(missing["provided"])
        self.assertIsNone(missing["value"])
        changed = deepcopy(original)
        source = changed["plan"]["market_replay"]["source_evidence"][0]["context"]
        source["reader_version"] = "other-reader"
        source["query"]["cutoff_by_session"]["2026-03-30"] = "2026-03-30T01:00:00Z"
        after = _run(changed,"synthetic_ui_fixture")["comparison_conditions"]
        self.assertEqual([a["label"] for a,b in zip(before,after) if a!=b],
                         ["数据读取版本","知识截止与逐日政策"])


if __name__ == "__main__":
    unittest.main()
