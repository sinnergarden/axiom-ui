"""Private, read-only pages from Research's atomically registered result index.

The index is the only discovery source. This module never scans an artifact
directory or interprets a manifest-supplied loader name as executable code.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any, Mapping


HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
MARKER = '<meta name="axiom-result-catalog" content="v1">'
ARTIFACT_FIELDS = {"artifact_key", "owner", "artifact_type", "artifact_id",
                   "artifact_contract_version", "content_digest", "root_id", "relative_path"}
HEAD_FIELDS = {"result_id", "question_id", "version_ref", "revision", "manifest_ref",
               "status", "reason", "updated_at"}
STATUSES = {"RUNNING", "PARTIAL", "COMPLETE", "FAILED", "BLOCKED"}
STOCK_LIMITS = dict(max_folds=10, max_prediction_rows=20000, max_market_rows=25000,
                    max_input_bytes=64 * 1024 * 1024, max_read_bytes=64 * 1024,
                    max_block_bytes=64 * 1024 * 1024, max_result_part_bytes=8 * 1024 * 1024,
                    max_result_buffer_bytes=64 * 1024 * 1024,
                    max_result_bytes=512 * 1024 * 1024)
RESEARCH_READERS = {
    "StockResultConfiguration": "load_stock_result_configuration",
    "StockSequentialResult": "load_stock_sequential_result",
    "StockMLBatchManifest": "load_stock_ml_batch_manifest",
    "StockPredictionBindings": "load_stock_prediction_bindings",
    "StockMLFoldProjection": "load_stock_fold_projection",
    "StockPredictionRun": "load_stock_prediction_projection",
    "StockDerivedSignal": "load_stock_derived_signal",
}
RUN_METADATA_MAX_BYTES = 32 * 1024 * 1024


class ResultCatalogError(ValueError):
    """Invalid local configuration, Research binding or owner result."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ResultCatalogError(message)


def _hash(value: Any, label: str) -> str:
    _require(type(value) is str and bool(HASH.fullmatch(value)), f"invalid {label}")
    return value


def _wire(value: Any) -> dict:
    wire = value.to_dict() if hasattr(value, "to_dict") else value
    _require(type(wire) is dict, "owner Reader must return an object")
    return wire


def _text(value: Any) -> str:
    return escape(str(value) if value is not None else "未提供", quote=True)


def _value(value: Any) -> str:
    if value is None:
        return "未提供"
    return _text(value)


def _short(value: Any) -> str:
    return str(value)[7:19] if type(value) is str and value.startswith("sha256:") else str(value)


def _percent(value: Any) -> str:
    if value is None:
        return "未提供（Owner 值为空）"
    try:
        with localcontext() as context:
            context.prec = 100
            shown = format((Decimal(str(value)) * 100).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")
            shown = shown.rstrip("0").rstrip(".") if "." in shown else shown
            return '<span title="Owner 原值：' + _text(value) + '">' + _text(shown + "%") + '</span>'
    except (ArithmeticError, ValueError):
        return _text(value)


def _decimal_display(value: Any) -> str:
    if value is None:
        return "未提供（Owner 值为空）"
    try:
        with localcontext() as context:
            context.prec = 100
            shown = format(Decimal(str(value)).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")
            shown = shown.rstrip("0").rstrip(".") if "." in shown else shown
            return '<span title="Owner 原值：' + _text(value) + '">' + _text(shown) + '</span>'
    except (ArithmeticError, ValueError):
        return _text(value)


def _money(value: Any) -> str:
    if type(value) is not int:
        return "未提供（Owner 值为空）"
    sign = "-" if value < 0 else ""
    major, minor = divmod(abs(value), 100)
    return f"{sign}{major:,}.{minor:02d} 元"


def _metrics(rows: list[tuple[str, str]]) -> str:
    return '<table class="metrics"><tbody>' + ''.join(
        '<tr><th scope="row">' + _text(label) + '</th><td>' + value + '</td></tr>'
        for label, value in rows) + '</tbody></table>'


def _strategy_label(spec: Any, strategy_ref: Any) -> str:
    if type(spec) is not dict:
        return "引用 " + _short(strategy_ref)
    gate = spec.get("market_gate")
    if gate is not None and not (
            spec.get("contract_version") == "stock_strategy_spec_v1" and
            spec.get("selection") == "rank_buffer" and
            type(spec.get("top_k")) is int and
            type(spec.get("rank_buffer")) is dict and
            type(spec["rank_buffer"].get("keep_rank")) is int and
            type(gate) is dict and set(gate) ==
            {"check", "rule", "security_id", "window_sessions"} and
            gate["check"] == "rebalance_sessions_only" and
            gate["rule"] == "close_above_sma" and
            gate["security_id"] == "000300.SH" and
            type(gate["window_sessions"]) is int and
            gate["window_sessions"] == 120):
        return "引用 " + _short(strategy_ref)
    selection = spec.get("selection")
    parts = (["Top " + str(spec["top_k"])] if type(spec.get("top_k")) is int
             else [str(selection or "策略")])
    buffer = spec.get("rank_buffer")
    if (spec.get("contract_version") == "stock_strategy_spec_v1" and
            selection == "top_k"):
        parts.append("等权")
    elif selection == "rank_buffer" and type(buffer) is dict and \
            type(buffer.get("keep_rank")) is int:
        parts.append("排名缓冲 · 保留前 " + str(buffer["keep_rank"]))
    elif selection:
        parts.append(str(selection))
    if spec.get("exit_overlay") is not None:
        parts.append("含退出规则")
    label = " · ".join(parts)
    return label + " + CSI300 SMA120 周频风控" if gate is not None else label


def _signal_stat(value: Any, valid_count: Any) -> str:
    if value is None:
        reason = ("有效日 " + str(valid_count) if valid_count is not None
                  else "Owner 值为空")
        return "未提供（" + _text(reason) + "）"
    return _text(value) + ("（有效日 " + _text(valid_count) + "）"
                           if valid_count is not None else "")


def _root_map(research_root: str | Path, engine_root: str | Path) -> dict[str, Path]:
    roots = {"research": Path(research_root).resolve(strict=True),
             "engine": Path(engine_root).resolve(strict=True)}
    _require(all(path.is_dir() for path in roots.values()), "trusted roots must be directories")
    return roots


def _engine_limits(value: dict | None) -> dict:
    if value is None:
        return dict(STOCK_LIMITS)
    _require(type(value) is dict and set(value) == set(STOCK_LIMITS) and
             all(type(item) is int and item > 0 for item in value.values()),
             "engine_limits needs the complete positive Engine budget")
    return dict(value)


def _relative_file(ref: Mapping[str, Any], roots: Mapping[str, Path]) -> Path:
    _require(type(ref) is dict and set(ref) == ARTIFACT_FIELDS, "malformed typed artifact")
    _require(ref["owner"] in {"Research", "Engine"} and
             ref["root_id"] == ref["owner"].lower(), "artifact owner/root mismatch")
    _hash(ref["content_digest"], "artifact content digest")
    return _checked_relative_path(ref["root_id"], ref["relative_path"], roots)


def _checked_relative_path(root_id: str, relative: str, roots: Mapping[str, Path]) -> Path:
    _require(root_id in roots, "untrusted artifact root")
    _require(type(relative) is str and relative and "\\" not in relative and
             not relative.startswith("/") and not relative.endswith("/") and
             all(part not in {"", ".", ".."} for part in relative.split("/")) and
             PurePosixPath(relative).as_posix() == relative, "unsafe artifact relative path")
    root = roots[root_id]
    path = (root / relative).resolve(strict=True)
    _require(path.is_relative_to(root) and path.is_file(), "artifact escapes root or is not a file")
    return path


def _engine_nested_artifact(ref: dict, root: Path) -> Path:
    """The v8 owner loader asks for its saved profile and result parts here."""
    _require(type(ref) is dict and type(ref.get("manifest_uri")) is str,
             "invalid Engine nested artifact")
    uri = ref["manifest_uri"]
    _require("://" not in uri and "\\" not in uri, "network/foreign URI refused")
    path = Path(uri)
    _require(path.is_absolute() and ".." not in path.parts,
             "Engine nested artifact needs a local absolute path")
    resolved = path.resolve(strict=True)
    _require(resolved.is_relative_to(root) and resolved.is_file(),
             "Engine nested artifact escapes trusted root")
    return resolved


def _unique_json_pairs(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "duplicate saved run metadata key")
        value[key] = item
    return value


def _run_metadata_summary(ref: dict, roots: Mapping[str, Path]) -> dict:
    """Verify the registered run document and policy identity without opening result parts."""
    kind = "BacktestRun"
    try:
        path = _relative_file(ref, roots)
        before = path.stat()
        if before.st_size > RUN_METADATA_MAX_BYTES:
            return {"availability": "NOT_OPENED", "artifact_type": kind,
                    "artifact_id": ref["artifact_id"], "reason": "METADATA_BUDGET"}
        _require(before.st_size > 0, "empty run metadata")
        with path.open("rb") as stream:
            payload = stream.read(RUN_METADATA_MAX_BYTES + 1)
        _require(len(payload) == before.st_size and
                 len(payload) <= RUN_METADATA_MAX_BYTES,
                 "run metadata changed or exceeded summary budget")
        wire = json.loads(payload, object_pairs_hook=_unique_json_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              ResultCatalogError("nonfinite run metadata")))
        after = path.stat()
        _require((before.st_ino, before.st_size, before.st_mtime_ns) ==
                 (after.st_ino, after.st_size, after.st_mtime_ns),
                 "run metadata changed during read")
        _require(type(wire) is dict and wire.get("contract_version") ==
                 ref["artifact_contract_version"] and wire.get("run_id") ==
                 ref["artifact_id"] and wire.get("content_digest") ==
                 ref["content_digest"], "registered run metadata identity mismatch")
        unsigned = {key: value for key, value in wire.items() if key != "content_digest"}
        canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode("utf-8")
        _require("sha256:" + sha256(canonical).hexdigest() == ref["content_digest"],
                 "run metadata content digest mismatch")
        request = wire["request_manifest"]
        policy = request["portfolio_policy"]
        _require(type(policy) is dict and
                 ("strategy_spec" not in policy or
                  type(policy["strategy_spec"]) is dict),
                 "invalid run strategy metadata")
        policy_digest = "sha256:" + sha256(json.dumps(
            policy, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False).encode("utf-8")).hexdigest()
        _require(wire["request_ref"] == request["request_ref"] and
                 type(wire["committed_sequence"]) is int,
                 "run request metadata mismatch")
        return {"availability": "METADATA_VERIFIED", "artifact_type": kind,
                "artifact_id": wire["run_id"], "content_digest": wire["content_digest"],
                "committed_sequence": wire["committed_sequence"],
                "strategy_ref": policy_digest,
                "strategy_spec": policy.get("strategy_spec"),
                **{field: wire.get(field) for field in
                   ("signal_ref", "market_ref", "profile_ref")}}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError,
            RecursionError, OverflowError) as exc:
        return {"availability": "UNAVAILABLE", "artifact_type": kind,
                "artifact_id": ref.get("artifact_id"), "reason": type(exc).__name__}


