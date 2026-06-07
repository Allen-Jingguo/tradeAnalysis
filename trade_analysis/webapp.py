from __future__ import annotations

import argparse
import base64
import json
import tempfile
from dataclasses import asdict, is_dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .analyzer import AnalysisConfig, analyze_trades
from .image_importer import import_trades_from_image, merge_image_import_results, write_imported_csv
from .loader import load_stock_profiles, load_strategy_signals, load_trades

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_INPUT = ROOT / "data" / "sample_trades.csv"
DEFAULT_STRATEGY = ROOT / "data" / "sample_strategy_signals.csv"
DEFAULT_STOCK = ROOT / "data" / "sample_stock_profiles.csv"
DEFAULT_IMAGE = Path("/Users/allenan/Desktop/微信图片_20260531220448_5_2.jpg")


class TradeAnalysisHandler(BaseHTTPRequestHandler):
    server_version = "tradeAnalysisWeb/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/static/"):
            self._send_static(unquote(parsed.path.removeprefix("/static/")), _content_type(parsed.path))
            return
        if parsed.path == "/api/defaults":
            self._send_json({
                "input": str(DEFAULT_INPUT),
                "strategy": str(DEFAULT_STRATEGY),
                "stock": str(DEFAULT_STOCK),
                "image": str(DEFAULT_IMAGE) if DEFAULT_IMAGE.exists() else "",
                "account_size": 500000,
                "overtrade_daily_count": 3,
            })
            return
        if parsed.path == "/api/analyze":
            query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
            self._handle_analyze(query)
            return
        self._send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/analyze", "/api/import-image", "/api/clear-history"}:
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(body or "{}")
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            if parsed.path == "/api/import-image":
                self._send_json(build_image_import_payload(payload))
            elif parsed.path == "/api/clear-history":
                self._send_json(build_clear_history_payload())
            else:
                self._handle_analyze(payload)
        except Exception as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _handle_analyze(self, payload: dict[str, Any]) -> None:
        try:
            response = build_analysis_payload(payload)
        except Exception as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._send_json(response)

    def _send_static(self, relative: str, content_type: str) -> None:
        target = (STATIC_DIR / relative).resolve()
        if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
            self._send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return
        if not target.exists() or not target.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status)


def build_analysis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    input_source = str(payload.get("input") or DEFAULT_INPUT).strip()
    strategy_source = str(payload.get("strategy") or payload.get("strategy_source") or DEFAULT_STRATEGY).strip()
    stock_source = str(payload.get("stock") or payload.get("stock_source") or DEFAULT_STOCK).strip()
    use_strategy = _to_bool(payload.get("use_strategy", True)) and bool(strategy_source)
    use_stock = _to_bool(payload.get("use_stock", True)) and bool(stock_source)

    cfg = AnalysisConfig(
        account_size=_to_float(payload.get("account_size"), 500000.0),
        overtrade_daily_count=int(_to_float(payload.get("overtrade_daily_count"), 3)),
        revenge_window_minutes=int(_to_float(payload.get("revenge_window_minutes"), 60)),
        max_single_trade_pct=_to_float(payload.get("max_single_trade_pct"), 0.20),
        strategy_window_days=int(_to_float(payload.get("strategy_window_days"), 3)),
        max_signal_lag_hours=_to_float(payload.get("max_signal_lag_hours"), 24.0),
        max_signal_slippage_pct=_to_float(payload.get("max_signal_slippage_pct"), 2.0),
        min_stock_score=_to_float(payload.get("min_stock_score"), 60.0),
        min_avg_volume=_to_float(payload.get("min_avg_volume"), 500000.0),
        min_market_cap=_to_float(payload.get("min_market_cap"), 2_000_000_000.0),
        max_volatility_pct=_to_float(payload.get("max_volatility_pct"), 8.0),
        emotional_trade_ratio=_to_float(payload.get("emotional_trade_ratio"), 0.35),
    )

    trades = load_trades(_resolve_source(input_source))
    strategy_signals = load_strategy_signals(_resolve_source(strategy_source)) if use_strategy else []
    stock_profiles = load_stock_profiles(_resolve_source(stock_source)) if use_stock else []
    result = analyze_trades(trades, cfg, strategy_signals=strategy_signals, stock_profiles=stock_profiles)

    return {
        "sources": {
            "input": input_source,
            "strategy": strategy_source if use_strategy else "",
            "stock": stock_source if use_stock else "",
        },
        "result": _to_jsonable(result),
    }


