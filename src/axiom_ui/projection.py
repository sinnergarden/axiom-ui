"""Read-only UI composition; Data JSON is only the Data fact layer.

No lookup, build, train, replay, account aggregation, or implicit current-ref
resolution is performed here. The caller supplies saved owner responses.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping


class ProjectionError(ValueError):
    """An owner response cannot be displayed with its semantics intact."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ProjectionError(reason)


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
    return "sha256:" + sha256(encoded.encode()).hexdigest()


def _generated(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProjectionError("invalid generated_at") from exc
    _require(instant.tzinfo is not None and instant.utcoffset() is not None,
             "generated_at requires timezone")
    return value


def _latest_timestamp(points: list[dict], field: str) -> str | None:
    values = [point[field] for point in points if point[field] is not None]
    if not values:
        return None
    def instant(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise ProjectionError("invalid source freshness timestamp") from exc
        _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
                 "source freshness timestamp lacks timezone")
        return parsed.astimezone(timezone.utc)
    return max(values, key=instant)


def _data(batch: Any) -> dict:
    wire = batch.to_json() if hasattr(batch, "to_json") else batch
    _require(type(wire) is dict and set(wire) == {"records", "field_meta", "context"},
             "unsupported DataBatch structure")
    context = wire["context"]
    _require(type(context) is dict and context.get("contract_version") == "data_batch_v1" and
             type(context.get("reader_version")) is str and
             type(context.get("snapshot_id")) is str and
             context["snapshot_id"] not in ("", "current", "latest") and
             type(context.get("query")) is dict and
             type(wire["records"]) is list and type(wire["field_meta"]) is dict,
             "incompatible or unpinned DataBatch")
    return wire


def chart_context(*, mode: str, security_id: str, session_refs: Mapping[str, Mapping[str, Any]],
                  price_basis: str, adjustment_anchor: str | None, time_axis: str,
                  generated_at: str | None = None) -> dict:
    """Bind a browse or run-replay chart to actual per-session owner refs."""
    _require(mode in {"browse", "run_replay"} and type(security_id) is str and bool(security_id),
             "invalid chart mode/security")
    _require(type(session_refs) is dict and bool(session_refs), "explicit session refs required")
    refs = {}
    for session, ref in session_refs.items():
        _require(type(session) is str and type(ref) is dict and
                 type(ref.get("snapshot_id")) is str and
                 ref["snapshot_id"] not in ("", "current", "latest") and
                 type(ref.get("query")) is dict and
                 type(ref.get("reader_version")) is str,
                 "unresolved session ViewRef")
        refs[session] = dict(ref)
    _require(price_basis in {"unadjusted", "common_anchor_adjusted_v1"} and
             (price_basis == "unadjusted") == (adjustment_anchor is None),
             "ambiguous price basis/anchor")
    _require(time_axis in {"session", "decision_available", "economic_period"},
             "unknown time axis")
    identity = {"contract_version": "p12_chart_projection_v1", "mode": mode,
                "security_id": security_id, "session_refs": refs,
                "price_basis": price_basis, "adjustment_anchor": adjustment_anchor,
                "time_axis": time_axis}
    return {**identity, "chart_context_digest": _digest(identity),
            "generated_at": _generated(generated_at)}


def project_data_layer(batch: Any, *, field: str, security_id: str, role: str,
                       chart: Mapping[str, Any] | None = None,
                       generated_at: str | None = None) -> dict:
    """Project an already-read Data field; retain every field-meta and query ref.

    The caller supplies a Data read made from the chart's saved query refs.
    This function checks those refs rather than resolving `current` itself.
    """
    wire = _data(batch)
    context = wire["context"]
    query = context["query"]
    definition = wire["field_meta"].get(field)
    _require(type(definition) is dict and type(definition.get("by_key")) is list and
             field in (query.get("fields") or []), "unknown field or missing provenance")
    _require(role in {"candles", "volume", "data_fact"}, "unsupported daily Data role")
    metadata = {}
    for meta in definition["by_key"]:
        _require(type(meta) is dict, "malformed per-key metadata")
        key = (meta.get("security_id"), meta.get("session"))
        _require(key not in metadata, "duplicate per-key metadata")
        metadata[key] = meta
    points = []
    for record in wire["records"]:
        _require(type(record) is dict and field in record, "malformed Data record")
        if record.get("security_id") != security_id:
            continue
        key = security_id, record.get("session")
        _require(key in metadata, "missing per-key provenance")
        meta = metadata.pop(key)
        points.append({"security_id": security_id, "session": key[1],
                       "value": record[field], "provenance": meta,
                       "missing_reason": meta.get("missing_reason"),
                       "source_available_time": meta.get("usable_from"),
                       "observed_time": meta.get("first_observed_at")})
    _require(bool(points), "INSUFFICIENT_SCOPE")
    _require(not any(key[0] == security_id for key in metadata), "unmatched provenance")
    points.sort(key=lambda point: point["session"])
    view_ref = {"snapshot_id": context["snapshot_id"], "domain": context.get("domain"),
                "query": query, "reader_version": context["reader_version"],
                "derivation": context.get("derivation")}
    if chart is not None:
        _require(chart.get("contract_version") == "p12_chart_projection_v1" and
                 chart.get("security_id") == security_id, "CONTEXT_MISMATCH")
        for point in points:
            pinned = chart.get("session_refs", {}).get(point["session"])
            _require(type(pinned) is dict and
                     all(pinned.get(k) == view_ref.get(k) for k in
                         ("snapshot_id", "query", "reader_version", "derivation")),
                     "CONTEXT_MISMATCH")
    basis = query.get("price_basis")
    _require(basis in {"unadjusted", "common_anchor_adjusted_v1"}, "unknown price basis")
    return {"contract_version": "p12_chart_projection_v1", "role": role,
            "field": field, "unit": definition.get("unit"), "dtype": definition.get("dtype"),
            "stage": "canonical" if context.get("derivation") is None else "base",
            "value_semantics": "Data selected fact" if context.get("derivation") is None else "Data stable derived value",
            "time_semantics": "session", "price_basis": basis,
            "adjustment_anchor": query.get("adjustment_anchor"),
            "source_ref": view_ref, "source_digest": _digest(view_ref),
            "chart_context_digest": chart.get("chart_context_digest") if chart else None,
            "points": points, "data_context": context,
            "freshness": {"last_source_available_time": _latest_timestamp(points, "source_available_time"),
                          "last_observed_time": _latest_timestamp(points, "observed_time")},
            "quality_state": "limited" if context.get("limitations") else "reported",
            "limitations": context.get("limitations"),
            "is_reconstructed": False, "generated_at": _generated(generated_at)}


def unavailable_layer(*, role: str, requested_ref: str | None,
                      requested_stage: str | None = None, unit: str | None = None,
                      reason: str = "LAYER_UNAVAILABLE", generated_at: str | None = None) -> dict:
    """Explicitly represent a missing owner artifact without recomputing it."""
    _require(role in {"feature", "signal", "decision", "fill", "account"}, "unknown owner role")
    _require(reason in {"LAYER_UNAVAILABLE", "ARTIFACT_NOT_FOUND", "UNKNOWN_STAGE"},
             "unknown layer status")
    if role == "feature":
        _require(requested_stage in {"base", "cross_sectional", "model_input"},
                 "UNKNOWN_STAGE")
    return {"contract_version": "p12_chart_projection_v1", "role": role,
            "requested_ref": requested_ref, "requested_stage": requested_stage,
            "unit": unit, "status": reason, "points": None,
            "is_reconstructed": False, "generated_at": _generated(generated_at)}
