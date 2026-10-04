"""Write explicit synthetic UI contract fixtures; no account computation.

All prices/metrics below are handwritten display values, not Engine acceptance.
Hashing only binds the synthetic Data records/provenance used by reader tests.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path


def digest(value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + sha256(text.encode()).hexdigest()


SECURITY = "cn.etf.SSE.510300.20120528"
DAYS = ["2026-03-30", "2026-03-31", "2026-04-01", "2026-04-02", "2026-04-29", "2026-04-30"]
PRICES = [
    ["10.00", "10.10", "9.90", "10.00", 10000],
    ["10.10", "10.60", "10.00", "10.50", 13000],
    ["10.50", "10.60", "10.00", "10.10", 14000],
    ["10.00", "10.20", "9.90", "10.00", 14000],
    ["9.00", "9.70", "8.90", "9.50", 15000],
    ["9.50", "9.90", "9.40", "9.80", 16000],
]


def market(prices, snapshot):
    fields = ["open", "high", "low", "close", "volume_units"]
    records = [{"security_id": SECURITY, "session": day, **dict(zip(fields, price))}
               for day, price in zip(DAYS, prices)]
    query = {"fields": fields, "symbols": [SECURITY], "sessions": DAYS,
             "price_basis": "unadjusted", "adjustment_anchor": None,
             "pit_policy": "synthetic_observed", "purpose": "market_replay",
             "cutoff_by_session": {d: d+"T20:00:00+08:00" for d in DAYS},
             "policy_by_session": None, "universe_id": None}
    context = {"contract_version": "data_batch_v1", "snapshot_id": snapshot,
               "domain": "market_daily", "reader_version": "synthetic_reader_v1",
               "contract_id": "synthetic_daily_v1", "source_profile_id": "synthetic",
               "query": query, "limitations": ["Synthetic UI fixture only"], "coverage": None}
    meta = {f: {"unit": "fund units" if f == "volume_units" else "CNY/fund unit",
                "dtype": "int64" if f == "volume_units" else "decimal",
                "by_key": [{"security_id": SECURITY, "session": d, "missing_reason": None,
                            "usable_from": d+"T12:00:00Z", "first_observed_at": d+"T12:00:00Z",
                            "evidence_ref": "synthetic:evidence:"+d} for d in DAYS]}
            for f in fields}
    batch = {"records": records, "field_meta": meta, "context": context}
    base = deepcopy(batch)
    base_fields = ["open", "close", "volume_units"]
    base["context"]["query"]["fields"] = base_fields
    base["records"] = [{k: r[k] for k in ("security_id", "session", *base_fields)} for r in records]
    base["field_meta"] = {k: meta[k] for k in base_fields}
    replay = {"contract_version": "market_replay_v1", "price_basis": "unadjusted",
              "rows": deepcopy(base["records"]), "source_refs": [digest(base)],
              "source_evidence": [{"reference": digest(base), "context": base["context"]}]}
    return batch, replay


def example(run_id, old=False, blocked=False, failed=False):
    prices = deepcopy(PRICES)
    if old:
        prices[-1] = ["9.50", "9.70", "8.10", "8.33", 16000]
    batch, replay = market(prices, "synthetic:old-snapshot" if old else "synthetic:current-snapshot")
    amounts = [999900, 1004900, 1000900, 999800, 1004700, 993000 if old else 1007700]
    indices = ["0.9999", "1.0049", "1.0009", "0.9998", "1.0047", "0.993" if old else "1.0077"]
    watermarks = [2, 3, 4, 6, 8, 9]
    cash = [899900, 899900, 899900, 999800, 909700, 909700]
    nav = [{"session": d, "cash_minor": c, "market_value_minor": n-c,
            "receivable_minor": 0, "nav_minor": n, "nav_index": idx, "committed_sequence": seq}
           for d, c, n, idx, seq in zip(DAYS, cash, amounts, indices, watermarks)]
    positions = [{"session": DAYS[i], "security_id": SECURITY, "quantity": 100,
                  "sellable_quantity": 0 if i in (0, 4) else 100,
                  "mark_price": prices[i][3], "mark_session": DAYS[i], "is_stale": False,
                  "market_value_minor": n-c, "committed_sequence": watermarks[i]}
                 for i, (n, c) in enumerate(zip(amounts, cash)) if i != 3]
    fills = [
        {"fill_id": run_id+":fill:0", "order_id": run_id+":order:0", "session": DAYS[0], "security_id": SECURITY,
         "side": "BUY", "quantity": 100, "price": "10.00", "gross_minor": 100000, "fee_minor": 100,
         "cash_delta_minor": -100100, "sequence": 1, "execution_admission": "SYNTHETIC_FIXTURE"},
        {"fill_id": run_id+":fill:1", "order_id": run_id+":order:1", "session": DAYS[3], "security_id": SECURITY,
         "side": "SELL", "quantity": 100, "price": "10.00", "gross_minor": 100000, "fee_minor": 100,
         "cash_delta_minor": 99900, "sequence": 5, "execution_admission": "SYNTHETIC_FIXTURE"},
        {"fill_id": run_id+":fill:2", "order_id": run_id+":order:2", "session": DAYS[4], "security_id": SECURITY,
         "side": "BUY", "quantity": 100, "price": "9.00", "gross_minor": 90000, "fee_minor": 100,
         "cash_delta_minor": -90100, "sequence": 7, "execution_admission": "SYNTHETIC_FIXTURE"},
    ]
    orders = [{"order_id": f["order_id"], "session": f["session"], "security_id": SECURITY,
               "side": f["side"], "quantity": 100, "filled_quantity": 100, "status": "FILLED",
               "reason": None, "market_state": "synthetic_known", "state_reason": "synthetic_fixture",
               "execution_admission": "SYNTHETIC_FIXTURE"} for f in fills]
    decisions = [{"feature_session": "2026-03-27", "trade_session": DAYS[0], "status": "DECISION_COMPLETE",
                  "selected_security_id": SECURITY, "intents": [{"security_id": SECURITY, "side": "BUY", "quantity": 100}],
                  "trace": [{"reason": "SYNTHETIC_SAVED_RULE"}]}]
    metrics = {"total_return": "-0.007" if old else "0.0077", "max_drawdown": "-0.01184" if old else "-0.005075131853",
               "total_fees_minor": 300, "turnover_minor": 290000, "fill_count": 3, "unfilled_order_count": 0}
    if blocked:
        for point in nav:
            point.update(cash_minor=1000000, market_value_minor=0, nav_minor=1000000, nav_index="1", committed_sequence=1)
        positions, fills = [], []
        orders = [{"order_id": run_id+":order:0", "session": DAYS[0], "security_id": SECURITY,
                   "side": "BUY", "quantity": 100, "filled_quantity": 0, "status": "EXPIRED",
                   "reason": "UNKNOWN_MARKET_STATUS", "market_state": "unknown_status", "state_reason": "status_source_missing"}]
        metrics = {"total_return": "0", "max_drawdown": "0", "total_fees_minor": 0,
                   "turnover_minor": 0, "fill_count": 0, "unfilled_order_count": 1}
    if failed:
        nav, positions, fills, orders, decisions, metrics = None, None, None, None, None, None
    run = {"contract_version": "backtest_run_v1", "run_id": run_id, "account_id": "synthetic-account",
           "content_digest": "synthetic:digest:"+run_id, "committed_sequence": 1 if blocked else 9,
           "status": "FAILED" if failed else "COMPLETE", "signal_ref": "synthetic:signal-v1" if old else "synthetic:signal-v2",
           "market_ref": "synthetic:market-old" if old else "synthetic:market-current", "profile_ref": "synthetic:strict" if blocked else "synthetic:profile",
           "core_version": "synthetic_core_v1", "runtime_version": "synthetic_runtime_v1", "implementation_ref": "synthetic:implementation",
           "plan": {"start_session": DAYS[0], "end_session": DAYS[-1], "initial_account": {"cash_minor": 1000000},
                    "profile": {"unknown_status_policy": "block", "lot_size": 100}, "market_replay": replay},
           "nav": nav, "positions": positions, "orders": orders, "fills": fills, "decisions": decisions, "metrics": metrics,
           "limitations": ["Handwritten synthetic UI contract fixture; not Engine acceptance or real profitability evidence"], "final_account": None}
    dd = ["-0.0001", "0", "-0.00398049557", "-0.005075131853", "-0.000199024779", "-0.01184" if old else "0"]
    episodes = [
        {"episode_id": run_id+":episode:closed", "security_id": SECURITY, "status": "CLOSED", "entry_session": DAYS[0], "exit_session": DAYS[3],
         "entry_sequence": 1, "exit_sequence": 5, "left_censored": False, "income_status": "OBSERVED_ONLY", "statistics_eligible": True,
         "exclusion_reasons": [], "buy_cost_minor": 100100, "sell_proceeds_minor": 99900, "fees_minor": 200,
         "dividend_income_minor": 0, "pending_dividend_minor": None, "receivable_minor": 0, "net_pnl_minor": -200,
         "marked_pnl_minor": None, "return_denominator_minor": 100100, "net_return": "-0.001998001998001998",
         "fill_refs": [{"fill_id": f["fill_id"], "sequence": f["sequence"]} for f in fills[:2]], "dividends": []},
        {"episode_id": run_id+":episode:open", "security_id": SECURITY, "status": "OPEN", "entry_session": DAYS[4], "exit_session": None,
         "entry_sequence": 7, "exit_sequence": None, "left_censored": False, "income_status": "COVERAGE_UNKNOWN", "statistics_eligible": False,
         "exclusion_reasons": ["OPEN"], "buy_cost_minor": 90100, "sell_proceeds_minor": 0, "fees_minor": 100,
         "dividend_income_minor": 0, "pending_dividend_minor": None, "receivable_minor": None, "net_pnl_minor": None,
         "marked_pnl_minor": -6800 if old else 7900, "return_denominator_minor": 90100, "net_return": None,
         "fill_refs": [{"fill_id": fills[-1]["fill_id"], "sequence": fills[-1]["sequence"]}], "dividends": []},
    ] if fills else []
    benchmark = {"security_id": "000300.SH", "series_kind": "price_index_excluding_dividends", "unit": "index points",
                 "anchor_session": "2026-03-27", "anchor_close": "4000", "status": "COMPLETE", "total_return": "0.01", "max_drawdown": "-0.00744",
                 "series": [{"session": d, "close": c, "nav_index": idx, "daily_return": None, "drawdown": drawdown, "valid": True,
                             "missing_reason": None, "source_refs": ["synthetic:index"]}
                            for d,c,idx,drawdown in zip(DAYS,["4000","4030","4000","4005","4050","4040"],
                              ["1","1.0075","1","1.00125","1.0125","1.01"],["0","0","-0.00744","-0.0062","0","-0.00246"])]}
    evaluation = {"contract_version": "evaluation_report_v1", "evaluation_ref": "synthetic:evaluation:"+run_id, "content_digest": "synthetic:evaluation-digest:"+run_id,
        "input_run_ref": {k: run[k] for k in ("run_id", "content_digest", "committed_sequence")},
        "signal_ref": run["signal_ref"], "market_ref": run["market_ref"], "profile_ref": run["profile_ref"],
        "spec_ref": "synthetic:spec", "spec": {"description": "synthetic saved P10 display values"}, "status": "PARTIAL",
        "evaluation_version": "synthetic_p10", "implementation_ref": "synthetic:implementation", "benchmark_ref": "synthetic:index",
        "benchmark_input": None, "dividend_scope_ref": None, "dividend_scope": None,
        "series": [{**{k:p[k] for k in ("session","nav_minor","nav_index","committed_sequence")}, "peak_nav_minor": None,
                    "drawdown": "0" if blocked else value} for p,value in zip(nav or [],dd)],
        "monthly_returns": [{"month":"2026-03","status":"PARTIAL","first_session":DAYS[0],"last_session":DAYS[1],"boundary_session":None,
             "return":None,"observed_return":"0" if blocked else "0.0049","reason":"SHORT_FIRST_MONTH","committed_sequence":run["committed_sequence"]},
            {"month":"2026-04","status":"COMPLETE","first_session":DAYS[2],"last_session":DAYS[-1],"boundary_session":DAYS[1],
             "return":"0" if blocked else "-0.01184" if old else "0.002786","observed_return":None,"reason":None,"committed_sequence":run["committed_sequence"]}],
        "pnl_distribution": {"status":"INSUFFICIENT_SAMPLE","metric":"net_pnl_minor","unit":"CNY fen","included_episode_count":0 if blocked else 1,"minimum_episodes":10,"bins":[]},
        "episodes": episodes, "episode_metrics": {"closed_count": 0 if blocked else 1, "eligible_closed_count": 0 if blocked else 1,
             "open_count": 0 if blocked else 1, "left_censored_count":0,"income_pending_count":0,"win_count":0,"loss_count":0 if blocked else 1,
             "tie_count":0,"win_rate":None if blocked else "0","mean_net_pnl_minor":None if blocked else "-200",
             "mean_episode_return":None if blocked else "-0.001998001998001998","return_denominator":"cumulative_buy_cost_including_fees",
             "weighting":"equal_closed_episode","dividend_scope_status":"COVERAGE_UNKNOWN"},
        "benchmark": benchmark, "limitations": ["Synthetic UI values only; dividend scope unknown; benchmark price index excludes dividends"]}
    research = {"question_id":"synthetic:question","title":"动量规则的退场如何影响结果？","hypothesis":"合成说明：只演示问题、版本与运行导航。",
        "version_id":"synthetic:version-v1" if old else "synthetic:version-v2", "version_label":"v1 · 旧输入" if old else "v2 · 固定输入",
        "created_at":"2026-10-04T12:03:00Z" if failed else "2026-10-04T12:02:00Z" if blocked else "2026-10-04T12:00:00Z" if old else "2026-10-04T12:04:00Z",
        "tags":["ETF","合成"],"favorite":not old and not blocked and not failed,"shelved":old,
        "status":"FAILED" if failed else "BLOCKED" if blocked else "NEGATIVE" if old else "COMPLETE",
        "parameters":{"top_k":1},"changes":[{"field":"market_ref","before":"synthetic:market-old","after":"synthetic:market-current"}],"signal_evaluation":None}
    return {"run":run,"research":research,"evaluation":None if failed else evaluation,"data_batch":None if failed else batch}


if __name__ == "__main__":
    fixture = {"fixture_kind":"synthetic_ui_workbench","description":"All handwritten synthetic contract values; not a real or accepted account run",
        "runs":[example("synthetic:run-v2"),example("synthetic:run-v1",old=True),example("synthetic:blocked",blocked=True),example("synthetic:failed",failed=True)]}
    output = Path(__file__).with_name("synthetic_workbench.json")
    output.write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+"\n")
    print(output.name)
