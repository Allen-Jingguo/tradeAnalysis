from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean

from .models import MatchedTrade, OpenPosition, StockProfile, StrategySignal, TradeRecord


@dataclass(slots=True)
class AnalysisConfig:
    account_size: float = 100000.0
    overtrade_daily_count: int = 8
    revenge_window_minutes: int = 60
    max_single_trade_pct: float = 0.20
    premature_take_profit_pct: float = 3.0
    chase_position_ratio: float = 0.80
    strategy_window_days: int = 3
    max_signal_lag_hours: float = 24.0
    max_signal_slippage_pct: float = 2.0
    min_stock_score: float = 60.0
    min_avg_volume: float = 500000.0
    min_market_cap: float = 2_000_000_000.0
    max_volatility_pct: float = 8.0
    emotional_trade_ratio: float = 0.35


@dataclass(slots=True)
class AnalysisResult:
    trades: list[TradeRecord]
    matched: list[MatchedTrade]
    open_positions: list[OpenPosition]
    strategy_signals: list[StrategySignal]
    stock_profiles: list[StockProfile]
    metrics: dict
    findings: list[dict]
    recommendations: list[dict]


def analyze_trades(
    trades: list[TradeRecord],
    config: AnalysisConfig | None = None,
    strategy_signals: list[StrategySignal] | None = None,
    stock_profiles: list[StockProfile] | None = None,
) -> AnalysisResult:
    cfg = config or AnalysisConfig()
    signals = strategy_signals or []
    profiles = stock_profiles or []
    matched, open_positions = _match_round_trips(trades)
    metrics = _build_metrics(trades, matched, open_positions, signals, profiles, cfg)
    findings = _detect_findings(trades, matched, open_positions, signals, profiles, metrics, cfg)
    recommendations = _build_recommendations(findings, metrics)
    return AnalysisResult(trades, matched, open_positions, signals, profiles, metrics, findings, recommendations)


def _match_round_trips(trades: list[TradeRecord]) -> tuple[list[MatchedTrade], list[OpenPosition]]:
    lots: dict[str, deque[dict]] = defaultdict(deque)
    matched: list[MatchedTrade] = []

    for trade in trades:
        if trade.is_buy:
            lots[trade.code].append({
                "qty": trade.quantity,
                "price": trade.price,
                "fee_left": trade.fee,
                "time": trade.timestamp,
                "name": trade.name,
                "reason": trade.reason,
                "plan": trade.plan,
                "emotion": trade.emotion,
                "stop_loss": trade.stop_loss,
                "target_price": trade.target_price,
            })
            continue

        sell_qty_left = trade.quantity
        sell_fee_left = trade.fee
        while sell_qty_left > 0 and lots[trade.code]:
            lot = lots[trade.code][0]
            matched_qty = min(sell_qty_left, int(lot["qty"]))
            lot_qty_before = int(lot["qty"])
            buy_fee = float(lot["fee_left"]) * matched_qty / lot_qty_before if lot_qty_before else 0.0
            sell_fee = sell_fee_left * matched_qty / sell_qty_left if sell_qty_left else 0.0
            matched.append(MatchedTrade(
                code=trade.code,
                name=trade.name or str(lot["name"]),
                buy_time=lot["time"],
                sell_time=trade.timestamp,
                quantity=matched_qty,
                buy_price=float(lot["price"]),
                sell_price=trade.price,
                buy_reason=str(lot["reason"]),
                sell_reason=trade.reason,
                buy_plan=str(lot["plan"]),
                sell_plan=trade.plan,
                buy_emotion=str(lot["emotion"]),
                sell_emotion=trade.emotion,
                stop_loss=float(lot["stop_loss"] or trade.stop_loss),
                target_price=float(lot["target_price"] or trade.target_price),
                post_price_1d=trade.post_price_1d,
                post_price_3d=trade.post_price_3d,
                post_price_5d=trade.post_price_5d,
                fee=buy_fee + sell_fee,
            ))
            lot["qty"] = lot_qty_before - matched_qty
            lot["fee_left"] = float(lot["fee_left"]) - buy_fee
            sell_qty_left -= matched_qty
            sell_fee_left -= sell_fee
            if lot["qty"] <= 0:
                lots[trade.code].popleft()

    open_positions = []
    for code, code_lots in lots.items():
        total_qty = sum(int(lot["qty"]) for lot in code_lots)
        if total_qty <= 0:
            continue
        avg_cost = sum(float(lot["price"]) * int(lot["qty"]) for lot in code_lots) / total_qty
        first = min(lot["time"] for lot in code_lots)
        last = max(lot["time"] for lot in code_lots)
        latest = code_lots[-1]
        open_positions.append(OpenPosition(
            code=code,
            name=str(latest["name"]),
            quantity=total_qty,
            avg_cost=avg_cost,
            first_buy_time=first,
            last_buy_time=last,
            reason=str(latest["reason"]),
            plan=str(latest["plan"]),
            emotion=str(latest["emotion"]),
            stop_loss=float(latest["stop_loss"]),
            target_price=float(latest["target_price"]),
        ))
    return matched, open_positions


