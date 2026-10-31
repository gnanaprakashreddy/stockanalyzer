"""Fundamental valuation models used by the analyst agent.

All per-share values are returned in the stock's *trading* currency.
"""
import math

import numpy as np

from . import data

FINANCIAL_SECTORS = {"Financial Services", "Financial"}


def _num(v):
    try:
        v = float(v)
        return v if math.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _pick(*vals):
    for v in vals:
        v = _num(v)
        if np.isfinite(v):
            return v
    return np.nan


def _fin_to_trade_fx(inf: dict) -> float:
    """Factor to convert reporting-currency amounts into trading currency (handles ADRs)."""
    return data.fx_rate(inf.get("financialCurrency") or inf.get("currency"), inf.get("currency"))


# ---------------------------------------------------------------- CAPM / WACC
def cost_of_equity(beta: float, mkt: dict) -> float:
    beta = beta if np.isfinite(beta) else 1.0
    beta = min(max(beta, 0.5), 2.5)
    return mkt["risk_free_rate"] + beta * mkt["equity_risk_premium"]


def wacc(symbol: str, inf: dict, mkt: dict, beta: float) -> dict:
    ke = cost_of_equity(beta, mkt)
    mcap = _num(inf.get("marketCap"))
    debt = _pick(inf.get("totalDebt"), 0.0)
    debt = 0.0 if not np.isfinite(debt) else debt
    fin = data.statement(symbol, "financials")
    interest = abs(data.first(fin, "Interest Expense", "Interest Expense Non Operating"))
    tax = data.first(fin, "Tax Rate For Calcs")
    tax = tax if np.isfinite(tax) and 0 <= tax <= 0.5 else mkt["tax_rate"]
    kd = interest / debt if debt > 0 and np.isfinite(interest) else mkt["risk_free_rate"] + 0.02
    kd = min(max(kd, mkt["risk_free_rate"]), 0.18)
    debt_trade = debt * _fin_to_trade_fx(inf) if debt else 0.0
    if not np.isfinite(mcap) or mcap <= 0:
        we, wd = 1.0, 0.0
    else:
        we, wd = mcap / (mcap + debt_trade), debt_trade / (mcap + debt_trade)
    w = we * ke + wd * kd * (1 - tax)
    return {"wacc": w, "cost_of_equity": ke, "cost_of_debt": kd, "tax": tax, "equity_weight": we}


# ---------------------------------------------------------------- DCF
def dcf_from_inputs(base_fcf, g0, r, gt, years, hi, cash, debt, shares, fx=1.0) -> dict:
    """Core two-stage DCF maths: growth g0 for `hi` years, fading linearly to gt by `years`."""
    pv, fcf, proj = 0.0, base_fcf, []
    for t in range(1, years + 1):
        g = g0 if t <= hi else g0 - (g0 - gt) * (t - hi) / max(years - hi, 1)
        fcf *= 1 + g
        disc = fcf / (1 + r) ** t
        pv += disc
        proj.append({"Year": t, "Growth": g, "FCF": fcf, "PV of FCF": disc})
    tv = fcf * (1 + gt) / (r - gt) if r > gt else np.nan
    pv_tv = tv / (1 + r) ** years
    ev = pv + pv_tv
    equity = ev + cash - debt
    return {"value": equity / shares * fx, "ev": ev, "pv_fcf": pv, "pv_tv": pv_tv, "equity": equity, "projections": proj}


