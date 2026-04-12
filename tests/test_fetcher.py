import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from src.data.fetcher import fetch_ticker, fetch_watchlist, validate_dataframe


# --- validate_dataframe ---

def make_df(rows=60):
    idx = pd.date_range(end="2026-04-10", periods=rows, freq="B")
    return pd.DataFrame({"Close": [100.0 + i for i in range(rows)]}, index=idx)


def test_validate_dataframe_passes_valid():
    df = make_df(60)
    assert validate_dataframe(df, "NVDA") is True


def test_validate_dataframe_fails_too_few_rows():
    df = make_df(10)
    assert validate_dataframe(df, "NVDA") is False


def test_validate_dataframe_fails_empty():
    df = pd.DataFrame()
    assert validate_dataframe(df, "NVDA") is False


def test_validate_dataframe_fails_nan_close():
    df = make_df(60)
    df.iloc[-1, df.columns.get_loc("Close")] = float("nan")
    assert validate_dataframe(df, "NVDA") is False


def test_validate_dataframe_fails_missing_close_column():
    idx = pd.date_range(end="2026-04-10", periods=60, freq="B")
    df = pd.DataFrame({"Open": [100.0] * 60}, index=idx)
    assert validate_dataframe(df, "NVDA") is False


# --- fetch_ticker ---

def test_fetch_ticker_returns_dataframe():
    mock_df = make_df(60)
    with patch("src.data.fetcher.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.return_value = mock_df
        result = fetch_ticker("NVDA")
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 60


def test_fetch_ticker_retries_on_empty_then_succeeds():
    empty_df = pd.DataFrame()
    good_df = make_df(60)
    history_mock = MagicMock(side_effect=[empty_df, empty_df, good_df])
    with patch("src.data.fetcher.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history = history_mock
        result = fetch_ticker("AMZN")
    assert len(result) == 60
    assert history_mock.call_count == 3


def test_fetch_ticker_raises_after_max_retries():
    empty_df = pd.DataFrame()
    with patch("src.data.fetcher.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.return_value = empty_df
        with pytest.raises(RuntimeError, match="GOOGL"):
            fetch_ticker("GOOGL")


# --- fetch_watchlist ---

def test_fetch_watchlist_returns_dict_keyed_by_ticker():
    mock_df = make_df(60)
    with patch("src.data.fetcher.fetch_ticker", return_value=mock_df):
        result = fetch_watchlist(["NVDA", "AMZN", "GOOGL"])
    assert set(result.keys()) == {"NVDA", "AMZN", "GOOGL"}
    assert all(isinstance(v, pd.DataFrame) for v in result.values())


def test_fetch_watchlist_default_tickers():
    mock_df = make_df(60)
    with patch("src.data.fetcher.fetch_ticker", return_value=mock_df):
        result = fetch_watchlist()
    assert set(result.keys()) == {"NVDA", "AMZN", "GOOGL"}


def test_fetch_watchlist_is_immutable_dict():
    """Returned mapping should not be mutated by callers — values are DataFrames with copy semantics."""
    mock_df = make_df(60)
    with patch("src.data.fetcher.fetch_ticker", return_value=mock_df):
        result = fetch_watchlist(["NVDA"])
    # Replacing a key in the returned dict does not affect re-fetching
    result["NVDA"] = pd.DataFrame()
    with patch("src.data.fetcher.fetch_ticker", return_value=mock_df) as mock_fetch:
        fresh = fetch_watchlist(["NVDA"])
    assert len(fresh["NVDA"]) == 60