def _build_metrics(
    trades: list[TradeRecord],
    matched: list[MatchedTrade],
    open_positions: list[OpenPosition],
    strategy_signals: list[StrategySignal],
    stock_profiles: list[StockProfile],
    cfg: AnalysisConfig,
) -> dict:
    realized_pnl = sum(m.pnl for m in matched)
    wins = [m for m in matched if m.is_win]
    losses = [m for m in matched if not m.is_win]
    day_counter = Counter(t.date_key for t in trades)
    by_code = Counter(t.code for t in trades)
    buy_amounts = [t.amount for t in trades if t.is_buy]
    strategy_review = _review_strategy_alignment(trades, strategy_signals, cfg)
    stock_review = _review_stock_profiles(trades, stock_profiles, cfg)
    return {
        "trade_count": len(trades),
        "matched_count": len(matched),
        "open_position_count": len(open_positions),
        "strategy_signal_count": len(strategy_signals),
        "strategy_aligned_trade_count": len(strategy_review["aligned"]),
        "strategy_conflict_trade_count": len(strategy_review["conflicts"]),
        "strategy_unsupported_trade_count": len(strategy_review["unsupported"]),
        "strategy_alignment_rate": round(len(strategy_review["aligned"]) / len(strategy_review["reviewable"]) * 100, 2) if strategy_review["reviewable"] else 0.0,
        "stock_profile_count": len(stock_profiles),
        "stock_risk_trade_count": len(stock_review),
        "stock_risk_code_count": len({case["trade"].code for case in stock_review}),
        "realized_pnl": round(realized_pnl, 2),
        "win_rate": round(len(wins) / len(matched) * 100, 2) if matched else 0.0,
        "avg_win": round(mean([m.pnl for m in wins]), 2) if wins else 0.0,
        "avg_loss": round(mean([m.pnl for m in losses]), 2) if losses else 0.0,
        "profit_factor": round(sum(m.pnl for m in wins) / abs(sum(m.pnl for m in losses)), 2) if losses and sum(m.pnl for m in wins) else 0.0,
        "avg_holding_days": round(mean([m.holding_days for m in matched]), 2) if matched else 0.0,
        "loser_holding_days": round(mean([m.holding_days for m in losses]), 2) if losses else 0.0,
        "winner_holding_days": round(mean([m.holding_days for m in wins]), 2) if wins else 0.0,
        "max_trades_per_day": max(day_counter.values()) if day_counter else 0,
        "active_days": len(day_counter),
        "top_traded_codes": by_code.most_common(5),
        "avg_buy_amount": round(mean(buy_amounts), 2) if buy_amounts else 0.0,
        "max_buy_amount": round(max(buy_amounts), 2) if buy_amounts else 0.0,
        "max_single_trade_pct": round(max(buy_amounts) / cfg.account_size * 100, 2) if buy_amounts and cfg.account_size > 0 else 0.0,
    }


def _detect_findings(
    trades: list[TradeRecord],
    matched: list[MatchedTrade],
    open_positions: list[OpenPosition],
    strategy_signals: list[StrategySignal],
    stock_profiles: list[StockProfile],
    metrics: dict,
    cfg: AnalysisConfig,
) -> list[dict]:
    findings: list[dict] = []
    _add_no_plan_findings(findings, trades)
    _add_emotion_findings(findings, trades, matched, cfg)
    _add_overtrade_findings(findings, trades, cfg)
    _add_revenge_findings(findings, trades, matched, cfg)
    _add_chasing_findings(findings, trades, cfg)
    _add_strategy_alignment_findings(findings, trades, strategy_signals, cfg)
    _add_stock_profile_findings(findings, trades, stock_profiles, cfg)
    _add_stop_loss_findings(findings, matched)
    _add_premature_take_profit_findings(findings, matched, cfg)
    _add_loss_aversion_findings(findings, metrics)
    _add_position_sizing_findings(findings, trades, cfg)
    _add_averaging_down_findings(findings, trades)
    _add_open_position_findings(findings, open_positions)
    findings.sort(key=lambda f: (-int(f.get("severity", 0)), str(f.get("type", ""))))
    return findings