def dcf(symbol: str, inf: dict, mkt: dict, cfg: dict, beta: float) -> dict:
    """Two-stage free-cash-flow-to-firm DCF. High growth fades linearly to terminal growth."""
    out = {"value": np.nan, "note": ""}
    if inf.get("sector") in FINANCIAL_SECTORS:
        out["note"] = "DCF skipped for financials (use DDM / P/B)"
        return out
    cf = data.statement(symbol, "cashflow")
    fcf_hist = data.row(cf, "Free Cash Flow")
    if fcf_hist.empty:
        ocf, capex = data.row(cf, "Operating Cash Flow"), data.row(cf, "Capital Expenditure")
        if not ocf.empty and not capex.empty:
            fcf_hist = (ocf + capex).dropna()
    if fcf_hist.empty:
        out["note"] = "No free cash flow data"
        return out
    recent = fcf_hist.iloc[:3]
    base = float(recent.mean()) if len(recent) > 1 else float(recent.iloc[0])
    base = max(base, float(fcf_hist.iloc[0])) if fcf_hist.iloc[0] > 0 else base
    if base <= 0:
        out["note"] = "Negative free cash flow - DCF not meaningful"
        return out

    candidates = [_num(inf.get("earningsGrowth")), _num(inf.get("revenueGrowth"))]
    if len(fcf_hist) >= 3 and fcf_hist.iloc[-1] > 0:
        n = len(fcf_hist) - 1
        candidates.append((fcf_hist.iloc[0] / fcf_hist.iloc[-1]) ** (1 / n) - 1)
    candidates = [c for c in candidates if np.isfinite(c)]
    g0 = float(np.median(candidates)) if candidates else mkt["terminal_growth"]
    g0 = min(max(g0, cfg["min_initial_growth"]), cfg["max_initial_growth"])

    w = wacc(symbol, inf, mkt, beta)
    r = max(w["wacc"], mkt["terminal_growth"] + 0.02)
    gt = mkt["terminal_growth"]
    cash = _pick(inf.get("totalCash"), 0.0)
    debt = _pick(inf.get("totalDebt"), 0.0)
    shares = _pick(inf.get("sharesOutstanding"), inf.get("impliedSharesOutstanding"))
    if not np.isfinite(shares) or shares <= 0:
        out["note"] = "Shares outstanding unavailable"
        return out
    res = dcf_from_inputs(base, g0, r, gt, cfg["projection_years"], cfg["high_growth_years"], cash, debt, shares, _fin_to_trade_fx(inf))
    pv_tv, ev = res["pv_tv"], res["ev"]
    out.update(
        value=res["value"], wacc=r, growth=g0, terminal_growth=gt, base_fcf=base,
        cash=cash, debt=debt, shares=shares, fx=_fin_to_trade_fx(inf), projections=res["projections"], wacc_detail=w,
        years=cfg["projection_years"], high_years=cfg["high_growth_years"],
        tv_share=pv_tv / ev if ev else np.nan,
        note=f"WACC {r:.1%}, g {g0:.1%}->{gt:.1%}, TV {pv_tv / ev:.0%} of EV",
    )
    return out


def dcf_sensitivity(dcf_out: dict, inf: dict = None) -> str:
    """Fair value range for WACC +1% / -1%."""
    if not np.isfinite(dcf_out.get("value", np.nan)):
        return ""
    o = dcf_out
    v = lambda r: dcf_from_inputs(o["base_fcf"], o["growth"], r, o["terminal_growth"], o["years"], o["high_years"],
                                  o["cash"], o["debt"], o["shares"], o["fx"])["value"]
    return f"{v(o['wacc'] + 0.01):,.0f} - {v(max(o['wacc'] - 0.01, o['terminal_growth'] + 0.005)):,.0f}"


# ---------------------------------------------------------------- DDM
def ddm(inf: dict, mkt: dict, beta: float) -> dict:
    """Gordon growth dividend discount model."""
    d0 = _pick(inf.get("dividendRate"), inf.get("trailingAnnualDividendRate"))
    if not np.isfinite(d0) or d0 <= 0:
        return {"value": np.nan, "note": "No dividend"}
    ke = cost_of_equity(beta, mkt)
    roe, payout = _num(inf.get("returnOnEquity")), _num(inf.get("payoutRatio"))
    g = roe * (1 - payout) if np.isfinite(roe) and np.isfinite(payout) and 0 <= payout <= 1 else mkt["terminal_growth"]
    g = min(max(g, 0.0), ke - 0.02, mkt["terminal_growth"] + 0.03)
    return {"value": d0 * (1 + g) / (ke - g), "note": f"ke {ke:.1%}, g {g:.1%}"}


# ---------------------------------------------------------------- Graham / Relative
def graham_number(inf: dict) -> float:
    eps, bvps = _num(inf.get("trailingEps")), _num(inf.get("bookValue"))
    if np.isfinite(eps) and np.isfinite(bvps) and eps > 0 and bvps > 0:
        return math.sqrt(22.5 * eps * bvps)
    return np.nan


def relative_value(inf: dict, sector_medians: dict, market: str) -> dict:
    """Fair value from same-market sector-median multiples (P/E on EPS, P/B on book value)."""
    med = sector_medians.get((market, inf.get("sector")), {})
    vals, notes = [], []
    eps = _pick(inf.get("forwardEps"), inf.get("trailingEps"))
    if np.isfinite(eps) and eps > 0 and np.isfinite(med.get("forwardPE", np.nan)):
        vals.append(eps * med["forwardPE"])
        notes.append(f"sector fwd P/E {med['forwardPE']:.1f}")
    bv = _num(inf.get("bookValue"))
    if inf.get("sector") in FINANCIAL_SECTORS and np.isfinite(bv) and bv > 0 and np.isfinite(med.get("priceToBook", np.nan)):
        vals.append(bv * med["priceToBook"])
        notes.append(f"sector P/B {med['priceToBook']:.1f}")
    return {"value": float(np.mean(vals)) if vals else np.nan, "note": ", ".join(notes)}


