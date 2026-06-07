import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trade_analysis.analyzer import AnalysisConfig, analyze_trades
from trade_analysis.image_importer import ImageImportResult, OCRBox, merge_image_import_results, parse_broker_order_boxes
from trade_analysis.loader import load_stock_profiles, load_strategy_signals, load_trades
from trade_analysis.webapp import ROOT, build_analysis_payload, build_clear_history_payload


class AnalyzerTest(unittest.TestCase):
    def test_sample_analysis_finds_behavioral_issues(self):
        trades = load_trades(ROOT / "data" / "sample_trades.csv")
        result = analyze_trades(trades, AnalysisConfig(account_size=500000, overtrade_daily_count=3))
        finding_types = {f["type"] for f in result.findings}
        self.assertEqual(result.metrics["trade_count"], 6)
        self.assertEqual(result.metrics["matched_count"], 2)
        self.assertIn("revenge_trading", finding_types)
        self.assertIn("no_trade_plan", finding_types)
        self.assertIn("fomo_chasing", finding_types)
        self.assertIn("premature_take_profit", finding_types)

    def test_fifo_open_position_after_partial_unmatched(self):
        trades = load_trades(ROOT / "data" / "sample_trades.csv")
        result = analyze_trades(trades)
        open_codes = {p.code for p in result.open_positions}
        self.assertIn("002475", open_codes)

    def test_strategy_and_stock_sources_flag_system_and_symbol_risks(self):
        trades = load_trades(ROOT / "data" / "sample_trades.csv")
        signals = load_strategy_signals(ROOT / "data" / "sample_strategy_signals.csv")
        profiles = load_stock_profiles(ROOT / "data" / "sample_stock_profiles.csv")

        result = analyze_trades(
            trades,
            AnalysisConfig(account_size=500000, overtrade_daily_count=3),
            strategy_signals=signals,
            stock_profiles=profiles,
        )
        finding_types = {f["type"] for f in result.findings}

        self.assertEqual(result.metrics["strategy_signal_count"], 4)
        self.assertEqual(result.metrics["stock_profile_count"], 3)
        self.assertIn("strategy_signal_conflict", finding_types)
        self.assertIn("stock_risk_filter_failed", finding_types)
        self.assertIn("emotion_driven_trading", finding_types)

    def test_web_payload_includes_trades_findings_and_recommendations(self):
        payload = build_analysis_payload({
            "input": str(ROOT / "data" / "sample_trades.csv"),
            "strategy": str(ROOT / "data" / "sample_strategy_signals.csv"),
            "stock": str(ROOT / "data" / "sample_stock_profiles.csv"),
            "account_size": 500000,
            "overtrade_daily_count": 3,
        })

        result = payload["result"]
        self.assertEqual(len(result["trades"]), 6)
        self.assertGreaterEqual(len(result["findings"]), 1)
        self.assertGreaterEqual(len(result["recommendations"]), 1)
        self.assertIn("metrics", result)

    def test_parse_broker_order_image_boxes_filters_unfilled_orders(self):
        boxes = [
            OCRBox("光迅科技", 43, 1138, 246, 1200, 0.95),
            OCRBox("211.600", 448, 1142, 616, 1190, 0.95),
            OCRBox("200", 774, 1142, 858, 1190, 0.99),
            OCRBox("买入", 1025, 1141, 1125, 1201, 0.98),
            OCRBox("买 2026052910:35:51", 51, 1208, 369, 1248, 0.97),
            OCRBox("211.600", 448, 1202, 616, 1250, 0.95),
            OCRBox("200", 776, 1200, 858, 1250, 0.99),
            OCRBox("光迅科技", 43, 1303, 247, 1365, 0.95),
            OCRBox("211.480", 448, 1306, 616, 1356, 0.95),
            OCRBox("200", 776, 1306, 858, 1354, 0.99),
            OCRBox("买入", 1026, 1308, 1122, 1364, 0.98),
            OCRBox("买 2026052910:35:43", 51, 1374, 371, 1413, 0.97),
            OCRBox("0.000", 498, 1366, 616, 1416, 0.99),
            OCRBox("0", 832, 1366, 858, 1416, 0.99),
        ]

        result = parse_broker_order_boxes(boxes)

        self.assertEqual(result.imported_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.trades[0]["name"], "光迅科技")
        self.assertEqual(result.trades[0]["side"], "BUY")

    def test_parse_broker_order_image_boxes_skips_reverse_repo_and_normalizes_a_share_name(self):
        boxes = [
            OCRBox("委托时间", 44, 540, 220, 594, 0.97),
            OCRBox("委托/均价", 420, 540, 618, 594, 0.95),
            OCRBox("委托/成交", 662, 540, 860, 594, 0.91),
            OCRBox("状态", 1032, 542, 1128, 596, 0.92),
            OCRBox("R-001", 44, 650, 190, 700, 0.97),
            OCRBox("0.825", 498, 650, 616, 698, 1.0),
            OCRBox("370", 775, 650, 858, 698, 1.0),
            OCRBox("卖出", 1025, 650, 1125, 710, 0.98),
            OCRBox("2026052915:12:04", 95, 710, 373, 750, 0.94),
            OCRBox("100.000", 450, 710, 616, 760, 0.98),
            OCRBox("370", 775, 710, 858, 760, 1.0),
            OCRBox("京东方 A", 45, 815, 245, 875, 0.85),
            OCRBox("5.280", 498, 815, 616, 865, 1.0),
            OCRBox("2000", 750, 815, 858, 865, 1.0),
            OCRBox("买入", 1025, 815, 1125, 875, 0.99),
            OCRBox("买 2026052910:13:41", 68, 875, 369, 915, 0.89),
            OCRBox("5.280", 498, 875, 616, 925, 1.0),
            OCRBox("2000", 750, 875, 858, 925, 1.0),
        ]

        result = parse_broker_order_boxes(boxes)

        self.assertEqual(result.imported_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.trades[0]["name"], "京东方A")
        self.assertEqual(result.skipped[0]["reason"], "非股票/ETF交易品种，已跳过")

    def test_parse_broker_execution_image_boxes_reads_history_fills(self):
        boxes = [
            OCRBox("成交日期", 44, 704, 222, 760, 0.94),
            OCRBox("成交价", 390, 704, 570, 760, 0.94),
            OCRBox("成交量", 704, 704, 846, 760, 0.98),
            OCRBox("成交额", 976, 704, 1114, 760, 0.98),
            OCRBox("R-001", 43, 810, 190, 860, 0.98),
            OCRBox("质押回购拆出", 896, 812, 1136, 866, 0.96),
            OCRBox("0.825", 480, 834, 600, 886, 1.0),
            OCRBox("370", 784, 834, 868, 882, 1.0),
            OCRBox("37000.000", 920, 868, 1138, 916, 0.96),
            OCRBox("20260529 15:12:05", 43, 874, 361, 916, 0.94),
            OCRBox("江海股份", 43, 1140, 247, 1200, 0.98),
            OCRBox("卖出", 1034, 1140, 1138, 1202, 0.99),
            OCRBox("77.980", 454, 1164, 598, 1214, 1.0),
            OCRBox("一200", 758, 1164, 868, 1212, 0.76),
            OCRBox("15596.000", 922, 1196, 1138, 1244, 0.72),
            OCRBox("2026052914:55:51", 95, 1199, 357, 1235, 0.82),
        ]

        result = parse_broker_order_boxes(boxes)

        self.assertEqual(result.imported_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.trades[0]["name"], "江海股份")
        self.assertEqual(result.trades[0]["side"], "SELL")
        self.assertEqual(result.trades[0]["quantity"], 200)

    def test_clear_history_removes_generated_image_import_csv(self):
        generated = ROOT / "output" / "image_imported_trades.csv"
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text("timestamp,code\n", encoding="utf-8")

        payload = build_clear_history_payload()

        self.assertFalse(generated.exists())
        self.assertIn(str(generated), payload["deleted"])

    def test_merge_image_import_results_deduplicates_same_trade(self):
        trade = {
            "trade_id": "img-1",
            "timestamp": "2026-05-29 10:35:51",
            "code": "光迅科技",
            "name": "光迅科技",
            "side": "BUY",
            "price": 211.6,
            "quantity": 200,
        }

        merged = merge_image_import_results([
            ImageImportResult(trades=[dict(trade)], skipped=[], engine="easyocr"),
            ImageImportResult(trades=[dict(trade)], skipped=[], engine="easyocr"),
        ])

        self.assertEqual(merged.imported_count, 1)
        self.assertEqual(merged.duplicate_count, 1)


if __name__ == "__main__":
    unittest.main()
