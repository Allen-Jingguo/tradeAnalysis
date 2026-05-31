from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import StockProfile, StrategySignal, TradeRecord

_SIDE_BUY = {"BUY", "B", "买", "买入", "建仓", "加仓"}
_SIDE_SELL = {"SELL", "S", "卖", "卖出", "减仓", "清仓", "止盈", "止损"}

_FIELD_ALIASES = {
    "trade_id": ["trade_id", "id", "成交编号", "订单号"],
    "timestamp": ["timestamp", "datetime", "time", "date", "成交时间", "交易时间", "日期"],
    "code": ["code", "symbol", "ticker", "证券代码", "股票代码", "代码"],
    "name": ["name", "证券名称", "股票名称", "名称"],
    "side": ["side", "action", "direction", "买卖", "操作", "方向"],
    "price": ["price", "成交价格", "价格", "成交价"],
    "quantity": ["quantity", "qty", "volume", "成交数量", "数量", "股数"],
    "fee": ["fee", "commission", "手续费", "费用"],
    "reason": ["reason", "entry_reason", "exit_reason", "理由", "买卖理由"],
    "plan": ["plan", "trade_plan", "交易计划", "计划"],
    "emotion": ["emotion", "mood", "心理", "情绪"],
    "market_context": ["market_context", "context", "市场环境", "大盘环境"],
    "stop_loss": ["stop_loss", "stop", "止损", "止损价"],
    "target_price": ["target_price", "target", "目标价", "止盈价"],
    "day_high": ["day_high", "high", "当日最高", "日高"],
    "day_low": ["day_low", "low", "当日最低", "日低"],
    "post_price_1d": ["post_price_1d", "after_1d", "1日后价格"],
    "post_price_3d": ["post_price_3d", "after_3d", "3日后价格"],
    "post_price_5d": ["post_price_5d", "after_5d", "5日后价格"],
    "tags": ["tags", "标签"],
}

_STRATEGY_ALIASES = {
    "signal_id": ["signal_id", "alert_id", "id", "信号ID", "提醒ID"],
    "timestamp": ["timestamp", "datetime", "time", "date", "created_at", "generated_at", "signal_time", "alert_time", "信号时间", "日期"],
    "code": ["code", "symbol", "ticker", "证券代码", "股票代码", "代码"],
    "name": ["name", "证券名称", "股票名称", "名称"],
    "action": ["action", "signal", "side", "direction", "recommendation", "操作", "信号", "建议", "买卖"],
    "strategy": ["strategy", "scanner", "template", "model", "策略", "扫描器", "模板"],
    "source": ["source", "platform", "来源", "平台"],
    "price": ["price", "signal_price", "entry_price", "trigger_price", "close", "last", "最新价", "信号价", "入场价", "触发价"],
    "confidence": ["confidence", "score", "rank_score", "rating", "置信度", "评分"],
    "stop_loss": ["stop_loss", "stop", "stop_price", "止损", "止损价"],
    "target_price": ["target_price", "target", "take_profit", "目标价", "止盈价"],
    "valid_until": ["valid_until", "expires_at", "expire_time", "有效期至", "过期时间"],
    "reason": ["reason", "notes", "description", "signal_reason", "理由", "说明"],
    "risk_tags": ["risk_tags", "tags", "risk", "风险标签", "标签"],
}

_STOCK_ALIASES = {
    "timestamp": ["timestamp", "datetime", "time", "date", "updated_at", "as_of", "日期", "更新时间"],
    "code": ["code", "symbol", "ticker", "证券代码", "股票代码", "代码"],
    "name": ["name", "证券名称", "股票名称", "名称"],
    "source": ["source", "platform", "来源", "平台"],
    "price": ["price", "last_price", "close", "last", "最新价", "收盘价"],
    "score": ["score", "rating", "rank_score", "stock_score", "综合评分", "评分"],
    "trend": ["trend", "trend_state", "status", "technical_trend", "趋势", "状态"],
    "sector": ["sector", "industry", "板块", "行业"],
    "avg_volume": ["avg_volume", "average_volume", "volume_avg", "avg_daily_volume", "日均成交量", "平均成交量"],
    "market_cap": ["market_cap", "mkt_cap", "capitalization", "市值", "总市值"],
    "volatility_pct": ["volatility_pct", "volatility", "atr_pct", "波动率", "ATR%"],
    "pe": ["pe", "pe_ratio", "市盈率", "PE"],
    "risk_tags": ["risk_tags", "tags", "risk", "风险标签", "标签"],
}

_JSON_LIST_KEYS = ("trades", "signals", "alerts", "results", "data", "items", "rows", "records", "scanner_results", "stocks")


def load_trades(path: str | Path) -> list[TradeRecord]:
    rows = _load_rows(path)
    trades = [_row_to_trade(row, idx + 1) for idx, row in enumerate(rows)]
    trades.sort(key=lambda t: (t.timestamp, t.trade_id))
    return trades


