"""Bind already saved Data display layers to a validated UI view.

No factor adjustment, event inference, current discovery or account execution.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path

from .projection import _require


def _consumer_run_ref(view):
    """The browser exporter writes integer watermarks as decimal text."""
    run = view["run"]
    sequence = run.get("committed_sequence")
    _require(type(sequence) is int or type(sequence) is str and sequence.isdecimal(),
             "malformed saved consumer watermark")
    return {"run_id": run.get("run_id"), "content_digest": run.get("content_digest"),
            "committed_sequence": int(sequence)}


def attach_review_display(view, saved, *, manifest_sha256, snapshot_id, anchor_session, knowledge_cutoff, run_ref):
    """Owner loader verifies bytes; these checks bind the consumer's chosen clock."""
    manifest, layer = saved.get("manifest"), saved.get("ohlcv")
    _require(isinstance(run_ref, dict) and all(str(run_ref.get(k)) == str(view["run"].get(k))
             for k in ("run_id", "content_digest", "committed_sequence")),
             "CONTEXT_MISMATCH: saved display consumer/run identity")
    _require(isinstance(manifest, dict) and isinstance(layer, dict) and
             layer.get("contract_version") == "review_display_v1" and
             manifest.get("context") == layer.get("context"), "unsupported saved Data display")
    context = layer["context"]
    _require(context.get("usage") == "retrospective_review" and
             context.get("snapshot_id") == snapshot_id and context.get("anchor_session") == anchor_session and
             context.get("knowledge_cutoff") == knowledge_cutoff,
             "CONTEXT_MISMATCH: saved display Snapshot/anchor/cutoff")
    source = view["market"].get("native_chart") or view["market"].get("data_batch") or {}
    replay_only_v5 = view["run"].get("contract_version") == "backtest_run_v5" and not source
    if replay_only_v5:
        candidates = [item for item in view["market"].get("source_evidence") or []
                      if (item.get("context") or {}).get("domain") == "market_daily"]
        _require(len(candidates) == 1 and candidates[0].get("reference") in
                 (view["market"].get("source_refs") or []),
                 "CONTEXT_MISMATCH: saved ETF price source identity")
        source = {"context": candidates[0]["context"], "records": view["market"].get("rows")}
    _require((source.get("context") or {}).get("snapshot_id") == snapshot_id,
             "CONTEXT_MISMATCH: display/run market Snapshot")
    stock = view["run"].get("contract_version") in {"backtest_run_v3", "backtest_run_v4"}
    price_unit, volume = ("CNY/share", "volume_shares") if stock else ("CNY/fund unit", "volume_units")
    metadata, rows = layer.get("field_meta") or {}, layer.get("records")
    _require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), "malformed saved display rows")
    _require(all(metadata.get(k, {}).get("unit") == price_unit for k in
                 ("open", "high", "low", "close", "native_open", "native_high", "native_low", "native_close")) and
             metadata.get(volume, {}).get("unit") == ("shares" if stock else "fund units"),
             "CONTEXT_MISMATCH: display/run price or quantity unit")
    keys = [(r.get("security_id"), r.get("session")) for r in rows]
    _require(len(keys) == len(set(keys)), "duplicate saved display point")
    original_rows = source.get("records")
    configuration = view.get("configuration") or {}
    start, end = configuration.get("start_session"), configuration.get("end_session")
    _require(isinstance(original_rows, list) and original_rows and isinstance(start, str) and isinstance(end, str),
             "native display scope must retain saved rows and the original run window")
    native_keys = {(r.get("security_id"), r.get("session")) for r in original_rows
                   if isinstance(r.get("session"), str) and start <= r["session"] <= end}
    _require(native_keys and set(keys) == native_keys,
             "CONTEXT_MISMATCH: display/native scope keys; missing or extra rows are refused")
    if replay_only_v5:
        originals = {(row["security_id"], row["session"]): row for row in original_rows}
        for row in rows:
            original = originals[row["security_id"], row["session"]]
            for display_field, replay_field in (("native_open", "open"),
                                                 ("native_close", "close"),
                                                 ("volume_units", "volume_units")):
                shown, native_saved = row.get(display_field), original.get(replay_field)
                if shown is None or native_saved is None:
                    continue
                try:
                    equal = Decimal(str(shown)) == Decimal(str(native_saved))
                except InvalidOperation:
                    equal = False
                _require(equal, "CONTEXT_MISMATCH: display/native ETF price or volume")
    query = (source.get("context") or {}).get("query") or {}
    _require(not query.get("symbols") or {k[0] for k in native_keys}.issubset(query["symbols"]),
             "CONTEXT_MISMATCH: native security query scope")
    _require(not query.get("sessions") or {k[1] for k in native_keys}.issubset(query["sessions"]),
             "CONTEXT_MISMATCH: native session query scope")
    source_meta = source.get("field_meta") or {}
    _require((replay_only_v5 and
              (view["run"].get("price_unit"), view["run"].get("quantity_unit")) ==
              (price_unit, "fund units")) or
             (source_meta.get("close", {}).get("unit") == price_unit and
              source_meta.get(volume, {}).get("unit") == ("shares" if stock else "fund units")),
             "CONTEXT_MISMATCH: original native price/quantity unit")
    reasons = {(r["security_id"], r["session"]): r.get("missing_reason")
               for r in metadata.get("display_scale", {}).get("by_key") or []}
    fields = ("security_id", "session", "open", "high", "low", "close", "native_open", "native_high",
              "native_low", "native_close", "native_pre_close", volume, "amount_cny", "display_scale")
    view["market"]["review_display"] = {
        "contract_version": "review_display_v1", "manifest_sha256": manifest_sha256,
        "scope_policy": "exact_native_keys_in_original_run_window; reject_missing_and_extra_rows",
        "display_projection": True, "context": deepcopy(context),
        "records": [{**{k: deepcopy(r[k]) for k in fields if k in r},
                     "display_missing_reason": reasons.get((r["security_id"], r["session"]))} for r in rows],
        "field_units": {k: meta.get("unit") for k, meta in metadata.items()},
        "names_status": manifest.get("names_status"), "events_status": manifest.get("events_status")}
    names = saved.get("securities")
    if names is not None:
        _require(names.get("name_kind") == "snapshot_label" and names.get("name_validity") == "unknown",
                 "unsupported saved name interval")
        labels = {}
        for row in (names.get("batch") or {}).get("records") or []:
            if not row.get("name"):
                continue
            key, label = row["security_id"], row["name"]
            _require(key not in labels or labels[key] == label, "ambiguous saved snapshot name")
            labels[key] = label
        view["market"]["security_labels"] = labels
        view["market"]["security_name_scope"] = "snapshot_label; historical name validity unknown"
    view["market"]["review_events"] = [{"domain": domain, "event": deepcopy(row)}
        for domain, batch in (saved.get("events") or {}).items() for row in batch.get("records") or []]


