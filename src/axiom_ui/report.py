"""Offline display of saved Engine output; no execution or account calculation."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
from typing import Any

from .projection import ProjectionError, _digest, _generated, _require


_TABLES = (
    ("nav", "净值 · Owner 保存值"),
    ("positions", "持仓 · 逐交易日"),
    ("decisions", "决策 · 意图"),
    ("orders", "委托 · 非成交"),
    ("fills", "成交 · 模拟"),
    ("cash_ledger", "现金流水"),
    ("position_ledger", "持仓流水"),
)
_LABELS = {
    "session": "交易日", "security_id": "证券", "cash_minor": "现金（元）",
    "market_value_minor": "市值（元）", "receivable_minor": "应收（元）",
    "nav_minor": "净资产（元）", "nav_index": "净值指数",
    "committed_sequence": "已提交水位", "sequence": "事件水位",
    "quantity": "数量（基金份额）", "sellable_quantity": "可卖（基金份额）",
    "mark_price": "估值价格（元/份）", "mark_session": "估值交易日",
    "is_stale": "估值过期", "price": "成交价格（元/份）",
    "gross_minor": "成交金额（元）", "fee_minor": "费用（元）",
    "cash_delta_minor": "现金变动（元）", "total_fees_minor": "总费用（元）",
    "turnover_minor": "成交额（元）",
    "market_state": "市场状态", "state_reason": "状态来源原因",
    "reason": "Owner 原因", "status": "Owner 状态",
}
_CSS = """
:root{color-scheme:dark;font-family:system-ui,-apple-system,sans-serif;background:#11171f;color:#e2e9f2}
body{margin:0}main{max-width:1280px;margin:auto;padding:24px}h1{font-size:25px;margin:8px 0}
h2{font-size:18px;margin-top:0}p{line-height:1.6}a{color:#99c9ef}nav{display:flex;flex-wrap:wrap;gap:16px;margin:20px 0}
.eyebrow,.muted{color:#99aabd;font-size:13px}.banner{padding:14px 18px;background:#322c1e;border-left:4px solid #e7bd6b}
.banner strong{color:#f4d494}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:20px 0}
.card,section{background:#18212c;border:1px solid #2b3849;border-radius:8px;padding:16px}
.card span{display:block;color:#99aabd;font-size:12px;margin-bottom:8px}.card b{font-family:ui-monospace,monospace;font-size:14px;overflow-wrap:anywhere}
section{margin:16px 0;scroll-margin:16px}.limits{border-color:#746039}.limits li{margin:9px 0;line-height:1.5}
.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}
th,td{padding:10px;text-align:left;border-bottom:1px solid #2b3849}th{color:#a9bfd5;font-weight:500}
td.number{text-align:right;font-variant-numeric:tabular-nums}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;color:#c1d3e3}
summary{cursor:pointer;color:#99c9ef}.missing{color:#e7bd6b}code{font-family:ui-monospace,monospace}
@media(max-width:600px){main{padding:12px}.card,section{padding:12px}h1{font-size:21px}}
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)


def _text(value: Any) -> str:
    if value is None:
        return '<span class="missing">未提供</span>'
    if isinstance(value, (dict, list)):
        return escape(_json(value))
    return escape(str(value))


def _cell(key: str, value: Any) -> str:
    if key.endswith("_minor") and value is not None:
        _require(type(value) is int, f"{key} requires integer CNY minor units")
        # Unit formatting only. NAV, fees, returns and all ledger values come from Engine.
        whole, cents = divmod(abs(value), 100)
        amount = f"{'-' if value < 0 else ''}{whole:,}.{cents:02d}"
        return f'<td class="number" title="原始整数分：{value}">{amount}<small class="muted"> 元</small></td>'
    return f'<td>{_text(value)}</td>'


def _table(key: str, title: str, wire: dict) -> str:
    rows = wire.get(key)
    if rows is None:
        body = '<p class="missing">LAYER_UNAVAILABLE · Owner 未提供该产物；不重建、不填零。</p>'
    else:
        _require(type(rows) is list and all(type(row) is dict for row in rows),
                 f"malformed {key} rows")
        if not rows:
            body = '<p>Owner 保存的列表为空。</p>'
        else:
            columns = list(dict.fromkeys(k for row in rows for k in row))
            header = "".join(f'<th scope="col">{escape(_LABELS.get(k, k))}</th>' for k in columns)
            content = "".join("<tr>" + "".join(_cell(k, row.get(k)) for k in columns) + "</tr>"
                              for row in rows)
            body = f'<div class="scroll"><table><thead><tr>{header}</tr></thead><tbody>{content}</tbody></table></div>'
    return f'<section id="{key}"><h2>{title}</h2>{body}</section>'


def _watermarks(wire: dict) -> None:
    """Check display consistency, without reconstructing or interpreting the ledger."""
    nav = wire.get("nav")
    positions = wire.get("positions")
    if nav is None or positions is None:
        return
    _require(type(nav) is list and type(positions) is list, "malformed account history")
    watermarks = {}
    for row in nav:
        _require(type(row) is dict and type(row.get("session")) is str and
                 type(row.get("committed_sequence")) is int,
                 "NAV needs an explicit session/watermark")
        session = row["session"]
        _require(session not in watermarks, "duplicate NAV session")
        watermarks[session] = row["committed_sequence"]
    for row in positions:
        _require(type(row) is dict and type(row.get("session")) is str and
                 type(row.get("committed_sequence")) is int,
                 "position needs an explicit session/watermark")
        _require(row["session"] in watermarks and
                 row["committed_sequence"] == watermarks[row["session"]],
                 "CONTEXT_MISMATCH: NAV/positions committed watermark")


def render_backtest_report(path: str | Path, *, synthetic: bool = False,
                           shareable: bool = False,
                           generated_at: str | None = None) -> str:
    """Read one saved run through Engine's validating Reader and render offline HTML.

    The Reader checks the owner contract and digest without rerunning a backtest.
    Raw mappings belong to render_sample_report and cannot claim saved evidence.
    """
    _require(isinstance(path, (str, Path)), "saved report requires a path and Engine Reader")
    _require(type(synthetic) is bool, "synthetic label must be explicit boolean")
    _require(type(shareable) is bool, "shareable mode must be explicit boolean")
    from axiom_engine.runtime import load_backtest_run
    return _render(load_backtest_run(path), evidence_kind=("synthetic_owner_output" if synthetic else
                   "saved_backtest_output"), generated_at=generated_at, shareable=shareable)


def render_sample_report(run: Any, *, shareable: bool = False, generated_at: str | None = None) -> str:
    """Render a synthetic display fixture; it can never claim saved-run evidence."""
    _require(type(shareable) is bool, "shareable mode must be explicit boolean")
    return _render(run, evidence_kind="synthetic", generated_at=generated_at, shareable=shareable)


def _render(run: Any, *, evidence_kind: str, generated_at: str | None, shareable: bool) -> str:
    wire = run.to_dict() if hasattr(run, "to_dict") else run
    _require(type(wire) is dict and wire.get("contract_version") == "backtest_run_v1",
             "unsupported Engine run contract")
    _require(all(type(wire.get(k)) is str and wire[k] for k in ("run_id", "account_id", "status")),
             "run/account/status identity required")
    try:
        _json(wire)  # Reject non-JSON/nonfinite inputs; never modify the caller's payload.
    except (ValueError, TypeError) as exc:
        raise ProjectionError("run output must be finite JSON") from exc
    _watermarks(wire)
    generated = _generated(generated_at)
    source_digest = _digest(wire)
    banner = ("合成展示样例 · 不是真实回测完成证据" if evidence_kind == "synthetic" else
              "Owner 已保存的合成回测 · 不是真实数据收益验收" if evidence_kind == "synthetic_owner_output" else
              "已保存的模拟回测产物 · 策略有效性与数据资格仍须单独验收")
    orders = wire.get("orders")
    _require(orders is None or (type(orders) is list and all(type(row) is dict for row in orders)),
             "malformed orders rows")
    blocked = any(row.get("reason") == "UNKNOWN_MARKET_STATUS" for row in orders or [])
    execution_notice = ('''<div class="banner"><strong>执行阻断 · 市场状态缺证（UNKNOWN_MARKET_STATUS）</strong>
<p>Owner 记录了状态缺证的委托。cash-only / 零成交结果不构成收益验收；
COMPLETE 仅表示 Owner 保存状态。订单原因与状态来源见委托表。</p></div>''' if blocked else "")
    cards = "".join(f'<div class="card"><span>{label}</span><b>{_text(value)}</b></div>' for label, value in (
        ("运行 Run", wire["run_id"]), ("账户 Account", wire["account_id"]),
        ("Owner 保存状态", wire["status"]), ("最终已提交水位", wire.get("committed_sequence")),
        ("实验 Experiment", wire.get("experiment_id")),
    ))
    limitations = wire.get("limitations")
    _require(limitations is None or type(limitations) is list, "malformed limitations")
    limits = ("".join(f"<li>{_text(item)}</li>" for item in limitations) if limitations else
              '<li class="missing">Owner 未提供限制说明；不能推断为无限制。</li>')
    refs = {k: wire.get(k) for k in ("contract_version", "content_digest", "signal_ref", "market_ref", "profile_ref",
                                   "core_version", "runtime_version", "implementation_ref")}
    metrics = wire.get("metrics")
    _require(metrics is None or type(metrics) is dict, "malformed metrics")
    metric_body = ('<p class="missing">LAYER_UNAVAILABLE · 未保存标准评估。</p>' if metrics is None else
                   ("<div class=\"scroll\"><table><tbody>" + "".join(
                       f"<tr><th>{escape(_LABELS.get(k, k))}</th>{_cell(k, v)}</tr>" for k, v in metrics.items())
                    + "</tbody></table></div>"))
    table_html = "".join(_table(k, title, wire) for k, title in _TABLES)
    links = "".join(f'<a href="#{k}">{title.split(" · ")[0]}</a>' for k, title in _TABLES)
    inputs = ('<p class="muted">分享报告省略冻结计划中的原始市场/信号输入和完整原文；固定引用、版本与结果表保留。</p>'
              if shareable else f'<details><summary>冻结计划与 Data 输入上下文</summary><pre>{_text(wire.get("plan"))}</pre></details>')
    original = ('' if shareable else f'<details><summary>展示输入原文 · 完整保存值</summary><pre>{escape(_json(wire))}</pre></details>')
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Axiom · {_text(wire['run_id'])}</title><style>{_CSS}</style></head>
<body><main><div class="eyebrow">AXIOM / 只读证据报告</div><h1>运行与账户 · 模拟回测</h1>
<div class="banner"><strong>{banner}</strong><p>只展示 Owner 已传入的净值、持仓、意图、委托与成交。所有指标来自保存产物。</p></div>
{execution_notice}
<div class="cards">{cards}</div><p class="muted">实验 ID 未提供时只保留 signal_ref 关联，不推断实验身份。
金额按 CNY 整数分格式化为元；悬停金额可见原始分值。价格原样显示，数量为基金份额。</p>
<section class="limits"><h2>实验假设与限制</h2><ul>{limits}</ul></section>
<nav aria-label="报告栏目">{links}<a href="#versions">数据与实现版本</a></nav>
<section id="versions"><h2>固定引用与版本</h2><p class="muted">Data 身份以 market_ref 及保存 plan 的输入引用为准；不解析 current/latest。</p>
<pre>{escape(_json(refs))}</pre>{inputs}</section>{table_html}
<section id="metrics"><h2>标准评估 · Owner 原值</h2>{metric_body}<p class="muted">不补算 CAGR、Sharpe 或其他未保存指标。</p></section>
<section><h2>最终账户投影 · 原始 JSON</h2><p class="muted">原始字段 *_minor 的金额单位为分。</p><pre>{_text(wire.get('final_account'))}</pre></section>
<section>{original}
<p class="muted">展示输入摘要：{source_digest}<br>页面生成时间：{escape(generated)}<br>
页面生成时间不是来源更新时间。此页无网络、计算任务或交易操作。</p></section>
</main></body></html>'''
