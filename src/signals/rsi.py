"""
RSI signal computation.

compute_rsi_signal is a pure function: given a DataFrame with a Close column,
it returns an immutable dict with the last 3 RSI values, the current RSI, and
a signal label.
"""

import pandas as pd
import pandas_ta as ta

_RSI_PERIOD = 14
_RSI_OVERSOLD = 30
_RSI_OVERBOUGHT = 70
_TREND_WINDOW = 3


def compute_rsi_signal(df: pd.DataFrame) -> dict[str, object]:
    """
    Compute RSI(14) signal from a DataFrame with a Close column.

    Returns a dict with:
        "values"  : list[float]  — last 3 RSI readings (oldest → newest)
        "current" : float        — most recent RSI value
        "signal"  : str          — "oversold" | "overbought" | "neutral"

    Raises ValueError on invalid input.
    """
    if df is None or df.empty or "Close" not in df.columns:
        raise ValueError("DataFrame must be non-empty and contain a 'Close' column")

    rsi_series = ta.rsi(df["Close"], length=_RSI_PERIOD)
    recent = rsi_series.dropna().iloc[-_TREND_WINDOW:]
    values = [float(v) for v in recent]
    current = values[-1]

    if current < _RSI_OVERSOLD:
        signal = "oversold"
    elif current > _RSI_OVERBOUGHT:
        signal = "overbought"
    else:
        signal = "neutral"

    return {"values": values, "current": current, "signal": signal}
