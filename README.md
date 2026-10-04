# Axiom UI research workbench

This minimal Python package is a read-only P12 boundary for the demo. It
projects an already-read DataBatch into a canonical Data layer, pins explicit
session-to-query refs for chart replay, and returns an unavailable state for
missing Feature or other owner artifacts. No owner output is recomputed or
inferred from the current Data Snapshot.

An offline HTML report displays Engine's saved `backtest_run_v1`: fixed run and
account identity, signal/market/profile refs, implementation versions, limitations,
NAV, positions, decisions, orders, simulated fills, ledgers and owner metrics.
NAV and positions retain per-session committed watermarks. CNY integer cents are
formatted as yuan with the original cents in the cell tooltip; decimal prices
retain their original precision. Missing output is unavailable, not zero.

```sh
# Explicitly synthetic UI fixture; does not execute Engine or prove a backtest.
PYTHONPATH=src python3 -m axiom_ui examples/synthetic_run.json --sample --output /tmp/axiom-sample.html

# Saved owner output: requires Engine's public, validating read API.
PYTHONPATH=src:/path/to/axiom-engine/src python3 -m axiom_ui /path/to/run.json --output /tmp/axiom-run.html

# Owner-saved golden fixture: validates through the same Reader and labels synthetic.
PYTHONPATH=src:/path/to/axiom-engine/src python3 -m axiom_ui /path/to/golden.json --synthetic --output /tmp/axiom-golden.html

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Open the exported HTML locally. It needs no browser dependencies, network,
server, database, owner application startup or deployment. Existing output files
are refused. The report never builds/trains/replays or writes to owner artifacts.
Experiment identity is shown only when provided by the owner; `signal_ref` is
retained when an experiment ID has not been supplied.
Owner orders with `UNKNOWN_MARKET_STATUS` produce a prominent execution-block
notice. Cash-only/zero-fill output is not return acceptance. `market_state`,
`state_reason`, order status and reason are retained, without granting a proxy
permission to trade from prices or volume.
An owner profile with `unknown_status_policy=etf_daily_observed` is explicitly
labelled as an ETF daily simulation approximation. Its saved execution parameters
and per-order `execution_admission` are shown; the original unknown market state
remains visible. The UI never chooses or changes this policy.
For an approved sharing destination, add `--shareable` to omit the frozen
market/signal input plan and full JSON payload while retaining saved result
tables, fixed refs, versions and limitations. This option does not publish or
upload anything.

Public design remains in
[axiom-docs](https://github.com/sinnergarden/axiom-docs/blob/main/docs/design/06_axiom_ui.md).
The interactive workbench is an offline, local entry point. Long-history acceptance uses an explicitly supplied Snapshot and saved owner result; a short sample does not establish twelve-year coverage.


## Interactive workbench

The three views share the selected Research version/run: saved NAV and owner
benchmark/drawdown comparison, OHLCV and simulated fill replay, monthly returns
and complete holding episodes. Only Engine computes account metrics and episode
bins. Missing/partial output, strict market-status blocking, and explicit ETF
daily approximation remain visible. The page is self-contained, makes no network
requests, and retains raw references and exact amounts in its local projection.
Integer values are serialized as decimal text for browser precision; `≈` marks
abbreviated display, and the saved decimal stays in details/tooltips.

```sh
PYTHONPATH=src python3 -m axiom_ui examples/synthetic_workbench.json --sample --workbench --output /tmp/axiom-workbench-sample.html

# Optional inputs are explicit saved files, each validated by its owner Reader.
PYTHONPATH=src:/path/to/axiom-engine/src:/path/to/axiom-research/src python3 -m axiom_ui /path/to/run.json --workbench --evaluation /path/to/evaluation.json --experiment-index /path/to/research-index.json --compare /path/to/previous-run.json --output /tmp/axiom-workbench.html
```

`render_saved_workbench` accepts `data_batches={run_id: already_read_batch}` or
`data_batch_paths={run_id: explicit_saved_response}`; the CLI equivalent is
`--data-batch RUN_ID=/path/to/ohlcv.json`. Registered Research DataBatch references
validate the whole response identity and, for path inputs, the exact file digest.
OHLCV must come from Data's public Reader with the same frozen replay Query,
Snapshot, reader/provenance and unadjusted basis; extending its field set to
high/low must reproduce the original common DataBatch digest. The renderer does
not discover roots or issue queries. Without this layer it shows the saved close
and volume with **K-line unavailable**, rather than inventing high/low.

Research's `ExperimentReader` supplies question descriptions, version parameters,
manual changes, saved run timestamps and read-only filters. Tags/groups remain question-level; favorite/shelved use
the run organization projection. Question flags are retained separately in
provenance and cannot silently stand in for run flags. Recent question grouping
uses owner `last_activity_at`, with saved run/version times inside the group.
Failed and unrun records, including questions with no version, remain navigable without invented Engine run IDs or
zero-valued metrics. External account/evaluation paths are loaded only when
explicitly supplied; index URIs are never auto-followed. Parent-child version
differences use Research's public `compare_versions` projection. Immutable
historical evaluation references are kept separate from newer reports on the
same account run; unregistered loaded reports are explicitly separate contexts.

Workbench HTML embeds private result and provenance data. Keep exports local;
`--shareable` is supported only by the older static report. Public source includes
only hand-written synthetic UI fixtures, tests and sanitized acceptance notes.
Canonical requirements and financial definitions remain in axiom-docs.