def _append(findings: list[dict], type_: str, severity: int, title: str, evidence: str, advice: str) -> None:
    findings.append({
        "type": type_,
        "severity": severity,
        "title": title,
        "evidence": evidence,
        "advice": advice,
    })


def _review_strategy_alignment(
    trades: list[TradeRecord],
    strategy_signals: list[StrategySignal],
    cfg: AnalysisConfig,
) -> dict[str, list]:
    review: dict[str, list] = {
        "reviewable": [],
        "aligned": [],
        "conflicts": [],
        "unsupported": [],
        "late": [],
        "slippage": [],
        "risk_control_drift": [],
    }
    if not strategy_signals:
        return review

    has_exit_signals = any(signal.is_exit_signal for signal in strategy_signals)
    for trade in trades:
        if not trade.is_buy and not has_exit_signals:
            continue
        review["reviewable"].append(trade)
        candidates = _valid_signals_for_trade(trade, strategy_signals, cfg)
        if not candidates:
            review["unsupported"].append({"trade": trade, "reason": "没有同代码有效策略信号"})
            continue

        support = _best_signal([s for s in candidates if _signal_supports_trade(s, trade)])
        conflict = _best_signal([s for s in candidates if _signal_conflicts_with_trade(s, trade)])
        if support:
            case = {"trade": trade, "signal": support}
            review["aligned"].append(case)
            _add_strategy_execution_issues(review, trade, support, cfg)
        elif conflict:
            review["conflicts"].append({"trade": trade, "signal": conflict})
        else:
            review["unsupported"].append({"trade": trade, "reason": "有同代码信号，但没有支持本次方向的信号"})
    return review


def _valid_signals_for_trade(
    trade: TradeRecord,
    strategy_signals: list[StrategySignal],
    cfg: AnalysisConfig,
) -> list[StrategySignal]:
    window = timedelta(days=max(1, cfg.strategy_window_days))
    candidates = []
    for signal in strategy_signals:
        if signal.code != trade.code:
            continue
        if signal.timestamp is None:
            if signal.valid_until is None or trade.timestamp <= signal.valid_until:
                candidates.append(signal)
            continue
        if trade.timestamp < signal.timestamp:
            continue
        valid_until = signal.valid_until or signal.timestamp + window
        if trade.timestamp <= valid_until:
            candidates.append(signal)
    return candidates


def _best_signal(signals: list[StrategySignal]) -> StrategySignal | None:
    if not signals:
        return None
    return max(signals, key=lambda s: (s.timestamp is not None, s.timestamp or datetime.min, s.confidence))


def _signal_supports_trade(signal: StrategySignal, trade: TradeRecord) -> bool:
    if trade.is_buy:
        return signal.action == "BUY"
    return signal.action in {"SELL", "AVOID"}


def _signal_conflicts_with_trade(signal: StrategySignal, trade: TradeRecord) -> bool:
    if trade.is_buy:
        return signal.action in {"SELL", "AVOID"}
    return signal.action in {"BUY", "HOLD"}


def _add_strategy_execution_issues(
    review: dict[str, list],
    trade: TradeRecord,
    signal: StrategySignal,
    cfg: AnalysisConfig,
) -> None:
    if signal.timestamp is not None:
        lag_hours = (trade.timestamp - signal.timestamp).total_seconds() / 3600
        if lag_hours > cfg.max_signal_lag_hours:
            review["late"].append({"trade": trade, "signal": signal, "lag_hours": lag_hours})

    if signal.price > 0:
        if trade.is_buy:
            slippage_pct = (trade.price - signal.price) / signal.price * 100
        else:
            slippage_pct = (signal.price - trade.price) / signal.price * 100
        if slippage_pct > cfg.max_signal_slippage_pct:
            review["slippage"].append({"trade": trade, "signal": signal, "slippage_pct": slippage_pct})

    if trade.is_buy and signal.action == "BUY":
        drift_limit = max(1.0, cfg.max_signal_slippage_pct)
        if signal.stop_loss > 0:
            if trade.stop_loss <= 0:
                review["risk_control_drift"].append({"trade": trade, "signal": signal, "reason": "未带入策略止损"})
            elif abs(trade.stop_loss - signal.stop_loss) / signal.stop_loss * 100 > drift_limit:
                review["risk_control_drift"].append({"trade": trade, "signal": signal, "reason": "止损价偏离策略"})
        if signal.target_price > 0 and trade.target_price <= 0:
            review["risk_control_drift"].append({"trade": trade, "signal": signal, "reason": "未带入策略目标价"})