def _load_account(ref: dict, roots: Mapping[str, Path], limits: dict) -> tuple[dict, list]:
    """Reuse the fixed Engine owner for one account, including v7/v8 parts."""
    path = _relative_file(ref, roots)
    if ref["artifact_contract_version"] in {"backtest_run_v7", "backtest_run_v8"}:
        from axiom_engine.runtime import load_stock_backtest_projection
        saved = load_stock_backtest_projection(
            path, artifact_reader=lambda nested: _engine_nested_artifact(
                nested, roots["engine"]), limits=limits)
        wire = saved.wire
        nav = saved.rows["nav"]
    else:
        _require(ref["artifact_contract_version"] in
                 {"backtest_run_v1", "backtest_run_v2", "backtest_run_v3",
                  "backtest_run_v4", "backtest_run_v5", "backtest_run_v6"},
                 "unsupported BacktestRun contract")
        from axiom_engine.runtime import load_backtest_run
        wire = _wire(load_backtest_run(path))
        nav = wire.get("nav") or []
    _require(wire.get("contract_version") == ref["artifact_contract_version"] and
             wire.get("run_id") == ref["artifact_id"] and
             wire.get("content_digest") == ref["content_digest"],
             "BacktestRun identity mismatch")
    return wire, nav


def _artifact_summary(ref: dict, roots: Mapping[str, Path], *, engine_limits: dict | None = None) -> dict:
    """Only fixed owner readers may supply values beyond the manifest."""
    kind = ref["artifact_type"]
    if kind not in {"BacktestRun", "BacktestEvaluation", "StockSignalEvaluation",
                    *RESEARCH_READERS}:
        return {"availability": "METADATA_ONLY", "artifact_type": kind,
                "artifact_id": ref["artifact_id"]}
    try:
        path = _relative_file(ref, roots)
        if kind in RESEARCH_READERS:
            import axiom_research
            loader = getattr(axiom_research, RESEARCH_READERS[kind])
            saved = (loader(path, research_root=roots["research"])
                     if kind in {"StockSequentialResult", "StockMLFoldProjection",
                                 "StockPredictionRun", "StockPredictionBindings",
                                 "StockDerivedSignal"}
                     else loader(path))
            wire = _wire(saved)
            _require(saved.identity == ref["artifact_id"] and
                     saved.content_digest == ref["content_digest"] and
                     wire.get("contract_version") == ref["artifact_contract_version"],
                     "Research artifact identity mismatch")
            return {"availability": "VERIFIED", "artifact_type": kind,
                    "artifact_id": saved.identity, "contract_version": wire["contract_version"],
                    "status": wire.get("status"), "configuration_ref":
                    wire.get("configuration_ref"), "batch_ref": wire.get("batch_ref"),
                    "signal_stage": wire.get("signal_stage"),
                    "score_semantics": wire.get("score_semantics"),
                    "parent_signal_refs": wire.get("parent_signal_refs"),
                    "fold_count": len(wire["folds"]) if type(wire.get("folds")) is list else None,
                    "signal_count": (len(wire["frames"]) if type(wire.get("frames")) is list
                                     else len(wire["prediction_input"]["frames"])
                                     if type(wire.get("prediction_input")) is dict and
                                     type(wire["prediction_input"].get("frames")) is list else None)}
        if kind == "BacktestRun":
            wire, nav = _load_account(ref, roots, engine_limits or STOCK_LIMITS)
            return {"availability": "VERIFIED", "artifact_type": kind,
                    "artifact_id": wire["run_id"], "status": wire.get("status"),
                    "content_digest": wire["content_digest"],
                    "committed_sequence": wire.get("committed_sequence"),
                    **{field: wire.get(field) for field in
                       ("signal_ref", "market_ref", "profile_ref")},
                    "strategy_spec": (wire.get("request_manifest", {}).get("portfolio_policy", {})
                                      .get("strategy_spec")),
                    "first_session": nav[0].get("session") if nav else None,
                    "last_session": nav[-1].get("session") if nav else None,
                    "nav_count": len(nav),
                    "initial_nav_minor": wire.get("initial_nav_minor"),
                    "final_nav_minor": nav[-1].get("nav_minor") if nav else None,
                    "metrics": wire.get("metrics")}
        if kind == "BacktestEvaluation":
            from axiom_engine.runtime import load_backtest_evaluation
            wire = _wire(load_backtest_evaluation(path))
            _require(wire.get("contract_version") == ref["artifact_contract_version"] and
                     wire.get("evaluation_ref") == ref["artifact_id"] and
                     wire.get("content_digest") == ref["content_digest"],
                     "BacktestEvaluation identity mismatch")
            series = wire.get("series") if type(wire.get("series")) is list else []
            return {"availability": "VERIFIED", "artifact_type": kind,
                    "artifact_id": wire["evaluation_ref"],
                    "contract_version": wire["contract_version"],
                    "status": wire.get("status"),
                    "input_run_ref": wire.get("input_run_ref"),
                    **{field: wire.get(field) for field in
                       ("signal_ref", "market_ref", "profile_ref")},
                    "period_metrics": wire.get("period_metrics"),
                    "first_session": series[0].get("session") if series else None,
                    "last_session": series[-1].get("session") if series else None,
                    "session_count": len(series),
                    "risk_metrics": wire.get("risk_metrics"),
                    "execution_summary": wire.get("execution_summary"),
                    "monthly_returns": wire.get("monthly_returns"),
                    "benchmark_comparisons": {
                        name: {field: item.get(field) for field in
                               ("status", "return_basis", "unavailable_reason")}
                        for name, item in (wire.get("benchmark_comparisons") or {}).items()}}
        from axiom_research import load_stock_signal_evaluation
        saved = load_stock_signal_evaluation(path, research_root=roots["research"])
        wire = _wire(saved)
        _require(wire.get("contract_version") == ref["artifact_contract_version"] and
                 wire.get("evidence_ref") == ref["artifact_id"] and
                 wire.get("content_digest") == ref["content_digest"],
                 "StockSignalEvaluation identity mismatch")
        summary = wire.get("summary") or {}
        return {"availability": "VERIFIED", "artifact_type": kind,
                "artifact_id": wire["evidence_ref"], "status": wire.get("status"),
                "signal_refs": wire.get("input_signal_refs"),
                "summary": {key: summary.get(key) for key in
                            ("mean_ic", "mean_rank_ic", "valid_ic_session_count",
                             "valid_rank_ic_session_count")}}
    except (FileNotFoundError, ImportError, OSError, ValueError, KeyError, TypeError,
            AttributeError) as exc:
        # Keep the registered result visible while making an unavailable or
        # mismatched original explicit. Never substitute synthetic zero values.
        return {"availability": "UNAVAILABLE", "artifact_type": kind,
                "artifact_id": ref.get("artifact_id"), "reason": type(exc).__name__}


