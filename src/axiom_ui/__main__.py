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
    parser.add_argument("run", type=Path, help="explicit saved Engine backtest JSON")
    parser.add_argument("--output", required=True, type=Path, help="new HTML file; existing files are refused")
    labels = parser.add_mutually_exclusive_group()
    labels.add_argument("--sample", action="store_true", help="handwritten synthetic display fixture; bypasses Engine Reader")
    labels.add_argument("--synthetic", action="store_true", help="owner-saved synthetic run; validates with Engine Reader and labels synthetic")
    parser.add_argument("--shareable", action="store_true", help="omit frozen raw inputs and complete payload from the export")
    parser.add_argument("--workbench", action="store_true", help="export the interactive, read-only workbench")
    parser.add_argument("--compare", action="append", type=Path, default=[], help="explicit saved comparison run; repeatable")
    parser.add_argument("--evaluation", action="append", type=Path, default=[], help="saved Engine evaluation via public Reader")
    parser.add_argument("--experiment", action="append", type=Path, default=[], help="saved Research rotation experiment via public Reader")
    parser.add_argument("--experiment-index", type=Path, help="explicit Research experiment index via public ExperimentReader")
    parser.add_argument("--data-batch", action="append", default=[], metavar="RUN_ID=PATH", help="explicit saved DataBatch public response; no Data query")
    args = parser.parse_args()
    if args.workbench and args.shareable:
        parser.error("--shareable applies to the static report; workbench exports are private local results")
    if not args.workbench and (args.compare or args.evaluation or args.experiment or args.experiment_index or args.data_batch):
        parser.error("comparison/evaluation/experiment inputs require --workbench")
    if args.sample and (args.compare or args.evaluation or args.experiment or args.experiment_index or args.data_batch):
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
                html = render_saved_workbench([args.run, *args.compare],
                    evaluation_paths=args.evaluation, experiment_paths=args.experiment,
                    experiment_index_path=args.experiment_index,
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