def _review_stock_profiles(
    trades: list[TradeRecord],
    stock_profiles: list[StockProfile],
    cfg: AnalysisConfig,
) -> list[dict]:
    if not stock_profiles:
        return []
    cases = []
    for trade in trades:
        if not trade.is_buy:
            continue
        profile = _profile_for_trade(trade, stock_profiles)
        if not profile:
            continue
        reasons = _stock_profile_risk_reasons(profile, cfg)
        if reasons:
            cases.append({"trade": trade, "profile": profile, "reasons": reasons})
    return cases


def _profile_for_trade(trade: TradeRecord, stock_profiles: list[StockProfile]) -> StockProfile | None:
    candidates = [p for p in stock_profiles if p.code == trade.code]
    if not candidates:
        return None
    valid = [p for p in candidates if p.timestamp is None or p.timestamp <= trade.timestamp]
    if not valid:
        return None
    return max(valid, key=lambda p: (p.timestamp is not None, p.timestamp or datetime.min))


def _stock_profile_risk_reasons(profile: StockProfile, cfg: AnalysisConfig) -> list[str]:
    reasons = []
    if profile.score > 0 and profile.score < cfg.min_stock_score:
        reasons.append(f"评分{profile.score:g}低于{cfg.min_stock_score:g}")
    if _is_downtrend(profile.trend):
        reasons.append(f"趋势偏弱({profile.trend})")
    if profile.avg_volume > 0 and profile.avg_volume < cfg.min_avg_volume:
        reasons.append(f"日均成交量{profile.avg_volume:g}低于{cfg.min_avg_volume:g}")
    if profile.market_cap > 0 and profile.market_cap < cfg.min_market_cap:
        reasons.append(f"市值{profile.market_cap:g}低于{cfg.min_market_cap:g}")
    if profile.volatility_pct > cfg.max_volatility_pct:
        reasons.append(f"波动率{profile.volatility_pct:g}%高于{cfg.max_volatility_pct:g}%")

    risk_tags = [tag for tag in profile.risk_tags if _is_high_risk_tag(tag)]
    if risk_tags:
        reasons.append("风险标签:" + "/".join(risk_tags[:3]))
    return reasons


def _is_downtrend(value: str) -> bool:
    text = value.lower()
    return any(k in text for k in ["down", "bear", "weak", "sell", "下降", "下行", "下跌", "偏弱", "走弱", "破位", "空头"])


def _is_high_risk_tag(tag: str) -> bool:
    text = tag.lower()
    return any(k in text for k in [
        "st", "delist", "blacklist", "low_liquidity", "high_volatility", "downtrend",
        "退市", "黑名单", "低流动", "流动性低", "高波动", "趋势转弱", "破位",
        "业绩预警", "亏损", "问询", "减持", "庄股", "追高风险",
    ])


def _emotion_categories_for_trade(trade: TradeRecord) -> list[str]:
    return _emotion_categories(" ".join([
        trade.emotion,
        trade.reason,
        " ".join(trade.tags),
    ]))


def _emotion_categories(text: str) -> list[str]:
    raw = text.lower()
    patterns = [
        ("报复/回本", ["报复", "回本", "赚回来", "revenge"]),
        ("焦虑急躁", ["焦虑", "急躁", "着急", "慌", "冲动", "panic"]),
        ("恐惧退出", ["恐惧", "害怕", "怕亏", "怕回撤", "扛不住", "fear"]),
        ("贪婪重仓", ["贪婪", "梭哈", "满仓", "重仓", "all in"]),
        ("FOMO追涨", ["怕踏空", "fomo", "追高", "追涨", "错过", "踏空"]),
        ("无聊手痒", ["无聊", "手痒", "随手", "试一下"]),
    ]
    return [label for label, keywords in patterns if any(keyword in raw for keyword in keywords)]