def _account_bindings(manifest: dict, summaries: Mapping[str, dict]) -> set[int]:
    invalid = set()
    for index, account in enumerate(manifest.get("accounts") or []):
        backtest = account.get("backtest_ref")
        if backtest is None:
            continue
        try:
            report = summaries.get(backtest.get("artifact_key")) or {}
            run_verified = report.get("availability") in {"VERIFIED", "METADATA_VERIFIED"}
            if run_verified:
                _require(all(report.get(field) == backtest.get(reference) for field, reference in
                             (("artifact_id", "run_id"), ("content_digest", "content_digest"),
                              ("committed_sequence", "committed_sequence"))),
                         "account BacktestRun identity mismatch")
                if report.get("strategy_ref") is not None:
                    _require(report["strategy_ref"] == account.get("strategy_ref"),
                             "account strategy metadata mismatch")
            expected = {field: backtest.get(field) for field in
                        ("run_id", "content_digest", "committed_sequence")}
            for evaluation in account.get("evaluation_refs") or []:
                _require(evaluation.get("input_run_ref") == expected,
                         "account evaluation is bound to another run")
                saved = summaries.get(evaluation.get("artifact_key")) or {}
                if saved.get("availability") == "VERIFIED":
                    _require(saved.get("artifact_id") == evaluation.get("evaluation_ref") and
                             saved.get("input_run_ref") == expected,
                             "loaded account evaluation identity mismatch")
                    if run_verified:
                        _require(all(saved.get(field) == report.get(field) for field in
                                     ("signal_ref", "market_ref", "profile_ref")),
                                 "loaded account evaluation input refs mismatch")
        except ResultCatalogError:
            invalid.add(index)
    return invalid


def _page(title: str, body: str, *, local_form: bool = False) -> str:
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'style-src \'unsafe-inline\'; base-uri \'none\'; form-action ' +
            ("'self'" if local_form else "'none'") + '">'
            + MARKER + '<title>' + _text(title) + '</title>'
            '<style>body{margin:0;background:#f3f6fa;color:#25374d;font:15px/1.6 '
            '-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1000px;'
            'margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dce5ef;'
            'border-radius:12px;padding:20px;margin:14px 0}a{color:#416e99}small{color:#52677e}'
            'h1{font-size:29px}h2{font-size:21px}h3{font-size:17px}ul{padding-left:22px}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere}svg{width:100%;height:auto}'
            'code{overflow-wrap:anywhere}.metrics{width:100%;border-collapse:collapse;margin:10px 0}'
            '.metrics th,.metrics td{padding:7px 10px;border-bottom:1px solid #dce5ef;text-align:left}'
            '.metrics th{width:38%;color:#52677e;font-weight:500}.metrics td{overflow-wrap:anywhere}'
            'dl{display:grid;grid-template-columns:150px 1fr;gap:6px 12px}'
            'dt{font-weight:600}dd{margin:0;overflow-wrap:anywhere}</style></head><body><main>'
            + body + '</main></body></html>')


