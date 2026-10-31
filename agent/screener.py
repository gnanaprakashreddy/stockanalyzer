"""Multi-factor screener to surface new high-growth-potential ideas (Growth / Quality / Value / Momentum)."""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from . import data

FIELDS = ["shortName", "sector", "currency", "marketCap", "revenueGrowth", "earningsGrowth", "returnOnEquity",
          "profitMargins", "debtToEquity", "forwardPE", "trailingPE", "priceToBook", "pegRatio", "trailingPegRatio",
          "enterpriseToEbitda", "targetMeanPrice", "recommendationKey", "currentPrice", "regularMarketPrice"]


def fetch_infos(symbols, workers: int = 4) -> pd.DataFrame:
    symbols = list(dict.fromkeys(symbols))
    with ThreadPoolExecutor(workers) as ex:
        infos = list(ex.map(data.info, symbols))
    rows = []
    for s, inf in zip(symbols, infos):
        if not inf or inf.get("_partial"):
            continue
        r = {k: inf.get(k) for k in FIELDS}
        r["symbol"], r["market"] = s, data.market_of(s)
        rows.append(r)
    df = pd.DataFrame(rows).set_index("symbol") if rows else pd.DataFrame()
    for c in df.columns:
        if c not in ("shortName", "sector", "currency", "recommendationKey", "market"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if not df.empty:
        df["price"] = df["currentPrice"].fillna(df["regularMarketPrice"])
        df["peg"] = df["pegRatio"].fillna(df["trailingPegRatio"])
        df["analyst_upside"] = df["targetMeanPrice"] / df["price"] - 1
    return df


def sector_medians(df: pd.DataFrame) -> dict:
    out = {}
    if df.empty:
        return out
    for (mkt, sec), g in df.groupby(["market", "sector"]):
        out[(mkt, sec)] = {
            "forwardPE": g["forwardPE"].where((g["forwardPE"] > 0) & (g["forwardPE"] < 150)).median(),
            "priceToBook": g["priceToBook"].where(g["priceToBook"] > 0).median(),
        }
    return out


def _rank(s: pd.Series, ascending=True) -> pd.Series:
    return s.rank(pct=True, ascending=ascending).fillna(0.5)


def score(df: pd.DataFrame, px: pd.DataFrame, weights: dict) -> pd.DataFrame:
    d = df.copy()
    px = px.ffill()
    ret6 = px.iloc[-1] / px.iloc[-min(126, len(px))] - 1 if len(px) else pd.Series(dtype=float)
    ret12 = px.iloc[-1] / px.iloc[0] - 1 if len(px) else pd.Series(dtype=float)
    above200 = (px.iloc[-1] > px.rolling(200, min_periods=150).mean().iloc[-1]) if len(px) else pd.Series(dtype=bool)
    d["ret_6m"], d["ret_12m"] = ret6.reindex(d.index), ret12.reindex(d.index)
    d["above_200dma"] = above200.reindex(d.index)

    out = []
    for _, g in d.groupby("market"):
        g = g.copy()
        g["s_growth"] = (_rank(g["revenueGrowth"]) + _rank(g["earningsGrowth"])) / 2
        g["s_quality"] = (_rank(g["returnOnEquity"]) + _rank(g["profitMargins"]) + _rank(g["debtToEquity"], ascending=False)) / 3
        peg = g["peg"].where(g["peg"] > 0)
        fpe = g["forwardPE"].where(g["forwardPE"] > 0)
        g["s_value"] = (_rank(peg, ascending=False) + _rank(fpe, ascending=False) + _rank(g["analyst_upside"])) / 3
        g["s_momentum"] = (_rank(g["ret_6m"]) + _rank(g["ret_12m"]) + g["above_200dma"].astype(float).fillna(0.5)) / 3
        g["score"] = 100 * (weights["growth"] * g["s_growth"] + weights["quality"] * g["s_quality"]
                            + weights["valuation"] * g["s_value"] + weights["momentum"] * g["s_momentum"])
        out.append(g)
    return pd.concat(out).sort_values("score", ascending=False) if out else d


def thesis(r: pd.Series) -> str:
    pts = []
    if pd.notna(r.get("revenueGrowth")) and r["revenueGrowth"] > 0.15:
        pts.append(f"revenue +{r['revenueGrowth']:.0%} YoY")
    if pd.notna(r.get("earningsGrowth")) and r["earningsGrowth"] > 0.15:
        pts.append(f"earnings +{r['earningsGrowth']:.0%}")
    if pd.notna(r.get("returnOnEquity")) and r["returnOnEquity"] > 0.18:
        pts.append(f"high ROE {r['returnOnEquity']:.0%}")
    if pd.notna(r.get("profitMargins")) and r["profitMargins"] > 0.2:
        pts.append(f"net margin {r['profitMargins']:.0%}")
    if pd.notna(r.get("peg")) and 0 < r["peg"] < 1.5:
        pts.append(f"reasonable PEG {r['peg']:.1f}")
    if pd.notna(r.get("analyst_upside")) and r["analyst_upside"] > 0.1:
        pts.append(f"consensus target +{r['analyst_upside']:.0%}")
    if r.get("above_200dma") is True or r.get("above_200dma") == 1.0:
        pts.append("price above 200-DMA")
    risks = []
    if pd.notna(r.get("forwardPE")) and r["forwardPE"] > 60:
        risks.append(f"rich valuation (fwd P/E {r['forwardPE']:.0f})")
    if pd.notna(r.get("debtToEquity")) and r["debtToEquity"] > 150:
        risks.append("high leverage")
    txt = "; ".join(pts) if pts else "balanced factor profile"
    return txt + (f". Watch: {', '.join(risks)}" if risks else "")
