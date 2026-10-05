"""Extend a previously validated UI export with explicit saved Owner layers."""
from copy import deepcopy
from pathlib import Path

from .projection import _require
from .saved_layers import attach_fill_display, load_consumer_receipt_for_view, load_review_display_for_view
from .workbench import _evaluation, _render, _wire


def _validation_run(browser_run):
    """Restore only integer fields serialized as text by our browser exporter."""
    run = deepcopy(browser_run)
    for key in ("committed_sequence", "initial_nav_minor"):
        if run.get(key) is not None:
            run[key] = int(run[key])
    for point in run.get("nav") or []:
        for key in ("nav_minor", "committed_sequence"):
            point[key] = int(point[key])
    for fill in run.get("fills") or []:
        fill["sequence"] = int(fill["sequence"])
    return run


def enrich_saved_projection(projection_path, *, projection_file_ref, evaluation_paths=None,
                            review_displays=None, review_consumer_receipts=None, fill_display_paths=None):
    """No re-read/replay of large accounts; each new layer uses its Owner loader.

The required external byte ref must come from a trusted previous export receipt,
not be generated from untrusted input at this call. It binds a fixed existing
export; it does not grant Owner validation to an arbitrary dict or fresh file.
"""
    _require(isinstance(projection_path, (str, Path)), "explicit saved projection file required; dicts are not trusted")
    from .public_share import load_projection
    result, actual_ref = load_projection(projection_path)
    _require(isinstance(projection_file_ref, str) and projection_file_ref == actual_ref,
             "CONTEXT_MISMATCH: saved projection external byte reference")
    groups = {}
    for view in result.get("views") or []:
        run_id = view.get("run", {}).get("run_id")
        if run_id:
            groups.setdefault(run_id, []).append(view)
    for run_id, path in (evaluation_paths or {}).items():
        _require(run_id in groups and isinstance(path, (str, Path)), "evaluation requires explicit loaded run/path")
        from axiom_engine.runtime import load_backtest_evaluation
        saved = _wire(load_backtest_evaluation(path))
        for view in groups[run_id]:
            view["evaluation"] = _evaluation(saved, _validation_run(view["run"]))
            registered = (view.get("research") or {}).get("evaluation_ref") or {}
            if isinstance(registered, dict) and registered.get("evaluation_ref") != saved["evaluation_ref"]:
                view["evaluation_registration_status"] = "INDEPENDENT_SAVED_OWNER_REPORT"
    for run_id, binding in (review_displays or {}).items():
        _require(run_id in groups, "display requires explicit loaded run")
        first = groups[run_id][0]
        load_review_display_for_view(first, **binding)
        for view in groups[run_id][1:]:
            view["market"] = deepcopy(first["market"])
    for run_id, binding in (review_consumer_receipts or {}).items():
        _require(run_id in groups and run_id not in (review_displays or {}) and
                 isinstance(binding, dict) and set(binding) == {"receipt_path", "receipt_sha256"},
                 "consumer receipt requires a unique loaded run and fixed byte reference")
        first = groups[run_id][0]
        load_consumer_receipt_for_view(first, **binding)
        for view in groups[run_id][1:]:
            view["market"] = deepcopy(first["market"])
    for run_id, path in (fill_display_paths or {}).items():
        _require(run_id in groups and isinstance(path, (str, Path)),
                 "fill display requires an explicit loaded run/path")
        from axiom_engine.runtime import load_fill_display
        report = _wire(load_fill_display(path))
        first = groups[run_id][0]
        attach_fill_display(first, report)
        for view in groups[run_id][1:]:
            view["market"]["fill_display"] = deepcopy(first["market"]["fill_display"])
    return result


def render_enriched_workbench(projection_path, *, projection_file_ref, evaluation_paths=None,
                              review_displays=None, review_consumer_receipts=None,
                              fill_display_paths=None, generated_at=None):
    result = enrich_saved_projection(projection_path, projection_file_ref=projection_file_ref,
                                     evaluation_paths=evaluation_paths, review_displays=review_displays,
                                     review_consumer_receipts=review_consumer_receipts,
                                     fill_display_paths=fill_display_paths)
    return _render(result["views"], generated_at or result.get("generated_at"))
