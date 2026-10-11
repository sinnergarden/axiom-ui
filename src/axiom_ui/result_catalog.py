"""Private, read-only pages from Research's atomically registered result index.

The index is the only discovery source. This module never scans an artifact
directory or interprets a manifest-supplied loader name as executable code.
"""
from __future__ import annotations

from datetime import datetime, timezone
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


def _root_map(research_root: str | Path, engine_root: str | Path) -> dict[str, Path]:
    roots = {"research": Path(research_root).resolve(strict=True),
             "engine": Path(engine_root).resolve(strict=True)}
    _require(all(path.is_dir() for path in roots.values()), "trusted roots must be directories")
    return roots


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


def _artifact_summary(ref: dict, roots: Mapping[str, Path]) -> dict:
    """Only fixed owner readers may supply values beyond the manifest."""
    kind = ref["artifact_type"]
    if kind not in {"BacktestRun", "BacktestEvaluation", "StockSignalEvaluation"}:
        return {"availability": "METADATA_ONLY", "artifact_type": kind,
                "artifact_id": ref["artifact_id"]}
    try:
        path = _relative_file(ref, roots)
        if kind == "BacktestRun":
            if ref["artifact_contract_version"] in {"backtest_run_v7", "backtest_run_v8"}:
                from axiom_engine.runtime import load_stock_backtest_projection
                saved = load_stock_backtest_projection(
                    path, artifact_reader=lambda nested: _engine_nested_artifact(
                        nested, roots["engine"]), limits=STOCK_LIMITS)
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
            return {"availability": "VERIFIED", "artifact_type": kind,
                    "artifact_id": wire["run_id"], "status": wire.get("status"),
                    "content_digest": wire["content_digest"],
                    "committed_sequence": wire.get("committed_sequence"),
                    "final_nav_minor": nav[-1].get("nav_minor") if nav else None,
                    "metrics": wire.get("metrics")}
        if kind == "BacktestEvaluation":
            from axiom_engine.runtime import load_backtest_evaluation
            wire = _wire(load_backtest_evaluation(path))
            _require(wire.get("contract_version") == ref["artifact_contract_version"] and
                     wire.get("evaluation_ref") == ref["artifact_id"] and
                     wire.get("content_digest") == ref["content_digest"],
                     "BacktestEvaluation identity mismatch")
            return {"availability": "VERIFIED", "artifact_type": kind,
                    "artifact_id": wire["evaluation_ref"], "status": wire.get("status"),
                    "input_run_ref": wire.get("input_run_ref"),
                    "period_metrics": wire.get("period_metrics")}
        from axiom_research import load_stock_signal_evaluation
        saved = load_stock_signal_evaluation(path)
        wire = _wire(saved)
        _require(wire.get("contract_version") == ref["artifact_contract_version"] and
                 wire.get("evidence_ref") == ref["artifact_id"] and
                 wire.get("content_digest") == ref["content_digest"],
                 "StockSignalEvaluation identity mismatch")
        summary = wire.get("summary") or {}
        return {"availability": "VERIFIED", "artifact_type": kind,
                "artifact_id": wire["evidence_ref"], "status": wire.get("status"),
                "summary": {key: summary.get(key) for key in
                            ("mean_ic", "mean_rank_ic", "valid_ic_session_count",
                             "valid_rank_ic_session_count")}}
    except (FileNotFoundError, ImportError, OSError, ValueError, KeyError, TypeError,
            AttributeError) as exc:
        # Keep the registered result visible while making an unavailable or
        # mismatched original explicit. Never substitute synthetic zero values.
        return {"availability": "UNAVAILABLE", "artifact_type": kind,
                "artifact_id": ref.get("artifact_id"), "reason": type(exc).__name__}


