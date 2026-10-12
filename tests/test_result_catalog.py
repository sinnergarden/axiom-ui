"""Small synthetic Research v2 discovery and fixed owner Reader tests."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from axiom_ui.result_catalog import (STOCK_LIMITS, ResultCatalogError, _engine_limits,
                                     _artifact_summary, _detail, _engine_nested_artifact,
                                     _relative_file, open_result_detail, refresh_result_catalog)
from axiom_ui.__main__ import main
from axiom_ui.result_server import build_result_server


def digest(seed):
    return "sha256:" + sha256(seed.encode()).hexdigest()


class CatalogTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.research = self.root / "research"
        self.engine = self.root / "engine"
        self.output = self.root / "ui"
        self.research.mkdir()
        self.engine.mkdir()
        (self.research / "index.json").write_text("{}")
        self.run_id = digest("one account")
        self.eval_id = digest("evaluation")
        self.run_digest = digest("run content")
        self.eval_digest = digest("eval content")
        self.run_ref = {"run_id": self.run_id, "content_digest": self.run_digest,
                        "committed_sequence": 7}
        self.run2_id = digest("second account")
        self.run2_digest = digest("second run content")
        self.run2_ref = {"run_id": self.run2_id, "content_digest": self.run2_digest,
                         "committed_sequence": 9}
        self.shared_signal = digest("shared-signal")
        self.signal_input = digest("engine-prediction-input")
        self.market_ref = digest("market")
        self.profile_ref = digest("profile")
        self.signal_eval_id = digest("signal-evaluation")
        self.signal_eval_digest = digest("signal-evaluation-content")
        self.run_wire = {"contract_version": "backtest_run_v8", "run_id": self.run_id,
                         "content_digest": self.run_digest,
                         "committed_sequence": 7, "status": "COMPLETE",
                         "signal_ref": self.signal_input, "market_ref": self.market_ref,
                         "profile_ref": self.profile_ref,
                         "request_manifest": {"portfolio_policy": {"strategy_spec": {
                             "selection": "top_k", "top_k": 5}}},
                         "metrics": {"total_return": "0.1", "max_drawdown": "-0.05",
                                     "total_fees_minor": 123}}
        self.eval_wire = {"contract_version": "evaluation_report_v3",
                          "evaluation_ref": self.eval_id, "content_digest": self.eval_digest,
                          "status": "COMPLETE", "input_run_ref": self.run_ref,
                          "signal_ref": self.signal_input, "market_ref": self.market_ref,
                          "profile_ref": self.profile_ref,
                          "period_metrics": {"account": {"cagr": None,
                                                         "cagr_reason": "INSUFFICIENT_SPAN"}}}
        self.signal_eval_wire = {"contract_version": "stock_signal_evidence_v8",
                                 "evidence_ref": self.signal_eval_id,
                                 "content_digest": self.signal_eval_digest,
                                 "status": "COMPLETE", "summary": {"mean_ic": "0.03",
                                 "mean_rank_ic": "0.04", "valid_ic_session_count": 10,
                                 "valid_rank_ic_session_count": 9}}
        self.manifests = {}
        self.heads = []
        self.owner_calls = []
        self.result_calls = []
        self.signal_calls = []

    def artifact(self, key, kind, identity, content, filename, contract="v1"):
        (self.engine / filename).write_text("{}")
        return {"artifact_key": key, "owner": "Engine", "artifact_type": kind,
                "artifact_id": identity, "artifact_contract_version": contract,
                "content_digest": content, "root_id": "engine", "relative_path": filename}

    def add(self, name, question, version, status="COMPLETE", revision=0, accounts=None,
            artifacts=None, signals=None, reason=None):
        result_id = digest(name)
        manifest_digest = digest(name + ":" + str(revision))
        manifest = {"contract_version": "experiment_result_manifest_v1", "result_id": result_id,
                    "question_id": question, "version_ref": version, "revision": revision,
                    "status": status, "reason": reason, "content_digest": manifest_digest,
                    "artifacts": artifacts or [], "accounts": accounts or [], "signals": signals or [],
                    "folds": []}
        head = {k: manifest[k] for k in ("result_id", "question_id", "version_ref", "revision",
                                         "status", "reason")}
        head.update(manifest_ref={"root_id": "research", "relative_path": name + ".json",
                                  "content_digest": manifest_digest}, updated_at="2026-10-11T00:00:00Z")
        (self.research / (name + ".json")).write_text("{}")
        self.manifests[result_id] = manifest
        self.heads.append(head)
        return head

    def refresh(self, open_id=None, action=None):
        outer = self

        class Reader:
            def __init__(self, path):
                assert path == (outer.research / "index.json").resolve()

            def index(self):
                return {"contract_version": "experiment_projection_v2", "store_revision": 4,
                        "content_digest": digest("index"), "result_heads": outer.heads,
                        "questions": [{"question": {"question_id": "q1", "title": "问题一"},
                                       "versions": [{"version_ref": "v1", "label": "初版"},
                                                    {"version_ref": "v2", "label": "修订"}]},
                                      {"question": {"question_id": "q2", "title": "问题二"},
                                       "versions": [{"version_ref": "v3", "label": "另一版本"}]}]}

            def result(self, result_id, *, roots):
                outer.result_calls.append(result_id)
                assert roots == {"research": outer.research.resolve(),
                                 "engine": outer.engine.resolve()}
                return outer.manifests[result_id]

        research = ModuleType("axiom_research")
        research.ExperimentReader = Reader
        def signal_loader(path, *, research_root):
            outer.signal_calls.append((path, research_root))
            return outer.signal_eval_wire
        research.load_stock_signal_evaluation = signal_loader
        engine = ModuleType("axiom_engine")
        runtime = ModuleType("axiom_engine.runtime")

        def run_loader(path, *, artifact_reader, limits):
            outer.owner_calls.append(("run", path))
            assert limits["max_result_bytes"] > 0
            wire = (outer.run_wire if path.name == "run.json" else
                    {"contract_version": "backtest_run_v8", "run_id": outer.run2_id,
                     "content_digest": outer.run2_digest,
                     "committed_sequence": 9, "status": "COMPLETE",
                     "signal_ref": outer.signal_input, "market_ref": outer.market_ref,
                     "profile_ref": outer.profile_ref,
                     "request_manifest": {"portfolio_policy": {"strategy_spec": {
                         "selection": "rank_buffer", "top_k": 5,
                         "rank_buffer": {"keep_rank": 10}}}},
                     "metrics": {"total_return": "0.05", "max_drawdown": "-0.02",
                                 "total_fees_minor": 456}})
            return SimpleNamespace(wire=wire, rows={"nav": [{"nav_minor": 110000}]})

        def evaluation_loader(path):
            outer.owner_calls.append(("evaluation", path))
            return outer.eval_wire

        runtime.load_stock_backtest_projection = run_loader
        runtime.load_backtest_evaluation = evaluation_loader
        with patch.dict(sys.modules, {"axiom_research": research, "axiom_engine": engine,
                                      "axiom_engine.runtime": runtime}):
            if action is not None:
                return action()
            if open_id is not None:
                return open_result_detail(research_root=self.research, engine_root=self.engine,
                                          output_dir=self.output, result_id=open_id)
            return refresh_result_catalog(research_root=self.research, engine_root=self.engine,
                                          output_dir=self.output, generated_at="2026-10-11T00:00:00Z")

    def test_multiple_ideas_versions_accounts_and_append_revision(self):
        run = self.artifact("run-a", "BacktestRun", self.run_id, self.run_digest,
                            "run.json", "backtest_run_v8")
        run2 = self.artifact("run-b", "BacktestRun", self.run2_id, self.run2_digest,
                             "run-b.json", "backtest_run_v8")
        report = self.artifact("eval-a", "BacktestEvaluation", self.eval_id,
                               self.eval_digest, "eval.json", "evaluation_report_v3")
        (self.research / "signal-eval.json").write_text("{}")
        signal_eval = {"artifact_key": "signal-eval", "owner": "Research",
                       "artifact_type": "StockSignalEvaluation",
                       "artifact_id": self.signal_eval_id,
                       "artifact_contract_version": "stock_signal_evidence_v8",
                       "content_digest": self.signal_eval_digest,
                       "root_id": "research", "relative_path": "signal-eval.json"}
        account = {"strategy_ref": digest("strategy-a"), "signal_run_ref": self.shared_signal,
                   "status": "COMPLETE", "reason": None,
                   "backtest_ref": {"artifact_key": "run-a", **self.run_ref},
                   "evaluation_refs": [{"artifact_key": "eval-a", "evaluation_ref": self.eval_id,
                                        "content_digest": self.eval_digest,
                                        "input_run_ref": self.run_ref}]}
        account2 = {"strategy_ref": digest("strategy-b"), "signal_run_ref": self.shared_signal,
                    "status": "COMPLETE", "reason": None,
                    "backtest_ref": {"artifact_key": "run-b", **self.run2_ref},
                    "evaluation_refs": []}
        first_head = self.add("r1", "q1", "v1", accounts=[account, account2],
                 artifacts=[run, run2, report, signal_eval],
                 signals=[{"signal_run_ref": self.shared_signal, "status": "COMPLETE",
                           "evaluation_artifact_keys": ["signal-eval"]},
                          {"signal_run_ref": digest("signal-b"), "status": "PARTIAL",
                           "reason": "评价未提供", "evaluation_artifact_keys": []}])
        self.add("r2", "q1", "v2", status="PARTIAL", reason="评价未齐")
        self.add("r3", "q2", "v3", status="BLOCKED", reason="输入不足")
        first = self.refresh()
        self.assertEqual(first["result_count"], 3)
        self.assertIsNone(first["verified_saved_backtest_count"])
        html = (self.output / "index.html").read_text()
        self.assertIn("问题一", html)
        self.assertIn("问题二", html)
        self.assertIn("BLOCKED", html)
        self.assertIn("已验证保存回测：详情待读取", html)
        self.assertNotIn(str(self.engine), html)
        self.assertEqual(len(self.owner_calls), 0)
        self.assertEqual(self.result_calls, [])
        opened = self.refresh(open_id=first_head["result_id"])
        self.assertEqual((opened["availability"], opened["verified_saved_backtest_count"]),
                         ("MANIFEST_VERIFIED", 2))
        self.assertEqual(len(self.owner_calls), 3)
        self.assertEqual(len(self.signal_calls), 1)
        self.assertEqual(self.signal_calls[0][1], self.research.resolve())
        detail = Path(opened["output_file"]).read_text()
        self.assertIn("策略：top_k · Top 5", detail)
        self.assertIn("策略：rank_buffer · Top 5 · keep_rank 10", detail)
        self.assertGreaterEqual(detail.count(self.shared_signal), 3)
        self.assertIn("累计收益 · 原回测", detail)
        self.assertIn("10%", detail)
        self.assertIn("平均 IC", detail)
        self.assertIn("0.03", detail)
        self.assertIn("INSUFFICIENT_SPAN", detail)
        self.assertEqual(self.result_calls, [first_head["result_id"]])
        self.eval_wire["market_ref"] = digest("other-market")
        mismatched = Path(self.refresh(open_id=first_head["result_id"])["output_file"]).read_text()
        self.assertIn("CONTEXT_MISMATCH", mismatched)
        self.assertNotIn("10%", mismatched)
        self.assertIn("5%", mismatched)
        self.eval_wire["market_ref"] = self.market_ref
        (self.engine / "run.json").unlink()
        missing_run = Path(self.refresh(open_id=first_head["result_id"])["output_file"]).read_text()
        self.assertIn("账户保存件未提供", missing_run)
        self.assertNotIn("CONTEXT_MISMATCH", missing_run)
        self.assertNotIn("10%", missing_run)
        self.assertIn("5%", missing_run)
        self.assertIn("保存账户或评价不可用，指标暂不展示", missing_run)
        (self.engine / "run.json").write_text("{}")
        second = self.refresh()
        self.assertEqual(first["index_sha256"], second["index_sha256"])
        self.heads[0]["revision"] = 1
        self.heads[0]["manifest_ref"]["content_digest"] = digest("r1:1")
        self.manifests[self.heads[0]["result_id"]]["revision"] = 1
        self.manifests[self.heads[0]["result_id"]]["content_digest"] = digest("r1:1")
        third = self.refresh()
        self.assertEqual(third["result_count"], 3)
        self.assertIn("登记修订 4", (self.output / "index.html").read_text())

    def test_missing_owner_is_visible_and_path_escape_refused(self):
        missing = {"artifact_key": "missing", "owner": "Engine", "artifact_type": "BacktestRun",
                   "artifact_id": self.run_id, "artifact_contract_version": "backtest_run_v8",
                   "content_digest": self.run_digest, "root_id": "engine", "relative_path": "missing.json"}
        head = self.add("lost", "q1", "v1", artifacts=[missing])
        self.refresh()
        self.refresh(open_id=head["result_id"])
        filename = "result-" + head["result_id"][7:] + "-" + head["manifest_ref"]["content_digest"][7:19] + ".html"
        self.assertIn("UNAVAILABLE", (self.output / filename).read_text())
        with self.assertRaises(ResultCatalogError):
            _relative_file(dict(missing, relative_path="../outside.json"),
                           {"engine": self.engine})
        outside = self.root / "outside.json"
        outside.write_text("{}")
        with self.assertRaises(ResultCatalogError):
            _engine_nested_artifact({"manifest_uri": str(outside)}, self.engine)

    def test_derived_signal_reader_and_missing_leaf_stay_separate(self):
        first_id, second_id = digest("derived-one"), digest("derived-two")
        content = digest("derived-content")
        (self.research / "one.json").write_text("{}")
        roots = {"research": self.research.resolve(), "engine": self.engine.resolve()}
        def ref(key, identity, filename):
            return {"artifact_key": key, "owner": "Research",
                    "artifact_type": "StockDerivedSignal", "artifact_id": identity,
                    "artifact_contract_version": "derived_signal_run_v1",
                    "content_digest": content, "root_id": "research",
                    "relative_path": filename}
        first, missing = ref("first", first_id, "one.json"), ref("missing", second_id, "missing.json")
        calls = []
        def load(path, *, research_root):
            calls.append((path, research_root))
            return SimpleNamespace(identity=first_id, content_digest=content,
                to_dict=lambda: {"contract_version": "derived_signal_run_v1",
                    "signal_stage": "final", "score_semantics": "static-combined",
                    "parent_signal_refs": {"a": digest("parent-a"), "b": digest("parent-b")}})
        research = ModuleType("axiom_research")
        research.load_stock_derived_signal = load
        (self.research / "bindings.json").write_text("{}")
        binding_id, binding_content = digest("bindings"), digest("bindings-content")
        def load_bindings(path, *, research_root):
            calls.append((path, research_root))
            return SimpleNamespace(identity=binding_id, content_digest=binding_content,
                to_dict=lambda: {"contract_version": "stock_prediction_input_refs_v2",
                                 "frames": []})
        research.load_stock_prediction_bindings = load_bindings
        with patch.dict(sys.modules, {"axiom_research": research}):
            binding = dict(first, artifact_type="StockPredictionBindings",
                           artifact_id=binding_id, content_digest=binding_content,
                           artifact_contract_version="stock_prediction_input_refs_v2",
                           relative_path="bindings.json")
            binding_summary = _artifact_summary(binding, roots)
            head = self.add("derived", "q1", "v1", artifacts=[first, missing],
                signals=[{"signal_run_ref": first_id, "status": "COMPLETE",
                          "prediction_artifact_key": "first", "evaluation_artifact_keys": []},
                         {"signal_run_ref": second_id, "status": "COMPLETE",
                          "prediction_artifact_key": "missing", "evaluation_artifact_keys": []}])
            html, run_ids = _detail(head, self.manifests[head["result_id"]], roots, None)
        self.assertEqual(binding_summary["availability"], "VERIFIED")
        self.assertEqual(calls, [((self.research / "bindings.json").resolve(), self.research.resolve()),
                                 ((self.research / "one.json").resolve(), self.research.resolve())])
        self.assertEqual(run_ids, set())
        self.assertIn("static-combined", html)
        self.assertIn("保存信号阶段", html)
        self.assertIn("StockDerivedSignal · VERIFIED", html)
        self.assertIn("StockDerivedSignal · UNAVAILABLE", html)
        self.assertIn("信号保存件未提供：FileNotFoundError", html)

    def test_refresh_refuses_owner_root_or_foreign_output(self):
        self.add("r1", "q1", "v1")
        with self.assertRaises(ResultCatalogError):
            refresh_result_catalog(research_root=self.research, engine_root=self.engine,
                                   output_dir=self.root)
        self.output.mkdir()
        (self.output / "other.txt").write_text("do not touch")
        with self.assertRaises(ResultCatalogError):
            self.refresh()
        self.assertEqual((self.output / "other.txt").read_text(), "do not touch")

    def test_duplicate_head_rejects_before_writing(self):
        head = self.add("r1", "q1", "v1")
        self.heads.append(dict(head))
        with self.assertRaises(ResultCatalogError):
            self.refresh()
        self.assertFalse(self.output.exists())

    def test_private_output_refuses_git_worktree(self):
        self.add("r1", "q1", "v1")
        with self.assertRaises(ResultCatalogError):
            refresh_result_catalog(research_root=self.research, engine_root=self.engine,
                                   output_dir=Path(__file__).resolve().parents[1] / "private-result-export")

    def test_cli_uses_one_private_root_config_for_both_actions(self):
        config = self.root / "roots.json"
        config.write_text(json.dumps({"research_root": str(self.research),
                                      "engine_root": str(self.engine),
                                      "engine_limits": dict(STOCK_LIMITS)}))
        with patch.object(sys, "argv", ["axiom-ui", "--refresh-results", "--workspace-config",
                                        str(config), "--output", str(self.output)]), \
             patch("axiom_ui.result_catalog.refresh_result_catalog",
                   return_value={"output_dir": str(self.output)}) as refresh, \
             patch("builtins.print"):
            main()
        self.assertEqual(refresh.call_args.kwargs["research_root"], str(self.research))
        with patch.object(sys, "argv", ["axiom-ui", "--open-result", digest("r1"),
                                        "--workspace-config", str(config), "--output", str(self.output)]), \
             patch("axiom_ui.result_catalog.open_result_detail",
                   return_value={"output_file": str(self.output / "one.html")}) as opened, \
             patch("builtins.print"):
            main()
        self.assertEqual(opened.call_args.kwargs["result_id"], digest("r1"))
        self.assertEqual(opened.call_args.kwargs["engine_limits"], STOCK_LIMITS)
        with patch.object(sys, "argv", ["axiom-ui", "--serve-results", "--workspace-config",
                                        str(config)]), \
             patch("axiom_ui.result_server.serve_result_catalog") as serve:
            main()
        self.assertEqual(serve.call_args.kwargs["research_root"], str(self.research))
        with self.assertRaises(ResultCatalogError):
            _engine_limits({"max_result_bytes": 100})

    def test_loopback_click_reads_only_selected_result_and_refreshes(self):
        first = self.add("r1", "q1", "v1")

        def run():
            with build_result_server(research_root=self.research, engine_root=self.engine) as server:
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                base = f"http://127.0.0.1:{server.server_port}"
                try:
                    index = urlopen(base + "/", timeout=3).read().decode()
                    self.assertIn(first["result_id"][7:], index)
                    self.assertEqual(self.result_calls, [])
                    self.assertEqual(self.owner_calls, [])
                    urlopen(base + "/result/" + first["result_id"][7:], timeout=3).read()
                    self.assertEqual(self.result_calls, [first["result_id"]])
                    self.add("r2", "q2", "v3", status="BLOCKED", reason="事实缺失")
                    self.assertNotIn("事实缺失", urlopen(base + "/", timeout=3).read().decode())
                    urlopen(Request(base + "/refresh", data=b"", method="POST"), timeout=3)
                    self.assertIn("事实缺失", urlopen(base + "/", timeout=3).read().decode())
                    with self.assertRaises(HTTPError) as absent:
                        urlopen(base + "/result/" + "0" * 64, timeout=3)
                    self.assertEqual(absent.exception.code, 404)
                    with self.assertRaises(HTTPError) as foreign:
                        urlopen(Request(base + "/refresh", data=b"", method="POST",
                                        headers={"Origin": "https://other.example"}), timeout=3)
                    self.assertEqual(foreign.exception.code, 403)
                finally:
                    server.shutdown()
                    worker.join(timeout=3)

        self.refresh(action=run)