def _detail(head: dict, manifest: dict | None, roots: Mapping[str, Path], error: str | None,
            *, engine_limits: dict | None = None, detail_mode: str = "summary",
            full_href: str | None = None, result_href: str | None = None,
            remote: bool = False) -> tuple[str, set[str]]:
    _require(detail_mode in {"summary", "full"}, "invalid detail mode")
    title = "实验结果 · " + head["result_id"][7:19]
    pieces = ['<p><a href="index.html">← 返回实验列表</a></p><h1>' + _text(title) + '</h1>',
              '<section><p>登记状态：' + _text(head["status"]) +
              ' · 修订 ' + _text(head["revision"]) + '</p><p>结果 ID：<code>' +
              _text(head["result_id"]) + '</code></p><p>原因：' + _value(head["reason"]) + '</p></section>']
    if manifest is None:
        pieces.append('<section role="status">保存清单未能验证：' + _text(error) +
                      '。保留索引记录，不展示账户或统计。</section>')
        return _page(title, ''.join(pieces)), set()
    refs = {ref["artifact_key"]: ref for ref in manifest["artifacts"]}
    if detail_mode == "summary":
        pieces.append('<p>快速摘要：逐项读取保存评价与登记的账户元数据；失败或未展开的保存件单独标注。训练、信号评价和账户结果分片未展开；模型与 OOS 祖先未审。</p>' +
                      ('<p><a href="' + _text(full_href) +
                       '">显式验证全部保存原件（可能较慢）</a></p>' if full_href else
                       '<p>完整原件验证可使用 --detail-mode full 显式执行。</p>'))
    summaries = {}
    for key, ref in refs.items():
        if detail_mode == "full" or ref["artifact_type"] == "BacktestEvaluation":
            summaries[key] = _artifact_summary(ref, roots, engine_limits=engine_limits)
        elif ref["artifact_type"] == "BacktestRun" and ref["artifact_contract_version"] in {
                "backtest_run_v7", "backtest_run_v8"}:
            summaries[key] = _run_metadata_summary(ref, roots)
        else:
            summaries[key] = {"availability": "NOT_OPENED",
                              "artifact_type": ref["artifact_type"],
                              "artifact_id": ref["artifact_id"]}
    invalid_accounts = _account_bindings(manifest, summaries)
    folds = manifest.get("folds") or []
    pieces.append('<details><summary>训练折（' + str(len(folds)) +
                  '）· 展开查看</summary>' +
                  ('<ul>' + ''.join('<li>Fold <code>' + _text(_short(row.get("fold_ref"))) +
                   '</code> · ' + _value(row.get("status")) +
                   (' · ' + _text(row["reason"]) if row.get("reason") else '') + '</li>'
                   for row in folds) + '</ul>' if folds else '<p>未登记</p>') + '</details>')
    signals = manifest.get("signals") or []
    signal_cards = []
    for signal_index, signal in enumerate(signals):
        rows = []
        prediction = summaries.get(signal.get("prediction_artifact_key")) or {}
        if (prediction.get("availability") == "VERIFIED" and
                prediction.get("artifact_type") == "StockDerivedSignal"):
            rows.append(_metrics([
                ("保存信号阶段", _value(prediction.get("signal_stage"))),
                ("保存分数语义", _value(prediction.get("score_semantics"))),
                ("原始父 Signal", _text(json.dumps(
                    prediction.get("parent_signal_refs"), ensure_ascii=False, sort_keys=True))),
            ]))
        elif signal.get("prediction_artifact_key") and prediction.get("availability") != "VERIFIED":
            rows.append('<p>信号保存件' +
                        ('未展开验证' if prediction.get("availability") == "NOT_OPENED"
                         else '未提供') + '：' +
                        _text(prediction.get("reason") or "Owner 未验证") + '</p>')
        for evaluation_index, key in enumerate(signal.get("evaluation_artifact_keys") or []):
            if result_href:
                rows.append('<p><a href="' + result_href + "/signal/" + str(signal_index) + "/" +
                            str(evaluation_index) + '">按需读取此项信号评价</a></p>')
            saved = summaries.get(key) or {}
            if saved.get("availability") != "VERIFIED":
                rows.append('<p>信号评价' + ('未展开' if saved.get("availability") == "NOT_OPENED"
                                             else '未提供') + '：' +
                            _text(saved.get("reason") or "Owner 未验证") + '</p>')
                continue
            metrics = saved.get("summary") or {}
            valid_ic = metrics.get("valid_ic_session_count")
            valid_rank = metrics.get("valid_rank_ic_session_count")
            rows.append(_metrics([
                ("平均 IC", _signal_stat(metrics.get("mean_ic"), valid_ic)),
                ("平均 RankIC", _signal_stat(metrics.get("mean_rank_ic"), valid_rank)),
            ]))
        signal_cards.append('<section><h3>Signal ' + _text(_short(signal.get("signal_run_ref"))) +
                            '</h3><p>状态：' + _value(signal.get("status")) +
                            ' · 原因：' + _value(signal.get("reason")) + '</p>' +
                            (''.join(rows) if rows else '<p>信号评价未登记</p>') +
                            '<details><summary>完整 Signal 引用</summary><code>' +
                            _value(signal.get("signal_run_ref")) + '</code></details></section>')
    signal_section = ('<details><summary>保存 Signal（' + str(len(signals)) +
                      '）· 展开查看</summary>' +
                      (''.join(signal_cards) if signal_cards else '<p>未登记</p>') +
                      '</details>')
    accounts = manifest.get("accounts") or []
    account_cards = []
    for index, account in enumerate(accounts):
        backtest = account.get("backtest_ref") or {}
        run = ({"availability": "UNAVAILABLE", "reason": "CONTEXT_MISMATCH"}
               if index in invalid_accounts else summaries.get(backtest.get("artifact_key")) or {})
        metrics = run.get("metrics") or {}
        label = _strategy_label(run.get("strategy_spec"), account.get("strategy_ref"))
        values = _metrics([
            ("保存交易范围", _value(run.get("first_session")) + ' — ' +
             _value(run.get("last_session")) + ' · ' + _value(run.get("nav_count")) + ' 日'),
            ("初始资金", _money(run.get("initial_nav_minor"))),
            ("累计收益 · 原回测", _percent(metrics.get("total_return"))),
            ("最大回撤 · 原回测", _percent(metrics.get("max_drawdown"))),
            ("总费用", _money(metrics.get("total_fees_minor"))),
            ("期末净资产", _money(run.get("final_nav_minor"))),
        ]) if run.get("availability") == "VERIFIED" else (
            '<p>账户原件未展开验证；以下数值只取已验证的 Owner 评价及其保存的账户引用。</p>'
            if run.get("availability") in {"NOT_OPENED", "METADATA_VERIFIED"} else
            '<p>账户保存件未提供：' + _text(run.get("reason") or "Owner 未验证") + '</p>')
        evaluations = []
        for item in account.get("evaluation_refs") or []:
            report = summaries.get(item.get("artifact_key")) or {}
            if run.get("availability") not in {"VERIFIED", "NOT_OPENED", "METADATA_VERIFIED"} or \
                    report.get("availability") != "VERIFIED":
                evaluations.append('<p>评价 ' + _text(_short(item.get("evaluation_ref"))) +
                                   ' · 保存账户或评价不可用，指标暂不展示</p>')
                continue
            period = report.get("period_metrics") or {}
            leg = period.get("account") or {}
            benchmark = period.get("benchmark") or {}
            risk = report.get("risk_metrics") or {}
            sharpe = risk.get("sharpe") or {}
            execution = report.get("execution_summary") or {}
            benchmarks = report.get("benchmark_comparisons") or {}
            window = period.get("window") or {}
            rows = [("账户累计收益 · 原评价", _percent(leg.get("total_return"))),
                    ("账户期末净资产 · 原评价", _money(leg.get("final_nav_minor"))),
                    ("账户 CAGR · 原评价", _percent(leg.get("cagr")) +
                     ("（" + _text(leg["cagr_reason"]) + "）"
                      if leg.get("cagr_reason") else '')),
                    ("沪深 300 累计收益 · 价格指数", _percent(benchmark.get("total_return"))),
                    ("沪深 300 CAGR · 价格指数", _percent(benchmark.get("cagr"))),
                    ("沪深 300 最大回撤 · 价格指数", _percent(benchmark.get("max_drawdown")))]
            if risk:
                rows.extend([
                    ("账户最大回撤 · 原评价", _percent(leg.get("max_drawdown"))),
                    ("Sharpe · 原评价", _decimal_display(sharpe.get("value")) + ' · ' +
                     _value(sharpe.get("status"))),
                    ("Sharpe 无风险年利率假设", _percent(
                        (sharpe.get("risk_free") or {}).get("annual_effective_rate"))),
                    ("初始资金 · 原评价", _money(leg.get("initial_nav_minor"))),
                    ("总费用 · 原评价", _money(execution.get("fees_minor"))),
                    ("双边换手 · Owner 比值", _decimal_display(
                        execution.get("two_sided_turnover"))),
                    ("费用率 · Owner 保存值", _percent(execution.get("fee_ratio"))),
                    ("保存交易日", _value(report.get("first_session")) + ' — ' +
                     _value(report.get("last_session")) + ' · ' +
                     _value(report.get("session_count")) + ' 日'),
                    ("评价范围", _value(window.get("anchor_session")) + ' — ' +
                     _value(window.get("end_session")) + ' · Sharpe 观测日 ' +
                     _value(sharpe.get("observations"))),
                ])
            benchmark_rows = ''.join(
                '<li>' + _text(name) + '：' + _value(value.get("status")) +
                (' · ' + _text(value["return_basis"]) if value.get("return_basis") else '') +
                (' · 原因 ' + _text(value["unavailable_reason"])
                 if value.get("unavailable_reason") else '') + '</li>'
                for name, value in benchmarks.items())
            monthly = report.get("monthly_returns") or []
            monthly_rows = ''.join('<li>' + _value(row.get("month")) + '：' +
                                   _percent(row.get("return")) + ' · ' +
                                   _value(row.get("status")) +
                                   (' · ' + _text(row["reason"]) if row.get("reason") else '') +
                                   '</li>' for row in monthly)
            evaluations.append('<div><h4>评价 ' + _text(_short(item.get("evaluation_ref"))) +
                               ' · ' + _value(report.get("contract_version")) +
                               ' · ' + _value(report.get("status")) + '</h4>' +
                               _metrics(rows) +
                               ('<p>基准供应状态（账户指标仍按保存值展示）：</p><ul>' +
                                benchmark_rows + '</ul>' if benchmarks else '') +
                               ('<p>年度收益：该保存评价未提供独立年度序列；不由 UI 汇总月收益。</p>'
                                '<details><summary>保存月收益（' + str(len(monthly)) +
                                '）</summary><ul>' + monthly_rows + '</ul></details>'
                                if monthly else '') + '</div>')
        if result_href and backtest:
            values += '<p><a href="' + result_href + "/account/" + str(index) + '">按需查看此账户曲线</a></p>'
        account_cards.append('<section><h3>账户 ' + str(index + 1) + ' · 策略：' +
                             _text(label) + '</h3><p>状态：' +
                             _value(account.get("status")) + ' · 原因：' +
                             _value(account.get("reason")) + '</p><p>关联 Signal：<code>' +
                             _value(account.get("signal_run_ref")) + '</code></p>' + values +
                             ''.join(evaluations) + ('<details><summary>策略与账户原始引用</summary><pre>' +
                             _text(json.dumps({"strategy_ref": account.get("strategy_ref"),
                                               "backtest_ref": account.get("backtest_ref"),
                                               "evaluation_refs": account.get("evaluation_refs")},
                                              ensure_ascii=False, indent=2)) +
                             '</pre></details>' if not remote else '') + '</section>')
    pieces.append('<h2>策略账户（' + str(len(accounts)) + '）</h2>' +
                  (''.join(account_cards) if account_cards else '<section>未登记</section>'))
    pieces.append(signal_section)
    if not remote:
        pieces.append('<section><h2>保存产物与完整引用</h2><ul>' + ''.join(
            '<li><details><summary>' + _text(ref["artifact_type"]) + ' · ' +
            _text(summaries[key]["availability"]) + '</summary><pre>' +
            _text(json.dumps({"reference": ref, "owner_summary": {
                name: value for name, value in summaries[key].items() if name not in
                {"metrics", "period_metrics", "final_nav_minor"}}},
                             ensure_ascii=False, indent=2)) + '</pre></details></li>'
            for key, ref in refs.items()) + '</ul></section>')
    verified_runs = {summaries[account["backtest_ref"]["artifact_key"]]["artifact_id"]
                     for index, account in enumerate(accounts) if index not in invalid_accounts and
                     type(account.get("backtest_ref")) is dict and
                     summaries.get(account["backtest_ref"]["artifact_key"], {}).get("availability") == "VERIFIED"}
    return _page(title, ''.join(pieces)), verified_runs


