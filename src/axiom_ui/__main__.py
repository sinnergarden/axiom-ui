"""Explicit local export. Reads one saved artifact and creates one new UI file."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .report import render_backtest_report, render_sample_report
from .workbench import render_saved_workbench, render_sample_workbench


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Export an offline, read-only Axiom run report")
    parser.add_argument("run", type=Path, nargs="?", help="explicit saved Engine backtest JSON; optional for a Research index workbench")
    parser.add_argument("--output", type=Path, help="HTML file or private catalog directory")
    labels = parser.add_mutually_exclusive_group()
    labels.add_argument("--sample", action="store_true", help="handwritten synthetic display fixture; bypasses Engine Reader")
    labels.add_argument("--synthetic", action="store_true", help="owner-saved synthetic run; validates with Engine Reader and labels synthetic")
    parser.add_argument("--shareable", action="store_true", help="omit frozen raw inputs and complete payload from the export")
    parser.add_argument("--workbench", action="store_true", help="export the interactive, read-only workbench")
    parser.add_argument("--compare", action="append", type=Path, default=[], help="explicit saved comparison run; repeatable")
    parser.add_argument("--evaluation", action="append", type=Path, default=[], help="saved Engine evaluation via public Reader")
    parser.add_argument("--experiment", action="append", type=Path, default=[], help="saved Research rotation experiment via public Reader")
    parser.add_argument("--experiment-index", type=Path, help="explicit Research experiment index via public ExperimentReader")
    parser.add_argument("--stock-ml", action="append", type=Path, default=[], help="explicit saved stock ML directory via Research public Readers")
    parser.add_argument("--stock-stage-report", action="append", type=Path, default=[], help="explicit saved stage report via Research public Reader; requires --stock-ml")
    parser.add_argument("--data-batch", action="append", default=[], metavar="RUN_ID=PATH", help="explicit saved DataBatch public response; no Data query")
    parser.add_argument("--refresh-results", action="store_true", help="refresh the private Research v2 result catalog")
    parser.add_argument("--open-result", help="read one registered result detail after a list refresh")
    parser.add_argument("--serve-results", action="store_true", help="temporary loopback read-only result browser")
    parser.add_argument("--port", type=int, default=0, help="loopback port for --serve-results; default chooses a free port")
    parser.add_argument("--workspace-config", type=Path, help="private JSON with research_root and engine_root")
    parser.add_argument("--research-root", type=Path, help="trusted Research root containing index.json")
    parser.add_argument("--engine-root", type=Path, help="trusted Engine artifact root")
    args = parser.parse_args()
    if args.refresh_results or args.open_result is not None or args.serve_results:
        if sum((bool(args.refresh_results), args.open_result is not None, bool(args.serve_results))) != 1 or (
                args.workspace_config is not None and
                (args.research_root is not None or args.engine_root is not None)) or (
                args.workspace_config is None and
                (args.research_root is None or args.engine_root is None)) or (
                not args.serve_results and args.output is None) or (
                args.serve_results and args.output is not None) or (
                not args.serve_results and args.port != 0) or (
                args.run is not None or
                args.workbench or args.sample or args.synthetic or
                args.shareable or args.compare or args.evaluation or args.experiment or
                args.experiment_index or args.stock_ml or args.stock_stage_report or args.data_batch):
            parser.error("result catalog requires one action and trusted roots; export also needs --output DIR")
        try:
            from .result_catalog import refresh_result_catalog, open_result_detail
            if args.workspace_config is not None:
                config = json.loads(args.workspace_config.read_text(encoding="utf-8"),
                                    object_pairs_hook=_unique)
                if (type(config) is not dict or
                        not {"research_root", "engine_root"} <= set(config) or
                        not set(config) <= {"research_root", "engine_root", "engine_limits"}):
                    raise ValueError("workspace config needs trusted roots and optional engine_limits")
                research_root, engine_root = config["research_root"], config["engine_root"]
                engine_limits = config.get("engine_limits")
            else:
                research_root, engine_root = args.research_root, args.engine_root
                engine_limits = None
            if args.serve_results:
                from .result_server import serve_result_catalog
                serve_result_catalog(research_root=research_root, engine_root=engine_root,
                                     engine_limits=engine_limits, port=args.port)
                return
            if args.refresh_results:
                refreshed = refresh_result_catalog(research_root=research_root,
                                                   engine_root=engine_root,
                                                   output_dir=args.output)
                result_path = refreshed["output_dir"]
            else:
                opened = open_result_detail(research_root=research_root, engine_root=engine_root,
                                            output_dir=args.output, result_id=args.open_result,
                                            engine_limits=engine_limits)
                result_path = opened["output_file"]
        except (OSError, ValueError, ImportError) as exc:
            parser.exit(2, f"Axiom results: {exc}\n")
        print(result_path)
        return
    if args.research_root is not None or args.engine_root is not None or args.workspace_config is not None or args.port != 0:
        parser.error("trusted roots/port require a result catalog action")
    if args.output is None:
        parser.error("--output is required for report exports")
    if args.workbench and args.shareable:
        parser.error("--shareable applies to the static report; workbench exports are private local results")
    if args.run is None and not (args.workbench and args.experiment_index and not (args.sample or args.synthetic)):
        parser.error("a saved run or --workbench --experiment-index is required")
    if not args.workbench and (args.compare or args.evaluation or args.experiment or args.experiment_index or args.data_batch or args.stock_ml or args.stock_stage_report):
        parser.error("comparison/evaluation/experiment inputs require --workbench")
    if args.sample and (args.compare or args.evaluation or args.experiment or args.experiment_index or args.data_batch or args.stock_ml or args.stock_stage_report):
        parser.error("synthetic UI fixtures cannot load saved owner inputs")
    try:
        if args.workbench:
            if args.sample:
                run = json.loads(args.run.read_text(encoding="utf-8"), object_pairs_hook=_unique)
                html = render_sample_workbench(run)
            else:
                synthetic_ids = []
                if args.synthetic:
                    from axiom_engine.runtime import load_backtest_run
                    synthetic_ids = [load_backtest_run(args.run).to_dict()["run_id"]]
                batches = {}
                for value in args.data_batch:
                    run_id, separator, path = value.partition("=")
                    if not separator or not run_id or not path or run_id in batches:
                        raise ValueError("--data-batch requires unique RUN_ID=PATH")
                    batches[run_id] = Path(path)
                html = render_saved_workbench(([args.run] if args.run is not None else []) + args.compare,
                    evaluation_paths=args.evaluation, experiment_paths=args.experiment,
                    experiment_index_path=args.experiment_index,
                    stock_ml_paths=args.stock_ml,
                    stock_stage_report_paths=args.stock_stage_report,
                    data_batch_paths=batches,
                    synthetic_run_ids=synthetic_ids)
        elif args.sample:
            run = json.loads(args.run.read_text(encoding="utf-8"), object_pairs_hook=_unique)
            html = render_sample_report(run, shareable=args.shareable)
        else:
            html = render_backtest_report(args.run, synthetic=args.synthetic, shareable=args.shareable)
        # Never overwrite an owner artifact or an existing export.
        with args.output.open("x", encoding="utf-8") as target:
            target.write(html)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(2, f"Axiom report: {exc}\n")
    print(args.output)


if __name__ == "__main__":
    main()
