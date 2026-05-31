import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trade_analysis.analyzer import AnalysisConfig, analyze_trades
from trade_analysis.image_importer import OCRBox, parse_broker_order_boxes
from trade_analysis.loader import load_stock_profiles, load_strategy_signals, load_trades
from trade_analysis.webapp import build_analysis_payload


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


if __name__ == "__main__":
    unittest.main()