def _atomic_html(path: Path, html: str) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="." + path.name + ".", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(html)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _private_output(output_dir: str | Path, roots: Mapping[str, Path]) -> Path:
    raw_output = Path(output_dir)
    _require(not raw_output.is_symlink(), "UI output symlink refused")
    output = raw_output.resolve()
    _require(all(output != root and not output.is_relative_to(root) and
                 not root.is_relative_to(output)
                 for root in roots.values()), "UI output must be outside owner roots")
    _require(not any((ancestor / ".git").exists() for ancestor in (output, *output.parents)),
             "private UI output must be outside Git worktrees")
    if output.exists():
        _require(output.is_dir() and not output.is_symlink(), "UI output must be a directory")
        existing = output / "index.html"
        _require((not any(output.iterdir())) or
                 (existing.is_file() and MARKER in existing.read_text(encoding="utf-8")),
                 "refusing to write into a non-UI directory")
    return output


def refresh_result_catalog(*, research_root: str | Path, engine_root: str | Path,
                           output_dir: str | Path, generated_at: str | None = None) -> dict:
    """Rebuild only the light index; no manifest or owner artifact is read."""
    roots = _root_map(research_root, engine_root)
    output = _private_output(output_dir, roots)
    from axiom_research import ExperimentReader
    reader = ExperimentReader(roots["research"] / "index.json")
    projection = _wire(reader.index())
    _require(projection.get("contract_version") == "experiment_projection_v2", "Research v2 index required")
    heads = projection.get("result_heads")
    _require(type(heads) is list, "malformed Research result heads")
    by_question = {}
    for item in projection.get("questions") or []:
        question = item.get("question") or {}
        by_question[question.get("question_id")] = (question, {
            version["version_ref"]: version for version in item.get("versions") or []})
    seen = set()
    entries = []
    detail_pages = []
    for head in sorted(heads, key=lambda value: value.get("updated_at", "")
                    if type(value) is dict else "", reverse=True):
        _require(type(head) is dict and set(head) == HEAD_FIELDS, "malformed Research result head")
        result_id = _hash(head["result_id"], "result_id")
        _require(result_id not in seen and head["status"] in STATUSES and
                 type(head["revision"]) is int and head["revision"] >= 0,
                 "duplicate result or invalid revision/status")
        seen.add(result_id)
        _require(head["question_id"] in by_question and
                 head["version_ref"] in by_question[head["question_id"]][1],
                 "Research result is not bound to its question/version")
        manifest_ref = head["manifest_ref"]
        _require(type(manifest_ref) is dict and set(manifest_ref) ==
                 {"root_id", "relative_path", "content_digest"} and
                 manifest_ref["root_id"] == "research", "invalid manifest reference")
        manifest_digest = _hash(manifest_ref["content_digest"], "manifest digest")
        filename = "result-" + result_id[7:] + "-" + manifest_digest[7:19] + ".html"
        stub = ('<p><a href="index.html">← 返回实验列表</a></p><h1>保存结果</h1>'
                '<section><p>索引登记：' + _text(head["status"]) + ' · 修订 ' +
                _text(head["revision"]) + '</p><p>结果 ID：<code>' +
                _text(result_id) + '</code></p><p>原因：' + _value(head["reason"]) +
                '</p><p>详情尚未读取。请在本机终端使用同一可信根与输出目录执行 '
                '<code>python3 -m axiom_ui --open-result ' + _text(result_id) +
                ' --research-root … --engine-root … --output …</code>，再打开此页。</p></section>')
        detail_pages.append((filename, _page("Axiom · 保存结果待读取", stub)))
        question, versions = by_question[head["question_id"]]
        entries.append((head, filename, question.get("title"),
                        versions[head["version_ref"]].get("label")))
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    cards = ''.join('<section><h2>' + _value(title) + ' · ' + _value(label) + '</h2>'
                    '<p>结果 ' + _text(head["result_id"][7:19]) + ' · 状态 ' +
                    _text(head["status"]) + ' · 修订 ' + _text(head["revision"]) +
                    (' · ' + _text(head["reason"]) if head.get("reason") else '') + '</p>'
                    '<p><a href="' + _text(filename) + '">选择结果并读取详情</a></p></section>'
                    for head, filename, title, label in entries)
    body = ('<h1>研究实验结果</h1><p>Research 保存索引 · 本地只读 · 显式刷新</p>'
            '<p>结果 ' + str(len(entries)) + ' · 已验证保存回测：详情待读取' +
            ' · 登记修订 ' + str(sum(head["revision"] + 1 for head, *_ in entries)) + '</p>'
            '<small>生成时间：' + _text(timestamp) + ' · 索引修订：' +
            _text(projection.get("store_revision")) + ' · 索引摘要：' +
            _text(projection.get("content_digest")) + '</small>' +
            (cards if cards else '<section role="status">暂无登记结果。</section>'))
    output.mkdir(parents=True, exist_ok=True)
    for filename, html in detail_pages:
        _atomic_html(output / filename, html)
    _atomic_html(output / "index.html", _page("Axiom · 研究实验结果", body))
    return {"contract_version": "ui_result_catalog_refresh_v1", "result_count": len(entries),
            "store_revision": projection.get("store_revision"),
            "verified_saved_backtest_count": None,
            "index_content_digest": projection.get("content_digest"),
            "generated_at": timestamp,
            "index_sha256": "sha256:" + sha256((output / "index.html").read_bytes()).hexdigest(),
            "output_dir": str(output)}


