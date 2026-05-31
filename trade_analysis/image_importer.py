from __future__ import annotations

import csv
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any


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
class ImageImportResult:
    trades: list[dict[str, Any]]
    skipped: list[dict[str, Any]]
    boxes: list[OCRBox] = field(default_factory=list)
    engine: str = ""

    @property
    def imported_count(self) -> int:
        return len(self.trades)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


def import_trades_from_image(image_path: str | Path, engine: str = "auto") -> ImageImportResult:
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    boxes, used_engine = _read_ocr_boxes(path, engine)
    result = parse_broker_order_boxes(boxes)
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


def parse_broker_order_boxes(boxes: list[OCRBox]) -> ImageImportResult:
    data_boxes = [box for box in boxes if box.y >= 620 and box.y <= 2250 and box.text.strip()]
    date_boxes = [box for box in data_boxes if _extract_datetime(box.text)]
    trades: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for idx, date_box in enumerate(sorted(date_boxes, key=lambda b: b.y), 1):
        timestamp = _extract_datetime(date_box.text)
        if timestamp is None:
            continue

        main_band = _nearby_boxes(data_boxes, date_box.y - 66, tolerance=34)
        detail_band = _nearby_boxes(data_boxes, date_box.y, tolerance=34)
        name = _extract_name(main_band)
        side = _extract_side(main_band, detail_band)
        order_price = _number_in_x_range(main_band, 380, 660, prefer="float")
        order_qty = _number_in_x_range(main_band, 680, 910, prefer="int")
        deal_price = _number_in_x_range(detail_band, 380, 660, prefer="float")
        deal_qty = _number_in_x_range(detail_band, 680, 910, prefer="int")

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
        if not deal_price or not deal_qty:
            skipped.append({**raw, "reason": "成交价格或成交数量为 0，按未成交委托跳过"})
            continue

        trades.append({
            "trade_id": f"img-{idx}",
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "code": name,
            "name": name,
            "side": side,
            "price": deal_price,
            "quantity": int(deal_qty),
            "fee": 0,
            "reason": "图片导入：历史委托成交记录",
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
            "tags": "图片导入;历史委托",
            "raw": raw,
        })

    return ImageImportResult(trades=trades, skipped=skipped, boxes=boxes)


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


def _extract_name(boxes: list[OCRBox]) -> str:
    candidates = []
    for box in sorted(boxes, key=lambda b: b.x):
        text = _clean_text(box.text)
        if box.x > 330 or not text:
            continue
        if _extract_datetime(text) or _is_numeric_token(text):
            continue
        if text in {"买", "卖", "买入", "卖出"}:
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
    normalized = str(text).replace(",", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", normalized)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _is_numeric_token(text: str) -> bool:
    normalized = str(text).replace(",", "").strip()
    return bool(re.fullmatch(r"-?\d+(?:\.\d+)?", normalized))


def _normalize_name(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("京东 方", "京东方")
    return text


def _clean_text(text: str) -> str:
    return str(text).strip().replace("　", " ")


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
