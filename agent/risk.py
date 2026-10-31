"""Risk metrics, technical indicators and mean-variance portfolio optimisation."""
import numpy as np
import pandas as pd

TRADING_DAYS = 252


# ---------------------------------------------------------------- Risk
def max_drawdown(series: pd.Series) -> float:
    s = series.dropna()
    return float((s / s.cummax() - 1).min()) if len(s) else np.nan


def risk_metrics(rets: pd.Series, rf: float, bench: pd.Series | None = None) -> dict:
    r = rets.dropna()
    if len(r) < 30:
        return {}
    ann_ret = (1 + r).prod() ** (TRADING_DAYS / len(r)) - 1
    vol = r.std() * np.sqrt(TRADING_DAYS)
    downside = r[r < 0].std() * np.sqrt(TRADING_DAYS)
    var95 = -np.percentile(r, 5)
    cvar95 = -r[r <= np.percentile(r, 5)].mean()
    out = {
        "ann_return": ann_ret,
        "volatility": vol,
        "sharpe": (ann_ret - rf) / vol if vol else np.nan,
        "sortino": (ann_ret - rf) / downside if downside else np.nan,
        "max_drawdown": max_drawdown((1 + r).cumprod()),
        "var95_1d": var95,
        "cvar95_1d": cvar95,
        "beta": np.nan,
    }
    if bench is not None:
        j = pd.concat([r, bench], axis=1, join="inner").dropna()
        if len(j) > 30 and j.iloc[:, 1].var() > 0:
            out["beta"] = j.cov().iloc[0, 1] / j.iloc[:, 1].var()
    return out


# ---------------------------------------------------------------- Technicals
def rsi(close: pd.Series, n: int = 14) -> float:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return float((100 - 100 / (1 + rs)).iloc[-1])


def technicals(close: pd.Series) -> dict:
    c = close.dropna()
    if len(c) < 60:
        return {}
    last = c.iloc[-1]
    sma50, sma200 = c.rolling(50).mean().iloc[-1], c.rolling(200).mean().iloc[-1] if len(c) >= 200 else np.nan
    ema12, ema26 = c.ewm(span=12).mean(), c.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    yr = c.iloc[-252:]
    ret = lambda d: last / c.iloc[-1 - d] - 1 if len(c) > d else np.nan
    if np.isfinite(sma200):
        trend = "Uptrend" if last > sma200 and sma50 > sma200 else "Downtrend" if last < sma200 and sma50 < sma200 else "Sideways"
    else:
        trend = "Uptrend" if last > sma50 else "Downtrend"
    return {
        "price": last,
        "chg_1d": ret(1),
        "ret_1m": ret(21), "ret_3m": ret(63), "ret_6m": ret(126), "ret_12m": ret(252),
        "sma50": sma50, "sma200": sma200,
        "rsi14": rsi(c),
        "macd_bullish": bool(macd.iloc[-1] > signal.iloc[-1]),
        "from_52w_high": last / yr.max() - 1,
        "from_52w_low": last / yr.min() - 1,
        "trend": trend,
    }


# ---------------------------------------------------------------- Optimisation
def optimise(rets: pd.DataFrame, exp_ret: pd.Series, rf: float, max_w: float, sims: int, seed: int = 42) -> dict:
    """Monte-Carlo efficient frontier with per-asset weight cap. Returns max-Sharpe and min-variance weights."""
    cols = list(rets.columns)
    n = len(cols)
    if n < 2:
        return {}
    cov = rets.cov().values * TRADING_DAYS
    mu = exp_ret.reindex(cols).fillna(rf).values
    rng = np.random.default_rng(seed)
    cap = max(max_w, 1.0 / n + 1e-9)
    w = rng.dirichlet(np.ones(n), sims * 3)
    w = w[(w <= cap).all(axis=1)][:sims]
    if len(w) == 0:
        w = np.full((1, n), 1.0 / n)
    port_ret = w @ mu
    port_vol = np.sqrt(np.einsum("ij,jk,ik->i", w, cov, w))
    sharpe = (port_ret - rf) / port_vol
    i_s, i_v = int(np.nanargmax(sharpe)), int(np.nanargmin(port_vol))
    return {
        "max_sharpe": pd.Series(w[i_s], index=cols),
        "min_variance": pd.Series(w[i_v], index=cols),
        "max_sharpe_stats": (port_ret[i_s], port_vol[i_s], sharpe[i_s]),
        "min_variance_stats": (port_ret[i_v], port_vol[i_v], sharpe[i_v]),
    }


def portfolio_stats(w: np.ndarray, mu: np.ndarray, cov: np.ndarray, rf: float) -> tuple:
    r = float(w @ mu)
    v = float(np.sqrt(w @ cov @ w))
    return r, v, (r - rf) / v if v else np.nan


def risk_contribution(rets: pd.DataFrame, weights: pd.Series) -> pd.Series:
    cov = rets.cov() * TRADING_DAYS
    w = weights.reindex(cov.columns).fillna(0)
    port_var = float(w @ cov @ w)
    return (w * (cov @ w)) / port_var if port_var else w * np.nan
