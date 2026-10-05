"""Extend a previously validated UI export with explicit saved Owner layers."""
from copy import deepcopy
from pathlib import Path

from .projection import _require
from .saved_layers import load_review_display_for_view
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


def enrich_saved_projection(projection, *, evaluation_paths=None, review_displays=None):
    """No re-read/replay of large accounts; each new layer uses its Owner loader.

The input must be an existing validated ui_workbench_projection_v1 export.
This preserves its Research records and original account display facts.
"""
    result = _wire(projection)
    _require(result.get("contract_version") == "ui_workbench_projection_v1", "validated UI projection required")
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
    return result


def render_enriched_workbench(projection, *, evaluation_paths=None, review_displays=None, generated_at=None):
    result = enrich_saved_projection(projection, evaluation_paths=evaluation_paths, review_displays=review_displays)
    return _render(result["views"], generated_at or result.get("generated_at"))