def _account_bindings(manifest: dict, summaries: Mapping[str, dict]) -> None:
    for account in manifest.get("accounts") or []:
        backtest = account.get("backtest_ref")
        if backtest is None:
            continue
        key = backtest.get("artifact_key")
        report = summaries.get(key)
        if report and report.get("availability") == "VERIFIED":
            _require(all(report.get(field) == backtest.get(reference) for field, reference in
                         (("artifact_id", "run_id"), ("content_digest", "content_digest"),
                          ("committed_sequence", "committed_sequence"))),
                     "account BacktestRun identity mismatch")
        expected = {field: backtest.get(field) for field in
                    ("run_id", "content_digest", "committed_sequence")}
        for evaluation in account.get("evaluation_refs") or []:
            _require(evaluation.get("input_run_ref") == expected,
                     "account evaluation is bound to another run")
            saved = summaries.get(evaluation.get("artifact_key"))
            if saved and saved.get("availability") == "VERIFIED":
                _require(saved.get("artifact_id") == evaluation.get("evaluation_ref") and
                         saved.get("input_run_ref") == expected,
                         "loaded account evaluation identity mismatch")


def _page(title: str, body: str) -> str:
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
            + MARKER + '<title>' + _text(title) + '</title>'
            '<style>body{margin:0;background:#f3f6fa;color:#25374d;font:15px/1.6 '
            '-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1000px;'
            'margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dce5ef;'
            'border-radius:12px;padding:20px;margin:14px 0}a{color:#416e99}small{color:#52677e}'
            'h1{font-size:29px}h2{font-size:21px}h3{font-size:17px}ul{padding-left:22px}'
            'code{overflow-wrap:anywhere}dl{display:grid;grid-template-columns:150px 1fr;gap:6px 12px}'
            'dt{font-weight:600}dd{margin:0;overflow-wrap:anywhere}</style></head><body><main>'
            + body + '</main></body></html>')


def _detail(head: dict, manifest: dict | None, roots: Mapping[str, Path], error: str | None) -> tuple[str, set[str]]:
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
    summaries = {key: _artifact_summary(ref, roots) for key, ref in refs.items()}
    try:
        _account_bindings(manifest, summaries)
    except ResultCatalogError:
        summaries = {key: {"availability": "UNAVAILABLE", "reason": "CONTEXT_MISMATCH"}
                     for key in summaries}
    for key, label in (("folds", "训练折"), ("signals", "保存 Signal"),
                       ("accounts", "策略账户")):
        rows = manifest.get(key) or []
        items = []
        for row in rows:
            identity = row.get("fold_ref") or row.get("signal_run_ref") or row.get("strategy_ref")
            status = row.get("status")
            items.append('<li><strong>' + _value(identity) + '</strong> · ' + _value(status) +
                         (' · ' + _text(row["reason"]) if row.get("reason") else '') + '</li>')
        pieces.append('<section><h2>' + label + '（' + str(len(rows)) + '）</h2>' +
                      ('<ul>' + ''.join(items) + '</ul>' if items else '<p>未登记</p>') + '</section>')
    pieces.append('<section><h2>已登记产物</h2><ul>' + ''.join(
        '<li>' + _text(ref["artifact_type"]) + ' · <code>' + _text(ref["artifact_id"]) +
        '</code> · ' + _text(summaries[key]["availability"]) +
        (' · ' + _text(summaries[key]["reason"]) if summaries[key].get("reason") else '') +
        ('<details><summary>Owner 保存摘要</summary><pre>' + _text(json.dumps(
            {k: v for k, v in summaries[key].items() if k not in
             {"availability", "artifact_type", "artifact_id"}}, ensure_ascii=False, indent=2)) +
         '</pre></details>' if summaries[key]["availability"] == "VERIFIED" else '') + '</li>'
        for key, ref in refs.items()) + '</ul></section>')
    verified_runs = {summary["artifact_id"] for summary in summaries.values()
                     if summary.get("artifact_type") == "BacktestRun" and
                     summary.get("availability") == "VERIFIED"}
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
                       output_dir: str | Path, result_id: str) -> dict:
    """Read one registered manifest and its fixed owner types into one local page."""
    result_id = _hash(result_id, "result_id")
    roots = _root_map(research_root, engine_root)
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
    html, run_ids = _detail(head, manifest, roots, error)
    _atomic_html(target, html)
    return {"contract_version": "ui_result_detail_v1", "result_id": result_id,
            "verified_saved_backtest_count": len(run_ids), "availability":
            "MANIFEST_VERIFIED" if manifest is not None else "UNAVAILABLE", "output_file": str(target)}
