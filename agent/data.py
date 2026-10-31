"""Market data access layer (Yahoo Finance via yfinance) with simple caching."""
import warnings
from functools import lru_cache

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")


def market_of(symbol: str) -> str:
    return "IN" if symbol.upper().endswith((".NS", ".BO")) else "US"


@lru_cache(maxsize=None)
def _ticker(symbol: str) -> yf.Ticker:
    return yf.Ticker(symbol)


@lru_cache(maxsize=None)
def info(symbol: str) -> dict:
    try:
        return _ticker(symbol).info or {}
    except Exception:
        return {}


@lru_cache(maxsize=None)
def statement(symbol: str, kind: str) -> pd.DataFrame:
    """kind: 'cashflow' | 'financials' | 'balance_sheet' (annual, newest column first)."""
    try:
        df = getattr(_ticker(symbol), kind)
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def row(df: pd.DataFrame, *names) -> pd.Series:
    """First matching statement row with NaNs dropped (newest first)."""
    for n in names:
        if not df.empty and n in df.index:
            s = pd.to_numeric(df.loc[n], errors="coerce").dropna()
            if len(s):
                return s
    return pd.Series(dtype=float)


def first(df: pd.DataFrame, *names, idx: int = 0):
    s = row(df, *names)
    return float(s.iloc[idx]) if len(s) > idx else np.nan


def prices(symbols, period: str = "2y") -> pd.DataFrame:
    symbols = list(dict.fromkeys(symbols))
    if not symbols:
        return pd.DataFrame()
    df = yf.download(symbols, period=period, auto_adjust=True, progress=False, threads=True)
    if df is None or df.empty:
        return pd.DataFrame()
    close = df["Close"] if "Close" in df.columns.get_level_values(0) else df
    if isinstance(close, pd.Series):
        close = close.to_frame(symbols[0])
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    # Not forward-filled: each column keeps only its own exchange's trading days.
    return close.groupby(level=0).last()


def fx_series(from_ccy: str, to_ccy: str, index: pd.DatetimeIndex) -> pd.Series:
    """Daily FX rate series converting from_ccy -> to_ccy, aligned to index."""
    if from_ccy == to_ccy:
        return pd.Series(1.0, index=index)
    px = prices([f"{from_ccy}{to_ccy}=X"])
    if px.empty:
        raise RuntimeError(f"Could not load FX rate {from_ccy}->{to_ccy}")
    s = px.iloc[:, 0]
    return s.reindex(s.index.union(index)).ffill().bfill().reindex(index)


@lru_cache(maxsize=None)
def fx_rate(from_ccy: str, to_ccy: str) -> float:
    if not from_ccy or not to_ccy or from_ccy == to_ccy:
        return 1.0
    px = prices([f"{from_ccy}{to_ccy}=X"], period="5d")
    s = px.iloc[:, 0].dropna() if not px.empty else px
    return float(s.iloc[-1]) if len(s) else 1.0


def price_now(inf: dict) -> float:
    for k in ("currentPrice", "regularMarketPrice", "previousClose"):
        v = inf.get(k)
        if v:
            return float(v)
    return np.nan