def load_review_display_for_view(view, *, directory, manifest_sha256, snapshot_id, anchor_session, knowledge_cutoff, run_ref):
    """Only the public saved-file loader; no Data Reader or exporter."""
    from axiom_data import load_review_display
    _require(isinstance(directory, (str, Path)), "saved display requires an explicit directory")
    saved = load_review_display(directory, manifest_sha256=manifest_sha256)
    attach_review_display(view, saved, manifest_sha256=manifest_sha256, snapshot_id=snapshot_id,
                          anchor_session=anchor_session, knowledge_cutoff=knowledge_cutoff, run_ref=run_ref)
    return saved


def attach_independent_labels(view, saved, *, label_manifest_sha256, display_manifest_sha256,
                              original_run_ref, current_run_ref, source_snapshot_id, label_cutoff):
    """Bind separately observed names; never present them as historical names."""
    manifest, securities = saved.get("manifest"), saved.get("securities")
    _require(isinstance(manifest, dict) and isinstance(securities, dict) and
             manifest.get("contract_version") == "review_security_labels_v1" and
             manifest.get("usage") == "retrospective_label" and
             securities.get("name_kind") == "observed_label" and
             securities.get("name_valid_from") is None and securities.get("name_valid_to") is None,
             "unsupported independent saved label contract")
    display = view["market"].get("review_display") or {}
    context = display.get("context") or {}
    display_ref = manifest.get("display_ref") or {}
    _require(display.get("manifest_sha256") == display_manifest_sha256 and
             display_ref.get("sha256") == display_manifest_sha256 and
             display_ref.get("snapshot_id") == context.get("snapshot_id") and
             display_ref.get("anchor_session") == context.get("anchor_session") and
             display_ref.get("knowledge_cutoff") == context.get("knowledge_cutoff"),
             "CONTEXT_MISMATCH: independent labels/original price display")
    _require(manifest.get("run_ref") == original_run_ref and
             current_run_ref == _consumer_run_ref(view) and
             manifest.get("source_snapshot_id") == source_snapshot_id and
             manifest.get("label_cutoff") == label_cutoff and
             label_manifest_sha256,
             "CONTEXT_MISMATCH: independent labels/run or observation clock")
    native_ids = {row["security_id"] for row in display.get("records") or []}
    _require(native_ids and set(manifest.get("security_ids") or []) == native_ids,
             "CONTEXT_MISMATCH: independent label security scope")
    batch = securities.get("batch") or {}
    _require((batch.get("context") or {}).get("snapshot_id") == source_snapshot_id and
             ((batch.get("context") or {}).get("query") or {}).get("cutoff") == label_cutoff,
             "CONTEXT_MISMATCH: independent label batch clock")
    labels = {}
    for row in batch.get("records") or []:
        key = row.get("security_id")
        _require(key in native_ids and key not in labels, "CONTEXT_MISMATCH: independent label key")
        if row.get("name"):
            labels[key] = row["name"]
    view["market"]["security_labels"] = labels
    view["market"]["security_name_scope"] = "independent observed Snapshot label; historical name validity unknown"
    view["market"]["security_label_source"] = {"manifest_sha256": label_manifest_sha256,
        "source_snapshot_id": source_snapshot_id, "label_cutoff": label_cutoff,
        "original_display_manifest_sha256": display_manifest_sha256}


