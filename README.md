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
day-count calculation and does not annualize drawdown. Saved v1/v2 have no invented Sharpe. CSI300
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
and normalization, daily IC/RankIC and valid/excluded pairs. An optional `stock_stage_report_paths` / `--stock-stage-report` input uses
`load_stock_stage_report` and binds all six input refs to the loaded experiment
and its Research registration. It displays the saved declared/actual training
windows, rows/sessions, IC/RankIC means and valid sessions, and native measurement
modes/status/seconds. Reused stages retain null seconds, and inherited Feature/Qlib
cold measurements remain separate from current-model timings. Build/total are
never summed and whole-receipt memory is not allocated to stages. Without a report,
the actual mature training window, aggregate means and timings stay unavailable.
ICIR is not calculated. The public contract is
[Research §4.6](https://github.com/sinnergarden/axiom-docs/blob/7a139c2792d9c512ebb039ef194ca5d09f390e5f/docs/design/05_axiom_research.md#stock-saved-stage-report-proposal). A blocked stock account retains its
owner status and reason. With no BacktestRun, account metrics, charts and
comparison are hidden. Research COMPLETE is a saved research registration;
it does not establish an account backtest or strategy performance.

The workbench also reads stock `backtest_run_v3` through the same public Engine
loader, together with its saved evaluation and exact Research registration.
Stock quantities and native daily volume are shares; prices are CNY per share.
Per-fill commission, seller stamp tax and transfer fees remain owner values.
The saved prediction universe, Shenzhen execution subset, model/execution
Snapshots, admission, profile and evidence clocks remain visible. An explicit
`stock_daily_observed` profile is labelled a retrospective daily approximation;
UNKNOWN status stays unknown. Strict blocking and zero-fill cash-only results
are a separate control, not strategy return acceptance. Actual run status and
its registration describe the current account; the old model manifest's account
status remains historical research provenance.

For v3, the validated native `market_daily` source supplies OHLCV and per-key
provenance. An optional explicit saved DataBatch must match that complete source
identity exactly. The display retains its original reference and query clocks,
while omitting full coverage tables and compressed payloads. It is clearly a
display projection, not a new complete DataBatch. Saved evaluation metrics,
monthly returns, episodes, bins and null CAGR are preserved without computation.
The stock contract is [Trade §6.1](https://github.com/sinnergarden/axiom-docs/blob/e65dff8a3c39fa750efa5162058ce2348f2ab6fa/docs/design/04_axiom_trade.md#stock-daily-observed-minimal).

```sh
PYTHONPATH=src:/path/to/axiom-research/src python3 -m axiom_ui --workbench --experiment-index /path/to/index.json --stock-ml /path/to/stock-experiment --stock-stage-report /path/to/stage-report.json --output /tmp/axiom-stock-stage.html
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
run. The common chart window defaults to the full saved range, with three/six-month and explicit
date windows.

## Reviewed interaction remediation

The implementation follows the approved [UI design](https://github.com/sinnergarden/axiom-docs/blob/6ea946fa26cb978bfd94bb825f791245b4e85adc/docs/design/06_axiom_ui.md#8-本轮整页交互与视觉规范).
Apache ECharts **6.1.0** is vendored from its fixed official tag. Its SHA-256,
upstream commit, Apache-2.0 license and NOTICE are retained in `assets/echarts.vendor.json`.
The standalone page embeds the checked bundle under its existing script-hash CSP;
there is no CDN, runtime fetch or frontend dependency installation.

Hover anywhere within the plot to see the nearest saved date. Click to lock it;
further hovering leaves the locked details intact. Drag to pan, use Ctrl+wheel
to zoom, drag the bottom overview or enter precise dates. The common range only
controls saved-point display. Original metrics and the final adjustment anchor
keep their full saved scope. Trade chains use actual decision/intent/order/fill
references, load year/month/batch details on demand and paginate long lists.

Saved `evaluation_report_v3` uses the same public Engine loader. It adds the
Owner's drawdown range, risk availability, rolling series, percentage-return bins
and benchmark choices; the UI performs no statistical computation. Old v1/v2
stay readable. Short-span nulls and missing benchmark inputs are displayed with
their reasons. The financial definition remains in [Trade §11.3](https://github.com/sinnergarden/axiom-docs/blob/c648cfc38571c1a4bad37c9a0010cd7d9659285b/docs/design/04_axiom_trade.md#saved-account-analysis).

`render_saved_workbench(..., review_displays={run_id: binding})` accepts an
explicit binding with `directory`, `manifest_sha256`, `snapshot_id`,
`anchor_session`, `knowledge_cutoff`, and the consumer's exact `run_ref`
(run ID, content digest, committed sequence). It only calls Data's saved
`load_review_display`, checks the run's Snapshot and units, and retains native
prices and missing factors. Snapshot name labels do not assert historical name
validity. Adjusted B/S coordinates require a separately saved Engine mapping;
`fill_display_paths={run_id: path}` reads Engine's public saved
`load_fill_display` document and checks the exact run, Data manifest, original
fill IDs/prices/units and coordinate coverage. Adjusted B/S uses only its saved
display prices; unavailable coordinates stay absent. The original fill price
remains in the transaction details and unadjusted chart. The v3 chart uses
Owner-saved account and benchmark cumulative-return strings for the percentage
view; older reports retain the saved normalized-index view.

For a saved display originally bound to an older run but proven identical to
the selected consumer's frozen market inputs, pass
`review_consumer_receipts={run_id: {"receipt_path": path,
"receipt_sha256": trusted_external_sha256}}`. The fixed Data receipt must
bind the current run's full identity, original price manifest and separately
observed security labels. UI reads both layers through Data's public saved
loaders; the independent label Snapshot and cutoff are shown explicitly, with
historical name validity unknown. The expected receipt digest must come from
the Data handoff, not from hashing an unreviewed file at call time.

`enrich_saved_projection(existing_export_path, projection_file_ref=trusted_external_byte_ref,
evaluation_paths={run_id: path},
review_displays={run_id: binding}, fill_display_paths={run_id: path})` can extend a previously validated
`ui_workbench_projection_v1` without reloading its large account document.
The required `sha256:...` byte ref comes from a trusted previous export receipt;
the function verifies the saved file against it and rejects arbitrary dictionaries.
It never creates trust by hashing untrusted input and accepting that result as
the expected ref. `render_enriched_workbench` enforces the same check even when
no new layer is supplied. Unverified mappings belong only in the explicit
synthetic sample renderer. Display rows must exactly cover the original native
keys inside the full run window; missing whole rows and extra securities/dates
are refused. Null prices on present rows remain null. Viewport changes do not
change that fixed scope or the final anchor.
New evaluation identity/watermarks are bound to the original account projection;
only the explicit public saved-file loaders run. This does not replay an account,
rerun evaluation, register a Research run or write any Owner file.

Workbench HTML embeds private result and provenance data. Keep the full export
local or in an authorized private destination. For public publication, use the
separate exporter below with an explicitly approved selection of saved results.
`--shareable` remains an option of the older static report; it does not authorize
public publication. Public source includes synthetic UI fixtures, tests,
sanitized acceptance notes and the reviewed public projection in `site/`.
Canonical requirements and financial definitions remain in
[axiom-docs](https://github.com/sinnergarden/axiom-docs/blob/a5a954902e1349199070077984d2473125222a9c/docs/ui-workbench-read-contract.md).
The saved v2 financial contract is
[Trade §11.2](https://github.com/sinnergarden/axiom-docs/blob/a5a954902e1349199070077984d2473125222a9c/docs/design/04_axiom_trade.md#long-history-evaluation).
Saved account event consumption follows
[Trade §9.2](https://github.com/sinnergarden/axiom-docs/blob/a5a954902e1349199070077984d2473125222a9c/docs/design/04_axiom_trade.md#etf-unit-split-application-proposal).

## Publish the selected saved results

The deployment target is [sinnergarden.github.io/axiom-ui](https://sinnergarden.github.io/axiom-ui/).
This is an operating recipe; canonical UI and owner boundaries remain in
[axiom-docs](https://github.com/sinnergarden/axiom-docs/blob/main/docs/design/06_axiom_ui.md).

1. Select the saved results authorized for public viewing in a private selection
   file outside this repository. Each entry gives its `slug`, `title` and explicit
   saved `input` and nonempty `run_ids` list. Omitting run selection is rejected;
   later accounts in the same input are not automatically included. The exporter does not discover Data roots or a current Snapshot,
   collect data, train models or replay a backtest.
2. Export and check the projection:

   ```sh
   PYTHONPATH=src python3 tools/export_public_site.py --selection /path/to/approved-selection.json --output site
   python3 tools/check_public_site.py site
   ```

   The exporter produces the static bundle and sanitized publication provenance
   in `site/publication.json`. Keep the private selection and source files outside
   the repository; review the generated public pages and checks before committing.
   Saved OHLCV for the selected account window and related securities remains
   available for continuous K-lines and B/S replay through the existing renderer.
   Original prices, units, basis, nulls and source/file references are preserved;
   the chart is explicitly a display subset, with no invented complete DataBatch
   digest. Full batches, coverage and complete per-key proof are omitted.
   A selection uses `authorization: "explicit_selected_public_results"`,
   `generated_at`, and `results: [{slug, title, input, run_ids}]`. Optional
   `performance_html` supplies an existing saved performance summary. Optional
   `process: {source, target}` binds a saved model/training summary to the exact
   selected stock signal and account identities; every target account must also
   be explicitly selected. Neither option runs the owner business functions.
3. Submit the generated `site/` changes and checks in a draft PR targeting
   `publish/ui-readonly`. After parent review and merge, publish only the reviewed
   `site/` tree to the dedicated `gh-pages` branch:

   ```sh
   # REVIEWED_MERGE must be the exact parent-approved default-branch commit.
   git subtree split --prefix=site REVIEWED_MERGE
   # Use the returned publication commit, with no force push.
   git push origin PUBLICATION_COMMIT:refs/heads/gh-pages
   ```

   The publishing branch contains only static public files. Confirm its tree
   matches `REVIEWED_MERGE:site` before pushing. GitHub's built-in Pages deployment
   publishes that branch automatically; no custom repository workflow is used.

Future updates use the same export, public checks, reviewed PR and static-tree
publication flow. The checker uses Python's standard library and needs no Owner
package or backend. Publishing never reads Data roots or runs owner business
functions. Keep PR/feature branches separate from the configured `gh-pages` source.

One-time repository setup selects **Settings → Pages → Build and deployment →
Source: Deploy from a branch → gh-pages → /(root)**. The tracked `.nojekyll`
file means these files need no Jekyll build. This is GitHub's supported branch
publishing mode; it needs no new token/workflow scope, credentials, custom domain
or paid service. The current credential cannot upload a custom Actions workflow,
so that approach was stopped without changing authentication. Pages settings
remain unchanged until the parent has reviewed the concrete publication.
