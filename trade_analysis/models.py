from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TradeRecord:
    trade_id: str
    timestamp: datetime
    code: str
    name: str
    side: str
    price: float
    quantity: int
    fee: float = 0.0
    reason: str = ""
    plan: str = ""
    emotion: str = ""
    market_context: str = ""
    stop_loss: float = 0.0
    target_price: float = 0.0
    day_high: float = 0.0
    day_low: float = 0.0
    post_price_1d: float = 0.0
    post_price_3d: float = 0.0
    post_price_5d: float = 0.0
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def amount(self) -> float:
        return self.price * self.quantity

    @property
    def date_key(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d")

    @property
    def is_buy(self) -> bool:
        return self.side == "BUY"

    @property
    def is_sell(self) -> bool:
        return self.side == "SELL"


@dataclass(slots=True)
class MatchedTrade:
    code: str
    name: str
    buy_time: datetime
    sell_time: datetime
    quantity: int
    buy_price: float
    sell_price: float
    buy_reason: str = ""
    sell_reason: str = ""
    buy_plan: str = ""
    sell_plan: str = ""
    buy_emotion: str = ""
    sell_emotion: str = ""
    stop_loss: float = 0.0
    target_price: float = 0.0
    post_price_1d: float = 0.0
    post_price_3d: float = 0.0
    post_price_5d: float = 0.0
    fee: float = 0.0

    @property
    def gross_pnl(self) -> float:
        return (self.sell_price - self.buy_price) * self.quantity

    @property
    def pnl(self) -> float:
        return self.gross_pnl - self.fee

    @property
    def pnl_pct(self) -> float:
        if self.buy_price <= 0:
            return 0.0
        return (self.sell_price - self.buy_price) / self.buy_price * 100

    @property
    def holding_hours(self) -> float:
        return max(0.0, (self.sell_time - self.buy_time).total_seconds() / 3600)

    @property
    def holding_days(self) -> float:
        return self.holding_hours / 24

    @property
    def is_win(self) -> bool:
        return self.pnl > 0


@dataclass(slots=True)
class OpenPosition:
    code: str
    name: str
    quantity: int
    avg_cost: float
    first_buy_time: datetime
    last_buy_time: datetime
    reason: str = ""
    plan: str = ""
    emotion: str = ""
    stop_loss: float = 0.0
    target_price: float = 0.0

    @property
    def amount(self) -> float:
        return self.avg_cost * self.quantity


@dataclass(slots=True)
class StrategySignal:
    signal_id: str
    timestamp: datetime | None
    code: str
    name: str = ""
    action: str = "BUY"
    strategy: str = ""
    source: str = ""
    price: float = 0.0
    confidence: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    valid_until: datetime | None = None
    reason: str = ""
    risk_tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_buy_signal(self) -> bool:
        return self.action == "BUY"

    @property
    def is_exit_signal(self) -> bool:
        return self.action in {"SELL", "AVOID"}


@dataclass(slots=True)
class StockProfile:
    code: str
    timestamp: datetime | None = None
    name: str = ""
    source: str = ""
    price: float = 0.0
    score: float = 0.0
    trend: str = ""
    sector: str = ""
    avg_volume: float = 0.0
    market_cap: float = 0.0
    volatility_pct: float = 0.0
    pe: float = 0.0
    risk_tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