def load_consumer_receipt_for_view(view, *, receipt_path, receipt_sha256):
    """Read Data's fixed consumer rebind receipt, then only public saved loaders."""
    _require(isinstance(receipt_path, (str, Path)) and isinstance(receipt_sha256, str),
             "independent labels require a fixed receipt path and external byte reference")
    raw = Path(receipt_path).read_bytes()
    _require(sha256(raw).hexdigest() == receipt_sha256.removeprefix("sha256:"),
             "CONTEXT_MISMATCH: consumer receipt external byte reference")
    receipt = json.loads(raw)
    current = _consumer_run_ref(view)
    display, labels = receipt.get("display_binding") or {}, receipt.get("independent_labels_binding") or {}
    _require(receipt.get("contract_version") == "review_display_consumer_receipt_v1" and
             str(receipt.get("status", "")).startswith("PASSED_ACTUAL_SAVED_INPUT_EQUALITY") and
             receipt.get("current_run_ref") == current and display.get("run_ref") == current and
             labels.get("current_run_ref") == current and
             labels.get("original_run_ref") == receipt.get("original_bound_run_ref"),
             "CONTEXT_MISMATCH: consumer receipt/run identity")
    _require(all(k in display for k in ("directory", "manifest_sha256", "snapshot_id",
            "anchor_session", "knowledge_cutoff", "run_ref")) and
             all(k in labels for k in ("directory", "manifest_sha256", "source_snapshot_id",
            "label_cutoff", "original_run_ref", "current_run_ref")),
             "incomplete saved consumer receipt")
    load_review_display_for_view(view, **{k: display[k] for k in ("directory", "manifest_sha256",
        "snapshot_id", "anchor_session", "knowledge_cutoff", "run_ref")})
    from axiom_data import load_review_security_labels
    saved = load_review_security_labels(labels["directory"], manifest_sha256=labels["manifest_sha256"])
    attach_independent_labels(view, saved, label_manifest_sha256=labels["manifest_sha256"],
        display_manifest_sha256=display["manifest_sha256"], original_run_ref=labels["original_run_ref"],
        current_run_ref=current, source_snapshot_id=labels["source_snapshot_id"],
        label_cutoff=labels["label_cutoff"])
    return receipt


def attach_fill_display(view, report):
    """Project Owner's saved adjusted coordinates without adjusting prices here."""
    _require(report.get("contract_version") == "fill_display_report_v1" and
             report.get("input_run_ref") == _consumer_run_ref(view),
             "CONTEXT_MISMATCH: saved fill display/run identity")
    layer = view["market"].get("review_display") or {}
    _require(report.get("display_ref") == "sha256:" + str(layer.get("manifest_sha256")),
             "CONTEXT_MISMATCH: saved fill coordinates/Data display identity")
    saved_fills, coords = report.get("fills"), report.get("coordinates")
    run_fills = view["run"].get("fills") or []
    _require(isinstance(saved_fills, list) and isinstance(coords, list) and
             len(saved_fills) == len(coords) == len(run_fills),
             "CONTEXT_MISMATCH: saved fill coordinate coverage")
    by_id = {r.get("fill_id"): r for r in run_fills}
    _require(len(by_id) == len(run_fills), "duplicate original fill identity")
    projected = []
    for fill, point in zip(saved_fills, coords):
        original = by_id.get(fill.get("fill_id"))
        _require(original is not None and all(str(original.get(k)) == str(fill.get(k)) for k in
                 ("fill_id", "order_id", "security_id", "session", "side", "quantity", "price",
                  "fee_minor", "sequence")) and
                 all(point.get(k) == fill.get(k) for k in ("fill_id", "security_id", "session")),
                 "CONTEXT_MISMATCH: saved coordinate/original fill link")
        _require(point.get("status") in {"AVAILABLE", "UNAVAILABLE"} and
                 (point.get("display_price") is not None) == (point["status"] == "AVAILABLE"),
                 "malformed saved fill display status")
        projected.append({k: deepcopy(point.get(k)) for k in
                          ("fill_id", "security_id", "session", "status", "reason",
                           "display_price", "source_unit", "target_unit")})
    view["market"]["fill_display"] = {"contract_version": report["contract_version"],
        "content_digest": report["content_digest"], "display_result_ref": report["display_result_ref"],
        "display_ref": report["display_ref"], "status": report["status"], "coordinates": projected,
        "display_projection": True}
