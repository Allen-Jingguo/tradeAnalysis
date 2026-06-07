from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


@dataclass(slots=True)
class OCRBox:
    text: str
    left: float
    top: float
    right: float
    bottom: float
    confidence: float = 0.0

    @property
    def x(self) -> float:
        return (self.left + self.right) / 2

    @property
    def y(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass(slots=True)
class TableLayout:
    data_top: float
    data_bottom: float
    name_right: float
    number_left: float
    number_right: float
    row_offset: float
    row_tolerance: float


@dataclass(slots=True)
class ExecutionLayout:
    data_top: float
    data_bottom: float
    name_right: float
    price_left: float
    price_right: float
    qty_left: float
    qty_right: float
    amount_left: float
    row_above: float = 86.0
    row_below: float = 44.0


@dataclass(slots=True)
class ImageImportResult:
    trades: list[dict[str, Any]]
    skipped: list[dict[str, Any]]
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    boxes: list[OCRBox] = field(default_factory=list)
    engine: str = ""

    @property
    def imported_count(self) -> int:
        return len(self.trades)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicates)


def import_trades_from_image(image_path: str | Path, engine: str = "auto", agent: str = "deepseek") -> ImageImportResult:
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    boxes, used_engine = _read_ocr_boxes(path, engine)
    result = parse_broker_order_boxes(boxes)
    agent_name = str(agent or "deepseek").lower().strip()
    if agent_name in {"deepseek", "deepseek-v4-pro", "deepseek_v4_pro", "auto"}:
        result, agent_engine = _apply_deepseek_agent(boxes, result)
        used_engine = f"{used_engine}+{agent_engine}"
    elif agent_name not in {"", "local", "none"}:
        raise ValueError(f"unsupported OCR agent: {agent}")
    result.engine = used_engine
    return result


def write_imported_csv(result: ImageImportResult, path: str | Path) -> Path:
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "timestamp", "code", "name", "side", "price", "quantity", "fee",
        "reason", "plan", "emotion", "market_context", "stop_loss", "target_price",
        "day_high", "day_low", "post_price_1d", "post_price_3d", "post_price_5d", "tags",
    ]
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in result.trades:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return out


def merge_image_import_results(results: list[ImageImportResult]) -> ImageImportResult:
    trades: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    boxes: list[OCRBox] = []
    seen: set[tuple] = set()
    engines = []

    for result in results:
        skipped.extend(result.skipped)
        duplicates.extend(result.duplicates)
        boxes.extend(result.boxes)
        if result.engine and result.engine not in engines:
            engines.append(result.engine)
        for trade in result.trades:
            key = _trade_duplicate_key(trade)
            if key in seen:
                duplicates.append({
                    "timestamp": trade.get("timestamp", ""),
                    "name": trade.get("name", ""),
                    "side": trade.get("side", ""),
                    "price": trade.get("price", 0),
                    "quantity": trade.get("quantity", 0),
                    "reason": "重复记录：时间、标的、方向、价格、数量完全一致",
                })
                continue
            seen.add(key)
            copied = dict(trade)
            trades.append(copied)

    trades = _sort_trades_desc(trades)
    for idx, trade in enumerate(trades, 1):
        trade["trade_id"] = f"img-{idx}"

    return ImageImportResult(
        trades=trades,
        skipped=skipped,
        duplicates=duplicates,
        boxes=boxes,
        engine="+".join(engines),
    )