def build_image_import_payload(payload: dict[str, Any]) -> dict[str, Any]:
    image_paths, temporary_paths = _image_paths_from_payload(payload)
    results = []
    try:
        for image_path in image_paths:
            results.append(import_trades_from_image(
                image_path,
                engine=str(payload.get("engine") or "auto"),
                agent=str(payload.get("agent") or "deepseek-v4-pro"),
            ))
    finally:
        for path in temporary_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    result = merge_image_import_results(results)
    out = write_imported_csv(result, ROOT / "output" / "image_imported_trades.csv")
    return {
        "csv_path": str(out),
        "engine": result.engine,
        "image_count": len(image_paths),
        "imported_count": result.imported_count,
        "skipped_count": result.skipped_count,
        "duplicate_count": result.duplicate_count,
        "trades": result.trades,
        "skipped": result.skipped,
        "duplicates": result.duplicates,
    }


def build_clear_history_payload() -> dict[str, Any]:
    generated_files = [
        ROOT / "output" / "image_imported_trades.csv",
    ]
    deleted = []
    for path in generated_files:
        if path.exists() and path.is_file():
            path.unlink()
            deleted.append(str(path))
    return {
        "deleted": deleted,
        "message": "已清除当前界面历史数据和自动生成的图片导入文件。",
    }


def _image_paths_from_payload(payload: dict[str, Any]) -> tuple[list[Path], list[Path]]:
    paths: list[Path] = []
    temporary_paths: list[Path] = []

    files = payload.get("files")
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict) and item.get("data_url"):
                tmp = _write_data_url_to_temp(str(item["data_url"]))
                temporary_paths.append(tmp)
                paths.append(tmp)

    data_urls = payload.get("data_urls")
    if isinstance(data_urls, list):
        for data_url in data_urls:
            tmp = _write_data_url_to_temp(str(data_url))
            temporary_paths.append(tmp)
            paths.append(tmp)

    data_url = str(payload.get("data_url") or "")
    if data_url:
        tmp = _write_data_url_to_temp(data_url)
        temporary_paths.append(tmp)
        paths.append(tmp)

    path_values = payload.get("image_paths")
    if isinstance(path_values, str):
        path_values = _split_image_paths(path_values)
    if isinstance(path_values, list):
        paths.extend(_resolve_local_image_path(str(path)) for path in path_values if str(path).strip())

    image_path = str(payload.get("image_path") or payload.get("path") or "").strip()
    if image_path:
        paths.extend(_resolve_local_image_path(path) for path in _split_image_paths(image_path))

    if not paths:
        raise ValueError("请先选择图片文件，或输入本地图片路径。")
    return paths, temporary_paths


def _write_data_url_to_temp(data_url: str) -> Path:
    if "," not in data_url:
        raise ValueError("invalid image data URL")
    header, encoded = data_url.split(",", 1)
    suffix = ".png"
    if "jpeg" in header or "jpg" in header:
        suffix = ".jpg"
    elif "webp" in header:
        suffix = ".webp"
    tmp = tempfile.NamedTemporaryFile(prefix="trade-image-", suffix=suffix, delete=False)
    with tmp:
        tmp.write(base64.b64decode(encoded))
    return Path(tmp.name)


def _split_image_paths(value: str) -> list[str]:
    return [part.strip() for part in value.replace(",", "\n").splitlines() if part.strip()]


def _resolve_local_image_path(image_path: str) -> Path:
    resolved = _resolve_source(image_path)
    if isinstance(resolved, str):
        raise ValueError("图片 OCR 当前只支持本地图片路径或上传文件。")
    return resolved


def _resolve_source(source: str) -> str | Path:
    if source.startswith(("http://", "https://")):
        return source
    path = Path(source).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _to_float(value: Any, default: float) -> float:
    if value in {None, ""}:
        return default
    return float(value)


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


def _content_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local trade analysis web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    httpd = ThreadingHTTPServer((args.host, args.port), TradeAnalysisHandler)
    print(f"tradeAnalysis web UI: http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
