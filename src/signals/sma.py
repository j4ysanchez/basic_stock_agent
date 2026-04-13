"""
SMA crossover signal computation.

compute_sma_signal is a pure function: given a DataFrame with a Close column,
it returns an immutable dict with SMA20, SMA50, and a crossover/trend label.
"""

import pandas as pd
import pandas_ta as ta

_SMA_FAST = 20
_SMA_SLOW = 50


def compute_sma_signal(df: pd.DataFrame) -> dict[str, object]:
    """
    Compute SMA(20/50) crossover signal from a DataFrame with a Close column.

    Returns a dict with:
        "sma20"  : float — current fast SMA value
        "sma50"  : float — current slow SMA value
        "signal" : str   — "bullish_cross" | "bearish_cross" |
                           "bullish_trend" | "bearish_trend" | "neutral"

    Crossover is detected by comparing today's vs yesterday's relative
    positions of SMA20 and SMA50.

    Raises ValueError on invalid input.
    """
    if df is None or df.empty or "Close" not in df.columns:
        raise ValueError("DataFrame must be non-empty and contain a 'Close' column")

    close = df["Close"]
    sma20 = ta.sma(close, length=_SMA_FAST).dropna()
    sma50 = ta.sma(close, length=_SMA_SLOW).dropna()

    if len(sma20) < 2 or len(sma50) < 2:
        raise ValueError("Insufficient data to compute SMA signals")

    today_fast, yday_fast = float(sma20.iloc[-1]), float(sma20.iloc[-2])
    today_slow, yday_slow = float(sma50.iloc[-1]), float(sma50.iloc[-2])

    if yday_fast <= yday_slow and today_fast > today_slow:
        signal = "bullish_cross"
    elif yday_fast >= yday_slow and today_fast < today_slow:
        signal = "bearish_cross"
    elif today_fast > today_slow:
        signal = "bullish_trend"
    elif today_fast < today_slow:
        signal = "bearish_trend"
    else:
        signal = "neutral"

    return {"sma20": today_fast, "sma50": today_slow, "signal": signal}