def _add_emotion_findings(
    findings: list[dict],
    trades: list[TradeRecord],
    matched: list[MatchedTrade],
    cfg: AnalysisConfig,
) -> None:
    if not trades:
        return
    classified = [(trade, _emotion_categories_for_trade(trade)) for trade in trades]
    emotional = [(trade, cats) for trade, cats in classified if cats]
    ratio = len(emotional) / len(trades)
    if len(emotional) >= 2 and ratio >= cfg.emotional_trade_ratio:
        counter = Counter(cat for _, cats in emotional for cat in cats)
        top = ", ".join(f"{cat}{count}次" for cat, count in counter.most_common(4))
        sample = ", ".join(f"{trade.code}@{trade.timestamp:%m-%d %H:%M}" for trade, _ in emotional[:5])
        _append(
            findings, "emotion_driven_trading", 3, "情绪驱动交易占比过高",
            f"{len(emotional)}/{len(trades)} 笔交易带有高风险情绪线索：{top}。样例：{sample}",
            "把情绪字段纳入下单前检查：报复、焦虑、恐惧、贪婪、FOMO 任一出现时先暂停，重新写入独立交易假设和失效条件。",
        )

    emotional_rounds = [
        match for match in matched
        if _emotion_categories(" ".join([match.buy_emotion, match.sell_emotion, match.buy_reason, match.sell_reason]))
    ]
    if emotional_rounds:
        avg_pnl = mean([m.pnl for m in emotional_rounds])
        loss_count = len([m for m in emotional_rounds if m.pnl < 0])
        if avg_pnl < 0 or loss_count / len(emotional_rounds) >= 0.6:
            _append(
                findings, "emotion_pnl_drag", 3, "情绪交易拖累盈亏",
                f"{len(emotional_rounds)} 笔已闭环交易带有情绪线索，平均盈亏 {avg_pnl:.2f}，亏损 {loss_count} 笔。",
                "按情绪标签统计盈亏贡献；若某类情绪连续两周为负，下一周该情绪出现时只能减仓或观望，不能主动开仓。",
            )

    missing_emotion = [trade for trade in trades if not trade.emotion]
    if len(trades) >= 5 and len(missing_emotion) / len(trades) >= 0.6:
        _append(
            findings, "emotion_record_missing", 1, "情绪记录不足",
            f"{len(missing_emotion)}/{len(trades)} 笔交易缺少情绪字段，难以判断是否存在冲动、恐惧或报复性交易。",
            "复盘模板中保留情绪必填项；没有明显情绪时填写'平静/按计划'，不要留空。",
        )


def _add_strategy_alignment_findings(
    findings: list[dict],
    trades: list[TradeRecord],
    strategy_signals: list[StrategySignal],
    cfg: AnalysisConfig,
) -> None:
    if not strategy_signals:
        return
    review = _review_strategy_alignment(trades, strategy_signals, cfg)
    if review["conflicts"]:
        sample = "; ".join(_format_strategy_case(case) for case in review["conflicts"][:5])
        _append(
            findings, "strategy_signal_conflict", 4, "交易与策略信号冲突",
            f"{len(review['conflicts'])} 笔交易方向与策略信号相反。{sample}",
            "把策略信号作为硬过滤：AVOID/SELL 时禁止新开仓；确需逆向交易时必须记录独立假设、仓位上限和最大亏损。",
        )
    if review["unsupported"]:
        sample = "; ".join(_format_strategy_case(case) for case in review["unsupported"][:5])
        _append(
            findings, "strategy_unsupported_trade", 3, "系统外交易/无策略信号",
            f"{len(review['unsupported'])} 笔交易没有找到支持本次方向的有效策略信号。{sample}",
            "区分'系统内交易'和'自由裁量交易'。没有信号的买入先降为观察仓，且必须写清楚为什么该标的优于策略池候选。",
        )
    if review["slippage"]:
        sample = "; ".join(
            f"{case['trade'].code} 滑点{case['slippage_pct']:.2f}%"
            for case in review["slippage"][:5]
        )
        _append(
            findings, "strategy_execution_slippage", 3, "策略执行滑点偏大",
            f"{len(review['slippage'])} 笔已对齐交易相对信号价滑点超过 {cfg.max_signal_slippage_pct:g}%。{sample}",
            "信号触发后设置可接受价格带；超过滑点上限就放弃，不用追价补偿错过的机会。",
        )
    if review["risk_control_drift"]:
        sample = "; ".join(
            f"{case['trade'].code} {case['reason']}"
            for case in review["risk_control_drift"][:5]
        )
        _append(
            findings, "strategy_risk_control_drift", 3, "策略风控参数未执行",
            f"{len(review['risk_control_drift'])} 笔买入未完整带入策略止损/目标。{sample}",
            "把策略止损、目标价、仓位上限随信号一起落单；手动修改必须留下原因，并重新计算单笔风险金额。",
        )
    if review["late"]:
        sample = "; ".join(
            f"{case['trade'].code} 延迟{case['lag_hours']:.1f}小时"
            for case in review["late"][:5]
        )
        _append(
            findings, "strategy_late_execution", 2, "策略信号执行延迟",
            f"{len(review['late'])} 笔交易晚于信号超过 {cfg.max_signal_lag_hours:g} 小时。{sample}",
            "为每类策略设定有效期。超过有效期后重新拉取信号，而不是把旧信号当作当前依据。",
        )