def open_result_detail(*, research_root: str | Path, engine_root: str | Path,
                       output_dir: str | Path, result_id: str,
                       engine_limits: dict | None = None,
                       detail_mode: str = "summary") -> dict:
    """Read one registered manifest and its fixed owner types into one local page."""
    result_id = _hash(result_id, "result_id")
    roots = _root_map(research_root, engine_root)
    limits = _engine_limits(engine_limits)
    output = _private_output(output_dir, roots)
    index_file = output / "index.html"
    _require(index_file.is_file(), "refresh the light list before opening a result")
    from axiom_research import ExperimentReader
    reader = ExperimentReader(roots["research"] / "index.json")
    projection = _wire(reader.index())
    _require(projection.get("contract_version") == "experiment_projection_v2", "Research v2 index required")
    _require(_hash(projection.get("content_digest"), "index digest") in
             index_file.read_text(encoding="utf-8"), "Research index changed; refresh the list first")
    heads = projection.get("result_heads")
    _require(type(heads) is list, "malformed Research result heads")
    matches = [head for head in heads if type(head) is dict and head.get("result_id") == result_id]
    _require(len(matches) == 1, "result is not uniquely registered")
    head = matches[0]
    _require(set(head) == HEAD_FIELDS and head["status"] in STATUSES and
             type(head["revision"]) is int and head["revision"] >= 0,
             "malformed Research result head")
    ref = head["manifest_ref"]
    _require(type(ref) is dict and set(ref) == {"root_id", "relative_path", "content_digest"}
             and ref["root_id"] == "research", "invalid manifest reference")
    manifest_digest = _hash(ref["content_digest"], "manifest digest")
    filename = "result-" + result_id[7:] + "-" + manifest_digest[7:19] + ".html"
    target = output / filename
    _require(target.is_file() and MARKER in target.read_text(encoding="utf-8") and
             filename in index_file.read_text(encoding="utf-8"),
             "result is absent from the refreshed local list")
    error = None
    try:
        _checked_relative_path(ref["root_id"], ref["relative_path"], roots)
        manifest = _wire(reader.result(result_id, roots=roots))
        _require(manifest.get("contract_version") == "experiment_result_manifest_v1" and
                 manifest.get("content_digest") == manifest_digest and
                 all(manifest.get(k) == head.get(k) for k in
                     ("result_id", "question_id", "version_ref", "revision", "status", "reason")) and
                 type(manifest.get("artifacts")) is list,
                 "Research head/manifest mismatch")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        manifest, error = None, type(exc).__name__
    html, run_ids = _detail(head, manifest, roots, error, engine_limits=limits,
                            detail_mode=detail_mode)
    _atomic_html(target, html)
    return {"contract_version": "ui_result_detail_v1", "result_id": result_id,
            "verified_saved_backtest_count": len(run_ids), "availability":
            "MANIFEST_VERIFIED" if manifest is not None else "UNAVAILABLE", "output_file": str(target)}


