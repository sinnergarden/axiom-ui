# Axiom UI research workbench

This minimal Python package is a read-only P12 boundary for the demo. It
projects an already-read DataBatch into a canonical Data layer, pins explicit
session-to-query refs for chart replay, and returns an unavailable state for
missing Feature or other owner artifacts. No owner output is recomputed or
inferred from the current Data Snapshot.

An offline HTML report displays Engine's saved `backtest_run_v1/v2`: fixed run and
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
Saved v2 unit-split applications appear separately as account changes, with
position mark-basis events and announced suspension event sources in details.
The page preserves the frozen issuer event, its provenance and original status;
Runtime `APPLIED` means the saved model application, not issuer implementation.
Application selection locates the saved date and position. It adds no fill or
B/S marker, computes no entitlement or rounding, and leaves original market
prices unchanged. V1 receives no invented event fields. Explicitly synthetic
owner 1:5 and holder-ceiling outputs validate this display; they do not establish
real held-unit conversion acceptance. Real zero-entitlement applications keep
their saved NO_ENTITLEMENT status and separate native source evidence.
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

The same public evaluation loader accepts saved v1 and v2 reports. V2 adds the
owner's annualization window and account/CSI300 CAGR alongside cumulative return
and maximum drawdown. The page preserves each leg's availability, null and reason;
v1 gains no invented annualization. A partial evaluation can retain available
CAGR, and a completed short sample can retain unavailable CAGR. Date selection
never changes these saved metrics or their scope. The UI performs no CAGR or
day-count calculation, does not annualize drawdown, and adds no Sharpe. CSI300
remains a price index excluding dividends; the account includes saved dividend
ledger entries, so their return bases differ. Simulated CAGR is not a forecast.
Saved NO_DECISION records are shown as account-wide decisions that preserve
existing holdings, including when no security was selected. The UI creates no
liquidation or order for them.

Market point details retain DataBatch OHLCV and the same-key Engine market row
separately. Prices stay in the DataBatch basis; market status, reason and source
refs stay in the saved Engine evidence without inferring them from a price bar.

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

A Research index can be opened before any account output exists. Explicit
`stock_ml_paths` / `--stock-ml` directories use Research's public
`load_stock_ml_experiment` and `load_stock_model` Readers, then bind all stage
identities to the existing registration. The panel displays saved feature IDs
and versions, fit cutoff, declared feature/prediction windows, label maturity
and normalization, daily IC/RankIC and valid/excluded pairs. The current Readers
do not expose the actual mature training window, aggregate IC/ICIR or timings;
these are unavailable, without estimates. A blocked stock account retains its
owner status and reason. With no BacktestRun, account metrics, charts and
comparison are hidden. Research COMPLETE is a saved research registration;
it does not establish an account backtest or strategy performance.

```sh
PYTHONPATH=src:/path/to/axiom-research/src python3 -m axiom_ui --workbench --experiment-index /path/to/index.json --stock-ml /path/to/stock-experiment --output /tmp/axiom-stock-stage.html
```

Research's `ExperimentReader` supplies question descriptions, version parameters,
manual changes, saved run timestamps and read-only filters. Tags/groups remain question-level; favorite/shelved use
the run organization projection. Question flags are retained separately in
provenance and cannot silently stand in for run flags. Recent question grouping
uses owner `last_activity_at`, with saved run/version times inside the group.
The default tree uses owner `saved_run_ref` groups and owner backtest/registration
counts. Changing a saved evaluation or registration does not add a backtest.
Registration history opens its saved version metadata and corresponding parent
difference; older registered versions are not marked unrun.
Failed and unrun records, including questions with no version, remain navigable
without invented Engine run IDs or zero-valued metrics. External account/evaluation paths are loaded only when
explicitly supplied; index URIs are never auto-followed. Parent-child version
differences use Research's public `compare_versions` projection. Immutable
historical evaluation references are kept separate from newer reports on the
same account run; unregistered loaded reports are explicitly separate contexts.

Comparison separates frozen conditions (period, initial account, execution/fee
policies, price basis, data coverage and knowledge cutoffs) from research changes.
Different signal or account identity alone does not make conditions incompatible;
missing conditions remain unverifiable. Dates and episode/month selection only
clip or highlight saved chart points. Metrics always describe the original full
run. K-lines default to the last three months, with six-month, full and explicit
date windows.

Workbench HTML embeds private result and provenance data. Deliver it locally or
to the user's authorized private destination; never include it in a public repo
or public deployment. `--shareable` is supported only by the older static report. Public source includes
only hand-written synthetic UI fixtures, tests and sanitized acceptance notes.
Canonical requirements and financial definitions remain in
[axiom-docs](https://github.com/sinnergarden/axiom-docs/blob/a5a954902e1349199070077984d2473125222a9c/docs/ui-workbench-read-contract.md).
The saved v2 financial contract is
[Trade §11.2](https://github.com/sinnergarden/axiom-docs/blob/a5a954902e1349199070077984d2473125222a9c/docs/design/04_axiom_trade.md#long-history-evaluation).
Saved account event consumption follows
[Trade §9.2](https://github.com/sinnergarden/axiom-docs/blob/a5a954902e1349199070077984d2473125222a9c/docs/design/04_axiom_trade.md#etf-unit-split-application-proposal).