def _format_strategy_case(case: dict) -> str:
    trade = case["trade"]
    signal = case.get("signal")
    if not signal:
        return f"{trade.code} {trade.side} {trade.timestamp:%m-%d %H:%M}({case.get('reason', '无信号')})"
    strategy = signal.strategy or signal.source or "策略"
    return f"{trade.code} {trade.side} vs {signal.action}({strategy})"


def _add_stock_profile_findings(
    findings: list[dict],
    trades: list[TradeRecord],
    stock_profiles: list[StockProfile],
    cfg: AnalysisConfig,
) -> None:
    cases = _review_stock_profiles(trades, stock_profiles, cfg)
    if not cases:
        return
    by_code: dict[str, set[str]] = defaultdict(set)
    severe = False
    for case in cases:
        code = case["trade"].code
        by_code[code].update(case["reasons"])
        severe = severe or any(any(k in reason for k in ["ST", "退市", "黑名单"]) for reason in case["reasons"])
    sample = "; ".join(f"{code}({', '.join(list(reasons)[:3])})" for code, reasons in list(by_code.items())[:5])
    _append(
        findings, "stock_risk_filter_failed", 4 if severe else 3, "交易标的风险过滤未通过",
        f"{len(cases)} 笔买入涉及 {len(by_code)} 个存在画像风险的标的。{sample}",
        "建立交易前标的过滤：评分、趋势、流动性、市值、波动率、风险标签任一不合格时禁止正常仓位买入，只允许小仓观察或跳过。",
    )