def load_strategy_signals(source: str | Path, http_headers: dict[str, str] | None = None) -> list[StrategySignal]:
    rows = _load_rows(source, http_headers=http_headers)
    signals = [_row_to_strategy_signal(row, idx + 1, str(source)) for idx, row in enumerate(rows)]
    signals.sort(key=lambda s: (s.timestamp or datetime.min, s.code, s.signal_id))
    return signals


def load_stock_profiles(source: str | Path, http_headers: dict[str, str] | None = None) -> list[StockProfile]:
    rows = _load_rows(source, http_headers=http_headers)
    profiles = [_row_to_stock_profile(row, idx + 1, str(source)) for idx, row in enumerate(rows)]
    profiles.sort(key=lambda p: (p.timestamp or datetime.min, p.code))
    return profiles


def _load_rows(source: str | Path, http_headers: dict[str, str] | None = None) -> list[dict]:
    text, suffix = _read_text_source(source, http_headers=http_headers)
    if not text:
        return []
    if suffix == ".jsonl":
        return [dict(json.loads(line)) for line in text.splitlines() if line.strip()]
    if text.lstrip().startswith(("[", "{")):
        return _load_json_rows(text)
    return [dict(row) for row in csv.DictReader(io.StringIO(text))]


def _read_text_source(source: str | Path, http_headers: dict[str, str] | None = None) -> tuple[str, str]:
    raw_source = str(source)
    if _is_url(raw_source):
        req = Request(raw_source, headers=http_headers or {})
        with urlopen(req, timeout=30) as response:
            content_type = response.headers.get_content_charset() or "utf-8-sig"
            data = response.read().decode(content_type)
        return data.strip(), Path(urlparse(raw_source).path).suffix.lower()

    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8-sig").strip(), path.suffix.lower()


def _is_url(source: str) -> bool:
    return urlparse(source).scheme in {"http", "https"}


def _load_json_rows(text: str) -> list[dict]:
    data = json.loads(text)
    rows = _extract_json_rows(data)
    if rows is not None:
        return rows
    raise ValueError(f"JSON input must be a list or an object with one of: {', '.join(_JSON_LIST_KEYS)}")


