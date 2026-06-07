from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from .analyzer import AnalysisResult


def write_markdown(result: AnalysisResult, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(render_markdown(result), encoding="utf-8")


def write_json(result: AnalysisResult, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(_to_jsonable(result), ensure_ascii=False, indent=2), encoding="utf-8")


def render_markdown(result: AnalysisResult) -> str:
    m = result.metrics
    lines = [
        "# 真人实盘操作分析报告",
        "",
        "> 说明：本报告是交易行为复盘，不构成医学/心理诊断，也不构成投资建议。",
        "",
        "## 总览",
        "",
        f"- 原始交易笔数：{m['trade_count']}",
        f"- 已配对买卖：{m['matched_count']}",
        f"- 未平仓持仓：{m['open_position_count']}",
        f"- 已实现盈亏：{m['realized_pnl']:.2f}",
        f"- 胜率：{m['win_rate']:.2f}%",
        f"- 盈亏比/Profit Factor：{m['profit_factor']:.2f}",
        f"- 平均盈利：{m['avg_win']:.2f}",
        f"- 平均亏损：{m['avg_loss']:.2f}",
        f"- 平均持有：{m['avg_holding_days']:.2f} 天",
        f"- 最大单日交易次数：{m['max_trades_per_day']}",
        f"- 最大单笔买入仓位占比：{m['max_single_trade_pct']:.2f}%",
        "",
        "## 主要问题",
        "",
    ]
    overview_extra = []
    if m.get("strategy_signal_count"):
        overview_extra.extend([
            f"- 策略信号数：{m['strategy_signal_count']}",
            f"- 策略一致率：{m['strategy_alignment_rate']:.2f}%",
            f"- 策略冲突交易：{m['strategy_conflict_trade_count']}",
            f"- 系统外/无信号交易：{m['strategy_unsupported_trade_count']}",
        ])
    if m.get("stock_profile_count"):
        overview_extra.extend([
            f"- 标的画像数：{m['stock_profile_count']}",
            f"- 标的风险交易：{m['stock_risk_trade_count']}",
            f"- 风险标的数：{m['stock_risk_code_count']}",
        ])
    if overview_extra:
        lines[-3:-2] = overview_extra + [""]

    if not result.findings:
        lines.append("- 暂未识别到明显行为问题。建议继续积累带计划、情绪、止损目标的交易记录。")
    for idx, f in enumerate(result.findings, 1):
        lines.extend([
            f"### {idx}. {f['title']}（严重度 {f['severity']}/4）",
            "",
            f"- 类型：`{f['type']}`",
            f"- 证据：{f['evidence']}",
            f"- 建议：{f['advice']}",
            "",
        ])

    _render_reassessment(lines, result.reassessment)

    lines.extend(["## 优化路径", ""])
    for rec in result.recommendations:
        lines.append(f"### {rec['stage']}：{rec['title']}")
        lines.extend(f"- {action}" for action in rec["actions"])
        lines.append("")

    if m.get("strategy_signal_count"):
        lines.extend([
            "## 策略信号一致性",
            "",
            f"- 可复核交易：{m['strategy_aligned_trade_count'] + m['strategy_conflict_trade_count'] + m['strategy_unsupported_trade_count']}",
            f"- 对齐交易：{m['strategy_aligned_trade_count']}",
            f"- 冲突交易：{m['strategy_conflict_trade_count']}",
            f"- 无支持信号交易：{m['strategy_unsupported_trade_count']}",
            "",
        ])

    if m.get("stock_profile_count"):
        lines.extend([
            "## 标的画像风险",
            "",
            f"- 已加载画像：{m['stock_profile_count']}",
            f"- 涉及风险画像的买入：{m['stock_risk_trade_count']}",
            f"- 涉及风险标的：{m['stock_risk_code_count']}",
            "",
        ])

    lines.extend(["## 已配对交易明细", ""])
    if result.matched:
        lines.append("| 代码 | 数量 | 买入 | 卖出 | 盈亏 | 盈亏% | 持有天数 |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        matched_desc = sorted(
            result.matched,
            key=lambda t: getattr(t, "sell_time", None) or getattr(t, "buy_time", None) or datetime.min,
            reverse=True,
        )
        for t in matched_desc[:100]:
            lines.append(
                f"| {t.code} {t.name} | {t.quantity} | {t.buy_price:.3f} | {t.sell_price:.3f} | "
                f"{t.pnl:.2f} | {t.pnl_pct:.2f}% | {t.holding_days:.2f} |"
            )
    else:
        lines.append("暂无完整买卖配对。")
    lines.append("")

    if result.open_positions:
        lines.extend(["## 未平仓持仓", "", "| 代码 | 数量 | 成本 | 首次买入 | 止损 | 目标 |", "|---|---:|---:|---|---:|---:|"])
        open_desc = sorted(
            result.open_positions,
            key=lambda p: getattr(p, "first_buy_time", None) or datetime.min,
            reverse=True,
        )
        for p in open_desc:
            lines.append(f"| {p.code} {p.name} | {p.quantity} | {p.avg_cost:.3f} | {p.first_buy_time:%Y-%m-%d} | {p.stop_loss:.3f} | {p.target_price:.3f} |")
        lines.append("")

    return "\n".join(lines)


def _render_reassessment(lines: list, reassessment: dict) -> None:
    if not reassessment or not reassessment.get("evaluated"):
        return
    risk = reassessment.get("risk_score", {})
    lines.extend([
        "## 新交易风险重评",
        "",
        f"- {reassessment.get('summary', '')}",
        f"- 新交易笔数：{reassessment.get('new_trade_count', 0)}（其中买入 {reassessment.get('new_buy_count', 0)}）",
        f"- 综合风险分：{risk.get('baseline', 0)} → {risk.get('current', 0)}（{risk.get('delta', 0):+d}）",
        "",
    ])

    improvement_points = reassessment.get("improvement_points") or []
    if improvement_points:
        lines.append("### 改善点")
        lines.extend(f"- {point}" for point in improvement_points)
        lines.append("")

    watch_points = reassessment.get("watch_points") or []
    if watch_points:
        lines.append("### 待改善点")
        lines.extend(f"- {point}" for point in watch_points)
        lines.append("")

    assessments = reassessment.get("new_trade_assessments") or []
    if assessments:
        lines.extend(["### 新交易逐笔体检", "", "| 代码 | 时间 | 方向 | 评分 | 结论 | 待改进 |", "|---|---|---|---:|---|---|"])
        for a in assessments:
            issues = "、".join(i["label"] for i in a.get("issues", [])) or "无"
            ts = str(a.get("timestamp", "")).replace("T", " ")[:16]
            lines.append(
                f"| {a.get('code', '')} {a.get('name', '')} | {ts} | {a.get('side', '')} | "
                f"{a.get('score', 0)} | {a.get('verdict', '')} | {issues} |"
            )
        lines.append("")


def _to_jsonable(obj):
    if is_dataclass(obj):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj
