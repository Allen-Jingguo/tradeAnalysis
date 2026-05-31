from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from urllib.parse import urlparse

from .analyzer import AnalysisConfig, analyze_trades
from .image_importer import import_trades_from_image, write_imported_csv
from .loader import load_stock_profiles, load_strategy_signals, load_trades
from .report import render_markdown, write_json, write_markdown

TEMPLATE_FIELDS = [
    "timestamp", "code", "name", "side", "price", "quantity", "fee",
    "reason", "plan", "emotion", "market_context", "stop_loss", "target_price",
    "day_high", "day_low", "post_price_1d", "post_price_3d", "post_price_5d", "tags",
]

SAMPLE_ROWS = [
    {
        "timestamp": "2026-05-06 10:12", "code": "300750", "name": "宁德时代", "side": "BUY",
        "price": "215.50", "quantity": "200", "fee": "8.5", "reason": "突破买入，担心踏空",
        "plan": "突破210买入，跌破205止损，目标235", "emotion": "焦虑", "market_context": "新能源板块强",
        "stop_loss": "205", "target_price": "235", "day_high": "217", "day_low": "208",
        "post_price_1d": "", "post_price_3d": "", "post_price_5d": "", "tags": "突破;怕踏空",
    },
    {
        "timestamp": "2026-05-07 14:45", "code": "300750", "name": "宁德时代", "side": "SELL",
        "price": "204.00", "quantity": "200", "fee": "9.1", "reason": "跌破后扛不住卖出",
        "plan": "原止损205，但盘中犹豫", "emotion": "恐惧", "market_context": "板块转弱",
        "stop_loss": "205", "target_price": "235", "day_high": "211", "day_low": "203",
        "post_price_1d": "209", "post_price_3d": "218", "post_price_5d": "225", "tags": "止损延迟",
    },
    {
        "timestamp": "2026-05-07 15:05", "code": "600519", "name": "贵州茅台", "side": "BUY",
        "price": "1620", "quantity": "100", "fee": "50", "reason": "想把刚才亏损赚回来",
        "plan": "", "emotion": "报复", "market_context": "大盘震荡",
        "stop_loss": "0", "target_price": "0", "day_high": "1625", "day_low": "1580",
        "post_price_1d": "", "post_price_3d": "", "post_price_5d": "", "tags": "报复交易;无计划",
    },
    {
        "timestamp": "2026-05-10 10:30", "code": "600519", "name": "贵州茅台", "side": "SELL",
        "price": "1650", "quantity": "100", "fee": "55", "reason": "赚一点先走",
        "plan": "", "emotion": "害怕回撤", "market_context": "白酒反弹",
        "stop_loss": "0", "target_price": "0", "day_high": "1665", "day_low": "1610",
        "post_price_1d": "1680", "post_price_3d": "1710", "post_price_5d": "1735", "tags": "过早止盈",
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze real trading records and behavioral issues.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_template = sub.add_parser("template", help="write a CSV template or sample")
    p_template.add_argument("--out", default="data/trades_template.csv")
    p_template.add_argument("--sample", action="store_true", help="include sample rows")

    p_image = sub.add_parser("image-import", help="OCR a broker order screenshot into trade CSV")
    p_image.add_argument("--image", required=True, help="local image path")
    p_image.add_argument("--out", default="output/image_imported_trades.csv", help="output trade CSV path")
    p_image.add_argument("--engine", default="auto", choices=["auto", "easyocr", "tesseract"], help="OCR engine")

    p_analyze = sub.add_parser("analyze", help="analyze CSV/JSON trade records")
    p_analyze.add_argument("--input", required=True, help="CSV/JSON/JSONL trade records")
    p_analyze.add_argument("--out", default="output/report.md", help="Markdown report path")
    p_analyze.add_argument("--json-out", default="", help="optional JSON report path")
    p_analyze.add_argument("--strategy-source", default="", help="optional strategy signal CSV/JSON/JSONL path or URL")
    p_analyze.add_argument("--stock-source", default="", help="optional stock profile/risk CSV/JSON/JSONL path or URL")
    p_analyze.add_argument("--http-header", action="append", default=[], help="HTTP header for URL sources, format KEY=VALUE")
    p_analyze.add_argument("--stockpilot-client-id", default="", help="StockPilot API client id; falls back to STOCKPILOT_CLIENT_ID")
    p_analyze.add_argument("--stockpilot-client-secret", default="", help="StockPilot API client secret; falls back to STOCKPILOT_CLIENT_SECRET")
    p_analyze.add_argument("--account-size", type=float, default=100000.0)
    p_analyze.add_argument("--overtrade-daily-count", type=int, default=8)
    p_analyze.add_argument("--revenge-window-minutes", type=int, default=60)
    p_analyze.add_argument("--max-single-trade-pct", type=float, default=0.20)
    p_analyze.add_argument("--strategy-window-days", type=int, default=3)
    p_analyze.add_argument("--max-signal-lag-hours", type=float, default=24.0)
    p_analyze.add_argument("--max-signal-slippage-pct", type=float, default=2.0)
    p_analyze.add_argument("--min-stock-score", type=float, default=60.0)
    p_analyze.add_argument("--min-avg-volume", type=float, default=500000.0)
    p_analyze.add_argument("--min-market-cap", type=float, default=2_000_000_000.0)
    p_analyze.add_argument("--max-volatility-pct", type=float, default=8.0)
    p_analyze.add_argument("--emotional-trade-ratio", type=float, default=0.35)
    p_analyze.add_argument("--print", action="store_true", help="print markdown report to stdout")

    args = parser.parse_args(argv)
    if args.cmd == "template":
        _write_template(args.out, include_sample=args.sample)
        print(f"written: {Path(args.out).resolve()}")
        return 0

    if args.cmd == "image-import":
        result = import_trades_from_image(args.image, engine=args.engine)
        out = write_imported_csv(result, args.out)
        print(
            f"imported={result.imported_count} skipped={result.skipped_count} "
            f"engine={result.engine} csv={out}"
        )
        return 0

    cfg = AnalysisConfig(
        account_size=args.account_size,
        overtrade_daily_count=args.overtrade_daily_count,
        revenge_window_minutes=args.revenge_window_minutes,
        max_single_trade_pct=args.max_single_trade_pct,
        strategy_window_days=args.strategy_window_days,
        max_signal_lag_hours=args.max_signal_lag_hours,
        max_signal_slippage_pct=args.max_signal_slippage_pct,
        min_stock_score=args.min_stock_score,
        min_avg_volume=args.min_avg_volume,
        min_market_cap=args.min_market_cap,
        max_volatility_pct=args.max_volatility_pct,
        emotional_trade_ratio=args.emotional_trade_ratio,
    )
    trades = load_trades(args.input)
    try:
        strategy_signals = load_strategy_signals(
            args.strategy_source,
            http_headers=_headers_for_source(args.strategy_source, args),
        ) if args.strategy_source else []
        stock_profiles = load_stock_profiles(
            args.stock_source,
            http_headers=_headers_for_source(args.stock_source, args),
        ) if args.stock_source else []
    except ValueError as exc:
        parser.error(str(exc))
    result = analyze_trades(trades, cfg, strategy_signals=strategy_signals, stock_profiles=stock_profiles)
    write_markdown(result, args.out)
    if args.json_out:
        write_json(result, args.json_out)
    if args.print:
        print(render_markdown(result))
    print(
        f"trades={result.metrics['trade_count']} matched={result.metrics['matched_count']} "
        f"signals={result.metrics['strategy_signal_count']} stock_profiles={result.metrics['stock_profile_count']} "
        f"findings={len(result.findings)} report={Path(args.out).resolve()}"
    )
    return 0


def _write_template(path: str, include_sample: bool = False) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TEMPLATE_FIELDS)
        writer.writeheader()
        if include_sample:
            writer.writerows(SAMPLE_ROWS)


def _headers_for_source(source: str, args: argparse.Namespace) -> dict[str, str]:
    headers = _parse_http_headers(args.http_header)
    if source and _is_stockpilot_url(source):
        client_id = args.stockpilot_client_id or os.getenv("STOCKPILOT_CLIENT_ID", "")
        client_secret = args.stockpilot_client_secret or os.getenv("STOCKPILOT_CLIENT_SECRET", "")
        if client_id:
            headers["X-CLIENT-ID"] = client_id
        if client_secret:
            headers["X-CLIENT-SECRET"] = client_secret
        if client_id or client_secret:
            headers.setdefault("Accept", "application/json")
    return headers


def _parse_http_headers(values: list[str]) -> dict[str, str]:
    headers = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"invalid --http-header {value!r}; expected KEY=VALUE")
        key, header_value = value.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"invalid --http-header {value!r}; header name is empty")
        headers[key] = header_value.strip()
    return headers


def _is_stockpilot_url(source: str) -> bool:
    host = urlparse(source).netloc.lower()
    return "stockpilot" in host


if __name__ == "__main__":
    raise SystemExit(main())
