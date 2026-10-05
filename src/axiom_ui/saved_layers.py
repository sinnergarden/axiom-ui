"""Bind already saved Data display layers to a validated UI view.

No factor adjustment, event inference, current discovery or account execution.
"""
from copy import deepcopy
from pathlib import Path

from .projection import _require


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
    _require((source.get("context") or {}).get("snapshot_id") == snapshot_id,
             "CONTEXT_MISMATCH: display/run market Snapshot")
    stock = view["run"].get("contract_version") == "backtest_run_v3"
    price_unit, volume = ("CNY/share", "volume_shares") if stock else ("CNY/fund unit", "volume_units")
    metadata, rows = layer.get("field_meta") or {}, layer.get("records")
    _require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), "malformed saved display rows")
    _require(all(metadata.get(k, {}).get("unit") == price_unit for k in
                 ("open", "high", "low", "close", "native_open", "native_high", "native_low", "native_close")) and
             metadata.get(volume, {}).get("unit") == ("shares" if stock else "fund units"),
             "CONTEXT_MISMATCH: display/run price or quantity unit")
    keys = [(r.get("security_id"), r.get("session")) for r in rows]
    _require(len(keys) == len(set(keys)), "duplicate saved display point")
    reasons = {(r["security_id"], r["session"]): r.get("missing_reason")
               for r in metadata.get("display_scale", {}).get("by_key") or []}
    fields = ("security_id", "session", "open", "high", "low", "close", "native_open", "native_high",
              "native_low", "native_close", "native_pre_close", volume, "amount_cny", "display_scale")
    view["market"]["review_display"] = {
        "contract_version": "review_display_v1", "manifest_sha256": manifest_sha256,
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