def parse_broker_order_boxes(boxes: list[OCRBox]) -> ImageImportResult:
    if _is_execution_page(boxes):
        return _parse_broker_execution_boxes(boxes)

    layout = _detect_table_layout(boxes)
    data_boxes = [
        box for box in boxes
        if layout.data_top <= box.y <= layout.data_bottom and box.text.strip()
    ]
    date_boxes = [box for box in data_boxes if _extract_datetime(box.text)]
    trades: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for date_box in sorted(date_boxes, key=lambda b: b.y):
        timestamp = _extract_datetime(date_box.text)
        if timestamp is None:
            continue

        main_band = _nearby_boxes(data_boxes, date_box.y - layout.row_offset, tolerance=layout.row_tolerance)
        detail_band = _nearby_boxes(data_boxes, date_box.y, tolerance=layout.row_tolerance)
        name = _extract_name(main_band, layout)
        side = _extract_side(main_band, detail_band)
        order_price, order_qty = _row_price_and_quantity(main_band, layout)
        deal_price, deal_qty = _row_price_and_quantity(detail_band, layout)

        raw = {
            "name": name,
            "side": side,
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "order_price": order_price,
            "order_quantity": order_qty,
            "deal_price": deal_price,
            "deal_quantity": deal_qty,
            "main_text": " ".join(box.text for box in sorted(main_band, key=lambda b: b.x)),
            "detail_text": " ".join(box.text for box in sorted(detail_band, key=lambda b: b.x)),
        }

        if not name or not side:
            skipped.append({**raw, "reason": "未能识别名称或买卖方向"})
            continue
        if _is_non_stock_product(name):
            skipped.append({**raw, "reason": "非股票/ETF交易品种，已跳过"})
            continue
        if not deal_price or not deal_qty:
            skipped.append({**raw, "reason": "成交价格或成交数量为 0，按未成交委托跳过"})
            continue

        trades.append(_trade_row(
            trade_id=f"img-{len(trades) + 1}",
            timestamp=timestamp,
            name=name,
            side=side,
            price=deal_price,
            quantity=int(deal_qty),
            reason="图片导入：历史委托成交记录",
            tags="图片导入;历史委托",
            raw=raw,
        ))

    trades = _sort_trades_desc(trades)
    return ImageImportResult(trades=trades, skipped=skipped, boxes=boxes)


def _parse_broker_execution_boxes(boxes: list[OCRBox]) -> ImageImportResult:
    layout = _detect_execution_layout(boxes)
    data_boxes = [
        box for box in boxes
        if layout.data_top <= box.y <= layout.data_bottom and box.text.strip()
    ]
    date_boxes = [box for box in data_boxes if _extract_datetime(box.text)]
    trades: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for date_box in sorted(date_boxes, key=lambda b: b.y):
        timestamp = _extract_datetime(date_box.text)
        if timestamp is None:
            continue

        row_boxes = [
            box for box in data_boxes
            if date_box.y - layout.row_above <= box.y <= date_box.y + layout.row_below
        ]
        name = _extract_execution_name(row_boxes, layout, date_box.y)
        side = _extract_side([], row_boxes)
        price = _number_near(row_boxes, layout.price_left, layout.price_right, date_box.y - 36, prefer="float")
        quantity = _number_near(row_boxes, layout.qty_left, layout.qty_right, date_box.y - 36, prefer="int")
        amount = _number_near(row_boxes, layout.amount_left, 1200.0, date_box.y, prefer="float")

        raw = {
            "name": name,
            "side": side,
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "deal_price": price,
            "deal_quantity": quantity,
            "deal_amount": amount,
            "row_text": " ".join(box.text for box in sorted(row_boxes, key=lambda b: (b.y, b.x))),
        }

        if name and _is_non_stock_product(name):
            skipped.append({**raw, "reason": "非股票/ETF交易品种，已跳过"})
            continue
        if not name or not side:
            skipped.append({**raw, "reason": "未能识别名称或买卖方向"})
            continue
        if not price or not quantity:
            skipped.append({**raw, "reason": "成交价格或成交数量为 0，按未成交记录跳过"})
            continue

        trades.append(_trade_row(
            trade_id=f"img-{len(trades) + 1}",
            timestamp=timestamp,
            name=name,
            side=side,
            price=price,
            quantity=abs(int(quantity)),
            reason="图片导入：历史成交记录",
            tags="图片导入;历史成交",
            raw=raw,
        ))

    trades = _sort_trades_desc(trades)
    return ImageImportResult(trades=trades, skipped=skipped, boxes=boxes)


