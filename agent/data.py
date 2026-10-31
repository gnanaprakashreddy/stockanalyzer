"""Market data access layer (Yahoo Finance via yfinance) with simple caching."""
import gzip
import json
import os
import threading
import time
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from . import sec

warnings.filterwarnings("ignore")


def market_of(symbol: str) -> str:
    return "IN" if symbol.upper().endswith((".NS", ".BO")) else "US"


@lru_cache(maxsize=None)
def _ticker(symbol: str) -> yf.Ticker:
    return yf.Ticker(symbol)


# ---------------------------------------------------------------- daily snapshot (GitHub Actions)
# A scheduled GitHub job (snapshot.py) saves profiles + statements for the screener universe every morning to the
# repo's `snapshot` branch. Reading that file costs zero Yahoo requests, which avoids cloud rate limits.
SNAPSHOT_URL = os.environ.get("SNAPSHOT_URL",
                              "https://raw.githubusercontent.com/gnanaprakashreddy/stockanalyzer/snapshot/fundamentals.json.gz")
SNAPSHOT_FILE = Path(os.environ["SNAPSHOT_FILE"]) if os.environ.get("SNAPSHOT_FILE") else None  # local override for testing
SNAPSHOT_MAX_AGE = 4 * 86400  # covers weekends/holidays
_SNAP = {"t": 0.0, "d": {}}


def _use_snapshot() -> bool:
    return os.environ.get("PA_NO_SNAPSHOT") != "1"


def snapshot() -> dict:
    """{symbol: {"t": epoch, "info": {...}, "st": {kind: {index, columns, data}}}} - reloaded every 3 hours."""
    if time.time() - _SNAP["t"] > (3 * 3600 if _SNAP["d"] else 300):  # no snapshot yet: look again in 5 min
        raw = None
        try:
            if SNAPSHOT_FILE and SNAPSHOT_FILE.exists():
                raw = SNAPSHOT_FILE.read_bytes()
            elif SNAPSHOT_URL:
                r = requests.get(SNAPSHOT_URL, timeout=20)
                raw = r.content if r.status_code == 200 else None
            if raw:
                _SNAP["d"] = json.loads(gzip.decompress(raw))
        except Exception:
            pass
        _SNAP["t"] = time.time()
    return _SNAP["d"]


def _snap(symbol: str):
    if not _use_snapshot():
        return None
    e = snapshot().get(symbol)
    return e if e and time.time() - e.get("t", 0) < SNAPSHOT_MAX_AGE else None


def df_to_json(df: pd.DataFrame) -> dict:
    df = df.where(pd.notna(df), None)
    return {"index": [str(i) for i in df.index], "columns": [pd.Timestamp(c).strftime("%Y-%m-%d") for c in df.columns],
            "data": df.values.tolist()}


def df_from_json(j: dict) -> pd.DataFrame:
    return pd.DataFrame(j["data"], index=j["index"], columns=pd.to_datetime(j["columns"]), dtype=float)


# ---------------------------------------------------------------- profile (info)
_INFO: dict = {}
_INFO_LOCK = threading.Lock()
GOOD_TTL = 24 * 3600   # full profiles: fundamentals change quarterly, so a day is plenty
SEC_TTL = 3600         # SEC-built profile: retry Yahoo (analyst targets etc.) after an hour
PARTIAL_TTL = 300      # throttled/partial result: retry after 5 minutes


def _info_ok(d) -> bool:
    return isinstance(d, dict) and len(d) > 10 and bool(d.get("longName") or d.get("shortName") or d.get("quoteType"))


def _fast_info(symbol: str) -> dict:
    """Minimal fallback from the (rarely throttled) price endpoint when the full profile is unavailable."""
    try:
        fi = _ticker(symbol).fast_info
        out = {"currency": fi.get("currency"), "marketCap": fi.get("marketCap"), "currentPrice": fi.get("lastPrice"),
               "sharesOutstanding": fi.get("shares"), "_partial": True}
        return {k: v for k, v in out.items() if v is not None}
    except Exception:
        return {"_partial": True}


def _ttl(d: dict) -> int:
    return PARTIAL_TTL if d.get("_partial") else SEC_TTL if d.get("_source") == "SEC EDGAR" else GOOD_TTL


def info_live(symbol: str, retries: bool = True):
    """Yahoo profile with retries/backoff, or None if Yahoo refuses."""
    for wait in ((0, 1.5, 4) if retries else (0,)):
        time.sleep(wait)
        try:
            d = _ticker(symbol).get_info()
        except Exception:
            d = None
        if _info_ok(d):
            return d
    return None


def info(symbol: str, quick: bool = False) -> dict:
    """Profile from: memory cache -> daily snapshot -> live Yahoo -> SEC EDGAR (US) -> basic price data.
    Failures are never cached for long, so a temporary Yahoo block heals itself.
    quick=True (bulk screening): one Yahoo attempt, no fallbacks; returns {} on failure and caches nothing."""
    hit = _INFO.get(symbol)
    if hit and time.time() - hit[0] < _ttl(hit[1]):
        return hit[1]
    e = _snap(symbol)
    d = dict(e["info"]) if e and _info_ok(e.get("info")) else info_live(symbol, retries=not quick)
    if quick:
        if d:
            with _INFO_LOCK:
                _INFO[symbol] = (time.time(), d)
        return d or {}
    if not d and market_of(symbol) == "US":
        fi = _fast_info(symbol)
        try:
            d = sec.info(symbol, fi.get("currentPrice", np.nan)) or None
        except Exception:
            d = None
        if d:
            d.setdefault("currency", fi.get("currency", "USD"))
    if not d:
        d = _fast_info(symbol)
    with _INFO_LOCK:
        _INFO[symbol] = (time.time(), d)
    return d


info.cache_clear = _INFO.clear


# ---------------------------------------------------------------- statements
_ST: dict = {}


def statement_live(symbol: str, kind: str) -> pd.DataFrame:
    for wait in (0, 1.5):
        time.sleep(wait)
        try:
            df = getattr(_ticker(symbol), kind)
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        except Exception:
            pass
    return pd.DataFrame()


def statement(symbol: str, kind: str) -> pd.DataFrame:
    """kind: 'cashflow' | 'financials' | 'balance_sheet' (+ 'quarterly_' variants), newest column first.
    Source order: memory cache -> daily snapshot -> live Yahoo -> SEC EDGAR (US, annual)."""
    hit = _ST.get((symbol, kind))
    if hit and time.time() - hit[0] < (GOOD_TTL if not hit[1].empty else PARTIAL_TTL):
        return hit[1]
    e = _snap(symbol)
    df = df_from_json(e["st"][kind]) if e and kind in e.get("st", {}) else statement_live(symbol, kind)
    if df.empty and market_of(symbol) == "US" and not kind.startswith("quarterly_"):
        df = sec.statement(symbol, kind)
    _ST[(symbol, kind)] = (time.time(), df)
    return df


statement.cache_clear = _ST.clear


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
