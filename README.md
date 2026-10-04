# Axiom UI read-only projections

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
This package is a small local export entry point, not the complete UI product.