def _detect_table_layout(boxes: list[OCRBox]) -> TableLayout:
    text_boxes = [box for box in boxes if box.text.strip()]
    header_boxes = [box for box in text_boxes if _is_table_header(box.text)]
    header_y = _median([box.y for box in header_boxes]) if header_boxes else 570.0
    status_box = _find_header_box(header_boxes, "状态")
    price_box = _find_header_box(header_boxes, "委托/均价")
    qty_box = _find_header_box(header_boxes, "委托/成交")

    date_boxes = [box for box in text_boxes if box.y > header_y and _extract_datetime(box.text)]
    date_ys = sorted(box.y for box in date_boxes)
    row_gap = _median([b - a for a, b in zip(date_ys, date_ys[1:]) if b - a > 20]) or 165.0
    row_offset = min(80.0, max(42.0, row_gap * 0.36))
    row_tolerance = min(38.0, max(24.0, row_offset * 0.55))

    number_left = (price_box.x - 160.0) if price_box else 360.0
    number_right = (status_box.x - 80.0) if status_box else 980.0
    if qty_box and status_box:
        number_right = (qty_box.x + status_box.x) / 2
    data_bottom = max([box.y for box in date_boxes], default=2250.0) + row_offset
    return TableLayout(
        data_top=header_y + 40.0,
        data_bottom=data_bottom,
        name_right=number_left - 12.0,
        number_left=number_left,
        number_right=number_right,
        row_offset=row_offset,
        row_tolerance=row_tolerance,
    )


def _detect_execution_layout(boxes: list[OCRBox]) -> ExecutionLayout:
    text_boxes = [box for box in boxes if box.text.strip()]
    header_boxes = [box for box in text_boxes if _is_execution_header(box.text)]
    header_y = _median([box.y for box in header_boxes]) if header_boxes else 732.0
    price_box = _find_header_box(header_boxes, "成交价")
    qty_box = _find_header_box(header_boxes, "成交量")
    amount_box = _find_header_box(header_boxes, "成交额")
    price_x = price_box.x if price_box else 520.0
    qty_x = qty_box.x if qty_box else 806.0
    amount_x = amount_box.x if amount_box else 1045.0

    date_boxes = [box for box in text_boxes if box.y > header_y and _extract_datetime(box.text)]
    data_bottom = max([box.y for box in date_boxes], default=2250.0) + 48.0
    price_qty_mid = (price_x + qty_x) / 2
    qty_amount_mid = (qty_x + amount_x) / 2
    return ExecutionLayout(
        data_top=header_y + 42.0,
        data_bottom=data_bottom,
        name_right=price_x - 130.0,
        price_left=price_x - 170.0,
        price_right=price_qty_mid,
        qty_left=price_qty_mid,
        qty_right=qty_amount_mid,
        amount_left=qty_amount_mid,
    )


def _trade_row(
    trade_id: str,
    timestamp: datetime,
    name: str,
    side: str,
    price: float,
    quantity: int,
    reason: str,
    tags: str,
    raw: dict[str, Any],
) -> dict[str, Any]:
    return {
        "trade_id": trade_id,
        "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "code": name,
        "name": name,
        "side": side,
        "price": price,
        "quantity": int(quantity),
        "fee": 0,
        "reason": reason,
        "plan": "",
        "emotion": "",
        "market_context": "",
        "stop_loss": 0,
        "target_price": 0,
        "day_high": 0,
        "day_low": 0,
        "post_price_1d": 0,
        "post_price_3d": 0,
        "post_price_5d": 0,
        "tags": tags,
        "raw": raw,
    }


