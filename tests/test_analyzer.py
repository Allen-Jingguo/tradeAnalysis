import os
import unittest
from datetime import datetime
from pathlib import Path
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trade_analysis.analyzer import AnalysisConfig, analyze_trades, reconcile_holdings
from trade_analysis.image_importer import (
    ImageImportResult,
    OCRBox,
    _is_holdings_page,
    _is_non_stock_product,
    import_trades_from_image,
    merge_image_import_results,
    parse_broker_holdings_boxes,
    parse_broker_order_boxes,
)
from trade_analysis.loader import load_stock_profiles, load_strategy_signals, load_trades
from trade_analysis.models import OpenPosition, StockProfile, StrategySignal, TradeRecord
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

    def test_parse_broker_execution_image_boxes_recognises_hk_connect_sell(self):
        boxes = [
            OCRBox("成交日期", 44, 704, 222, 760, 0.94),
            OCRBox("成交价", 390, 704, 570, 760, 0.94),
            OCRBox("成交量", 704, 704, 846, 760, 0.98),
            OCRBox("成交额", 976, 704, 1114, 760, 0.98),
            OCRBox("药明康德", 43, 1140, 247, 1200, 0.97),
            OCRBox("沪港通卖出", 970, 1138, 1138, 1200, 0.96),
            OCRBox("132.400", 454, 1164, 598, 1214, 1.0),
            OCRBox("一200", 758, 1164, 868, 1212, 0.78),
            OCRBox("23015.900", 922, 1196, 1138, 1244, 0.74),
            OCRBox("卖 2026052110:22:35", 51, 1199, 369, 1240, 0.88),
        ]

        result = parse_broker_order_boxes(boxes)

        self.assertEqual(result.imported_count, 1)
        self.assertEqual(result.trades[0]["name"], "药明康德")
        self.assertEqual(result.trades[0]["side"], "SELL")
        self.assertEqual(result.trades[0]["quantity"], 200)

    def test_parse_broker_execution_image_boxes_sorts_trades_descending(self):
        boxes = [
            OCRBox("成交日期", 44, 704, 222, 760, 0.94),
            OCRBox("成交价", 390, 704, 570, 760, 0.94),
            OCRBox("成交量", 704, 704, 846, 760, 0.98),
            OCRBox("成交额", 976, 704, 1114, 760, 0.98),
            OCRBox("江海股份", 43, 810, 247, 870, 0.98),
            OCRBox("买入", 1034, 810, 1138, 872, 0.99),
            OCRBox("72.070", 454, 834, 598, 884, 1.0),
            OCRBox("200", 758, 834, 868, 882, 1.0),
            OCRBox("14414.000", 922, 866, 1138, 914, 0.92),
            OCRBox("买 20260528 09:30:03", 43, 870, 361, 912, 0.94),
            OCRBox("江海股份", 43, 1140, 247, 1200, 0.98),
            OCRBox("卖出", 1034, 1140, 1138, 1202, 0.99),
            OCRBox("77.980", 454, 1164, 598, 1214, 1.0),
            OCRBox("一200", 758, 1164, 868, 1212, 0.78),
            OCRBox("15596.000", 922, 1196, 1138, 1244, 0.72),
            OCRBox("卖 20260529 14:55:51", 95, 1199, 357, 1235, 0.84),
        ]

        result = parse_broker_order_boxes(boxes)

        self.assertEqual(result.imported_count, 2)
        timestamps = [t["timestamp"] for t in result.trades]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))
        self.assertEqual(result.trades[0]["timestamp"], "2026-05-29 14:55:51")

    def test_merge_image_import_results_sorts_across_days_desc(self):
        earlier = {
            "trade_id": "img-1",
            "timestamp": "2026-05-26 09:35:11",
            "code": "埃斯顿",
            "name": "埃斯顿",
            "side": "BUY",
            "price": 28.93,
            "quantity": 200,
        }
        later = {
            "trade_id": "img-1",
            "timestamp": "2026-05-29 10:36:07",
            "code": "光迅科技",
            "name": "光迅科技",
            "side": "BUY",
            "price": 211.6,
            "quantity": 200,
        }

        merged = merge_image_import_results([
            ImageImportResult(trades=[dict(earlier)], skipped=[], engine="easyocr"),
            ImageImportResult(trades=[dict(later)], skipped=[], engine="easyocr"),
        ])

        self.assertEqual(merged.imported_count, 2)
        self.assertEqual(merged.trades[0]["timestamp"], "2026-05-29 10:36:07")
        self.assertEqual(merged.trades[0]["trade_id"], "img-1")
        self.assertEqual(merged.trades[1]["trade_id"], "img-2")

    def test_is_non_stock_product_tolerates_ocr_noise(self):
        self.assertTrue(_is_non_stock_product("R-001"))
        self.assertTrue(_is_non_stock_product("R - 001"))
        self.assertTrue(_is_non_stock_product("R-OO1"))
        self.assertTrue(_is_non_stock_product("R001"))
        self.assertTrue(_is_non_stock_product("GC001"))
        self.assertTrue(_is_non_stock_product("拆出质押购回"))
        self.assertTrue(_is_non_stock_product("质押回购拆出"))
        self.assertFalse(_is_non_stock_product("光迅科技"))
        self.assertFalse(_is_non_stock_product("京东方A"))

    def test_parse_broker_holdings_boxes_reads_wanlian_持仓_page(self):
        # Mirrors the attached 万联证券 持仓 screenshot: two-line rows with
        # 市值 | 盈亏 | 持仓/可用 | 成本/现价 column headers.
        boxes = [
            OCRBox("持仓股", 40, 440, 160, 480, 0.98),
            OCRBox("市值", 60, 540, 180, 580, 0.98),
            OCRBox("盈亏", 360, 540, 460, 580, 0.98),
            OCRBox("持仓/可用", 560, 540, 720, 580, 0.96),
            OCRBox("成本/现价", 800, 540, 960, 580, 0.96),
            # Row 1: 通信ETF (cost=1.605, price=1.663, qty=85000)
            OCRBox("通信ETF", 40, 620, 200, 660, 0.98),
            OCRBox("4,950.10", 320, 620, 460, 660, 0.98),
            OCRBox("85000", 580, 620, 700, 660, 0.99),
            OCRBox("1.605", 820, 620, 940, 660, 1.0),
            OCRBox("141,355.00", 40, 670, 240, 710, 0.98),
            OCRBox("3.630%", 320, 670, 440, 710, 0.97),
            OCRBox("85000", 580, 670, 700, 710, 0.99),
            OCRBox("1.663", 820, 670, 940, 710, 1.0),
            # Row 2: 德明利 (cost=643.743, price=630.500, qty=200)
            OCRBox("德明利", 40, 760, 180, 800, 0.98),
            OCRBox("-2,648.59", 300, 760, 460, 800, 0.96),
            OCRBox("200", 600, 760, 680, 800, 0.99),
            OCRBox("643.743", 800, 760, 960, 800, 1.0),
            OCRBox("126,100.00", 40, 810, 240, 850, 0.98),
            OCRBox("-2.060%", 300, 810, 460, 850, 0.97),
            OCRBox("200", 600, 810, 680, 850, 0.99),
            OCRBox("630.500", 800, 810, 960, 850, 1.0),
            # Row 3: 京东方 A (cost=4.254, price=6.430, qty=3000)
            OCRBox("京东方 A", 40, 1140, 220, 1180, 0.92),
            OCRBox("6,526.70", 320, 1140, 460, 1180, 0.98),
            OCRBox("3000", 580, 1140, 700, 1180, 0.99),
            OCRBox("4.254", 820, 1140, 940, 1180, 1.0),
            OCRBox("19,290.00", 40, 1190, 240, 1230, 0.98),
            OCRBox("51.140%", 320, 1190, 460, 1230, 0.97),
            OCRBox("3000", 580, 1190, 700, 1230, 0.99),
            OCRBox("6.430", 820, 1190, 940, 1230, 1.0),
            # Row 4: 标准券 (should be skipped as non-stock)
            OCRBox("标准券", 40, 1400, 180, 1440, 0.98),
            OCRBox("0.00", 320, 1400, 420, 1440, 0.99),
            OCRBox("0", 620, 1400, 680, 1440, 0.99),
            OCRBox("0.000", 820, 1400, 940, 1440, 1.0),
            OCRBox("0.00", 40, 1450, 180, 1490, 0.98),
            OCRBox("0.000%", 320, 1450, 420, 1490, 0.97),
            OCRBox("0", 620, 1450, 680, 1490, 0.99),
            OCRBox("100.000", 820, 1450, 940, 1490, 1.0),
        ]
        self.assertTrue(_is_holdings_page(boxes))

        result = parse_broker_holdings_boxes(boxes)

        self.assertEqual(len(result.holdings), 3)
        names = [h["name"] for h in result.holdings]
        self.assertIn("通信ETF", names)
        self.assertIn("德明利", names)
        self.assertIn("京东方A", names)
        jdf = next(h for h in result.holdings if h["name"] == "京东方A")
        self.assertEqual(jdf["quantity"], 3000)
        self.assertAlmostEqual(jdf["avg_cost"], 4.254, places=3)
        self.assertAlmostEqual(jdf["market_price"], 6.430, places=3)
        dml = next(h for h in result.holdings if h["name"] == "德明利")
        self.assertEqual(dml["quantity"], 200)
        self.assertAlmostEqual(dml["avg_cost"], 643.743, places=3)
        # 标准券 / 非股票品种 must land in skipped, not holdings.
        self.assertTrue(any("标准券" in s["name"] for s in result.skipped))

    def test_reconcile_holdings_flags_qty_and_missing_diffs(self):
        positions = [
            OpenPosition(code="光迅科技", name="光迅科技", quantity=200, avg_cost=210.0,
                         first_buy_time=datetime(2026, 5, 26), last_buy_time=datetime(2026, 5, 26)),
            OpenPosition(code="德明利", name="德明利", quantity=200, avg_cost=643.743,
                         first_buy_time=datetime(2026, 5, 28), last_buy_time=datetime(2026, 5, 28)),
            OpenPosition(code="云南锗业", name="云南锗业", quantity=100, avg_cost=80.0,
                         first_buy_time=datetime(2026, 5, 1), last_buy_time=datetime(2026, 5, 1)),
        ]
        holdings = [
            {"code": "光迅科技", "name": "光迅科技", "quantity": 300, "avg_cost": 223.625},
            {"code": "德明利", "name": "德明利", "quantity": 200, "avg_cost": 643.743},
            {"code": "京东方A", "name": "京东方A", "quantity": 3000, "avg_cost": 4.254},
        ]

        recon = reconcile_holdings(positions, holdings)

        by_code = {row["code"]: row for row in recon}
        self.assertEqual(by_code["光迅科技"]["status"], "qty_diff")
        self.assertEqual(by_code["光迅科技"]["delta"], 100)
        self.assertEqual(by_code["德明利"]["status"], "match")
        self.assertEqual(by_code["云南锗业"]["status"], "missing_in_actual")
        self.assertEqual(by_code["京东方A"]["status"], "missing_in_computed")

    def test_analyze_trades_auto_fills_exit_conditions_three_tier(self):
        # Tier 3 fallback (-5%/+10%): no signal, no profile.
        trades = [
            TradeRecord(trade_id="1", timestamp=datetime(2026, 5, 6, 10, 0), code="300750",
                        name="宁德时代", side="BUY", price=200.0, quantity=100),
        ]
        result = analyze_trades(trades)
        self.assertAlmostEqual(trades[0].stop_loss, 190.0, places=2)
        self.assertAlmostEqual(trades[0].target_price, 220.0, places=2)
        self.assertIn("退出条件自动补录", trades[0].tags)

        # Tier 1 signal override.
        trades = [
            TradeRecord(trade_id="1", timestamp=datetime(2026, 5, 6, 10, 0), code="300750",
                        name="宁德时代", side="BUY", price=200.0, quantity=100),
        ]
        signals = [StrategySignal(signal_id="s1", timestamp=datetime(2026, 5, 5),
                                  code="300750", action="BUY",
                                  stop_loss=192.0, target_price=235.0)]
        analyze_trades(trades, strategy_signals=signals)
        self.assertEqual(trades[0].stop_loss, 192.0)
        self.assertEqual(trades[0].target_price, 235.0)

        # Tier 2 ATR/volatility band.
        trades = [
            TradeRecord(trade_id="1", timestamp=datetime(2026, 5, 6, 10, 0), code="300750",
                        name="宁德时代", side="BUY", price=200.0, quantity=100),
        ]
        profiles = [StockProfile(code="300750", volatility_pct=4.0)]
        analyze_trades(trades, stock_profiles=profiles)
        # stop = 200 * (1 - 1.5*0.04) = 200 * 0.94 = 188.0
        self.assertAlmostEqual(trades[0].stop_loss, 188.0, places=2)
        # target = 200 * (1 + 3*0.04) = 200 * 1.12 = 224.0
        self.assertAlmostEqual(trades[0].target_price, 224.0, places=2)

    def test_reassessment_flags_improvement_and_remaining_risk_on_new_trades(self):
        # First day: undisciplined trade (no plan, no stop, oversized, emotional).
        # Second day: improved trade (plan, stop, target, calm, small size).
        trades = [
            TradeRecord(trade_id="1", timestamp=datetime(2026, 5, 6, 10, 0), code="300750",
                        name="宁德时代", side="BUY", price=200.0, quantity=400,
                        reason="追高买入", emotion="贪婪", plan="", stop_loss=0.0, target_price=0.0),
            TradeRecord(trade_id="2", timestamp=datetime(2026, 5, 7, 10, 0), code="600519",
                        name="贵州茅台", side="BUY", price=100.0, quantity=50,
                        reason="按计划回踩买入", emotion="平静",
                        plan="回踩95止损，目标120", stop_loss=95.0, target_price=120.0),
        ]
        result = analyze_trades(trades, AnalysisConfig(account_size=100000))
        re = result.reassessment

        self.assertTrue(re["evaluated"])
        self.assertEqual(re["new_trade_count"], 1)
        self.assertEqual(re["new_buy_count"], 1)
        self.assertEqual(re["prior_trade_count"], 1)
        # The new trade carries its own plan/stop/target, so it should score well.
        new_assess = re["new_trade_assessments"][0]
        self.assertEqual(new_assess["code"], "600519")
        self.assertIn("交易计划", new_assess["passed"])
        self.assertIn("止损价", new_assess["passed"])
        # Risk should not be worse than baseline once the disciplined trade is added.
        self.assertLessEqual(re["risk_score"]["current"], re["risk_score"]["baseline"])
        self.assertGreaterEqual(len(re["improvement_points"]), 1)

    def test_reassessment_skips_with_single_active_day(self):
        trades = load_trades(ROOT / "data" / "sample_trades.csv")
        # Force everything onto one notional cohort via explicit future cutoff.
        result = analyze_trades(trades, new_since=datetime(2030, 1, 1))
        self.assertFalse(result.reassessment["evaluated"])

    def test_import_trades_from_image_falls_back_when_deepseek_unconfigured(self):
        image_path = ROOT / "tests" / "_tmp_unused.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"")
        boxes = [
            OCRBox("成交日期", 44, 704, 222, 760, 0.94),
            OCRBox("成交价", 390, 704, 570, 760, 0.94),
            OCRBox("成交量", 704, 704, 846, 760, 0.98),
            OCRBox("成交额", 976, 704, 1114, 760, 0.98),
            OCRBox("江海股份", 43, 1140, 247, 1200, 0.98),
            OCRBox("卖出", 1034, 1140, 1138, 1202, 0.99),
            OCRBox("77.980", 454, 1164, 598, 1214, 1.0),
            OCRBox("一200", 758, 1164, 868, 1212, 0.78),
            OCRBox("15596.000", 922, 1196, 1138, 1244, 0.72),
            OCRBox("卖 20260529 14:55:51", 95, 1199, 357, 1235, 0.84),
        ]
        env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
        try:
            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch("trade_analysis.image_importer._read_ocr_boxes", return_value=(boxes, "easyocr")):
                result = import_trades_from_image(image_path, engine="auto", agent="deepseek")
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(result.imported_count, 1)
        self.assertEqual(result.trades[0]["name"], "江海股份")
        self.assertIn("deepseek-v4-pro-unconfigured", result.engine)


if __name__ == "__main__":
    unittest.main()
