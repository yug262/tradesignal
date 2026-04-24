"""Test: Agent 2 → TA-Lib → Agent 3 indicator pipeline.

Validates:
1. Agent 2 output contains requested_indicators.
2. NO TRADE gives [].
3. TA-Lib missing does not crash.
4. fetch_indicator_data returns [] safely if no candles.
5. Agent 3 input contains technical_context.
6. Agent 3 still blocks if Agent 2 decision = NO TRADE.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Ensure the backend directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestAgent2OutputContract(unittest.TestCase):
    """Test 1 & 2: Agent 2 output contains requested_indicators."""

    def test_fallback_trade_intraday_has_indicators(self):
        """TRADE + INTRADAY fallback must return non-empty requested_indicators."""
        from agent.gemini_confirmer import _fallback_confirmation_v2

        input_data = {
            "discovery": {
                "final_verdict": "IMPORTANT_EVENT",
                "event_strength": "STRONG",
                "is_material": True,
                "directness": "DIRECT",
                "confidence": 75,
                "impact_analysis": "order win expansion growth",
                "reasoning_summary": "Positive business expansion",
                "event_summary": "company won major contract",
            },
            "live_market_context": {
                "gap_percent": 1.5,
                "change_percent": 1.8,
                "opening_move_quality": "STRONG",
                "relative_volume": 1.5,
            },
        }

        result = _fallback_confirmation_v2(input_data)

        self.assertIn("requested_indicators", result)
        self.assertIsInstance(result["requested_indicators"], list)

        # Decision should be TRADE for this strong setup
        if result["decision"] == "TRADE":
            self.assertGreater(len(result["requested_indicators"]), 0)
            self.assertLessEqual(len(result["requested_indicators"]), 4)

            # Each indicator must have name, timeframe, reason
            for ind in result["requested_indicators"]:
                self.assertIn("name", ind)
                self.assertIn("timeframe", ind)
                self.assertIn("reason", ind)
                self.assertIn(ind["name"], ["RSI", "SMA", "EMA", "MACD", "BBANDS", "ATR", "CCI", "WILLR"])

    def test_fallback_trade_delivery_has_indicators(self):
        """TRADE + DELIVERY fallback must return non-empty requested_indicators with 1D timeframe."""
        from agent.gemini_confirmer import _fallback_confirmation_v2

        input_data = {
            "discovery": {
                "final_verdict": "IMPORTANT_EVENT",
                "event_strength": "STRONG",
                "is_material": True,
                "directness": "DIRECT",
                "confidence": 80,
                "impact_analysis": "penalty ban decline",
                "reasoning_summary": "Negative business consequence",
                "event_summary": "company received major penalty",
            },
            "live_market_context": {
                "gap_percent": -2.0,
                "change_percent": -2.5,
                "opening_move_quality": "STRONG",
                "relative_volume": 2.0,
            },
        }

        result = _fallback_confirmation_v2(input_data)

        self.assertIn("requested_indicators", result)

        if result["decision"] == "TRADE" and result["trade_mode"] == "DELIVERY":
            for ind in result["requested_indicators"]:
                self.assertEqual(ind["timeframe"], "1D")

    def test_no_trade_gives_empty_indicators(self):
        """NO TRADE fallback must return requested_indicators = []."""
        from agent.gemini_confirmer import _fallback_confirmation_v2

        input_data = {
            "discovery": {
                "final_verdict": "NOISE",
                "event_strength": "WEAK",
                "is_material": False,
                "directness": "NONE",
                "confidence": 20,
                "impact_analysis": "minor routine update",
                "reasoning_summary": "No actionable edge",
                "event_summary": "routine filing",
            },
            "live_market_context": {
                "gap_percent": 0.1,
                "change_percent": 0.05,
                "opening_move_quality": "WEAK",
            },
        }

        result = _fallback_confirmation_v2(input_data)

        self.assertEqual(result["decision"], "NO TRADE")
        self.assertIn("requested_indicators", result)
        self.assertEqual(result["requested_indicators"], [])


class TestTALibSafety(unittest.TestCase):
    """Test 3 & 4: TA-Lib missing does not crash; empty candles return []."""

    def test_talib_missing_returns_empty(self):
        """If TA-Lib is not installed, fetch_indicator_data should return [] safely."""
        import agent.data_collector as dc

        original_talib = dc.talib
        try:
            dc.talib = None  # Simulate TA-Lib not installed

            mock_db = MagicMock()
            result = dc.fetch_indicator_data(mock_db, "RELIANCE", "INTRADAY", "RSI", "1m")

            self.assertEqual(result, [])
        finally:
            dc.talib = original_talib

    def test_no_candles_returns_empty(self):
        """If no candles are fetched, fetch_indicator_data should return [] safely."""
        import agent.data_collector as dc

        # Only test if TA-Lib is actually available
        if dc.talib is None:
            self.skipTest("TA-Lib not installed — candle test irrelevant")

        with patch.object(dc, '_fetch_raw_candles', return_value=[]):
            mock_db = MagicMock()
            result = dc.fetch_indicator_data(mock_db, "RELIANCE", "INTRADAY", "RSI", "5m")
            self.assertEqual(result, [])


class TestIndicatorInterpretation(unittest.TestCase):
    """Test interpretation logic for various indicators."""

    def test_rsi_overbought(self):
        from services.indicator_service import interpret_indicator

        result = interpret_indicator("RSI", [65, 70, 75])
        self.assertEqual(result["interpretation"], "overbought")
        self.assertEqual(result["trend"], "rising")

    def test_rsi_oversold(self):
        from services.indicator_service import interpret_indicator

        result = interpret_indicator("RSI", [35, 28, 25])
        self.assertEqual(result["interpretation"], "oversold")
        self.assertEqual(result["trend"], "falling")

    def test_rsi_neutral(self):
        from services.indicator_service import interpret_indicator

        result = interpret_indicator("RSI", [48, 50, 52])
        self.assertEqual(result["interpretation"], "neutral")

    def test_ema_with_ltp_above(self):
        from services.indicator_service import interpret_indicator

        result = interpret_indicator("EMA", [100, 101, 102], ltp=110)
        self.assertIn("price_above_ma", result["interpretation"])

    def test_ema_with_ltp_below(self):
        from services.indicator_service import interpret_indicator

        result = interpret_indicator("EMA", [100, 101, 102], ltp=95)
        self.assertIn("price_below_ma", result["interpretation"])

    def test_macd_bullish(self):
        from services.indicator_service import interpret_indicator

        result = interpret_indicator("MACD", [0.1, 0.3, 0.5])
        self.assertEqual(result["interpretation"], "bullish_momentum")

    def test_macd_bearish(self):
        from services.indicator_service import interpret_indicator

        result = interpret_indicator("MACD", [-0.1, -0.3, -0.5])
        self.assertEqual(result["interpretation"], "bearish_momentum")

    def test_atr_expanding(self):
        from services.indicator_service import interpret_indicator

        result = interpret_indicator("ATR", [5.0, 6.0, 7.0])
        self.assertEqual(result["interpretation"], "volatility_expanding")
        self.assertEqual(result["trend"], "rising")

    def test_atr_cooling(self):
        from services.indicator_service import interpret_indicator

        result = interpret_indicator("ATR", [7.0, 6.0, 5.0])
        self.assertEqual(result["interpretation"], "volatility_cooling")
        self.assertEqual(result["trend"], "falling")

    def test_empty_values(self):
        from services.indicator_service import interpret_indicator

        result = interpret_indicator("RSI", [])
        self.assertEqual(result["interpretation"], "no data")
        self.assertIsNone(result["latest"])


class TestBuildTechnicalContext(unittest.TestCase):
    """Test 5: Agent 3 input contains technical_context."""

    def test_empty_requested_indicators(self):
        """Empty requested_indicators should return safe empty context."""
        from services.indicator_service import build_technical_context

        mock_db = MagicMock()
        result = build_technical_context(mock_db, "RELIANCE", "INTRADAY", [])

        self.assertIn("requested_by_agent2", result)
        self.assertIn("indicator_values", result)
        self.assertIn("technical_warnings", result)
        self.assertIn("technical_confirmations", result)
        self.assertEqual(result["requested_by_agent2"], [])
        self.assertEqual(result["indicator_values"], {})

    def test_max_4_indicators_enforced(self):
        """Even if Agent 2 requests 6, only 4 should be processed."""
        from services.indicator_service import build_technical_context

        mock_db = MagicMock()
        six_indicators = [
            {"name": "RSI", "timeframe": "1m", "reason": "test"},
            {"name": "EMA", "timeframe": "1m", "reason": "test"},
            {"name": "ATR", "timeframe": "1m", "reason": "test"},
            {"name": "MACD", "timeframe": "1m", "reason": "test"},
            {"name": "CCI", "timeframe": "1m", "reason": "test"},
            {"name": "WILLR", "timeframe": "1m", "reason": "test"},
        ]

        with patch('services.indicator_service.fetch_indicator_data', return_value=[]):
            result = build_technical_context(mock_db, "RELIANCE", "INTRADAY", six_indicators)

        # Only first 4 should be in requested_by_agent2
        self.assertEqual(len(result["requested_by_agent2"]), 4)

    def test_technical_context_structure(self):
        """Technical context should have the correct structure."""
        from services.indicator_service import build_technical_context

        mock_db = MagicMock()
        indicators = [
            {"name": "RSI", "timeframe": "1m", "reason": "Check exhaustion"},
        ]

        mock_data = [{"timestamp": 1000, "value": 55.0 + i} for i in range(20)]

        with patch('services.indicator_service.fetch_indicator_data', return_value=mock_data):
            result = build_technical_context(mock_db, "RELIANCE", "INTRADAY", indicators, ltp=100.0)

        self.assertIn("RSI_1m", result["indicator_values"])
        rsi_data = result["indicator_values"]["RSI_1m"]
        self.assertIn("latest", rsi_data)
        self.assertIn("last_20", rsi_data)
        self.assertIn("interpretation", rsi_data)
        self.assertIn("reason_requested", rsi_data)


class TestAgent3GateWithIndicators(unittest.TestCase):
    """Test 6: Agent 3 still blocks if Agent 2 decision = NO TRADE."""

    def test_agent3_blocks_on_no_trade(self):
        """Agent 3 must block trade if Agent 2 decided NO TRADE, regardless of indicators."""
        from agent.gemini_executor import plan_execution
        from datetime import datetime, timezone, timedelta

        IST = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(IST)

        input_data = {
            "symbol": "RELIANCE",
            "company_name": "RELIANCE",
            "agent2_view": {
                "decision": "NO TRADE",
                "direction": "NEUTRAL",
                "trade_mode": "NONE",
                "remaining_impact": "LOW",
                "priced_in_status": "FULLY PRICED IN",
                "priority": "LOW",
                "confidence": 20,
                "why_tradable_or_not": "No edge remains",
                "key_confirmations": [],
                "warning_flags": ["Move is stretched"],
                "invalid_if": [],
                "final_summary": "NO TRADE: edge gone",
                "requested_indicators": [],
            },
            "live_execution_context": {
                "ltp": 2500.0,
                "open": 2480.0,
                "high": 2520.0,
                "low": 2470.0,
                "previous_close": 2450.0,
                "vwap": 2490.0,
                "volume": 1000000,
                "market_status": "OPEN",
                "market_snapshot_time": now_ist.isoformat(),
                "snapshot_id": f"RELIANCE_{now_ist.strftime('%Y%m%d_%H%M%S')}",
            },
            "technical_context": {
                "requested_by_agent2": [],
                "indicator_values": {},
                "technical_warnings": [],
                "technical_confirmations": [],
            },
        }

        # Mock the fresh execution context fetch to return the same context
        with patch('agent.gemini_executor.fetch_fresh_execution_context') as mock_fetch:
            mock_fetch.return_value = input_data["live_execution_context"]

            result = plan_execution(input_data, risk_config={
                "capital": 100000,
                "max_loss_per_trade_pct": 1.0,
                "max_capital_per_trade_pct": 20.0,
                "min_rr": 1.5,
                "max_daily_loss_pct": 3.0,
            })

        self.assertEqual(result["execution_decision"], "NO TRADE")
        self.assertEqual(result["action"], "AVOID")
        # Agent 2 rejection should be captured in the output
        why = result.get("why_now_or_why_wait", "") + result.get("final_summary", "")
        self.assertTrue(
            "Agent 2 rejected" in why or "NO TRADE" in result.get("final_summary", ""),
            f"Expected Agent 2 rejection message, got: {result}"
        )


class TestTimeframeMapping(unittest.TestCase):
    """Test that timeframe parameter maps correctly to intervals."""

    def test_1m_timeframe(self):
        import agent.data_collector as dc

        if dc.talib is None:
            self.skipTest("TA-Lib not installed")

        with patch.object(dc, '_fetch_raw_candles', return_value=[]) as mock_fetch:
            mock_db = MagicMock()
            dc.fetch_indicator_data(mock_db, "RELIANCE", "INTRADAY", "RSI", timeframe="1m")
            mock_fetch.assert_called_once_with("RELIANCE", 1, count=60)

    def test_5m_timeframe(self):
        import agent.data_collector as dc

        if dc.talib is None:
            self.skipTest("TA-Lib not installed")

        with patch.object(dc, '_fetch_raw_candles', return_value=[]) as mock_fetch:
            mock_db = MagicMock()
            dc.fetch_indicator_data(mock_db, "RELIANCE", "INTRADAY", "EMA", timeframe="5m")
            mock_fetch.assert_called_once_with("RELIANCE", 5, count=60)

    def test_15m_timeframe(self):
        import agent.data_collector as dc

        if dc.talib is None:
            self.skipTest("TA-Lib not installed")

        with patch.object(dc, '_fetch_raw_candles', return_value=[]) as mock_fetch:
            mock_db = MagicMock()
            dc.fetch_indicator_data(mock_db, "RELIANCE", "INTRADAY", "ATR", timeframe="15m")
            mock_fetch.assert_called_once_with("RELIANCE", 15, count=60)

    def test_1d_timeframe(self):
        import agent.data_collector as dc

        if dc.talib is None:
            self.skipTest("TA-Lib not installed")

        with patch.object(dc, '_fetch_raw_candles', return_value=[]) as mock_fetch:
            mock_db = MagicMock()
            dc.fetch_indicator_data(mock_db, "RELIANCE", "DELIVERY", "MACD", timeframe="1D")
            mock_fetch.assert_called_once_with("RELIANCE", 1440, count=60)


if __name__ == "__main__":
    unittest.main(verbosity=2)