def _add_no_plan_findings(findings: list[dict], trades: list[TradeRecord]) -> None:
    if not trades:
        return
    missing_plan = [t for t in trades if not t.plan and (t.is_buy or not t.reason)]
    missing_stop = [t for t in trades if t.is_buy and t.stop_loss <= 0]
    ratio = len(missing_plan) / len(trades)
    if ratio >= 0.35:
        _append(
            findings, "no_trade_plan", 3, "交易计划缺失",
            f"{len(missing_plan)}/{len(trades)} 笔交易缺少明确计划。",
            "每次买入前强制写入：买入理由、无效条件、止损价、目标价、计划持有周期；缺一项不允许下单。",
        )
    if len(missing_stop) >= max(2, len([t for t in trades if t.is_buy]) // 2):
        _append(
            findings, "no_stop_loss", 3, "止损条件缺失",
            f"{len(missing_stop)} 笔买入没有记录止损价。",
            "止损不是预测，是风险预算。建议用固定R模型：单笔亏损上限=账户权益的0.5%-1%。",
        )


def _add_overtrade_findings(findings: list[dict], trades: list[TradeRecord], cfg: AnalysisConfig) -> None:
    by_day = Counter(t.date_key for t in trades)
    hot_days = [(day, count) for day, count in by_day.items() if count >= cfg.overtrade_daily_count]
    if hot_days:
        sample = ", ".join(f"{day}:{count}笔" for day, count in hot_days[:5])
        _append(
            findings, "overtrading", 3, "交易频率过高",
            f"发现 {len(hot_days)} 个高频交易日：{sample}。",
            "设置每日最大交易次数和冷静期。连续两笔亏损后当天停止主动开新仓，只允许按预案减仓。",
        )


def _add_revenge_findings(findings: list[dict], trades: list[TradeRecord], matched: list[MatchedTrade], cfg: AnalysisConfig) -> None:
    losses = [m for m in matched if m.pnl < 0]
    revenge = []
    for loss in losses:
        deadline = loss.sell_time + timedelta(minutes=cfg.revenge_window_minutes)
        later_buy = next((t for t in trades if t.is_buy and loss.sell_time < t.timestamp <= deadline), None)
        if later_buy:
            revenge.append((loss, later_buy))
    if revenge:
        examples = "; ".join(f"{l.code}亏损后 {b.code} 于{b.timestamp:%m-%d %H:%M}买入" for l, b in revenge[:4])
        _append(
            findings, "revenge_trading", 4, "亏损后报复性交易",
            f"亏损出局后 {cfg.revenge_window_minutes} 分钟内重新开仓 {len(revenge)} 次。{examples}",
            "亏损后增加强制暂停：至少等待30-60分钟，并复述下一笔交易的独立理由，不能用'把亏损赚回来'作为理由。",
        )


def _add_chasing_findings(findings: list[dict], trades: list[TradeRecord], cfg: AnalysisConfig) -> None:
    chasing = []
    for t in trades:
        if not t.is_buy:
            continue
        reason = f"{t.reason} {t.tags}".lower()
        near_high = t.day_high > t.day_low > 0 and (t.price - t.day_low) / (t.day_high - t.day_low) >= cfg.chase_position_ratio
        text_hit = any(k in reason for k in ["追高", "突破", "怕踏空", "fomo", "涨停", "冲高"])
        if near_high or text_hit:
            chasing.append(t)
    if chasing:
        sample = ", ".join(f"{t.code}@{t.price:g}" for t in chasing[:6])
        _append(
            findings, "fomo_chasing", 3, "追涨/FOMO 倾向",
            f"识别到 {len(chasing)} 笔疑似追涨买入：{sample}。",
            "把突破交易拆成两段：突破确认只买计划仓位的30%-50%，回踩不破再补；若无法给出回踩失效位则不追。",
        )


def _add_stop_loss_findings(findings: list[dict], matched: list[MatchedTrade]) -> None:
    violations = [m for m in matched if m.stop_loss > 0 and m.sell_price < m.stop_loss and m.pnl < 0]
    if violations:
        sample = ", ".join(f"{m.code} 止损{m.stop_loss:g}/卖{m.sell_price:g}" for m in violations[:5])
        _append(
            findings, "stop_loss_violation", 4, "止损执行延迟",
            f"{len(violations)} 笔亏损交易卖出价低于计划止损。{sample}",
            "使用硬止损或条件单；人工止损必须在触发后一个交易决策周期内执行，不能用基本面叙事替代风控。",
        )


def _add_premature_take_profit_findings(findings: list[dict], matched: list[MatchedTrade], cfg: AnalysisConfig) -> None:
    early = []
    for m in matched:
        if not m.is_win:
            continue
        future = max(m.post_price_1d, m.post_price_3d, m.post_price_5d)
        target_missed = m.target_price > 0 and m.sell_price < m.target_price and future >= m.target_price
        big_after = future > 0 and (future - m.sell_price) / m.sell_price * 100 >= cfg.premature_take_profit_pct
        if target_missed or big_after:
            early.append(m)
    if early:
        sample = ", ".join(f"{m.code} 卖{m.sell_price:g}/后高{max(m.post_price_1d,m.post_price_3d,m.post_price_5d):g}" for m in early[:5])
        _append(
            findings, "premature_take_profit", 2, "过早止盈",
            f"{len(early)} 笔盈利交易卖出后继续上涨。{sample}",
            "止盈改为分批：到第一目标只卖1/3或1/2，剩余用移动止盈跟随趋势，减少'赚一点就跑'。",
        )


def _add_loss_aversion_findings(findings: list[dict], metrics: dict) -> None:
    loser_days = float(metrics.get("loser_holding_days") or 0)
    winner_days = float(metrics.get("winner_holding_days") or 0)
    if loser_days > 0 and winner_days > 0 and loser_days >= winner_days * 2:
        _append(
            findings, "loss_aversion", 3, "亏损持有过久，盈利持有过短",
            f"亏损平均持有 {loser_days:.2f} 天，盈利平均持有 {winner_days:.2f} 天。",
            "把亏损仓位转为'证伪管理'：到失效位先退出，重新满足条件再买；不要用持有时间证明自己正确。",
        )


def _add_position_sizing_findings(findings: list[dict], trades: list[TradeRecord], cfg: AnalysisConfig) -> None:
    oversized = [t for t in trades if t.is_buy and cfg.account_size > 0 and t.amount / cfg.account_size > cfg.max_single_trade_pct]
    if oversized:
        sample = ", ".join(f"{t.code} {t.amount:.0f}" for t in oversized[:5])
        _append(
            findings, "oversized_position", 3, "单笔仓位过大",
            f"{len(oversized)} 笔买入超过账户 {cfg.max_single_trade_pct:.0%}。{sample}",
            "用风险金额倒推仓位：买入数量 = 单笔最大亏损金额 / (买入价-止损价)，而不是凭感觉决定仓位。",
        )


def _add_averaging_down_findings(findings: list[dict], trades: list[TradeRecord]) -> None:
    buys_by_code: dict[str, list[TradeRecord]] = defaultdict(list)
    for t in trades:
        if t.is_buy:
            buys_by_code[t.code].append(t)
    cases = []
    for code, buys in buys_by_code.items():
        buys.sort(key=lambda x: x.timestamp)
        for prev, cur in zip(buys, buys[1:]):
            if cur.price < prev.price * 0.97 and "计划" not in cur.plan:
                cases.append((prev, cur))
    if cases:
        sample = ", ".join(f"{cur.code} {prev.price:g}->{cur.price:g}" for prev, cur in cases[:5])
        _append(
            findings, "unplanned_averaging_down", 3, "非计划补仓/摊平亏损",
            f"发现 {len(cases)} 次下跌后补仓。{sample}",
            "补仓必须预先写入价格区间和最大仓位；如果是为了降低成本而不是提高胜率，应禁止。",
        )


def _add_open_position_findings(findings: list[dict], open_positions: list[OpenPosition]) -> None:
    missing_exit = [p for p in open_positions if p.stop_loss <= 0 and p.target_price <= 0]
    if missing_exit:
        sample = ", ".join(f"{p.code}x{p.quantity}" for p in missing_exit[:5])
        _append(
            findings, "open_position_without_exit", 2, "持仓缺少退出条件",
            f"{len(missing_exit)} 个持仓没有止损/目标记录。{sample}",
            "对所有持仓补录退出条件：破位价、时间止损、止盈分批线；没有退出条件的持仓先降到观察仓。",
        )


def _build_recommendations(findings: list[dict], metrics: dict) -> list[dict]:
    recs = []
    types = {f["type"] for f in findings}
    recs.append({
        "stage": "交易前",
        "title": "建立一页式交易计划",
        "actions": [
            "买入前写清楚：入场触发、失效条件、止损价、目标价、仓位、计划持有周期。",
            "计划字段为空时不允许下单；临盘理由只能补充，不能替代计划。",
        ],
    })
    if {"revenge_trading", "overtrading"} & types:
        recs.append({
            "stage": "交易中",
            "title": "加入冷静期和每日交易上限",
            "actions": [
                "连续两笔亏损后停止主动买入。",
                "单日交易次数超过阈值后只能执行已有止损/止盈计划。",
            ],
        })
    if {"stop_loss_violation", "oversized_position", "no_stop_loss"} & types:
        recs.append({
            "stage": "风控",
            "title": "用R倍数管理亏损",
            "actions": [
                "每笔最大亏损控制在账户权益0.5%-1%。",
                "仓位由止损距离反推，不用情绪和确定性感觉加仓。",
            ],
        })
    if {"premature_take_profit", "loss_aversion"} & types:
        recs.append({
            "stage": "退出",
            "title": "盈利分批、亏损证伪",
            "actions": [
                "盈利到第一目标只卖部分仓位，剩余使用移动止盈。",
                "亏损触发失效条件立即退出，避免把短线错误变成长线持仓。",
            ],
        })
    if {"strategy_signal_conflict", "strategy_unsupported_trade", "strategy_execution_slippage", "strategy_risk_control_drift"} & types:
        recs.append({
            "stage": "系统交易",
            "title": "把策略信号变成硬约束",
            "actions": [
                "买入必须能关联到有效 BUY 信号；AVOID/SELL 信号出现时禁止新开仓。",
                "记录信号价、有效期、止损、目标价，复盘时统计偏离策略的成本。",
            ],
        })
    if "stock_risk_filter_failed" in types:
        recs.append({
            "stage": "标的池",
            "title": "增加标的质量过滤",
            "actions": [
                "把评分、趋势、流动性、市值、波动率和风险标签做成买入前检查表。",
                "风险标的只允许小仓观察，不能用情绪或题材热度绕过过滤。",
            ],
        })
    if {"emotion_driven_trading", "emotion_pnl_drag"} & types:
        recs.append({
            "stage": "情绪管理",
            "title": "情绪触发冷静期",
            "actions": [
                "报复、焦虑、恐惧、贪婪、FOMO 任一出现时先暂停，重新写入交易假设。",
                "按情绪标签统计盈亏，连续拖累的情绪标签下一周禁止主动开仓。",
            ],
        })
    recs.append({
        "stage": "复盘",
        "title": "每周按错误类型统计",
        "actions": [
            "记录每笔交易的情绪标签：恐惧、贪婪、焦虑、无聊、报复、平静。",
            "只优化出现次数最多的前2类错误，避免同时改太多规则。",
        ],
    })
    return recs
