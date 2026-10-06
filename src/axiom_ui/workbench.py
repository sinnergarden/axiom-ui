"""Read-only workbench composition over explicit, validated owner results.

This module formats and binds saved facts. It never executes Research/Core,
calculates account statistics, resolves current, or writes an owner artifact.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .projection import ProjectionError, _digest, _generated, _require
from .report import _watermarks

ASSETS = Path(__file__).with_name("assets")


def _wire(value: Any) -> dict:
    wire = value.to_dict() if hasattr(value, "to_dict") else value
    _require(type(wire) is dict, "owner response must be a JSON object")
    try:
        return json.loads(json.dumps(wire, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ProjectionError("owner response must be finite JSON") from exc


def _decimal(value: Any, field: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    _require(type(value) is str, f"{field} must retain an owner decimal string")
    try:
        valid = Decimal(value).is_finite()
    except InvalidOperation:
        valid = False
    _require(valid, f"nonfinite {field}")


def _rows(value: Any, field: str, *, nullable: bool = False) -> list | None:
    if nullable and value is None:
        return None
    _require(type(value) is list and all(type(row) is dict for row in value),
             f"malformed {field}")
    return value


def _source_context(source: dict) -> dict:
    return source.get("context") or (source.get("batch") or {}).get("context") or {}


def _display_context(context: dict) -> dict:
    """Keep saved query identity and clocks without embedding coverage tables."""
    return {k: deepcopy(v) for k, v in context.items() if k != "coverage"}


def _source_summaries(sources: list[dict]) -> list[dict]:
    return [{"reference": source.get("reference"), "context": _display_context(_source_context(source)),
             "field_units": {k: {n: meta.get(n) for n in ("unit", "dtype")}
                             for k, meta in (source.get("batch", {}).get("field_meta") or {}).items()},
             "display_projection": True,
             "omitted": ["batch.records", "batch.field_meta.by_key", "context.coverage", "coverage_bundle.payload"]}
            for source in sources]


def _stock_native_chart(market: dict, *, price_unit: str = "CNY/share",
                        volume_field: str = "volume_shares", volume_unit: str = "shares",
                        compact_provenance: bool = False) -> dict | None:
    sources = [s for s in market.get("source_evidence") or []
               if _source_context(s).get("domain") == "market_daily"]
    if not sources:
        return None
    _require(len(sources) == 1, "ambiguous saved stock OHLCV source")
    source = sources[0]
    _require(source.get("reference") in (market.get("source_refs") or []), "unbound saved stock OHLCV source")
    # ETF v5's validated replay keeps the original DataBatch reference and
    # context, but does not embed its native price batch. The saved replay rows
    # remain available as a labeled close/volume view until Data display is bound.
    if source.get("batch") is None and volume_field == "volume_units":
        return None
    batch = source.get("batch") or {}
    fields = ("open", "high", "low", "close", volume_field)
    meta = batch.get("field_meta") or {}
    _require(all(meta.get(k, {}).get("unit") == price_unit for k in ("open", "close")) and
             all(k not in meta or meta[k].get("unit") == price_unit for k in ("high", "low")) and
             meta.get(volume_field, {}).get("unit") == volume_unit,
             "unexpected " + ("stock" if volume_field == "volume_shares" else "ETF") + " OHLCV unit")
    for field in (k for k in fields if k in meta):
        _rows(meta[field].get("by_key"), "saved stock OHLCV provenance")
    rows = _rows(batch.get("records"), "saved stock OHLCV")
    if any(k not in meta for k in ("high", "low")):
        return None
    return {"source_ref": source["reference"], "display_projection": True,
            "context": _display_context(batch["context"]), "omitted_context_fields": ["coverage"],
            "records": [{k: deepcopy(row.get(k)) for k in ("security_id", "session", *fields)} for row in rows],
        "field_meta": {k: ({n: deepcopy(meta[k].get(n)) for n in ("unit", "dtype")} | {"by_key": []}
                          if compact_provenance else deepcopy(meta[k])) for k in fields}}


def _stock_evaluation_display(wire: dict) -> dict:
    projected = {k: deepcopy(v) for k, v in wire.items()
                 if k not in ("benchmark_input", "dividend_scope", "base_evaluation", "benchmark_inputs")}
    for name in ("benchmark_input", "dividend_scope"):
        source = wire.get(name)
        if source is None:
            projected[name] = None
            continue
        projected[name] = {k: deepcopy(v) for k, v in source.items()
                           if k not in ("source_evidence", "coverage", "coverage_bundle")}
        projected[name]["source_evidence"] = _source_summaries(source.get("source_evidence") or [])
        projected[name]["display_projection"] = True
        projected[name]["omitted"] = ["coverage", "coverage_bundle.payload", "source_evidence.batch.records",
                                     "source_evidence.batch.field_meta.by_key"]
    if "base_evaluation" in wire:
        # The public Owner loader has checked the complete source closure. The
        # browser needs the unchanged values and refs, not a second native copy.
        projected["base_evaluation"] = _stock_evaluation_display(wire["base_evaluation"])
        projected["benchmark_inputs"] = {
            key: None if value is None else {
                k: deepcopy(v) for k, v in value.items()
                if k not in ("source_evidence", "coverage", "coverage_bundle")}
            for key, value in wire["benchmark_inputs"].items()}
        for value in projected["benchmark_inputs"].values():
            if value is not None:
                value["display_projection"] = True
                value["omitted"] = ["source_evidence", "coverage", "coverage_bundle"]
    return projected


def _comparison_conditions(plan: dict) -> list[dict]:
    """Project frozen comparison facts; identities/strategy inputs are not policies."""
    profile, replay = plan.get("profile") or {}, plan.get("market_replay") or {}
    evidence = replay.get("source_evidence") or []
    contexts = [_source_context(s) for s in evidence]
    queries = [c.get("query") or {} for c in contexts]
    facts = []
    def fact(key: str, label: str, value: Any, provided: bool) -> None:
        facts.append({"key": key, "label": label, "provided": provided, "value": deepcopy(value)})
    for key, label in (("start_session", "开始日期"), ("end_session", "结束日期"),
                       ("initial_account", "初始资金与持仓")):
        fact(key, label, plan.get(key), key in plan and plan[key] is not None)
    for key, label in (("commission_rate", "佣金率"), ("minimum_commission_minor", "最低佣金"),
                       ("slippage_bps", "滑点"), ("tax_rate", "税率"),
                       ("participation_rate", "量约束"), ("execution", "成交价格政策"),
                       ("settlement_sessions", "结算政策"), ("lot_size", "委托单位"),
                       ("unknown_status_policy", "市场状态政策"), ("approximation", "执行近似"),
                       ("decision_time_utc", "决策时间")):
        fact("profile." + key, label, profile.get(key), key in profile and profile[key] is not None)
    # Retain future operational keys without turning profile identity/prose into
    # a condition. The full profile remains available in expanded details.
    known = {f["key"].split(".")[-1] for f in facts if f["key"].startswith("profile.")}
    extra = {k: v for k, v in profile.items() if k not in known | {"contract_version", "limitation", "limitations"}}
    fact("profile.extra", "其他执行配置", extra, True)
    fact("price_basis", "价格口径", replay.get("price_basis"), replay.get("price_basis") is not None)
    for key, label in (("snapshot_id", "数据版本"), ("reader_version", "数据读取版本"),
                       ("contract_id", "数据合同"), ("source_profile_id", "数据来源配置"),
                       ("coverage", "数据覆盖说明")):
        values = [c.get(key) for c in contexts] if key != "coverage" or plan.get("contract_version") not in {"backtest_request_v3", "backtest_request_v4", "backtest_request_v6"} else [s.get("reference") for s in evidence]
        fact(key, label, values, bool(values) and all(v is not None for v in values))
    for key, label in (("symbols", "证券覆盖"), ("sessions", "交易日覆盖"),
                       ("pit_policy", "信息时间口径"), ("adjustment_anchor", "复权锚点")):
        fact("query." + key, label, [q.get(key) for q in queries], bool(queries) and all(key in q for q in queries))
    time_keys = ("cutoff_by_session", "cutoff", "policy_by_session")
    fact("query.knowledge_time", "知识截止与逐日政策",
         [{k: q[k] for k in time_keys if k in q} for q in queries],
         bool(queries) and all(any(q.get(k) is not None for k in time_keys) for q in queries))
    fact("cash_dividends", "保存分红事实", replay.get("cash_dividends"), "cash_dividends" in replay)
    fact("unit_split_policy", "份额拆分应用政策", plan.get("unit_split_policy"),
         "unit_split_policy" in plan and plan["unit_split_policy"] is not None)
    if plan.get("contract_version") == "backtest_request_v5":
        fact("portfolio_policy", "保存的 ETF 组合政策", plan.get("portfolio_policy"),
             plan.get("portfolio_policy") is not None)
    if plan.get("contract_version") in {"backtest_request_v3", "backtest_request_v4", "backtest_request_v6"}:
        for key, label in (("prediction_universe", "原预测范围"), ("execution_universe", "执行资格子集"),
                           ("portfolio_policy", "股票组合政策"), ("stock_action_policy", "股票现金行动政策")):
            fact(key, label, plan.get(key), plan.get(key) is not None)
    return facts


def _saved_fold_summary(plan: dict) -> dict:
    """Select original saved fold identities and dates from an Owner-validated v4 plan."""
    schedule = plan.get("prediction_schedule") or {}
    _require(schedule.get("contract_version") == "stock_prediction_schedule_v1" and
             type(schedule.get("schedule_ref")) is str and schedule["schedule_ref"],
             "missing saved prediction schedule")
    folds = _rows(schedule.get("folds"), "saved prediction folds")
    _require(bool(folds), "missing saved prediction folds")
    selected = []
    for fold in folds:
        frame, spec = fold.get("prediction_frame") or {}, fold.get("fold_spec") or {}
        summary = {"fold_ref": fold.get("fold_ref"), "fold_spec_ref": frame.get("fold_spec_ref"),
                   "signal_run_ref": frame.get("signal_run_ref"), "model_ref": frame.get("model_ref"),
                   "feature_ref": frame.get("feature_ref"), "fit_session": spec.get("fit_session"),
                   "oos_trade_sessions": deepcopy(spec.get("oos_trade_sessions"))}
        _require(all(type(summary[k]) is str and summary[k] for k in
                     ("fold_ref", "fold_spec_ref", "signal_run_ref", "model_ref", "feature_ref", "fit_session")) and
                 type(summary["oos_trade_sessions"]) is list and
                 all(type(day) is str and day for day in summary["oos_trade_sessions"]),
                 "malformed saved prediction fold summary")
        selected.append(summary)
    return {"schedule_ref": schedule["schedule_ref"], "folds": selected}


def _run(run: Any, evidence: str) -> dict:
    wire = _wire(run)
    _require(wire.get("contract_version") in {"backtest_run_v1", "backtest_run_v2", "backtest_run_v3", "backtest_run_v4", "backtest_run_v5", "backtest_run_v6"}, "unsupported run contract")
    stock = wire["contract_version"] in {"backtest_run_v3", "backtest_run_v4", "backtest_run_v6"}
    v4 = wire["contract_version"] == "backtest_run_v4"
    v6 = wire["contract_version"] == "backtest_run_v6"
    etf_v5 = wire["contract_version"] == "backtest_run_v5"
    if stock:
        _require(wire.get("runtime_version") == ("axiom.backtest/6" if v6 else "axiom.backtest/4" if v4 else "axiom.backtest/3") and
                 wire.get("core_version") in ({"axiom.stock_portfolio/3"} if v6 else
                                               {"axiom.stock_portfolio/2"} if v4 else
                                               {"axiom.stock_portfolio/1", "axiom.stock_portfolio/2"}) and
                 (wire.get("quantity_unit"), wire.get("price_unit")) == ("shares", "CNY/share"),
                 "unsupported stock version or units")
    if etf_v5:
        policy = (wire.get("plan") or {}).get("portfolio_policy") or {}
        hold = policy.get("contract_version") == "etf_buy_and_hold_policy_v1"
        _require(wire.get("runtime_version") == "axiom.backtest/5" and
                 wire.get("core_version") == ("axiom.etf_buy_and_hold/1" if hold else "axiom.rotation/1") and
                 policy.get("contract_version") in {"etf_buy_and_hold_policy_v1", "etf_rotation_policy_v1"} and
                 (wire.get("quantity_unit"), wire.get("price_unit")) == ("fund units", "CNY/fund unit") and
                 (wire.get("signal_ref") is None if hold else type(wire.get("signal_ref")) is str) and
                 type(wire.get("portfolio_policy_ref")) is str and wire["portfolio_policy_ref"],
                 "unsupported ETF v5 policy, version or units")
    _require(all(type(wire.get(k)) is str and wire[k]
                 for k in ("run_id", "account_id", "status")), "missing run identity")
    _watermarks(wire)
    for point in wire.get("nav") or []:
        _decimal(point.get("nav_index"), "nav_index")
        _require(type(point.get("nav_minor")) is int, "NAV must be integer CNY cents")
    for field in ("positions", "decisions", "orders", "fills"):
        _rows(wire.get(field), field, nullable=True)
    for fill in wire.get("fills") or []:
        _decimal(fill.get("price"), "fill price")
        _require(type(fill.get("quantity")) is int, "fill quantity must be integer units")
        _require(all(type(fill.get(k)) is int for k in ("gross_minor", "fee_minor", "cash_delta_minor")),
                 "fill amounts must be integer CNY cents")
        if stock:
            _require(fill.get("quantity_unit") == "shares" and all(type(fill.get(k)) is int for k in
                     ("commission_minor", "stamp_tax_minor", "transfer_fee_minor")), "missing stock fill units or fee components")
    metrics = wire.get("metrics")
    _require(metrics is None or type(metrics) is dict, "malformed owner metrics")
    for field in ("total_return", "max_drawdown"):
        if metrics is not None and field in metrics:
            _decimal(metrics[field], field, nullable=True)
    profile = (wire.get("plan") or {}).get("profile") or {}
    _require(type(profile) is dict, "malformed profile")
    if v6:
        _require(profile.get("contract_version") == "stock_daily_open_profile_v2" and
                 type(wire.get("stock_execution_rules_ref")) is str and
                 wire["stock_execution_rules_ref"] == (wire.get("plan") or {}).get("stock_execution_rules_ref") ==
                 profile.get("stock_execution_rules_ref") and
                 (wire.get("plan") or {}).get("market_replay", {}).get("contract_version") == "market_replay_v4",
                 "unsupported stock v6 rules/profile/replay")
        # Owner's public loader has already checked the complete rule and fee
        # documents. The browser only needs their saved identities and scalars.
        profile = {k: deepcopy(v) for k, v in profile.items()
                   if k not in {"stock_execution_rules", "stock_fee_schedule"}}
    market = (wire.get("plan") or {}).get("market_replay") or {}
    _require(type(market) is dict, "malformed frozen market replay")
    approximate = profile.get("unknown_status_policy") in {"etf_daily_observed", "stock_daily_observed"} or (
        v6 and profile.get("approximation") == "retrospective_daily_volume_proxy")
    blocked = any(row.get("reason") == "UNKNOWN_MARKET_STATUS" for row in wire.get("orders") or [])
    # Retain saved market values only for an explicitly named close/volume view.
    # Missing high/low is never converted into a synthetic candle.
    market_rows = deepcopy(market.get("rows") or [])
    _rows(market_rows, "saved market rows")
    view = {
        "view_id": wire["run_id"],
        "run": {k: deepcopy(wire.get(k)) for k in (
            "contract_version", "run_id", "account_id", "status", "content_digest",
            "committed_sequence", "signal_ref", "market_ref", "profile_ref",
            "core_version", "runtime_version", "implementation_ref", "metrics", "nav",
            "positions", "decisions", "orders", "fills", "limitations", "final_account", "initial_nav_minor",
            "quantity_unit", "price_unit")},
        "configuration": {"start_session": (wire.get("plan") or {}).get("start_session"),
                          "end_session": (wire.get("plan") or {}).get("end_session"),
                          "initial_account": deepcopy((wire.get("plan") or {}).get("initial_account")),
                          "profile": deepcopy(profile), "price_basis": market.get("price_basis")},
        "comparison_conditions": _comparison_conditions({**(wire.get("plan") or {}), "profile": profile} if v6 else wire.get("plan") or {}),
        "market": {"rows": market_rows, "price_basis": market.get("price_basis"),
                   "source_refs": deepcopy(market.get("source_refs")), "data_batch": None},
        "evidence_kind": evidence, "approximate": approximate, "blocked": blocked,
        "research": None, "evaluation": None,
    }
    if etf_v5:
        view["run"]["portfolio_policy_ref"] = wire["portfolio_policy_ref"]
        view["configuration"]["portfolio_policy"] = deepcopy(wire["plan"]["portfolio_policy"])
    if wire["contract_version"] in {"backtest_run_v2", "backtest_run_v5"}:
        applications = _rows(wire.get("unit_split_applications"), "saved unit split applications")
        events = _rows(market.get("unit_splits"), "saved unit split events")
        _require(all(type(item.get("event")) is dict for item in events), "malformed saved unit event")
        by_event = {item["event"].get("event_id"): item["event"] for item in events}
        _require(len(by_event) == len(events) and all(type(k) is str and k for k in by_event),
                 "missing/duplicate saved unit event identity")
        for application in applications:
            event = by_event.get(application.get("event_id"))
            _require(event is not None and application.get("security_id") == event.get("security_id") and
                     application.get("session") == event.get("effective_date"),
                     "CONTEXT_MISMATCH: saved unit application/event")
        for position in wire.get("positions") or []:
            _require("mark_basis_event_id" in position and
                     (position["mark_basis_event_id"] is None or position["mark_basis_event_id"] in by_event),
                     "CONTEXT_MISMATCH: saved mark basis event")
        for order in wire.get("orders") or []:
            ids = order.get("announced_suspension_event_ids")
            _require(type(ids) is list and all(type(i) is str and i in by_event for i in ids),
                     "CONTEXT_MISMATCH: saved suspension events")
        view["run"]["unit_split_applications"] = deepcopy(applications)
        view["market"]["unit_splits"] = deepcopy(events)
        event_refs = {ref for item in events for ref in item.get("source_refs") or []}
        view["market"]["unit_split_source_evidence"] = deepcopy([
            source for source in market.get("source_evidence") or []
            if source.get("reference") in event_refs and
            _source_context(source).get("domain") == "fund_share_conversions"])
        view["configuration"]["unit_split_policy"] = deepcopy((wire.get("plan") or {}).get("unit_split_policy"))
    if stock:
        plan = wire.get("plan") or {}
        _require(plan.get("contract_version") == ("backtest_request_v6" if v6 else "backtest_request_v4" if v4 else "backtest_request_v3") and
                 profile.get("unknown_status_policy") in {"stock_daily_observed", "block"}, "unsupported stock request/profile")
        view["run"].update({k: deepcopy(wire.get(k)) for k in
                            ("quantity_unit", "price_unit", "admission_ref", "supported_universe_ref", "stopped")})
        if v6:
            lifecycle = wire.get("lifecycle_admission")
            _require(type(lifecycle) is dict and set(lifecycle) ==
                     {"pre_listing_null", "listed_nonmember_gap", "member_gap", "held_gap"} and
                     all(type(value) is int and value >= 0 for value in lifecycle.values()),
                     "malformed saved lifecycle admission")
            view["run"].update(stock_execution_rules_ref=wire["stock_execution_rules_ref"],
                               lifecycle_admission=deepcopy(lifecycle))
        admission = plan.get("admission_evidence") or {}
        view["stock_context"] = {k: deepcopy(plan.get(k)) for k in
                                 ("prediction_universe", "execution_universe", "portfolio_policy", "stock_action_policy")}
        view["stock_context"].update(model_snapshot=(admission.get("model") or {}).get("snapshot"),
                                     execution_snapshot=(admission.get("execution") or {}).get("snapshot"),
                                     admission_status=admission.get("status"))
        if v4 or v6:
            summary = _saved_fold_summary(plan)
            _require(wire.get("signal_ref") == summary["schedule_ref"], "CONTEXT_MISMATCH: run/prediction schedule")
            view["stock_context"].update(summary)
        else:
            view["stock_context"]["signal_inputs"] = {k: deepcopy((plan.get("signal_frame") or {}).get(k)) for k in
                                                       ("feature_ref", "model_ref", "score_semantics", "score_unit")}
        view["market"]["source_evidence"] = _source_summaries(market.get("source_evidence") or [])
        view["market"]["native_chart"] = _stock_native_chart(market, compact_provenance=v6)
        view["market"]["cash_dividends"] = deepcopy(market.get("cash_dividends"))
        view["market"]["action_diagnostics"] = deepcopy(market.get("action_diagnostics"))
        view["market"]["action_blocks"] = deepcopy(market.get("action_blocks"))
    if etf_v5:
        view["market"]["source_evidence"] = _source_summaries(market.get("source_evidence") or [])
        view["market"]["native_chart"] = _stock_native_chart(market, price_unit="CNY/fund unit",
            volume_field="volume_units", volume_unit="fund units")
    return view


def _period_metrics(wire: dict, run: Mapping[str, Any]) -> None:
    """Validate saved v2 display facts and endpoints; never annualize wealth."""
    period = wire.get("period_metrics")
    _require(type(period) is dict and all(type(period.get(k)) is dict for k in
             ("window", "account", "benchmark")), "missing saved period metrics")
    window = period["window"]
    _require(all(k in window for k in ("anchor_session", "end_session", "elapsed_calendar_days",
                 "day_count", "year_segments", "year_fraction")) and
             window["day_count"] == "actual_actual_calendar_year_split" and
             type(window["elapsed_calendar_days"]) is int and window["elapsed_calendar_days"] > 0,
             "malformed saved period window")
    _decimal(window["year_fraction"], "saved year fraction")
    _require(all(type(window[k]) is str and window[k] for k in ("anchor_session", "end_session")),
             "malformed saved period dates")
    for row in _rows(window["year_segments"], "saved year segments"):
        _require(all(type(row.get(k)) is int for k in ("year", "days", "year_days")),
                 "malformed saved year segment")
    nav = run.get("nav") or []
    benchmark = wire["benchmark"]
    _require(nav and window["end_session"] == nav[-1]["session"] and
             window["anchor_session"] == benchmark.get("anchor_session"),
             "CONTEXT_MISMATCH: saved period window")
    for name in ("account", "benchmark"):
        leg = period[name]
        _require(all(k in leg for k in ("cagr_status", "cagr", "cagr_reason", "total_return", "max_drawdown")) and
                 leg["cagr_status"] in {"AVAILABLE", "INSUFFICIENT_SPAN", "MISSING_BOUNDARY"},
                 "malformed saved CAGR status")
        if leg["cagr_status"] == "AVAILABLE":
            _decimal(leg["cagr"], "saved CAGR")
            _require(leg["cagr_reason"] is None, "available CAGR must not have a missing reason")
        else:
            _require(leg["cagr"] is None and type(leg["cagr_reason"]) is str and bool(leg["cagr_reason"]),
                     "unavailable CAGR must retain null and reason")
        for key in ("total_return", "max_drawdown"):
            _decimal(leg[key], "saved period " + key, nullable=True)
    account = period["account"]
    _require(type(account.get("initial_nav_minor")) is int and type(account.get("final_nav_minor")) is int and
             account["final_nav_minor"] == nav[-1]["nav_minor"] and
             (run.get("initial_nav_minor") is None or account["initial_nav_minor"] == run["initial_nav_minor"]),
             "CONTEXT_MISMATCH: saved period account endpoints")
    leg, series = period["benchmark"], benchmark.get("series") or []
    for key in ("anchor_close", "end_close"):
        _require(key in leg, "missing saved period benchmark endpoint")
        _decimal(leg[key], "saved period " + key, nullable=True)
    _require(leg.get("anchor_close") == benchmark.get("anchor_close") and
             leg.get("end_close") == (series[-1].get("close") if series else None),
             "CONTEXT_MISMATCH: saved period benchmark endpoints")


def _evaluation(value: Any, run: Mapping[str, Any]) -> dict:
    wire = _wire(value)
    _require(wire.get("contract_version") in {"evaluation_report_v1", "evaluation_report_v2", "evaluation_report_v3"}, "unsupported evaluation contract")
    binding = wire.get("input_run_ref")
    _require(type(binding) is dict and all(binding.get(k) == run.get(k)
             for k in ("run_id", "content_digest", "committed_sequence")),
             "CONTEXT_MISMATCH: evaluation/run identity or watermark")
    _require(all(wire.get(k) == run.get(k) for k in ("signal_ref", "market_ref", "profile_ref")),
             "CONTEXT_MISMATCH: evaluation input refs")
    _require(wire.get("status") in {"COMPLETE", "PARTIAL"}, "unsupported evaluation status")
    nav = {row["session"]: row for row in run.get("nav") or []}
    series = _rows(wire.get("series"), "evaluation series")
    seen = set()
    for point in series:
        day = point.get("session")
        _require(day not in seen and day in nav and all(point.get(k) == nav[day].get(k)
                 for k in ("nav_minor", "nav_index", "committed_sequence")),
                 "CONTEXT_MISMATCH: evaluation series/NAV")
        seen.add(day)
        _decimal(point.get("drawdown"), "drawdown", nullable=True)
    _require(seen == set(nav), "CONTEXT_MISMATCH: evaluation session coverage")
    months = set()
    for month in _rows(wire.get("monthly_returns"), "monthly_returns"):
        _require(month.get("month") not in months, "duplicate monthly evaluation")
        months.add(month.get("month"))
        _require(month.get("status") in {"COMPLETE", "PARTIAL", "MISSING"}, "unknown month status")
        _decimal(month.get("return"), "month return", nullable=True)
        _decimal(month.get("observed_return"), "observed month return", nullable=True)
    fills = {f["fill_id"]: f for f in run.get("fills") or []}
    episodes = set()
    for episode in _rows(wire.get("episodes"), "episodes"):
        _require(episode.get("episode_id") not in episodes, "duplicate episode")
        episodes.add(episode.get("episode_id"))
        _require(episode.get("status") in {"CLOSED", "OPEN"}, "unknown episode status")
        _require(all(type(episode.get(k)) is bool for k in ("statistics_eligible", "left_censored")),
                 "episode qualification must retain owner booleans")
        for ref in _rows(episode.get("fill_refs"), "episode fill_refs"):
            fill = fills.get(ref.get("fill_id"))
            _require(fill is not None and fill.get("sequence") == ref.get("sequence") and
                     fill.get("security_id") == episode.get("security_id"),
                     "CONTEXT_MISMATCH: episode/fill")
        for field in ("net_pnl_minor", "marked_pnl_minor"):
            _require(episode.get(field) is None or type(episode.get(field)) is int,
                     "episode P&L must retain integer cents")
        _decimal(episode.get("net_return"), "episode return", nullable=True)
    metrics = wire.get("episode_metrics")
    _require(type(metrics) is dict, "missing episode metrics")
    for field in ("win_rate", "mean_net_pnl_minor", "mean_episode_return"):
        _decimal(metrics.get(field), field, nullable=True)
    _require(type(wire.get("benchmark")) is dict, "missing benchmark availability report")
    distribution = wire.get("pnl_distribution")
    _require(type(distribution) is dict and distribution.get("status") in
             {"AVAILABLE", "INSUFFICIENT_SAMPLE"}, "missing owner P&L distribution status")
    _require(distribution.get("metric") == "net_pnl_minor" and distribution.get("unit") == "CNY fen",
             "unexpected distribution metric/unit")
    for bucket in _rows(distribution.get("bins"), "distribution bins"):
        _require(type(bucket.get("count")) is int and bucket["count"] >= 0 and
                 all(bucket.get(k) is None or type(bucket[k]) is int for k in ("lower_minor", "upper_minor")),
                 "invalid saved distribution bin")
    _require(distribution["status"] != "INSUFFICIENT_SAMPLE" or not distribution["bins"],
             "insufficient sample must not claim owner distribution bins")
    if wire["contract_version"] in {"evaluation_report_v2", "evaluation_report_v3"}:
        version = "axiom.evaluation/3" if wire["contract_version"] == "evaluation_report_v3" else "axiom.evaluation/2"
        _require(wire.get("evaluation_version") == version, "unsupported saved evaluation version")
        _period_metrics(wire, run)
        if wire["contract_version"] == "evaluation_report_v3":
            _analysis_display_binding(wire, run)
    else:
        _require("period_metrics" not in wire, "v1 must not acquire period metrics")
    return _stock_evaluation_display(wire) if (run.get("contract_version") in {"backtest_run_v3", "backtest_run_v4"} or
                                             wire["contract_version"] == "evaluation_report_v3") else wire


def _analysis_display_binding(wire: dict, run: Mapping[str, Any]) -> None:
    """Check saved display links. No risk, return, binning or price calculation."""
    base = wire.get("base_evaluation")
    _require(type(base) is dict and base.get("contract_version") == "evaluation_report_v2" and
             base.get("evaluation_ref") == wire.get("base_evaluation_ref") and
             base.get("content_digest") == wire.get("base_evaluation_content_digest") and
             base.get("input_run_ref") == wire.get("input_run_ref"),
             "CONTEXT_MISMATCH: saved analysis/base evaluation")
    for key in ("series", "monthly_returns", "episodes", "episode_metrics", "pnl_distribution", "period_metrics"):
        _require(base.get(key) == wire.get(key), "CONTEXT_MISMATCH: saved analysis changed base values")
    nav = {p["session"]: p for p in run["nav"]}
    series = _rows(wire.get("analysis_series"), "saved analysis series")
    _require([p.get("session") for p in series] == list(nav), "CONTEXT_MISMATCH: saved analysis dates")
    for point in series:
        _require(point.get("committed_sequence") == nav[point["session"]]["committed_sequence"],
                 "CONTEXT_MISMATCH: saved analysis watermark")
        for key in ("account_cumulative_return", "rolling_return_20", "rolling_volatility_20"):
            _decimal(point.get(key), "saved " + key, nullable=key != "account_cumulative_return")
    dd = wire.get("drawdown_interval")
    _require(type(dd) is dict and dd.get("status") in {"AVAILABLE", "NO_DRAWDOWN"} and
             dd.get("drawdown") == wire["period_metrics"]["account"]["max_drawdown"],
             "CONTEXT_MISMATCH: saved drawdown range")
    if dd["status"] == "AVAILABLE":
        _require(dd.get("trough_session") in nav and
                 (dd.get("peak_session") in nav or (dd.get("peak_is_initial_anchor") is True and
                  dd.get("peak_session") == wire["period_metrics"]["window"]["anchor_session"])),
                 "CONTEXT_MISMATCH: saved drawdown dates")
    distribution = wire.get("return_distribution")
    _require(type(distribution) is dict and distribution.get("metric") == "net_return" and
             distribution.get("unit") == "fraction" and distribution.get("status") in
             {"AVAILABLE", "INSUFFICIENT_SAMPLE"}, "unsupported saved return distribution")
    for bucket in _rows(distribution.get("bins"), "saved return bins"):
        _require(type(bucket.get("count")) is int and bucket["count"] >= 0, "invalid saved return count")
        for key in ("lower", "upper"):
            _decimal(bucket.get(key), "saved bin " + key, nullable=True)
    _require(distribution["status"] != "INSUFFICIENT_SAMPLE" or not distribution["bins"],
             "insufficient sample must not claim return bins")
    for metric in ("sharpe", "calmar"):
        value = (wire.get("risk_metrics") or {}).get(metric)
        _require(type(value) is dict and type(value.get("status")) is str, "missing saved risk status")
        _decimal(value.get("value"), "saved " + metric, nullable=True)
    episodes = {e["episode_id"]: e for e in wire["episodes"]}
    for point in _rows(wire.get("episode_points"), "saved episode points"):
        episode = episodes.get(point.get("episode_id"))
        _require(episode and episode["statistics_eligible"] and point.get("net_return") == episode.get("net_return"),
                 "CONTEXT_MISMATCH: saved episode point")
    comparisons = wire.get("benchmark_comparisons")
    _require(type(comparisons) is dict and set(comparisons) == {"CSI300", "SSE_COMPOSITE", "NASDAQ100"},
             "missing saved benchmark choices")
    for key, comparison in comparisons.items():
        _require(type(comparison) is dict and comparison.get("input_ref") == wire.get("benchmark_refs", {}).get(key),
                 "CONTEXT_MISMATCH: saved benchmark identity")
        for point in _rows(comparison.get("series"), "saved benchmark comparison"):
            _require(point.get("account_session") in nav and
                     point.get("native_session") in {None, point.get("account_session")},
                     "CONTEXT_MISMATCH: saved benchmark dates")
            if comparison.get("currency") != "CNY":
                _require(point.get("account_relative_wealth") is None, "FX evidence required for account-relative wealth")


def _paths(values: Sequence[str | Path], field: str) -> None:
    _require(isinstance(values, Sequence) and not isinstance(values, (str, bytes)) and
             all(isinstance(p, (str, Path)) for p in values),
             f"{field} requires explicit paths via owner Reader")


def _catalog(reader: Any, views: list[dict]) -> list[dict]:
    """Bind a Research-owned index to explicit loaded results; never discover files."""
    projection = _wire(reader.index())
    _require(projection.get("contract_version") == "experiment_projection_v1", "unsupported Research projection")
    loaded, evaluations = {}, {}
    for view in views:
        loaded.setdefault(view["run"]["run_id"], view)
        if view["evaluation"] is not None:
            evaluations[view["evaluation"]["evaluation_ref"]] = view
    used, selected = set(), []
    for item in _rows(projection.get("questions"), "Research questions"):
        question, organization = item.get("question"), item.get("organization")
        _require(type(question) is dict and type(organization) is dict, "malformed Research question")
        runs = _rows(item.get("runs"), "Research runs")
        versions = _rows(item.get("versions"), "Research versions")
        versions_by_ref = {v["version_ref"]: v for v in versions}
        differences_by_ref = {v["version_ref"]: _wire(reader.compare_versions(v["parent_version_ref"], v["version_ref"]))
                              if v.get("parent_version_ref") else None for v in versions}
        historical_versions = {h.get("version_ref") for r in runs for h in r.get("registration_history") or []}
        for version in versions or [{"question_id": question.get("question_id"), "version_ref": None,
                                     "created_at": question.get("created_at")}]:
            _require(version.get("question_id") == question.get("question_id"), "CONTEXT_MISMATCH: Research version/question")
            records = [r for r in runs if r.get("version_ref") == version.get("version_ref")]
            if not records and version.get("version_ref") in historical_versions:
                # One saved account remains one navigation group. Older versions
                # are accessible through its immutable registration history.
                continue
            parent = version.get("parent_version_ref")
            difference = differences_by_ref.get(version.get("version_ref"))
            for record in records or [None]:
                if record:
                    _require(record.get("question_id") == question.get("question_id") and
                             record.get("status") in {"COMPLETE", "FAILED", "BLOCKED"}, "malformed Research run")
                backtest = record.get("backtest_ref") if record else None
                engine = loaded.get(backtest.get("run_id")) if type(backtest) is dict else None
                if engine:
                    _require(all(backtest.get(k) == engine["run"].get(k) for k in
                             ("run_id", "content_digest", "signal_ref", "committed_sequence")),
                             "CONTEXT_MISMATCH: Research/Engine run reference")
                    evaluation = record.get("evaluation_ref")
                    chosen = evaluations.get(evaluation.get("evaluation_ref")) if type(evaluation) is dict else None
                    if chosen:
                        saved = chosen["evaluation"]
                        _require(all(chosen["run"].get(k) == engine["run"].get(k) for k in
                                     ("run_id", "content_digest", "committed_sequence")) and
                                 evaluation.get("evaluation_ref") == saved.get("evaluation_ref") and
                                 evaluation.get("evaluation_content_digest") == saved.get("content_digest") and
                                 evaluation.get("input_run_ref") == saved.get("input_run_ref"),
                                 "CONTEXT_MISMATCH: Research/Engine evaluation reference")
                    view = deepcopy(chosen or engine)
                    if chosen or engine["evaluation"] is None:
                        used.add((chosen or engine)["view_id"])
                    if chosen is None:
                        # A separately loaded newer evaluation must not appear
                        # under an immutable record that references an older one.
                        view["evaluation"] = None
                else:
                    view = {"run": {"run_id": None, "status": None, "nav": None, "positions": None,
                                     "fills": None, "orders": None, "decisions": None, "metrics": None},
                            "configuration": {}, "market": {"rows": [], "data_batch": None},
                            "evaluation": None, "approximate": False, "blocked": False,
                            "evidence_kind": "research_record_only"}
                saved_run_ref = record.get("saved_run_ref") if record else None
                view["view_id"] = question["question_id"] + ":" + saved_run_ref if saved_run_ref else record["run_record_ref"] if record else (version["version_ref"] or question["question_id"]) + ":unrun"
                history = []
                for registration in _rows(record.get("registration_history") or [], "Research registration history") if record else []:
                    _require(registration.get("question_id") == question.get("question_id") and
                             registration.get("version_ref") in versions_by_ref,
                             "CONTEXT_MISMATCH: registration history/question or version")
                    historical_backtest = registration.get("backtest_ref")
                    if engine and historical_backtest:
                        _require(all(historical_backtest.get(k) == engine["run"].get(k) for k in
                                     ("run_id", "content_digest", "signal_ref", "committed_sequence")),
                                 "CONTEXT_MISMATCH: registration history/backtest")
                    ref = registration.get("evaluation_ref")
                    historical = evaluations.get(ref.get("evaluation_ref")) if type(ref) is dict else None
                    if historical:
                        saved = historical["evaluation"]
                        _require(engine is not None and
                                 all(historical["run"].get(k) == engine["run"].get(k) for k in
                                     ("run_id", "content_digest", "committed_sequence")) and
                                 ref.get("evaluation_content_digest") == saved.get("content_digest") and
                                 ref.get("input_run_ref") == saved.get("input_run_ref"),
                                 "CONTEXT_MISMATCH: registration history/evaluation")
                        used.add(historical["view_id"])
                    history.append({"record": deepcopy(registration),
                                    "evaluation": deepcopy(historical["evaluation"]) if historical else None})
                view["registration_history"] = history
                view["research_versions"] = deepcopy(versions_by_ref)
                view["research_version_comparisons"] = deepcopy(differences_by_ref)
                batch_refs = [r for r in (record.get("output_refs") or []) if r.get("artifact_type") == "DataBatch"] if record else []
                batch = view["market"]["data_batch"]
                if batch_refs and batch is not None:
                    matching = [r for r in batch_refs if r.get("artifact_id") == _digest(batch)]
                    _require(bool(matching), "CONTEXT_MISMATCH: Research/DataBatch identity")
                    file_digest = view["market"].get("data_batch_file_digest")
                    if file_digest is not None:
                        _require(any(r.get("content_digest") == file_digest for r in matching),
                                 "CONTEXT_MISMATCH: Research/DataBatch file digest")
                run_organization = record.get("organization") or {} if record else {}
                _require(type(run_organization) is dict, "malformed Research run organization")
                view["research"] = {"question_id": question.get("question_id"), "question_ref": question.get("question_ref"),
                    "title": question.get("title"), "hypothesis": question.get("hypothesis"), "description": question.get("description"),
                    "version_id": version.get("version_ref"), "version_label": version.get("label"),
                    "version_explanation": version.get("explanation"), "parameters": version.get("parameters"),
                    "input_refs": version.get("input_refs"), "changes": version.get("explicit_changes"),
                    "version_comparison": difference, "comparison_left_ref": parent,
                    "created_at": record.get("created_at") if record else version.get("created_at"),
                    "status": record.get("status") if record else None, "not_run": record is None,
                    "no_version": version.get("version_ref") is None, "last_activity_at": item.get("last_activity_at"),
                    "reason": record.get("reason") if record else None, "outcome": record.get("outcome") if record else None,
                    "run_record_ref": record.get("run_record_ref") if record else None,
                    "saved_run_ref": saved_run_ref, "run_kind": record.get("run_kind") if record else None,
                    "saved_backtest_count": item.get("saved_backtest_count"), "registration_count": item.get("registration_count"),
                    "output_refs": record.get("output_refs") if record else None,
                    "backtest_ref": backtest, "evaluation_ref": record.get("evaluation_ref") if record else None,
                    "tags": organization.get("tags"), "groups": organization.get("groups"),
                    "favorite": run_organization.get("favorite"), "shelved": run_organization.get("shelved"),
                    "run_organization_revision": run_organization.get("revision"),
                    "question_favorite": organization.get("favorite"), "question_shelved": organization.get("shelved"),
                    "organization_revision": organization.get("revision"),
                    "store_revision": projection.get("store_revision"), "index_content_digest": projection.get("content_digest")}
                selected.append(view)
    selected.extend(v for v in views if v["view_id"] not in used)
    _require(len({v["view_id"] for v in selected}) == len(selected), "duplicate Research selection identity")
    return selected


def _attach_batch(view: dict, batch: Any, source_run: dict) -> None:
    wire = batch.to_json() if hasattr(batch, "to_json") else batch
    _require(type(wire) is dict and set(wire) == {"records", "field_meta", "context"},
             "unsupported DataBatch")
    wire = _wire(wire)
    context = wire["context"]
    _require(type(context) is dict and context.get("contract_version") == "data_batch_v1" and
             context.get("snapshot_id") not in {None, "", "current", "latest"}, "unpinned DataBatch")
    market = (source_run.get("plan") or {}).get("market_replay") or {}
    query = context.get("query")
    _require(type(query) is dict and query.get("price_basis") == market.get("price_basis") == "unadjusted",
             "CONTEXT_MISMATCH: price basis; adjusted fills require owner display mapping")
    fields = query.get("fields") or []
    _require(all(k in fields for k in ("open", "high", "low", "close", "volume_units")),
             "OHLCV Data Query fields required")
    rows = _rows(wire.get("records"), "Data records")
    matches = []
    for source in market.get("source_evidence") or []:
        frozen = source.get("context") if type(source) is dict else None
        if type(frozen) is not dict or frozen.get("domain") != "market_daily":
            continue
        frozen_query = frozen.get("query") or {}
        if {k: v for k, v in query.items() if k != "fields"} != {
                k: v for k, v in frozen_query.items() if k != "fields"}:
            continue
        if not all(context.get(k) == frozen.get(k) for k in
                   ("snapshot_id", "domain", "reader_version", "derivation", "contract_id", "source_profile_id", "coverage")):
            continue
        if not set(frozen_query.get("fields") or []).issubset(fields):
            continue
        base_fields = frozen_query["fields"]
        # Prove the original run's common facts AND per-key provenance exactly.
        # Only the requested high/low extension differs; no latest resolution.
        base = {"context": frozen,
                "records": [{k: r[k] for k in ("security_id", "session", *base_fields)} for r in rows],
                "field_meta": {k: wire["field_meta"].get(k) for k in base_fields}}
        if _digest(base) == source.get("reference"):
            matches.append(source)
    _require(len(matches) == 1, "CONTEXT_MISMATCH: frozen Data Query/reader/provenance")
    _require(all(wire["field_meta"].get(k, {}).get("unit") == "CNY/fund unit"
                 for k in ("open", "high", "low", "close")) and
             wire["field_meta"].get("volume_units", {}).get("unit") == "fund units",
             "unexpected OHLCV unit")
    original = {(r["security_id"], r["session"]): r for r in market.get("rows") or []}
    seen = set()
    for row in rows:
        key = row.get("security_id"), row.get("session")
        _require(key not in seen, "duplicate Data key")
        seen.add(key)
        _require(key in original, "CONTEXT_MISMATCH: Data key outside saved run market")
        for field in ("open", "close"):
            if row.get(field) is not None and original[key].get(field) is not None:
                _require(Decimal(str(row[field])) == Decimal(str(original[key][field])),
                         "CONTEXT_MISMATCH: Data price/saved market")
    # Existing P12 validates per-key metadata and keeps query/source refs intact.
    from .projection import project_data_layer
    securities = {r["security_id"] for r in rows}
    for security in securities:
        for field in ("open", "high", "low", "close", "volume_units"):
            project_data_layer(wire, field=field, security_id=security,
                               role="volume" if field == "volume_units" else "candles",
                               generated_at="2026-10-04T00:00:00Z")
    view["market"]["data_batch"] = wire


def _attach_stock_ml(views: list[dict], paths: Sequence[str | Path]) -> None:
    """Bind explicitly loaded Research stages to their immutable registrations."""
    if not paths:
        return
    from axiom_research import load_stock_ml_experiment, load_stock_model
    seen = set()
    for path in paths:
        saved = load_stock_ml_experiment(path)
        experiment, model, evidence = _wire(saved), _wire(load_stock_model(path)), _wire(saved.evidence())
        _require(experiment.get("contract_version") == "stock_ml_experiment_v1" and
                 model.get("contract_version") == "stock_model_release_v1" and
                 evidence.get("contract_version") == "stock_signal_evidence_v1", "unsupported stock ML stage contract")
        ref = experiment.get("experiment_ref")
        _require(type(ref) is str and ref and ref not in seen, "missing/duplicate stock ML experiment identity")
        seen.add(ref)
        _require(model.get("model_ref") == experiment.get("model_ref") and
                 evidence.get("evidence_ref") == experiment.get("evidence_ref") and
                 evidence.get("signal_ref") == experiment.get("signal_run_ref"), "CONTEXT_MISMATCH: stock ML stages")
        _rows(evidence.get("series"), "saved stock signal evidence")
        bindings = {"StockMLExperiment":"experiment_ref", "FeatureBuild":"feature_ref",
                    "LabelBuild":"label_ref", "TrainingDataset":"dataset_ref",
                    "ModelRelease":"model_ref", "SignalRun":"signal_run_ref", "SignalEvidence":"evidence_ref"}
        matched = False
        for view in views:
            refs = (view.get("research") or {}).get("output_refs") or []
            if not any(r.get("artifact_type") == "StockMLExperiment" and r.get("artifact_id") == ref for r in refs):
                continue
            _require(all(any(r.get("artifact_type") == kind and r.get("artifact_id") == experiment.get(key)
                             for r in refs) for kind, key in bindings.items()), "CONTEXT_MISMATCH: stock ML registration")
            if view["run"].get("run_id"):
                inputs = (view.get("stock_context") or {}).get("signal_inputs") or {}
                _require(view["run"].get("contract_version") == "backtest_run_v3" and
                         view["run"].get("signal_ref") == experiment.get("signal_run_ref") and
                         all(inputs.get(k) == experiment.get(k) for k in ("feature_ref", "model_ref")),
                         "CONTEXT_MISMATCH: stock account/model inputs")
            _require("stock_ml" not in view, "duplicate stock ML registration attachment")
            view["stock_ml"] = {"experiment": deepcopy(experiment), "model": deepcopy(model),
                                "signal_evidence": deepcopy(evidence)}
            matched = True
        _require(matched, "CONTEXT_MISMATCH: stock ML without registered experiment")


def _attach_stock_stage_reports(views: list[dict], paths: Sequence[str | Path]) -> None:
    """Attach optional saved reports only to their six exact registered inputs."""
    if not paths:
        return
    from axiom_research import load_stock_stage_report
    bindings = {"StockMLExperiment":"experiment_ref", "FeatureBuild":"feature_ref",
                "TrainingDataset":"dataset_ref", "ModelRelease":"model_ref",
                "SignalRun":"signal_run_ref", "SignalEvidence":"evidence_ref"}
    for path in paths:
        report = _wire(load_stock_stage_report(path))
        _require((report.get("contract_version"), report.get("report_version")) ==
                 ("stock_stage_report_v1", "axiom.stock_stage_report/1"), "unsupported stock stage report contract")
        refs = report.get("input_refs")
        _require(type(refs) is dict and set(refs) == set(bindings.values()) and
                 all(type(ref) is str and ref for ref in refs.values()), "malformed stock stage report input refs")
        _require(type(report.get("training")) is dict and type(report.get("signal_summary")) is dict,
                 "malformed stock stage report projection")
        _rows(report.get("measurements"), "saved stock stage measurements")
        matched = False
        for view in views:
            stock = view.get("stock_ml")
            if not stock or stock["experiment"]["experiment_ref"] != refs["experiment_ref"]:
                continue
            registered = (view.get("research") or {}).get("output_refs") or []
            _require(all(stock["experiment"].get(key) == refs[key] and
                         any(r.get("artifact_type") == kind and r.get("artifact_id") == refs[key] for r in registered)
                         for kind, key in bindings.items()), "CONTEXT_MISMATCH: stock stage report inputs")
            _require("stage_report" not in stock, "duplicate stock stage report attachment")
            stock["stage_report"] = deepcopy(report)
            matched = True
        _require(matched, "CONTEXT_MISMATCH: stock stage report without loaded registered experiment")


def render_saved_workbench(run_paths: Sequence[str | Path], *,
                           evaluation_paths: Sequence[str | Path] = (),
                           experiment_paths: Sequence[str | Path] = (),
                           experiment_index_path: str | Path | None = None,
                           stock_ml_paths: Sequence[str | Path] = (),
                           stock_stage_report_paths: Sequence[str | Path] = (),
                           data_batches: Mapping[str, Any] | None = None,
                           data_batch_paths: Mapping[str, str | Path] | None = None,
                           review_displays: Mapping[str, Mapping[str, Any]] | None = None,
                           review_consumer_receipts: Mapping[str, Mapping[str, Any]] | None = None,
                           fill_display_paths: Mapping[str, str | Path] | None = None,
                           synthetic_run_ids: Sequence[str] = (),
                           generated_at: str | None = None) -> str:
    """Read explicit saved owner paths, validate refs, and render a private offline UI.

