"""
Stock data fetching via yfinance.

All functions are pure/functional — no mutation of shared state.
fetch_watchlist returns a plain dict (str -> DataFrame); callers treat it as immutable.
"""

import time
import logging
import yfinance as yf
import pandas as pd
from typing import Sequence

logger = logging.getLogger(__name__)

_DEFAULT_WATCHLIST: tuple[str, ...] = ("NVDA", "AMZN", "GOOGL")
_HISTORY_PERIOD = "60d"
_HISTORY_INTERVAL = "1d"
_MIN_ROWS = 50
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 1.0  # seconds


def validate_dataframe(df: pd.DataFrame, ticker: str) -> bool:
    """Return True if df has sufficient rows and a clean Close column."""
    if df is None or df.empty:
        logger.warning("Empty DataFrame for %s", ticker)
        return False
    if "Close" not in df.columns:
        logger.warning("Missing Close column for %s", ticker)
        return False
    if len(df) < _MIN_ROWS:
        logger.warning("Too few rows (%d) for %s, need %d", len(df), ticker, _MIN_ROWS)
        return False
    if df["Close"].isna().any():
        logger.warning("NaN values in Close column for %s", ticker)
        return False
    return True


def fetch_ticker(ticker: str) -> pd.DataFrame:
    """
    Fetch daily OHLCV history for a single ticker.

    Retries up to _MAX_RETRIES times with exponential backoff on empty results.
    Raises RuntimeError if all attempts fail validation.
    """
    for attempt in range(_MAX_RETRIES):
        df = yf.Ticker(ticker).history(period=_HISTORY_PERIOD, interval=_HISTORY_INTERVAL)
        if validate_dataframe(df, ticker):
            return df
        if attempt < _MAX_RETRIES - 1:
            wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
            logger.warning("Retry %d/%d for %s in %.1fs", attempt + 1, _MAX_RETRIES, ticker, wait)
            time.sleep(wait)

    raise RuntimeError(
        f"Failed to fetch valid data for {ticker} after {_MAX_RETRIES} attempts"
    )


def fetch_watchlist(tickers: Sequence[str] = _DEFAULT_WATCHLIST) -> dict[str, pd.DataFrame]:
    """
    Fetch data for all tickers in the watchlist.

    Returns a plain dict mapping ticker symbol -> DataFrame.
    Callers should treat the returned dict as immutable.
    """
    return {ticker: fetch_ticker(ticker) for ticker in tickers}
