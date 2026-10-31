"""Single-stock analysis shared by the daily report and the web app."""
import numpy as np
import pandas as pd

from . import data, risk, valuation


def rate_parts(upside, tech, f_score, f_n, z) -> list:
    """Scoring components behind the rating as (factor, points, reason)."""
    parts = []
    if np.isfinite(upside):
        pts = 2 if upside > 0.25 else 1 if upside > 0.10 else -2 if upside < -0.25 else -1 if upside < -0.10 else 0
        label = "undervalued" if upside > 0.1 else "overvalued" if upside < -0.1 else "fairly valued"
        parts.append(("Valuation", pts, f"{label} ({upside:+.1%} to blended fair value)"))
    if tech:
        parts.append(("Trend", {"Uptrend": 1, "Downtrend": -1}.get(tech["trend"], 0), f"{tech['trend'].lower()}, RSI {tech['rsi14']:.0f}"))
        if tech["rsi14"] > 75:
            parts.append(("RSI", -0.5, "overbought - avoid chasing"))
        elif tech["rsi14"] < 30:
            parts.append(("RSI", 0.5, "oversold - potential entry"))
    if f_n >= 6:
        if f_score / f_n >= 0.75:
            parts.append(("Fundamentals", 1, f"strong fundamentals (Piotroski {f_score}/{f_n})"))
        elif f_score / f_n <= 0.35:
            parts.append(("Fundamentals", -1, f"weak fundamentals (Piotroski {f_score}/{f_n})"))
    if np.isfinite(z) and z < 1.81:
        parts.append(("Distress risk", -1, f"Altman Z {z:.2f} in distress zone"))
    return parts


def rating_of(s: float) -> str:
    return "Strong Buy" if s >= 3 else "Buy / Accumulate" if s >= 1.5 else "Hold" if s >= -1 else "Reduce" if s > -2.5 else "Sell"


def rate(upside, tech, f_score, f_n, z):
    parts = rate_parts(upside, tech, f_score, f_n, z)
    s = float(sum(p for _, p, _ in parts))
    return rating_of(s), s, "; ".join(r for _, _, r in parts)


def analyse(symbol: str, cfg: dict, sector_medians: dict, close: pd.Series, bench_close: pd.Series) -> dict:
    """Run every model for one stock. `close`/`bench_close` are daily price series (local currency)."""
    _n = valuation._num
    inf = data.info(symbol)
    mkt_key = data.market_of(symbol)
    mkt = cfg["markets"][mkt_key]
    close = close.dropna()
    tech = risk.technicals(close)
    rm = risk.risk_metrics(close.pct_change(), mkt["risk_free_rate"], bench_close.dropna().pct_change())
    beta = rm.get("beta", np.nan)
    beta = beta if np.isfinite(beta) else _n(inf.get("beta"))

    d = valuation.dcf(symbol, inf, mkt, cfg["dcf"], beta)
    dd = valuation.ddm(inf, mkt, beta)
    rel = valuation.relative_value(inf, sector_medians, mkt_key)
    models = {"dcf": d["value"], "ddm": dd["value"], "relative": rel["value"],
              "graham": valuation.graham_number(inf), "analyst_target": _n(inf.get("targetMeanPrice"))}
    used = valuation.applicable_models(models, inf)
    fair = valuation.blended_fair_value(used, cfg["valuation_weights"])
    price = tech.get("price", data.price_now(inf))
    upside = fair / price - 1 if np.isfinite(fair) else np.nan
    fs, fn = valuation.piotroski(symbol)
    z = valuation.altman_z(symbol, inf)
    rating, score, why = rate(upside, tech, fs, fn, z)
    return dict(
        symbol=symbol, name=inf.get("shortName", symbol), sector=inf.get("sector", "Other"), market=mkt_key,
        ccy=inf.get("currency") or ("INR" if mkt_key == "IN" else "USD"), price=price,
        chg_1d=tech.get("chg_1d", np.nan), fair=fair, upside=upside, rating=rating, score=score, why=why,
        beta=beta, capm=valuation.cost_of_equity(beta, mkt), f_score=fs, f_n=fn, z=z,
        **{f"m_{k}": v for k, v in models.items()},
        dcf=d, ddm=dd, rel=rel, dcf_note=d["note"], models_used=", ".join(used),
        dcf_range=valuation.dcf_sensitivity(d, inf), ddm_note=dd["note"], rel_note=rel["note"],
        roe=_n(inf.get("returnOnEquity")), margin=_n(inf.get("profitMargins")), de=_n(inf.get("debtToEquity")),
        rev_g=_n(inf.get("revenueGrowth")), pe=_n(inf.get("trailingPE")), fpe=_n(inf.get("forwardPE")),
        pb=_n(inf.get("priceToBook")), ev_ebitda=_n(inf.get("enterpriseToEbitda")),
        div_yield=_n(inf.get("dividendYield")), reco=inf.get("recommendationKey", ""),
        **{f"t_{k}": v for k, v in tech.items()}, **{f"r_{k}": v for k, v in rm.items()},
    )


def read_holdings(path_or_buffer) -> pd.DataFrame:
    """Parse a holdings CSV (symbol,quantity,avg_cost[,broker]) into one row per symbol."""
    df = pd.read_csv(path_or_buffer, comment="#", skip_blank_lines=True)
    df.columns = [c.strip().lower() for c in df.columns]
    missing = {"symbol", "quantity", "avg_cost"} - set(df.columns)
    if missing:
        raise ValueError(f"Holdings CSV is missing column(s): {', '.join(sorted(missing))}")
    df = df.dropna(subset=["symbol"])
    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["avg_cost"] = pd.to_numeric(df["avg_cost"], errors="coerce")
    df["broker"] = df["broker"].fillna("").astype(str).str.strip() if "broker" in df.columns else ""
    df = df[df["quantity"] > 0]
    return df.groupby("symbol").apply(
        lambda g: pd.Series({"quantity": g["quantity"].sum(),
                             "avg_cost": (g["quantity"] * g["avg_cost"]).sum() / g["quantity"].sum(),
                             "broker": ", ".join(sorted({b for b in g["broker"] if b})) or "-"}),
        include_groups=False)