Data batches must be responses already obtained from Data's public Reader.
The workbench does not discover data roots or implicitly issue a Query.
"""
    for paths, field in ((run_paths, "runs"), (evaluation_paths, "evaluations"), (experiment_paths, "experiments"),
                         (stock_ml_paths, "stock ML experiments"), (stock_stage_report_paths, "stock stage reports")):
        _paths(paths, field)
    _require(experiment_index_path is None or isinstance(experiment_index_path, (str, Path)), "Research index requires explicit path")
    _require(not stock_ml_paths or experiment_index_path is not None, "stock ML requires explicit Research index")
    _require(not stock_stage_report_paths or stock_ml_paths, "stock stage reports require explicitly loaded stock ML")
    _require(bool(run_paths) or experiment_index_path is not None, "an explicit saved run or Research index is required")
    originals, views = [], []
    if run_paths:
        from axiom_engine.runtime import load_backtest_run
        for path in run_paths:
            original = _wire(load_backtest_run(path))
            views.append(_run(original, "synthetic_owner_output" if original["run_id"] in synthetic_run_ids else "saved_backtest_output"))
            # Public validation has finished. Retain only the display projection
            # for stock inputs before loading another large native document.
            originals.append(original if original["contract_version"] not in {"backtest_run_v3", "backtest_run_v4", "backtest_run_v5", "backtest_run_v6"} else
                             {"run_id": original["run_id"], "contract_version": original["contract_version"]})
            del original
    by_id = {v["run"]["run_id"]: v for v in views}
    _require(len(by_id) == len(views), "duplicate run identity")
    _require(set(synthetic_run_ids).issubset(by_id), "unknown synthetic run identity")
    if evaluation_paths:
        from axiom_engine.runtime import load_backtest_evaluation
        for path in evaluation_paths:
            evaluation = _wire(load_backtest_evaluation(path))
            run_id = (evaluation.get("input_run_ref") or {}).get("run_id")
            _require(run_id in by_id, "CONTEXT_MISMATCH: evaluation without loaded run")
            _require(not any(v["evaluation"] is not None and v["evaluation"].get("evaluation_ref") ==
                             evaluation.get("evaluation_ref") for v in views), "duplicate evaluation identity")
            verified = _evaluation(evaluation, by_id[run_id]["run"])
            if by_id[run_id]["evaluation"] is None:
                by_id[run_id]["evaluation"] = verified
            else:
                view = deepcopy(by_id[run_id])
                view["view_id"] = run_id + ":evaluation:" + evaluation["evaluation_ref"]
                view["evaluation"] = verified
                views.append(view)
            del evaluation
    if experiment_paths:
        from axiom_research import load_rotation_experiment
        for path in experiment_paths:
            experiment = load_rotation_experiment(path)
            manifest = experiment.manifest()
            for view in views:
                if view["run"]["signal_ref"] == manifest.get("signal_run_ref"):
                    view["research"] = {"experiment_ref": "sha256:" + experiment.path.name,
                        "question_id": None, "title": None, "hypothesis": None,
                        "version_id": None, "version_label": None, "created_at": None,
                        "tags": None, "favorite": None, "shelved": None,
                        "parameters": manifest.get("policy"), "changes": None,
                        "signal_ref": manifest.get("signal_run_ref"),
                        "feature_ref": manifest.get("feature_build"), "limitations": manifest.get("scope")}
    batches = dict(data_batches or {})
    file_digests = {}
    for run_id, path in (data_batch_paths or {}).items():
        _require(isinstance(path, (str, Path)), "DataBatch requires explicit response file path")
        _require(run_id not in batches, "duplicate DataBatch input for run")
        raw = Path(path).read_bytes()
        def unique(pairs):
            result = {}
            for key, value in pairs:
                _require(key not in result, "duplicate DataBatch JSON key")
                result[key] = value
            return result
        batches[run_id] = json.loads(raw, object_pairs_hook=unique)
        file_digests[run_id] = "sha256:" + sha256(raw).hexdigest()
    for run_id, batch in batches.items():
        _require(run_id in by_id, "CONTEXT_MISMATCH: Data without loaded run")
        original = next(r for r in originals if r["run_id"] == run_id)
        if original["contract_version"] in {"backtest_run_v3", "backtest_run_v4", "backtest_run_v5", "backtest_run_v6"}:
            market = by_id[run_id]["market"]
            source_refs = [s["reference"] for s in market.get("source_evidence") or []
                           if s["context"].get("domain") == "market_daily"]
            _require(len(source_refs) == 1 and _digest(_wire(batch)) == source_refs[0],
                     "CONTEXT_MISMATCH: stock saved DataBatch/native source identity")
            if market.get("native_chart") is not None:
                market["native_chart"]["explicit_saved_batch_matched"] = True
            else:
                market["explicit_saved_batch_matched"] = True
        else:
            _attach_batch(by_id[run_id], batch, original)
        by_id[run_id]["market"]["data_batch_file_digest"] = file_digests.get(run_id)
        for view in views:
            if view is not by_id[run_id] and view["run"]["run_id"] == run_id:
                view["market"] = deepcopy(by_id[run_id]["market"])
    if review_displays:
        from .saved_layers import load_review_display_for_view
        for run_id, binding in review_displays.items():
            _require(run_id in by_id and isinstance(binding, Mapping) and set(binding) ==
                     {"directory", "manifest_sha256", "snapshot_id", "anchor_session", "knowledge_cutoff", "run_ref"},
                     "saved display requires an explicit run and full clock binding")
            load_review_display_for_view(by_id[run_id], **binding)
            for view in views:
                if view is not by_id[run_id] and view["run"]["run_id"] == run_id:
                    view["market"] = deepcopy(by_id[run_id]["market"])
    if review_consumer_receipts:
        from .saved_layers import load_consumer_receipt_for_view
        for run_id, binding in review_consumer_receipts.items():
            _require(run_id in by_id and run_id not in (review_displays or {}) and
                     isinstance(binding, Mapping) and set(binding) == {"receipt_path", "receipt_sha256"},
                     "consumer receipt requires a unique loaded run and fixed byte reference")
            load_consumer_receipt_for_view(by_id[run_id], **binding)
            for view in views:
                if view is not by_id[run_id] and view["run"]["run_id"] == run_id:
                    view["market"] = deepcopy(by_id[run_id]["market"])
    if fill_display_paths:
        from axiom_engine.runtime import load_fill_display
        from .saved_layers import attach_fill_display
        for run_id, path in fill_display_paths.items():
            _require(run_id in by_id and isinstance(path, (str, Path)),
                     "fill display requires an explicit loaded run/path")
            report = _wire(load_fill_display(path))
            attach_fill_display(by_id[run_id], report)
            for view in views:
                if view is not by_id[run_id] and view["run"]["run_id"] == run_id:
                    view["market"]["fill_display"] = deepcopy(by_id[run_id]["market"]["fill_display"])
    if experiment_index_path is not None:
        from axiom_research import ExperimentReader
        views = _catalog(ExperimentReader(experiment_index_path), views)
    _attach_stock_ml(views, stock_ml_paths)
    _attach_stock_stage_reports(views, stock_stage_report_paths)
    return _render(views, generated_at)


def render_sample_workbench(sample: Mapping[str, Any], *, generated_at: str | None = None) -> str:
    """Explicit synthetic UI fixture; never represents an owner result or real run."""
    data = _wire(sample)
    _require(data.get("fixture_kind") == "synthetic_ui_workbench", "explicit synthetic fixture required")
    views = []
    for entry in _rows(data.get("runs"), "sample runs"):
        view = _run(entry.get("run"), "synthetic_ui_fixture")
        view["research"] = deepcopy(entry.get("research"))
        if entry.get("evaluation") is not None:
            view["evaluation"] = _evaluation(entry["evaluation"], view["run"])
        if entry.get("data_batch") is not None:
            _attach_batch(view, entry["data_batch"], entry["run"])
        views.append(view)
    _require(bool(views) and len({v["run"]["run_id"] for v in views}) == len(views),
             "empty/duplicate sample runs")
    return _render(views, generated_at)


def _render(views: list[dict], generated_at: str | None) -> str:
    _require(bool(views), "no saved records to display")
    payload = {"contract_version": "ui_workbench_projection_v1", "views": views,
               "generated_at": _generated(generated_at)}
    # Escaping '<' prevents owner strings from closing the inert JSON script.
    def browser_values(value):
        # Browser coordinates may use Number; saved integers must not silently
        # lose precision at JSON.parse. Display integers as exact decimal text.
        if type(value) is int:
            return str(value)
        if type(value) is list:
            return [browser_values(v) for v in value]
        if type(value) is dict:
            return {k: browser_values(v) for k, v in value.items()}
        return value
    data = json.dumps(browser_values(payload), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    css = (ASSETS / "workbench.css").read_text()
    vendor_manifest = json.loads((ASSETS / "echarts.vendor.json").read_text())
    vendor = (ASSETS / "echarts.6.1.0.min.js").read_bytes()
    _require(sha256(vendor).hexdigest() == vendor_manifest["files"]["echarts.6.1.0.min.js"]["sha256"],
             "chart vendor digest mismatch")
    # One hash-authorized inline script keeps exported HTML usable offline;
    # no CDN, eval permission, browser Owner dependency or business computation.
    script = vendor.decode("utf-8") + "\n;\n" + (ASSETS / "workbench-interactions.js").read_text() + "\n;\n" + (ASSETS / "workbench.js").read_text()
    script_hash = base64.b64encode(sha256(script.encode()).digest()).decode()
    template = (ASSETS / "workbench.html").read_text()
    replacements = {"SCRIPT_HASH": script_hash, "CSS": css, "DATA": data, "SCRIPT": script}
    # Substitute only original template slots; owner text is never reparsed.
    return re.sub(r"\{\{(SCRIPT_HASH|CSS|DATA|SCRIPT)\}\}",
                  lambda match: replacements[match.group(1)], template)