class LocalResultCatalog:
    """In-memory index snapshot for a short-lived loopback-only UI session."""

    def __init__(self, *, research_root: str | Path, engine_root: str | Path,
                 engine_limits: dict | None = None):
        self.roots = _root_map(research_root, engine_root)
        self.engine_limits = _engine_limits(engine_limits)
        from axiom_research import ExperimentReader
        self.reader = ExperimentReader(self.roots["research"] / "index.json")
        self.refresh()

    def refresh(self) -> None:
        projection = _wire(self.reader.index())
        _require(projection.get("contract_version") == "experiment_projection_v2",
                 "Research v2 index required")
        heads = projection.get("result_heads")
        _require(type(heads) is list and type(projection.get("questions")) is list,
                 "malformed Research result index")
        questions = {}
        for item in projection["questions"]:
            _require(type(item) is dict and type(item.get("question")) is dict and
                     type(item.get("versions")) is list, "malformed Research question")
            question = item["question"]
            versions = {v["version_ref"]: v for v in item["versions"]}
            questions[question["question_id"]] = (question, versions)
        indexed = {}
        for head in heads:
            _require(type(head) is dict and set(head) == HEAD_FIELDS,
                     "malformed Research result head")
            result_id = _hash(head["result_id"], "result_id")
            ref = head["manifest_ref"]
            _require(result_id not in indexed and head["status"] in STATUSES and
                     type(head["revision"]) is int and head["revision"] >= 0 and
                     type(ref) is dict and set(ref) ==
                     {"root_id", "relative_path", "content_digest"} and
                     ref["root_id"] == "research" and
                     head["question_id"] in questions and
                     head["version_ref"] in questions[head["question_id"]][1],
                     "duplicate or malformed registered result")
            _hash(ref["content_digest"], "manifest digest")
            indexed[result_id] = head
        self.projection = projection
        self.questions = questions
        self.heads = indexed
        self.generated_at = datetime.now(timezone.utc).isoformat()
        self.opened_runs: dict[str, set[str]] = {}

    def index_html(self, *, page: int = 1, page_size: int = 25, remote: bool = False) -> str:
        _require(type(page) is int and 1 <= page <= 1000000000 and
                 type(page_size) is int and 1 <= page_size <= 100, "invalid pagination")
        ordered = sorted(self.heads.items(), key=lambda pair: (pair[1]["updated_at"], pair[0]),
                         reverse=True)
        pages = max(1, (len(ordered) + page_size - 1) // page_size)
        _require(page <= pages, "page out of range")
        cards = []
        for result_id, head in ordered[(page - 1) * page_size:page * page_size]:
            question, versions = self.questions[head["question_id"]]
            cards.append('<section><h2>' + _value(question.get("title")) + ' · ' +
                         _value(versions[head["version_ref"]].get("label")) + '</h2><p>' +
                         '状态 ' + _text(head["status"]) + ' · 修订 ' +
                         _text(head["revision"]) + ' · 结果 <code>' +
                         _text(result_id[7:19]) + '</code></p><p>原因：' +
                         _value(head["reason"]) + '</p><p><a href="/result/' +
                         _text(result_id[7:]) + '">打开保存结果</a></p></section>')
        run_ids = set().union(*self.opened_runs.values()) if self.opened_runs else set()
        navigation = '<p>第 ' + str(page) + ' / ' + str(pages) + ' 页 · 每页 ' + str(page_size) + '</p>'
        for target, label in ((page - 1, "上一页"), (page + 1, "下一页")):
            if 1 <= target <= pages:
                navigation += '<a href="/?page=' + str(target) + '&amp;page_size=' + str(page_size) + '">' + label + '</a> '
        body = ('<h1>研究实验结果</h1><p>本机只读 · 仅打开所选详情</p>' +
                ('' if remote else '<p>分页仅减少页面内容；刷新仍完整读取并验证 Research 索引，不是数据库分页。</p>') + navigation +
                ('' if remote else '<form method="post" action="/refresh"><button type="submit">刷新保存索引</button></form>') +
                '<p>结果 ' + str(len(self.heads)) + ' · 本次已完整验证的账户原件 ' +
                str(len(run_ids)) + ' · 登记修订 ' +
                str(sum(h["revision"] + 1 for h in self.heads.values())) + '</p>'
                '<small>生成时间：' + _text(self.generated_at) + ' · 索引修订：' +
                _text(self.projection.get("store_revision")) + ' · 索引摘要：' +
                _text(self.projection.get("content_digest")) + '</small>' +
                (''.join(cards) if cards else '<section>暂无登记结果。</section>'))
        return _page("Axiom · 研究实验结果", body, local_form=True)

    def _manifest(self, result_id: str) -> tuple[dict, dict | None, str | None]:
        _hash(result_id, "result_id")
        _require(result_id in self.heads, "result_id is not in the current index")
        head = self.heads[result_id]
        ref = head["manifest_ref"]
        error = None
        try:
            _checked_relative_path(ref["root_id"], ref["relative_path"], self.roots)
            manifest = _wire(self.reader.result(result_id, roots=self.roots))
            _require(manifest.get("contract_version") == "experiment_result_manifest_v1" and
                     manifest.get("content_digest") == ref["content_digest"] and
                     all(manifest.get(key) == head.get(key) for key in
                         ("result_id", "question_id", "version_ref", "revision", "status", "reason")) and
                     type(manifest.get("artifacts")) is list,
                     "Research head/manifest mismatch")
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            manifest, error = None, type(exc).__name__
        return head, manifest, error

    def detail_html(self, result_id: str, *, detail_mode: str = "summary", remote: bool = False) -> str:
        head, manifest, error = self._manifest(result_id)
        html, run_ids = _detail(head, manifest, self.roots, error,
                                engine_limits=self.engine_limits,
                                detail_mode=detail_mode,
                                full_href="/result/" + result_id[7:] + "/full"
                                if detail_mode == "summary" and not remote else None,
                                result_href="/result/" + result_id[7:], remote=remote)
        self.opened_runs.setdefault(result_id, set()).update(run_ids)
        return html.replace('href="index.html"', 'href="/"', 1)

    def signal_html(self, result_id: str, signal_index: int, evaluation_index: int, *, remote: bool = False) -> str:
        """Read exactly one evidence report through the Research summary owner."""
        _, manifest, error = self._manifest(result_id)
        _require(manifest is not None, "manifest unavailable: " + str(error))
        signals = manifest.get("signals") or []
        _require(type(signal_index) is int and 0 <= signal_index < len(signals), "unknown signal")
        signal = signals[signal_index]
        keys = signal.get("evaluation_artifact_keys") or []
        _require(type(evaluation_index) is int and 0 <= evaluation_index < len(keys), "unknown evaluation")
        refs = {ref["artifact_key"]: ref for ref in manifest["artifacts"]}
        ref = refs[keys[evaluation_index]]
        _require(ref["owner"] == "Research" and ref["artifact_type"] == "StockSignalEvaluation",
                 "not a Research signal evaluation")
        body = '<p><a href="/result/' + result_id[7:] + '">返回结果</a></p><h1>单项信号评价</h1>'
        try:
            from axiom_research import load_stock_signal_evaluation_summary
            wire = _wire(load_stock_signal_evaluation_summary(
                _relative_file(ref, self.roots), research_root=self.roots["research"]))
            _require(wire.get("contract_version") == ref["artifact_contract_version"] and
                     wire.get("evidence_ref") == ref["artifact_id"] and
                     wire.get("content_digest") == ref["content_digest"], "signal report identity mismatch")
            _require(type(wire.get("input_signal_refs")) is list and
                     signal.get("signal_run_ref") in wire["input_signal_refs"], "signal binding mismatch")
            _hash(wire.get("label_ref"), "Label identity")
            _require(wire.get("audit_scope") == "report_and_bindings" and
                     wire.get("ancestors_audited") is False, "unknown owner audit scope")
            body += '<p>报告与必要 binding 已验证；模型、OOS 与其余祖先未审。统计不是账户收益。</p>'
            coverage = wire.get("coverage") or {}
            fields = ("scope_key_count", "reference_key_count", "mature_valid_label_count",
                      "prediction_valid_count", "valid_pair_count", "excluded_counts",
                      "comparison_mode", "common_statistics_ref", "native_statistics_ref")
            projected = {**wire, "coverage": {field: coverage.get(field) for field in fields}}
            native = coverage.get("native")
            if type(native) is dict:
                projected["coverage"]["native"] = {field: native.get(field) for field in fields}
            metrics = wire.get("summary") or {}
            label_spec = wire.get("label_spec") or {}
            body += '<section><h2>Label 与统计</h2>' + _metrics([
                ("Label 身份", _value(wire.get("label_ref"))),
                ("Label horizon（交易日）", _value(label_spec.get("horizon_sessions"))),
                ("Label 公式", _value(label_spec.get("formula"))),
                ("状态", _value(wire.get("status"))),
                ("平均 IC", _value(metrics.get("mean_ic"))),
                ("IC 有效天数", _value(metrics.get("valid_ic_session_count"))),
                ("平均 RankIC", _value(metrics.get("mean_rank_ic"))),
                ("RankIC 有效天数", _value(metrics.get("valid_rank_ic_session_count"))),
                ("ICIR 缺失原因", _value(metrics.get("icir_reason"))),
                ("RankICIR 缺失原因", _value(metrics.get("rank_icir_reason"))),
                ("共同样本身份", _value(wire.get("sample_mask_ref"))),
            ]) + '</section>'
            coverage_labels = (("样本格点数", "scope_key_count"),
                               ("参考成员格点数", "reference_key_count"),
                               ("成熟有效 Label 数", "mature_valid_label_count"),
                               ("有效预测数", "prediction_valid_count"),
                               ("有效配对数", "valid_pair_count"))
            for title, counts in (("共同样本覆盖（common）", coverage),
                                  ("信号自身覆盖（native）", native if type(native) is dict else {})):
                body += '<section><h2>' + title + '</h2>' + _metrics([
                    (label, _value(counts.get(field))) for label, field in coverage_labels])
                exclusions = counts.get("excluded_counts")
                body += '<h3>排除原因与数量（保存口径）</h3>'
                body += (_metrics([(reason, _value(count)) for reason, count in exclusions.items()])
                         if type(exclusions) is dict and exclusions else '<p>未提供排除原因记录。</p>')
                body += '</section>'
            body += ('<p>比较口径：' + _value(coverage.get("comparison_mode")) +
                     '。缺失字段均标为未提供；不补算比例或统计。</p>')
            limitations = wire.get("limitations")
            body += '<section><h2>保存限制</h2>' + (
                '<ul>' + ''.join('<li>' + _text(item) + '</li>' for item in limitations) + '</ul>'
                if type(limitations) is list and limitations else '<p>未提供</p>') + '</section>'
            details = {field: projected.get(field) for field in (
                "contract_version", "evidence_ref", "content_digest", "input_signal_refs", "label_ref",
                "label_spec", "sample_mask_ref", "statistics_ref", "summary", "coverage")}
            if not remote:
                body += '<details><summary>原合同摘要与完整引用</summary><pre>' + _text(json.dumps(
                    details, ensure_ascii=False, indent=2)) + '</pre></details>'

        except (ImportError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            body += '<p role="status">此项摘要不可用：' + _text(type(exc).__name__) + \
                    '。需要 Research 只读摘要 owner；未调用完整祖先 loader。</p>'
        return _page("单项信号评价", body)

    def account_html(self, result_id: str, account_index: int, *, start: str | None = None,
                     end: str | None = None, remote: bool = False) -> str:
        """Load one registered account via Engine; date filtering is display-only."""
        from datetime import date
        for value in (start, end):
            if value is not None:
                _require(type(value) is str and date.fromisoformat(value).isoformat() == value,
                         "invalid session date")
        _require(start is None or end is None or start <= end, "reversed date range")
        _, manifest, error = self._manifest(result_id)
        _require(manifest is not None, "manifest unavailable: " + str(error))
        accounts = manifest.get("accounts") or []
        _require(type(account_index) is int and 0 <= account_index < len(accounts), "unknown account")
        account = accounts[account_index]
        binding = account.get("backtest_ref")
        _require(type(binding) is dict, "no registered account")
        refs = {ref["artifact_key"]: ref for ref in manifest["artifacts"]}
        ref = refs[binding["artifact_key"]]
        _require(ref["owner"] == "Engine" and ref["artifact_type"] == "BacktestRun", "not an Engine account")
        if remote:
            # Registered evaluation leaf only: no account parts or training ancestry.
            from axiom_engine.runtime import load_backtest_evaluation
            evaluations = account.get("evaluation_refs") or []
            _require(bool(evaluations), "no registered evaluation curve")
            evaluation = evaluations[0]
            report_ref = refs[evaluation["artifact_key"]]
            _require(report_ref["owner"] == "Engine" and
                     report_ref["artifact_type"] == "BacktestEvaluation",
                     "not an Engine evaluation")
            path = _relative_file(report_ref, self.roots)
            _require(0 < path.stat().st_size <= RUN_METADATA_MAX_BYTES,
                     "evaluation curve metadata budget exceeded")
            report = _wire(load_backtest_evaluation(path))
            expected_run = {key: binding.get(key) for key in
                            ("run_id", "content_digest", "committed_sequence")}
            _require(report.get("contract_version") == report_ref["artifact_contract_version"] and
                     report.get("evaluation_ref") == report_ref["artifact_id"] ==
                     evaluation.get("evaluation_ref") and
                     report.get("content_digest") == report_ref["content_digest"] ==
                     evaluation.get("content_digest") and
                     report.get("input_run_ref") == evaluation.get("input_run_ref") == expected_run and
                     binding.get("run_id") == ref["artifact_id"] and
                     binding.get("content_digest") == ref["content_digest"],
                     "evaluation curve registered binding mismatch")
            nav = report.get("series")
            _require(type(nav) is list and bool(nav), "saved evaluation has no curve")
            wire = {"run_id": expected_run["run_id"]}
        else:
            wire, nav = _load_account(ref, self.roots, self.engine_limits)
            summary = {"availability": "VERIFIED", "artifact_id": wire["run_id"],
                       **{field: wire.get(field) for field in ("content_digest", "committed_sequence",
                                                              "signal_ref", "market_ref", "profile_ref")}}
            policy = wire.get("request_manifest", {}).get("portfolio_policy")
            if policy is not None:
                summary["strategy_ref"] = "sha256:" + sha256(json.dumps(
                    policy, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")).hexdigest()
            _require(not _account_bindings({"accounts": [account]}, {binding["artifact_key"]: summary}),
                     "account binding mismatch")
        rows = [row for row in nav if (start is None or row["session"] >= start) and
                (end is None or row["session"] <= end)]
        body = '<p><a href="/result/' + result_id[7:] + '">返回结果</a></p><h1>单账户曲线</h1>'
        body += ('<p>评价报告保存净值；已校验登记绑定，未重读账户原件。日期裁剪仅减少展示。默认完整保存区间；SVG 最多 600 点，明细仅显示所选区间最后 50 行。</p>' if remote else
                 '<p>仅此账户通过 Engine 原件验证。日期裁剪仅减少展示，owner 仍读取此账户所需分片。默认完整保存区间；SVG 最多 600 点，明细仅显示所选区间最后 50 行。</p>')
        if remote:
            body += '<p>曲线来源：按登记顺序选择第一份评价 <code>' + _text(report["evaluation_ref"]) + '</code> · ' + _text(report["contract_version"]) + '；不推断为最新评价。缺少保存序列时标为不可用，不补算。</p>'
        body += '<form method="get"><label>开始 <input type="date" name="start" value="' + _text(start or '') + '\"></label> <label>结束 <input type="date" name="end" value="' + _text(end or '') + '\"></label><button>查看区间</button></form>'
        body += '<p>账户：<code>' + _text(wire["run_id"]) + '</code> · 区间原始点数 ' + str(len(rows)) + ' / 全账户 ' + str(len(nav)) + '</p>'
        if rows:
            values = [Decimal(str(row["nav_minor"])) for row in rows]
            _require(all(value.is_finite() for value in values), "invalid NAV")
            low, high = min(values), max(values)
            span = high - low or Decimal(1)
            indices = (list(range(len(rows))) if len(rows) <= 600 else
                       [i * (len(rows) - 1) // 599 for i in range(600)])
            points = ' '.join(str(round(i * 900 / max(1, len(values) - 1), 2)) + ',' +
                              str(round(180 - float((value - low) / span) * 160, 2))
                              for i in indices for value in (values[i],))
            body += '<svg viewBox="0 0 900 200" role="img" aria-label="保存账户净值，纵轴按所选区间缩放"><polyline fill="none" stroke="#416e99" stroke-width="2" points="' + points + '"/></svg>'
            body += '<p>纵轴范围：' + _money(int(low)) + ' 至 ' + _money(int(high)) + '；横轴按保存交易行排序。</p>'
            body += ('<p>SVG 展示点数 ' + str(len(indices)) + ' / 区间原始点数 ' + str(len(rows)) +
                     '；按原始行号等距确定性抽样，保留首尾，可能省略区间内波动。未用展示点重算收益或其他指标。</p>')
            body += '<p>区间首尾：' + _text(rows[0]["session"]) + ' 至 ' + _text(rows[-1]["session"]) + '</p>'
            body += '<h2>保存净值明细（最后 ' + str(min(50, len(rows))) + ' / ' + str(len(rows)) + ' 行）</h2>'
            body += _metrics([(row["session"], _money(row["nav_minor"])) for row in rows[-50:]])
        else:
            body += '<p>所选区间没有保存的净值行。</p>'
        if not remote:
            self.opened_runs.setdefault(result_id, set()).add(wire["run_id"])
        return _page("单账户曲线", body, local_form=True)
