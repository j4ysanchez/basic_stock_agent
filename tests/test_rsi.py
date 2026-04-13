"""
Tests for src/signals/rsi.py.

Price series are constructed so the RSI outcome is deterministic:
- Monotonically rising prices  → all gains, no losses → RSI = 100 → "overbought"
- Monotonically falling prices → all losses, no gains → RSI = 0   → "oversold"
- Alternating ±1 prices        → equal gains/losses   → RSI ≈ 50  → "neutral"
"""

import pytest
import pandas as pd
from src.signals.rsi import compute_rsi_signal


def _make_close(prices: list[float]) -> pd.DataFrame:
    idx = pd.date_range(end="2026-04-10", periods=len(prices), freq="B")
    return pd.DataFrame({"Close": prices}, index=idx)


def _rising(n: int = 60) -> pd.DataFrame:
    return _make_close([100.0 + i for i in range(n)])


def _falling(n: int = 60) -> pd.DataFrame:
    return _make_close([100.0 + (n - 1 - i) for i in range(n)])


def _alternating(n: int = 60) -> pd.DataFrame:
    prices = [100.0 + (i % 2) for i in range(n)]
    return _make_close(prices)


# ---------------------------------------------------------------------------
# Return shape
# ---------------------------------------------------------------------------

def test_returns_required_keys():
    result = compute_rsi_signal(_rising())
    assert {"values", "current", "signal"} <= result.keys()


def test_values_contains_three_floats():
    result = compute_rsi_signal(_rising())
    assert len(result["values"]) == 3
    assert all(isinstance(v, float) for v in result["values"])


def test_current_is_last_element_of_values():
    result = compute_rsi_signal(_rising())
    assert result["current"] == result["values"][-1]


# ---------------------------------------------------------------------------
# Signal labels using known price series
# ---------------------------------------------------------------------------

def test_overbought_on_rising_prices():
    result = compute_rsi_signal(_rising())
    assert result["signal"] == "overbought"
    assert result["current"] > 70


def test_oversold_on_falling_prices():
    result = compute_rsi_signal(_falling())
    assert result["signal"] == "oversold"
    assert result["current"] < 30


def test_neutral_on_alternating_prices():
    result = compute_rsi_signal(_alternating())
    assert result["signal"] == "neutral"
    assert 30 <= result["current"] <= 70


# ---------------------------------------------------------------------------
# Edge cases / error handling
# ---------------------------------------------------------------------------

def test_raises_on_empty_dataframe():
    with pytest.raises(ValueError):
        compute_rsi_signal(pd.DataFrame())


def test_raises_on_missing_close_column():
    idx = pd.date_range(end="2026-04-10", periods=60, freq="B")
    df = pd.DataFrame({"Open": [100.0] * 60}, index=idx)
    with pytest.raises(ValueError):
        compute_rsi_signal(df)
