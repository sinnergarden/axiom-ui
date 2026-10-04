"""Explicit local export. Reads one saved artifact and creates one new UI file."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .report import render_backtest_report, render_sample_report


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
    args = parser.parse_args()
    try:
        if args.sample:
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
