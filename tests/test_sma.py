"""
Tests for src/signals/sma.py.

Trend tests use real price series with predictable SMA relationships:
- Rising prices  → SMA20 > SMA50 (recent avg > longer avg) → "bullish_trend"
- Falling prices → SMA20 < SMA50                           → "bearish_trend"
- Flat prices    → SMA20 == SMA50                          → "neutral"

Crossover tests patch pandas_ta.sma to inject exact yesterday/today values
that force a cross without needing to engineer fragile price series.
"""

import pytest
import pandas as pd
from unittest.mock import patch
from src.signals.sma import compute_sma_signal


def _make_close(prices: list[float]) -> pd.DataFrame:
    idx = pd.date_range(end="2026-04-10", periods=len(prices), freq="B")
    return pd.DataFrame({"Close": prices}, index=idx)


def _rising(n: int = 60) -> pd.DataFrame:
    return _make_close([100.0 + i for i in range(n)])


def _falling(n: int = 60) -> pd.DataFrame:
    return _make_close([100.0 + (n - 1 - i) for i in range(n)])


def _flat(n: int = 60) -> pd.DataFrame:
    return _make_close([100.0] * n)


def _mock_sma_series(values: list[float]) -> pd.Series:
    """Return a Series with the given values as its last elements (no NaNs)."""
    idx = pd.date_range(end="2026-04-10", periods=len(values), freq="B")
    return pd.Series(values, index=idx)


# ---------------------------------------------------------------------------
# Return shape
# ---------------------------------------------------------------------------

def test_returns_required_keys():
    result = compute_sma_signal(_rising())
    assert {"sma20", "sma50", "signal"} <= result.keys()


def test_sma_values_are_floats():
    result = compute_sma_signal(_rising())
    assert isinstance(result["sma20"], float)
    assert isinstance(result["sma50"], float)


# ---------------------------------------------------------------------------
# Signal labels using known price series
# ---------------------------------------------------------------------------

def test_bullish_trend_on_rising_prices():
    # Rising series: SMA20 (recent avg) > SMA50 (longer avg)
    result = compute_sma_signal(_rising())
    assert result["signal"] == "bullish_trend"
    assert result["sma20"] > result["sma50"]


def test_bearish_trend_on_falling_prices():
    # Falling series: SMA20 (recent avg) < SMA50 (longer avg)
    result = compute_sma_signal(_falling())
    assert result["signal"] == "bearish_trend"
    assert result["sma20"] < result["sma50"]


def test_neutral_on_flat_prices():
    result = compute_sma_signal(_flat())
    assert result["signal"] == "neutral"
    assert result["sma20"] == pytest.approx(result["sma50"])


# ---------------------------------------------------------------------------
# Crossover detection (patched pandas_ta.sma for exact control)
# ---------------------------------------------------------------------------

def test_bullish_cross_when_sma20_crosses_above_sma50():
    # yesterday: sma20 (99) < sma50 (100) → today: sma20 (101) > sma50 (100)
    sma20_series = _mock_sma_series([95.0, 97.0, 98.0, 99.0, 101.0])
    sma50_series = _mock_sma_series([100.0, 100.0, 100.0, 100.0, 100.0])

    with patch("src.signals.sma.ta.sma", side_effect=[sma20_series, sma50_series]):
        result = compute_sma_signal(_flat())

    assert result["signal"] == "bullish_cross"


def test_bearish_cross_when_sma20_crosses_below_sma50():
    # yesterday: sma20 (101) > sma50 (100) → today: sma20 (99) < sma50 (100)
    sma20_series = _mock_sma_series([105.0, 104.0, 103.0, 101.0, 99.0])
    sma50_series = _mock_sma_series([100.0, 100.0, 100.0, 100.0, 100.0])

    with patch("src.signals.sma.ta.sma", side_effect=[sma20_series, sma50_series]):
        result = compute_sma_signal(_flat())

    assert result["signal"] == "bearish_cross"


def test_bullish_trend_when_sma20_above_sma50_no_cross():
    # Both days: sma20 > sma50 — no crossover, just a trend
    sma20_series = _mock_sma_series([102.0, 103.0, 104.0, 105.0, 106.0])
    sma50_series = _mock_sma_series([100.0, 100.0, 100.0, 100.0, 100.0])

    with patch("src.signals.sma.ta.sma", side_effect=[sma20_series, sma50_series]):
        result = compute_sma_signal(_flat())

    assert result["signal"] == "bullish_trend"


def test_bearish_trend_when_sma20_below_sma50_no_cross():
    sma20_series = _mock_sma_series([94.0, 93.0, 92.0, 91.0, 90.0])
    sma50_series = _mock_sma_series([100.0, 100.0, 100.0, 100.0, 100.0])

    with patch("src.signals.sma.ta.sma", side_effect=[sma20_series, sma50_series]):
        result = compute_sma_signal(_flat())

    assert result["signal"] == "bearish_trend"


# ---------------------------------------------------------------------------
# Edge cases / error handling
# ---------------------------------------------------------------------------

def test_raises_on_empty_dataframe():
    with pytest.raises(ValueError):
        compute_sma_signal(pd.DataFrame())


def test_raises_on_missing_close_column():
    idx = pd.date_range(end="2026-04-10", periods=60, freq="B")
    df = pd.DataFrame({"Open": [100.0] * 60}, index=idx)
    with pytest.raises(ValueError):
        compute_sma_signal(df)