def _apply_deepseek_agent(boxes: list[OCRBox], fallback: ImageImportResult) -> tuple[ImageImportResult, str]:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return fallback, "deepseek-v4-pro-unconfigured"

    rows_text = _agent_ocr_rows(boxes)
    payload = {
        "model": os.environ.get("DEEPSEEK_OCR_MODEL", "deepseek-v4-pro"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是证券交易截图 OCR 校正 Agent。只输出 JSON，不要输出解释。"
                    "从万联证券历史成交/历史委托 OCR 文本中提取股票或 ETF 成交记录。"
                    "跳过 R-001、GC001、逆回购、质押回购、成交量为 0 的未成交记录。"
                    "卖出数量即使 OCR 是负数，输出 quantity 也要为正整数。"
                    "字段：trades 数组，每项含 timestamp(YYYY-MM-DD HH:MM:SS), name, side(BUY/SELL), price, quantity；"
                    "skipped 数组，每项含 name, timestamp, reason。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请根据以下 OCR 行文本校正并结构化交易记录。"
                    "优先使用成交价、成交量、成交日期，不要把成交额当成交量。\n\n"
                    f"{rows_text}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "stream": False,
    }
    request = Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        parsed = _extract_json_object(content)
        trades = []
        skipped = []
        for item in parsed.get("trades", []):
            row = _coerce_agent_trade(item, len(trades) + 1)
            if row:
                trades.append(row)
        for item in parsed.get("skipped", []):
            if isinstance(item, dict):
                skipped.append({
                    "name": str(item.get("name") or ""),
                    "timestamp": str(item.get("timestamp") or ""),
                    "reason": str(item.get("reason") or "DeepSeek Agent 跳过"),
                })
        if trades:
            trades = _sort_trades_desc(trades)
            for idx, trade in enumerate(trades, 1):
                trade["trade_id"] = f"img-{idx}"
            return ImageImportResult(trades=trades, skipped=skipped, boxes=boxes), "deepseek-v4-pro"
    except Exception:
        return fallback, "deepseek-v4-pro-fallback"
    return fallback, "deepseek-v4-pro-fallback"


def _agent_ocr_rows(boxes: list[OCRBox]) -> str:
    lines = []
    for box in sorted(boxes, key=lambda b: (b.y, b.x)):
        if box.y < 520 or box.y > 2300:
            continue
        lines.append(f"x={box.x:.0f} y={box.y:.0f} text={box.text}")
    return "\n".join(lines)


def _extract_json_object(content: str) -> dict[str, Any]:
    text = str(content).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("DeepSeek OCR response must be a JSON object")
    return data


def _coerce_agent_trade(item: Any, idx: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    timestamp = _parse_agent_datetime(item.get("timestamp"))
    name = _normalize_name(str(item.get("name") or "").strip())
    side = str(item.get("side") or "").strip().upper()
    if side in {"买", "买入", "B"}:
        side = "BUY"
    if side in {"卖", "卖出", "S"}:
        side = "SELL"
    price = _parse_number(str(item.get("price") or ""))
    quantity = _parse_number(str(item.get("quantity") or ""))
    if not timestamp or not name or side not in {"BUY", "SELL"} or not price or not quantity:
        return None
    if _is_non_stock_product(name):
        return None
    return _trade_row(
        trade_id=f"img-{idx}",
        timestamp=timestamp,
        name=name,
        side=side,
        price=price,
        quantity=abs(int(quantity)),
        reason="图片导入：DeepSeek V4 Pro Agent 校正",
        tags="图片导入;DeepSeek校正",
        raw=dict(item),
    )


def _parse_agent_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y%m%d %H:%M:%S", "%Y%m%d%H:%M:%S"):
        try:
            return datetime.strptime(raw, pattern)
        except ValueError:
            continue
    return _extract_datetime(raw)


def _read_ocr_boxes(path: Path, engine: str) -> tuple[list[OCRBox], str]:
    requested = engine.lower().strip()
    if requested in {"auto", "easyocr"}:
        try:
            return _read_easyocr(path), "easyocr"
        except Exception:
            if requested == "easyocr":
                raise
    if requested in {"auto", "tesseract"}:
        return _read_tesseract(path), "tesseract"
    raise ValueError(f"unsupported OCR engine: {engine}")


def _read_easyocr(path: Path) -> list[OCRBox]:
    import easyocr  # type: ignore

    reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
    raw = reader.readtext(str(path), detail=1, paragraph=False)
    boxes = []
    for points, text, confidence in raw:
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
        boxes.append(OCRBox(
            text=str(text).strip(),
            left=min(xs),
            top=min(ys),
            right=max(xs),
            bottom=max(ys),
            confidence=float(confidence),
        ))
    return boxes


def _read_tesseract(path: Path) -> list[OCRBox]:
    if not shutil.which("tesseract"):
        raise RuntimeError("未找到 OCR 引擎。请安装 tesseract，或安装 easyocr。")
    proc = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", "chi_sim+eng", "--psm", "6", "tsv"],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = csv.DictReader(StringIO(proc.stdout), delimiter="\t")
    boxes = []
    for row in rows:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        left = _safe_float(row.get("left"))
        top = _safe_float(row.get("top"))
        width = _safe_float(row.get("width"))
        height = _safe_float(row.get("height"))
        boxes.append(OCRBox(
            text=text,
            left=left,
            top=top,
            right=left + width,
            bottom=top + height,
            confidence=_safe_float(row.get("conf")),
        ))
    return boxes


def _nearby_boxes(boxes: list[OCRBox], y: float, tolerance: float) -> list[OCRBox]:
    return [box for box in boxes if abs(box.y - y) <= tolerance]


def _extract_name(boxes: list[OCRBox], layout: TableLayout) -> str:
    candidates = []
    for box in sorted(boxes, key=lambda b: b.x):
        text = _clean_text(box.text)
        if box.x > layout.name_right or not text:
            continue
        if _extract_datetime(text) or _is_numeric_token(text):
            continue
        if text in {"买", "卖", "买入", "卖出"}:
            continue
        candidates.append(text)
    if not candidates:
        return ""
    return _normalize_name("".join(candidates))


def _extract_execution_name(boxes: list[OCRBox], layout: ExecutionLayout, date_y: float) -> str:
    candidates = []
    for box in sorted(boxes, key=lambda b: (b.y, b.x)):
        text = _clean_text(box.text)
        if box.x > layout.name_right or box.y > date_y + 4 or not text:
            continue
        if _extract_datetime(text) or _is_numeric_token(text):
            continue
        if text in {"买", "卖", "买入", "卖出"}:
            continue
        if _is_table_header(text) or _is_execution_header(text):
            continue
        candidates.append(text)
    if not candidates:
        return ""
    return _normalize_name("".join(candidates))


def _extract_side(main_band: list[OCRBox], detail_band: list[OCRBox]) -> str:
    text = " ".join(box.text for box in [*main_band, *detail_band])
    if "买入" in text or re.search(r"(^|\s)买(\s|20|$)", text):
        return "BUY"
    if "卖出" in text or re.search(r"(^|\s)卖(\s|20|$)", text):
        return "SELL"
    return ""


def _row_price_and_quantity(boxes: list[OCRBox], layout: TableLayout) -> tuple[float, float]:
    candidates = []
    for box in boxes:
        if not (layout.number_left <= box.x <= layout.number_right):
            continue
        text = _clean_text(box.text)
        if not _is_numeric_token(text):
            continue
        number = _parse_number(text)
        if number is not None:
            candidates.append((box.x, number))
    candidates.sort(key=lambda item: item[0])
    if len(candidates) >= 2:
        return candidates[0][1], float(int(round(candidates[1][1])))
    if len(candidates) == 1:
        value = candidates[0][1]
        return (value, 0.0) if value < 1000 else (0.0, float(int(round(value))))
    return 0.0, 0.0


def _number_near(boxes: list[OCRBox], left: float, right: float, target_y: float, prefer: str) -> float:
    candidates = []
    for box in boxes:
        if not (left <= box.x <= right):
            continue
        text = _clean_text(box.text)
        if not _is_numeric_token(text):
            continue
        number = _parse_number(text)
        if number is not None:
            candidates.append((abs(box.y - target_y), abs((left + right) / 2 - box.x), number))
    if not candidates:
        return 0.0
    candidates.sort(key=lambda item: (item[0], item[1]))
    value = candidates[0][2]
    if prefer == "int":
        return float(int(round(value)))
    return value


def _number_in_x_range(boxes: list[OCRBox], left: float, right: float, prefer: str) -> float:
    candidates = []
    for box in boxes:
        if left <= box.x <= right:
            number = _parse_number(box.text)
            if number is not None:
                candidates.append((abs((left + right) / 2 - box.x), number))
    if not candidates:
        return 0.0
    candidates.sort(key=lambda item: item[0])
    value = candidates[0][1]
    if prefer == "int":
        return float(int(round(value)))
    return value


def _extract_datetime(text: str) -> datetime | None:
    normalized = re.sub(r"\s+", "", text)
    match = re.search(r"(20\d{6})(\d{2}:\d{2}:\d{2})", normalized)
    if not match:
        return None
    return datetime.strptime(" ".join(match.groups()), "%Y%m%d %H:%M:%S")


def _parse_number(text: str) -> float | None:
    normalized = _normalize_number_text(text)
    match = re.search(r"-?\d+(?:\.\d+)?", normalized)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _is_numeric_token(text: str) -> bool:
    normalized = _normalize_number_text(text)
    return bool(re.fullmatch(r"-?\d+(?:\.\d+)?", normalized))


def _normalize_number_text(text: Any) -> str:
    normalized = str(text).replace(",", "").strip()
    normalized = normalized.replace("−", "-").replace("－", "-").replace("—", "-").replace("–", "-")
    normalized = re.sub(r"(?<![\u4e00-\u9fff])一(?=\d)", "-", normalized)
    normalized = re.sub(r"^[^0-9.-]+(?=\d)", "", normalized)
    return normalized


def _normalize_name(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("京东 方", "京东方")
    text = re.sub(r"([\u4e00-\u9fff])\s+([ABH])$", r"\1\2", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(etf)\b", "ETF", text, flags=re.IGNORECASE)
    return text


def _clean_text(text: str) -> str:
    return str(text).strip().replace("　", " ")


def _is_table_header(text: str) -> bool:
    normalized = _clean_text(text)
    return any(part in normalized for part in ("委托时间", "委托/均价", "委托/成交", "状态"))


def _is_execution_header(text: str) -> bool:
    normalized = _clean_text(text)
    return any(part in normalized for part in ("成交日期", "成交价", "成交量", "成交额"))


def _is_execution_page(boxes: list[OCRBox]) -> bool:
    texts = [_clean_text(box.text) for box in boxes]
    return any("成交日期" in text for text in texts) and any("成交量" in text for text in texts)


def _find_header_box(boxes: list[OCRBox], text: str) -> OCRBox | None:
    for box in boxes:
        if text in _clean_text(box.text):
            return box
    return None


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _is_non_stock_product(name: str) -> bool:
    normalized = re.sub(r"\s+", "", name).upper()
    # OCR noise: capital O frequently misread as digit 0, and vice versa.
    digit_form = normalized.replace("O", "0")
    if re.fullmatch(r"R-?\d{3}", digit_form):
        return True
    if re.fullmatch(r"GC\d{3}", digit_form):
        return True
    return any(keyword in normalized for keyword in ("逆回购", "国债回购", "质押回购", "拆出质押", "质押购回"))


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _sort_trades_desc(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(trade: dict[str, Any]) -> str:
        return str(trade.get("timestamp") or "")
    return sorted(trades, key=key, reverse=True)


def _trade_duplicate_key(trade: dict[str, Any]) -> tuple:
    return (
        str(trade.get("timestamp") or "").strip(),
        re.sub(r"\s+", "", str(trade.get("name") or trade.get("code") or "")),
        str(trade.get("side") or "").strip().upper(),
        round(float(trade.get("price") or 0), 4),
        int(float(trade.get("quantity") or 0)),
    )
