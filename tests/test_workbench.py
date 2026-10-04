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


if __name__ == "__main__":
    unittest.main()
