"""Minimal read-only P12 projection from already saved owner responses."""
from .projection import ProjectionError, chart_context, project_data_layer, unavailable_layer
from .report import render_backtest_report, render_sample_report
from .workbench import render_saved_workbench, render_sample_workbench
from .enrichment import enrich_saved_projection, render_enriched_workbench
from .ml_result_entry import render_empty_stock_ml_entry
from .result_catalog import open_result_detail, refresh_result_catalog

__all__ = ["ProjectionError", "chart_context", "project_data_layer", "unavailable_layer", "render_backtest_report", "render_sample_report", "render_saved_workbench", "render_sample_workbench", "enrich_saved_projection", "render_enriched_workbench", "render_empty_stock_ml_entry", "refresh_result_catalog", "open_result_detail"]