# ---------------------------------------------------------------- Quality scores
def piotroski_detail(symbol: str) -> list:
    """Piotroski F-score tests as (name, passed or None if data missing)."""
    fin, bs, cf = (data.statement(symbol, k) for k in ("financials", "balance_sheet", "cashflow"))
    f = lambda df, n, i=0: data.first(df, *n, idx=i)
    ni0, ni1 = f(fin, ["Net Income"]), f(fin, ["Net Income"], 1)
    ta0, ta1 = f(bs, ["Total Assets"]), f(bs, ["Total Assets"], 1)
    cfo = f(cf, ["Operating Cash Flow"])
    ltd0, ltd1 = f(bs, ["Long Term Debt"]), f(bs, ["Long Term Debt"], 1)
    ca0, ca1 = f(bs, ["Current Assets"]), f(bs, ["Current Assets"], 1)
    cl0, cl1 = f(bs, ["Current Liabilities"]), f(bs, ["Current Liabilities"], 1)
    sh0, sh1 = f(bs, ["Ordinary Shares Number", "Share Issued"]), f(bs, ["Ordinary Shares Number", "Share Issued"], 1)
    gp0, gp1 = f(fin, ["Gross Profit"]), f(fin, ["Gross Profit"], 1)
    rv0, rv1 = f(fin, ["Total Revenue"]), f(fin, ["Total Revenue"], 1)
    tests = [
        (ni0 > 0, [ni0]),
        (ni0 / ta0 > 0, [ni0, ta0]),
        (cfo > 0, [cfo]),
        (cfo > ni0, [cfo, ni0]),
        ((ltd0 / ta0) <= (ltd1 / ta1), [ltd0, ta0, ltd1, ta1]),
        ((ca0 / cl0) > (ca1 / cl1), [ca0, cl0, ca1, cl1]),
        (sh0 <= sh1, [sh0, sh1]),
        ((gp0 / rv0) > (gp1 / rv1), [gp0, rv0, gp1, rv1]),
        ((rv0 / ta0) > (rv1 / ta1), [rv0, ta0, rv1, ta1]),
    ]
    names = ['Positive net income', 'Positive return on assets', 'Positive operating cash flow', 'Cash flow > net income (earnings quality)', 'Lower long-term debt / assets', 'Higher current ratio', 'No new shares issued', 'Higher gross margin', 'Higher asset turnover']
    return [(n, bool(ok) if all(np.isfinite(v) for v in vals) else None) for n, (ok, vals) in zip(names, tests)]


def piotroski(symbol: str) -> tuple:
    """Piotroski F-score. Returns (score, criteria_evaluated)."""
    valid = [ok for _, ok in piotroski_detail(symbol) if ok is not None]
    return sum(valid), len(valid)


def altman_z(symbol: str, inf: dict) -> float:
    if inf.get("sector") in FINANCIAL_SECTORS:
        return np.nan
    fin, bs = data.statement(symbol, "financials"), data.statement(symbol, "balance_sheet")
    ta = data.first(bs, "Total Assets")
    tl = data.first(bs, "Total Liabilities Net Minority Interest")
    wc = data.first(bs, "Working Capital")
    re = data.first(bs, "Retained Earnings")
    ebit = data.first(fin, "EBIT", "Operating Income")
    sales = data.first(fin, "Total Revenue")
    mcap = _num(inf.get("marketCap")) / _fin_to_trade_fx(inf)
    if not all(np.isfinite(v) for v in (ta, tl, wc, ebit, sales, mcap)) or ta <= 0 or tl <= 0:
        return np.nan
    re = re if np.isfinite(re) else 0.0
    return 1.2 * wc / ta + 1.4 * re / ta + 3.3 * ebit / ta + 0.6 * mcap / tl + 1.0 * sales / ta


# ---------------------------------------------------------------- Blend
def applicable_models(models: dict, inf: dict) -> dict:
    """Keep only models that suit the business, as an analyst would:
    DDM only for meaningful dividend payers, Graham only for value-style (P/E <= 25) companies."""
    use = dict(models)
    payout, pe = _num(inf.get("payoutRatio")), _num(inf.get("trailingPE"))
    if not (np.isfinite(payout) and payout >= 0.4):
        use.pop("ddm", None)
    if not (np.isfinite(pe) and 0 < pe <= 25):
        use.pop("graham", None)
    return {k: v for k, v in use.items() if np.isfinite(v) and v > 0}


def blended_fair_value(models: dict, weights: dict) -> float:
    num = den = 0.0
    for k, w in weights.items():
        v = models.get(k, np.nan)
        if np.isfinite(v) and v > 0:
            num += w * v
            den += w
    return num / den if den else np.nan