def _extract_json_rows(data: object) -> list[dict] | None:
    if isinstance(data, list):
        return [dict(row) for row in data if isinstance(row, dict)]
    if not isinstance(data, dict):
        return None
    for key in _JSON_LIST_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return [dict(row) for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            nested = _extract_json_rows(value)
            if nested is not None:
                return nested
    return None


def _row_to_trade(row: dict, idx: int) -> TradeRecord:
    mapped = {field: _get(row, aliases) for field, aliases in _FIELD_ALIASES.items()}
    timestamp = _parse_datetime(mapped["timestamp"])
    side = _parse_side(mapped["side"])
    code = str(mapped["code"] or "").strip().upper()
    if not code:
        raise ValueError(f"row {idx}: missing code")
    price = _to_float(mapped["price"])
    qty = int(_to_float(mapped["quantity"]))
    if price <= 0 or qty <= 0:
        raise ValueError(f"row {idx}: price and quantity must be positive")
    return TradeRecord(
        trade_id=str(mapped["trade_id"] or idx),
        timestamp=timestamp,
        code=code,
        name=str(mapped["name"] or code).strip(),
        side=side,
        price=price,
        quantity=qty,
        fee=_to_float(mapped["fee"]),
        reason=str(mapped["reason"] or "").strip(),
        plan=str(mapped["plan"] or "").strip(),
        emotion=str(mapped["emotion"] or "").strip(),
        market_context=str(mapped["market_context"] or "").strip(),
        stop_loss=_to_float(mapped["stop_loss"]),
        target_price=_to_float(mapped["target_price"]),
        day_high=_to_float(mapped["day_high"]),
        day_low=_to_float(mapped["day_low"]),
        post_price_1d=_to_float(mapped["post_price_1d"]),
        post_price_3d=_to_float(mapped["post_price_3d"]),
        post_price_5d=_to_float(mapped["post_price_5d"]),
        tags=_parse_tags(mapped["tags"]),
        raw=dict(row),
    )


def _row_to_strategy_signal(row: dict, idx: int, source: str) -> StrategySignal:
    mapped = {field: _get(row, aliases) for field, aliases in _STRATEGY_ALIASES.items()}
    code = str(mapped["code"] or "").strip().upper()
    if not code:
        raise ValueError(f"strategy row {idx}: missing code")
    return StrategySignal(
        signal_id=str(mapped["signal_id"] or idx),
        timestamp=_parse_datetime_optional(mapped["timestamp"]),
        code=code,
        name=str(mapped["name"] or code).strip(),
        action=_parse_signal_action(mapped["action"]),
        strategy=str(mapped["strategy"] or "").strip(),
        source=str(mapped["source"] or _source_label(source)).strip(),
        price=_to_float(mapped["price"]),
        confidence=_to_float(mapped["confidence"]),
        stop_loss=_to_float(mapped["stop_loss"]),
        target_price=_to_float(mapped["target_price"]),
        valid_until=_parse_datetime_optional(mapped["valid_until"]),
        reason=str(mapped["reason"] or "").strip(),
        risk_tags=_parse_tags(mapped["risk_tags"]),
        raw=dict(row),
    )


def _row_to_stock_profile(row: dict, idx: int, source: str) -> StockProfile:
    mapped = {field: _get(row, aliases) for field, aliases in _STOCK_ALIASES.items()}
    code = str(mapped["code"] or "").strip().upper()
    if not code:
        raise ValueError(f"stock profile row {idx}: missing code")
    return StockProfile(
        code=code,
        timestamp=_parse_datetime_optional(mapped["timestamp"]),
        name=str(mapped["name"] or code).strip(),
        source=str(mapped["source"] or _source_label(source)).strip(),
        price=_to_float(mapped["price"]),
        score=_to_float(mapped["score"]),
        trend=str(mapped["trend"] or "").strip(),
        sector=str(mapped["sector"] or "").strip(),
        avg_volume=_to_float(mapped["avg_volume"]),
        market_cap=_to_float(mapped["market_cap"]),
        volatility_pct=_to_float(mapped["volatility_pct"]),
        pe=_to_float(mapped["pe"]),
        risk_tags=_parse_tags(mapped["risk_tags"]),
        raw=dict(row),
    )


def _get(row: dict, aliases: Iterable[str]) -> str:
    normalized = {str(k).strip().lower(): v for k, v in row.items()}
    for alias in aliases:
        key = alias.strip().lower()
        if key in normalized:
            return normalized[key]
    return ""


def _parse_datetime(value: object) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("missing timestamp")
    patterns = [
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
    ]
    for pattern in patterns:
        try:
            return datetime.strptime(raw, pattern)
        except ValueError:
            continue
    return datetime.fromisoformat(raw)


def _parse_datetime_optional(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    return _parse_datetime(raw)


def _parse_side(value: object) -> str:
    raw = str(value or "").strip().upper()
    if raw in _SIDE_BUY:
        return "BUY"
    if raw in _SIDE_SELL:
        return "SELL"
    raw_cn = str(value or "").strip()
    if raw_cn in _SIDE_BUY:
        return "BUY"
    if raw_cn in _SIDE_SELL:
        return "SELL"
    raise ValueError(f"unknown side: {value}")


def _parse_signal_action(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "BUY"
    upper = raw.upper()
    lower = raw.lower()
    if upper in {"BUY", "B", "LONG", "ENTRY", "OPEN", "OPEN_LONG", "ADD", "ACCUMULATE"} or raw in {"买", "买入", "建仓", "加仓", "做多", "入选", "候选"}:
        return "BUY"
    if upper in {"SELL", "S", "EXIT", "CLOSE", "CLOSE_LONG", "REDUCE", "TAKE_PROFIT", "STOP_LOSS"} or raw in {"卖", "卖出", "减仓", "清仓", "止盈", "止损", "退出"}:
        return "SELL"
    if upper in {"AVOID", "SKIP", "BLOCK", "BLACKLIST", "EXCLUDE", "RISK", "NO_TRADE"} or raw in {"规避", "回避", "不买", "剔除", "黑名单", "风险", "禁买"}:
        return "AVOID"
    if upper in {"HOLD", "WATCH", "WAIT", "NEUTRAL"} or lower in {"hold", "watch", "wait", "neutral"} or raw in {"持有", "观察", "观望", "等待", "中性"}:
        return "HOLD"
    return upper


def _to_float(value: object) -> float:
    if value is None:
        return 0.0
    raw = str(value).strip().replace(",", "").replace("%", "").replace("$", "").replace("￥", "").replace("¥", "")
    if not raw or raw in {"-", "--", "None", "nan"}:
        return 0.0
    multiplier = 1.0
    upper = raw.upper()
    if raw.endswith("亿"):
        multiplier = 100_000_000.0
        raw = raw[:-1]
    elif raw.endswith("万"):
        multiplier = 10_000.0
        raw = raw[:-1]
    elif upper.endswith("B"):
        multiplier = 1_000_000_000.0
        raw = raw[:-1]
    elif upper.endswith("M"):
        multiplier = 1_000_000.0
        raw = raw[:-1]
    elif upper.endswith("K"):
        multiplier = 1_000.0
        raw = raw[:-1]
    return float(raw) * multiplier


def _parse_tags(value: object) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    for sep in [";", "，", ",", "|"]:
        if sep in raw:
            return [x.strip() for x in raw.split(sep) if x.strip()]
    return [raw]


def _source_label(source: str) -> str:
    if _is_url(source):
        parsed = urlparse(source)
        return parsed.netloc or source
    return Path(source).name
