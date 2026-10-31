"""Step-by-step, number-by-number explanation of how every figure in the Stock Analysis page is calculated."""
import math

import numpy as np
import pandas as pd

from . import financials, stock, valuation

_n = valuation._num


def _ok(v) -> bool:
    try:
        return v is not None and math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _p(v, signed=False):
    return (f"{v:+.1%}" if signed else f"{v:.1%}") if _ok(v) else "n/a"


def _x(v, d=2):
    return f"{v:,.{d}f}" if _ok(v) else "n/a"


def _sym(ccy):
    return {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(ccy, (ccy or "") + " ")


class _Fmt:
    """Formats statement amounts (reporting currency, Cr / M) and per-share amounts (trading currency)."""

    def __init__(self, fccy, ccy):
        self.div, self.lab = financials.unit(fccy)
        self.fs, self.ts = _sym(fccy), _sym(ccy)
        self.u = self.lab.split()[-1]

    def amt(self, v):
        return f"{self.fs}{v / self.div:,.0f} {self.u}" if _ok(v) else "n/a"

    def ps(self, v, d=2):
        return f"{self.ts}{v:,.{d}f}" if _ok(v) else "n/a"


def _get(df, row, i=0):
    if df is None or df.empty or row not in df.index or len(df.columns) <= i:
        return np.nan
    return _n(df.loc[row].iloc[i])


def _md(*lines):
    return ("md", "\n".join(lines))


# ------------------------------------------------------------------ 1. statements
def _statements(stt, f: _Fmt, inf):
    inc, bal, cf = stt["income"], stt["balance"], stt["cashflow"]
    out = []
    if not inc.empty:
        y0 = inc.columns[0]
        y1 = inc.columns[1] if len(inc.columns) > 1 else None
        g = lambda r, i=0: _get(inc, r, i)
        rev, rev1 = g("Revenue"), g("Revenue", 1)
        gp, ebitda, ebit, intr, ni, eps = (g("Gross profit"), g("EBITDA"), g("Operating profit (EBIT)"),
                                           abs(g("Interest expense")), g("Net profit"), g("EPS (diluted)"))
        steps = [f"Latest year: **{y0}**" + (f", compared with **{y1}**." if y1 else ".")]
        if _ok(rev):
            steps.append(f"1. **Revenue {f.amt(rev)}**" + (f" - grew **{_p(rev / rev1 - 1, True)}** from {f.amt(rev1)}. "
                         "Top-line growth is the starting point: without it, profits can only grow by cutting costs." if _ok(rev1) else "."))
        if _ok(gp) and _ok(rev):
            steps.append(f"2. **Gross profit {f.amt(gp)}** → gross margin = {f.amt(gp)} ÷ {f.amt(rev)} = **{_p(gp / rev)}**. "
                         "Of every 100 of sales, this much is left after direct costs - a measure of pricing power.")
        if _ok(ebitda) and _ok(rev):
            steps.append(f"3. **EBITDA {f.amt(ebitda)}** → EBITDA margin **{_p(ebitda / rev)}**. Operating profit before "
                         "depreciation - used in EV/EBITDA comparisons.")
        if _ok(ebit) and _ok(rev):
            steps.append(f"4. **Operating profit (EBIT) {f.amt(ebit)}** → operating margin = {f.amt(ebit)} ÷ {f.amt(rev)} = "
                         f"**{_p(ebit / rev)}**. Profit from the core business after all operating costs.")
        if _ok(ebit) and _ok(intr) and intr > 0:
            steps.append(f"5. **Interest {f.amt(intr)}** → interest coverage = EBIT ÷ interest = **{_x(ebit / intr, 1)}x** "
                         f"({'very comfortable' if ebit / intr > 10 else 'comfortable' if ebit / intr > 5 else 'watch closely' if ebit / intr > 2 else 'dangerous'}).")
        if _ok(ni) and _ok(rev):
            ni1 = g("Net profit", 1)
            steps.append(f"6. **Net profit {f.amt(ni)}** → net margin **{_p(ni / rev)}**"
                         + (f"; profit growth **{_p(ni / ni1 - 1, True)}**" if _ok(ni1) and ni1 > 0 else "") + ". This belongs to shareholders.")
        if _ok(eps):
            steps.append(f"7. **EPS {f.fs}{eps:,.2f}** = net profit ÷ shares. The 'E' in the P/E ratio.")
        if _ok(rev) and _ok(rev1) and _ok(ni) and _ok(g("Net profit", 1)) and g("Net profit", 1) > 0:
            rg, pg = rev / rev1 - 1, ni / g("Net profit", 1) - 1
            steps.append("")
            steps.append(f"**Analyst's read:** profit grew {'faster' if pg > rg else 'slower'} than revenue "
                         f"({_p(pg, True)} vs {_p(rg, True)}), so margins {'expanded (operating leverage or cost control)' if pg > rg else 'contracted (costs rising faster than sales)'}.")
        tbl = financials.scaled(inc.iloc[:, :2], inf.get("financialCurrency") or inf.get("currency") or "INR").copy() if y1 else None
        blocks = [_md(*steps)]
        if tbl is not None:
            tbl["Change"] = (inc.iloc[:, 0] / inc.iloc[:, 1] - 1).map(lambda v: _p(v, True))
            for c in tbl.columns[:2]:
                tbl[c] = tbl[c].map(lambda v: _x(v, 2))
            blocks.append(("table", tbl))
        out.append({"title": f"Income statement - line by line ({f.lab})", "blocks": blocks})

    if not bal.empty:
        b = lambda r, i=0: _get(bal, r, i)
        ta, tl, eq, debt, cash, ca, cl = (b("Total assets"), b("Total liabilities"), b("Shareholders' equity"), b("Total debt"),
                                          b("Cash & equivalents"), b("Current assets"), b("Current liabilities"))
        steps = [f"Snapshot date: **{bal.columns[0]}**."]
        if _ok(ta) and _ok(tl) and _ok(eq):
            mi = ta - tl - eq
            steps.append(f"1. **Assets {f.amt(ta)} = Liabilities {f.amt(tl)} + Equity {f.amt(eq)}**"
                         + (f" (+ {f.amt(mi)} minority interest - the share of subsidiaries owned by others)." if abs(mi) > 0.005 * ta else ".")
                         + " The balance sheet always balances.")
        if _ok(cash) or _ok(debt):
            nd = (debt if _ok(debt) else 0) - (cash if _ok(cash) else 0)
            steps.append(f"2. **Debt {f.amt(debt)}**, **cash {f.amt(cash)}** → net debt = debt - cash = **{f.amt(nd)}** "
                         + ("(**net cash** - the company could repay all debt today)." if nd < 0 else "."))
        if _ok(debt) and _ok(eq) and eq > 0:
            de = debt / eq
            steps.append(f"3. **Debt / Equity** = {f.amt(debt)} ÷ {f.amt(eq)} = **{de:.2f}** "
                         f"({'conservative' if de < 0.5 else 'moderate' if de < 1.5 else 'aggressive'}"
                         f"{'; normal for banks, whose business is lending' if inf.get('sector') in valuation.FINANCIAL_SECTORS else ''}).")
        if _ok(ca) and _ok(cl) and cl > 0:
            steps.append(f"4. **Current ratio** = current assets {f.amt(ca)} ÷ current liabilities {f.amt(cl)} = **{ca / cl:.2f}** "
                         f"({'comfortable' if ca / cl >= 1.5 else 'adequate' if ca / cl >= 1 else 'tight - check if negative working capital is part of the model'}).")
        sh = _n(inf.get("sharesOutstanding"))
        if _ok(eq) and _ok(sh) and sh > 0:
            fx = valuation._fin_to_trade_fx(inf)
            steps.append(f"5. **Book value per share** = equity ÷ shares = {f.amt(eq)} ÷ {sh:,.0f} = **{f.ps(eq / sh * fx)}**. "
                         "Used for P/B and the Graham number.")
        out.append({"title": "Balance sheet - what it owns and owes", "blocks": [_md(*steps)]})

    if not cf.empty:
        c = lambda r, i=0: _get(cf, r, i)
        ocf, capex, fcf, div, bb = c("Operating cash flow"), c("Capital expenditure"), c("Free cash flow"), c("Dividends paid"), c("Share buybacks")
        ni, rev = _get(inc, "Net profit"), _get(inc, "Revenue")
        steps = [f"Year: **{cf.columns[0]}**."]
        if _ok(ocf):
            steps.append(f"1. **Operating cash flow {f.amt(ocf)}**"
                         + (f" vs net profit {f.amt(ni)} → cash conversion = **{ocf / ni:.2f}x** - "
                            + ("profits are backed by real cash." if ocf / ni >= 0.9 else "profits are NOT fully turning into cash; check receivables/inventory.")
                            if _ok(ni) and ni > 0 else "."))
        if _ok(capex):
            steps.append(f"2. **Capital expenditure {f.amt(abs(capex))}**"
                         + (f" = {_p(abs(capex) / rev)} of revenue ({'asset-light' if abs(capex) / rev < 0.05 else 'capital-intensive' if abs(capex) / rev > 0.12 else 'moderate'})." if _ok(rev) else "."))
        if _ok(ocf) and _ok(capex):
            steps.append(f"3. **Free cash flow** = OCF - capex = {f.amt(ocf)} - {f.amt(abs(capex))} = **{f.amt(ocf - abs(capex))}**. "
                         "This is the cash the DCF model is built on.")
        elif _ok(fcf):
            steps.append(f"3. **Free cash flow {f.amt(fcf)}** - the cash the DCF model is built on.")
        ret = (abs(div) if _ok(div) else 0) + (abs(bb) if _ok(bb) else 0)
        fc = fcf if _ok(fcf) else (ocf - abs(capex) if _ok(ocf) and _ok(capex) else np.nan)
        if ret > 0:
            steps.append(f"4. **Returned to shareholders**: dividends {f.amt(abs(div) if _ok(div) else 0)} + buybacks "
                         f"{f.amt(abs(bb) if _ok(bb) else 0)} = {f.amt(ret)}"
                         + (f" = **{ret / fc:.0%} of free cash flow**" + (" (paying out more than it generates - funded by cash or debt)." if ret > fc else ".")
                            if _ok(fc) and fc > 0 else "."))
        out.append({"title": "Cash flow statement - following the money", "blocks": [_md(*steps)]})

    # DuPont
    ni, rev = _get(inc, "Net profit"), _get(inc, "Revenue")
    ta, eq = _get(bal, "Total assets"), _get(bal, "Shareholders' equity")
    if all(_ok(v) and v != 0 for v in (ni, rev, ta, eq)) and eq > 0:
        nm, at, em = ni / rev, rev / ta, ta / eq
        driver = max([("high margins", nm / 0.10), ("efficient use of assets", at / 1.0), ("financial leverage", em / 2.0)], key=lambda t: t[1])[0]
        out.append({"title": "Connecting the statements - DuPont ROE breakdown", "blocks": [_md(
            "ROE (return on equity) can be split into three drivers that come from all three statements:",
            "",
            f"- **Net margin** (income statement) = {f.amt(ni)} ÷ {f.amt(rev)} = **{_p(nm)}**",
            f"- **Asset turnover** (income ÷ balance sheet) = {f.amt(rev)} ÷ {f.amt(ta)} = **{at:.2f}x**",
            f"- **Equity multiplier** (balance sheet leverage) = {f.amt(ta)} ÷ {f.amt(eq)} = **{em:.2f}x**",
            "",
            f"**ROE = {_p(nm)} × {at:.3g} × {em:.2f} = {_p(nm * at * em)}**",
            "",
            f"The biggest driver here is **{driver}**. "
            + ("ROE driven by leverage is lower quality - it rises and falls with debt." if driver == "financial leverage"
               else "That is a high-quality source of returns."))]})
    return out


# ------------------------------------------------------------------ 2. ratios
def _ratios(stt, a, inf, f: _Fmt):
    inc, bal, cf = stt["income"], stt["balance"], stt["cashflow"]
    gi = lambda r, i=0: _get(inc, r, i)
    gb = lambda r: _get(bal, r)
    gc = lambda r: _get(cf, r)
    rev, rev1, ni, ni1 = gi("Revenue"), gi("Revenue", 1), gi("Net profit"), gi("Net profit", 1)
    gp, ebit, intr = gi("Gross profit"), gi("Operating profit (EBIT)"), abs(gi("Interest expense"))
    ta, eq, debt, ca, cl = gb("Total assets"), gb("Shareholders' equity"), gb("Total debt"), gb("Current assets"), gb("Current liabilities")
    ocf, fcf = gc("Operating cash flow"), gc("Free cash flow")
    A = f.amt

    def row(cat, name, formula, num, den, num_s, den_s, kind, rule, good):
        v = num / den if _ok(num) and _ok(den) and den != 0 else np.nan
        if kind == "growth":
            v = v - 1 if _ok(v) else v
        val = _p(v, kind == "growth") if kind in ("pct", "growth") else (f"{v:.2f}x" if _ok(v) else "n/a")
        verdict = ("✅" if good(v) else "⚠️") if _ok(v) else "–"
        return {"Category": cat, "Ratio": name, "Formula": formula, "Calculation": f"{num_s} ÷ {den_s}" if _ok(v) else "data missing",
                "Result": val, "Rule of thumb": rule, "": verdict}

    rows = [
        row("Growth", "Revenue growth", "Revenue ÷ last year's revenue - 1", rev, rev1, A(rev), A(rev1), "growth", "> 10% strong", lambda v: v > 0.08),
        row("Growth", "Profit growth", "Net profit ÷ last year's - 1", ni, ni1, A(ni), A(ni1), "growth", "≥ revenue growth", lambda v: v > 0.08),
        row("Profitability", "Gross margin", "Gross profit ÷ Revenue", gp, rev, A(gp), A(rev), "pct", "Stable/rising; industry-specific", lambda v: v > 0.3),
        row("Profitability", "Operating margin", "EBIT ÷ Revenue", ebit, rev, A(ebit), A(rev), "pct", "> 15% good", lambda v: v > 0.15),
        row("Profitability", "Net margin", "Net profit ÷ Revenue", ni, rev, A(ni), A(rev), "pct", "> 10% good", lambda v: v > 0.10),
        row("Returns", "ROE", "Net profit ÷ Equity", ni, eq, A(ni), A(eq), "pct", "> 15% good", lambda v: v > 0.15),
        row("Returns", "ROA", "Net profit ÷ Total assets", ni, ta, A(ni), A(ta), "pct", "> 5% (banks > 1%)", lambda v: v > 0.05),
        row("Returns", "ROCE", "EBIT ÷ (Assets - Current liabilities)", ebit, ta - cl if _ok(ta) and _ok(cl) else np.nan, A(ebit),
            A(ta - cl) if _ok(ta) and _ok(cl) else "n/a", "pct", "> cost of capital (~12%)", lambda v: v > 0.12),
        row("Leverage", "Debt / Equity", "Total debt ÷ Equity", debt, eq, A(debt), A(eq), "x", "< 0.5 conservative, > 1.5 high", lambda v: v < 1.0),
        row("Leverage", "Interest coverage", "EBIT ÷ Interest expense", ebit, intr if _ok(intr) and intr > 0 else np.nan, A(ebit), A(intr), "x",
            "> 5x safe, < 3x risky", lambda v: v > 5),
        row("Liquidity", "Current ratio", "Current assets ÷ Current liabilities", ca, cl, A(ca), A(cl), "x", "1.2 - 2 typical", lambda v: v >= 1.2),
        row("Cash quality", "Cash conversion", "Operating cash flow ÷ Net profit", ocf, ni, A(ocf), A(ni), "x", "≈ 1 or above", lambda v: v >= 0.9),
        row("Cash quality", "FCF margin", "Free cash flow ÷ Revenue", fcf, rev, A(fcf), A(rev), "pct", "> 10% strong", lambda v: v > 0.10),
    ]
    tbl = pd.DataFrame(rows)

    price, ccy = a["price"], a["ccy"]
    teps, bvps, dr = _n(inf.get("trailingEps")), _n(inf.get("bookValue")), _pick_div(inf)
    ev, ebitda = _n(inf.get("enterpriseValue")), _n(inf.get("ebitda"))
    peg = valuation._pick(inf.get("pegRatio"), inf.get("trailingPegRatio"))
    vrows = [
        {"Multiple": "P/E (trailing)", "Calculation": f"Price {f.ps(price)} ÷ EPS {f.ps(teps)}", "Result": _x(price / teps, 1) if _ok(teps) and teps > 0 else "n/a",
         "Meaning": "Years of current profit you pay for. Compare with growth and peers."},
        {"Multiple": "P/E (forward)", "Calculation": f"Price ÷ next-year EPS estimate {f.ps(_n(inf.get('forwardEps')))}", "Result": _x(a["fpe"], 1),
         "Meaning": "Lower than trailing P/E = profits expected to grow."},
        {"Multiple": "PEG", "Calculation": "P/E ÷ expected EPS growth (%)", "Result": _x(peg),
         "Meaning": "< 1 cheap for its growth, 1-2 fair, > 2 expensive."},
        {"Multiple": "P/B", "Calculation": f"Price {f.ps(price)} ÷ book value/share {f.ps(bvps)}", "Result": _x(price / bvps, 2) if _ok(bvps) and bvps > 0 else "n/a",
         "Meaning": "Key for banks. High P/B is justified only by high ROE."},
        {"Multiple": "EV/EBITDA", "Calculation": f"Enterprise value {A(ev / valuation._fin_to_trade_fx(inf)) if _ok(ev) else 'n/a'} ÷ EBITDA {A(ebitda)}",
         "Result": _x(a["ev_ebitda"], 1), "Meaning": "Debt-neutral multiple for comparing peers. < 10 cheap, > 20 rich (varies by sector)."},
        {"Multiple": "Dividend yield", "Calculation": f"Dividend/share {f.ps(dr)} ÷ Price {f.ps(price)}", "Result": _p(dr / price) if _ok(dr) else "n/a",
         "Meaning": "Cash return. Check payout ratio is sustainable."},
    ]
    blocks = [_md("Every ratio below is computed from the **latest annual statements** with the actual numbers substituted, "
                  "so you can check the arithmetic yourself. ✅ = passes the rule of thumb, ⚠️ = worth investigating."),
              ("table", tbl),
              _md("#### Valuation multiples (price-based)"), ("table", pd.DataFrame(vrows))]
    good = [r for r in rows if r[""] == "✅"]
    bad = [r for r in rows if r[""] == "⚠️"]
    blocks.append(_md(f"**Summary:** {len(good)} of {len(good) + len(bad)} ratios pass. "
                      + (f"Watch: {', '.join(r['Ratio'] for r in bad)}." if bad else "No weak spots on these measures.")
                      + (" Note: for banks and financials, debt, current ratio and margins work differently - focus on ROE, ROA and P/B."
                         if inf.get("sector") in valuation.FINANCIAL_SECTORS else "")))
    return [{"title": "Ratio analysis - formula, calculation, result", "blocks": blocks}]


def _pick_div(inf):
    return valuation._pick(inf.get("dividendRate"), inf.get("trailingAnnualDividendRate"))


# ------------------------------------------------------------------ 3. valuation
def _valuation(a, inf, cfg, f: _Fmt):
    out = []
    mkt = cfg["markets"][a["market"]]
    d, dd, rel = a["dcf"], a["ddm"], a["rel"]
    price = a["price"]
    beta = a["beta"]
    b_used = min(max(beta if _ok(beta) else 1.0, 0.5), 2.5)

    out.append({"title": "Step 1 · Cost of equity (CAPM) - the return investors demand", "blocks": [_md(
        f"- Risk-free rate (10-year government bond, {'India' if a['market'] == 'IN' else 'US'}): **{_p(mkt['risk_free_rate'])}**",
        f"- Beta vs {mkt['benchmark']} (2 years of daily returns): **{_x(beta)}**"
        + (f" → capped to {b_used:.2f} (allowed range 0.5-2.5)" if _ok(beta) and abs(b_used - beta) > 1e-9 else "")
        + ("" if _ok(beta) else " → not available, 1.0 assumed"),
        f"- Equity risk premium (extra return demanded for owning stocks): **{_p(mkt['equity_risk_premium'])}**",
        "",
        f"**Cost of equity = {_p(mkt['risk_free_rate'])} + {b_used:.2f} × {_p(mkt['equity_risk_premium'])} = {_p(a['capm'])}**",
        "",
        "This is the hurdle rate: if you expect the stock to return less than this, it is not worth the risk.")]})

    # DCF
    if _ok(d.get("value")):
        w = d["wacc_detail"]
        hist = d.get("fcf_hist", {})
        hist_s = " · ".join(f"{y}: {f.amt(v)}" for y, v in hist.items())
        recent = list(hist.values())[:3]
        avg = float(np.mean(recent)) if len(recent) > 1 else (recent[0] if recent else np.nan)
        lo, hi = d["growth_cap"]
        gi = d.get("growth_inputs", [])
        kd_txt = (f"interest {f.amt(w['interest'])} ÷ debt {f.amt(w['debt'])}" if w.get("kd_from_interest")
                  else f"risk-free + 2% (no interest data)")
        proj = pd.DataFrame(d["projections"])
        proj["Discount factor"] = [1 / (1 + d["wacc"]) ** t for t in proj["Year"]]
        disp = pd.DataFrame({"Year": proj["Year"], "Growth": proj["Growth"].map(_p),
                             f"FCF ({f.lab})": (proj["FCF"] / f.div).map(lambda v: f"{v:,.0f}"),
                             "÷ (1+WACC)^year": proj["Discount factor"].map(lambda v: f"× {v:.3f}"),
                             f"Present value ({f.lab})": (proj["PV of FCF"] / f.div).map(lambda v: f"{v:,.0f}")})
        last = proj["FCF"].iloc[-1]
        tv = last * (1 + d["terminal_growth"]) / (d["wacc"] - d["terminal_growth"])
        per_share_rep = d["equity"] / d["shares"]
        blocks = [
            _md("**Step 2 · Starting free cash flow**",
                f"- FCF history (newest first): {hist_s}",
                f"- Average of the latest {min(3, len(hist))} years = {f.amt(avg)}" if len(recent) > 1 else "",
                f"- Rule: use the higher of the 3-year average and the latest year (if positive), to avoid penalising a growing company → **base FCF = {f.amt(d['base_fcf'])}**",
                "",
                "**Step 3 · Growth rate for the next 5 years**",
                *[f"- {n}: {_p(v, True)}" for n, v in gi],
                f"- Median of these = {_p(d['growth_raw'], True)}"
                + (f" → limited to the {_p(lo)}-{_p(hi)} range = **{_p(d['growth'])}**" if abs(d["growth_raw"] - d["growth"]) > 1e-9
                   else f" → **{_p(d['growth'])}** (within the {_p(lo)}-{_p(hi)} limits)"),
                f"- Years {d['high_years'] + 1}-{d['years']}: growth fades in a straight line to the long-term rate of **{_p(d['terminal_growth'])}** "
                "(roughly long-run nominal GDP growth - no company outgrows the economy forever).",
                "",
                "**Step 4 · Discount rate (WACC)**",
                f"- Cost of equity (step 1) = {_p(w['cost_of_equity'])}",
                f"- Cost of debt = {kd_txt} = {_p(w['cost_of_debt'])}, after tax ({_p(w['tax'])}) = {_p(w['cost_of_debt'] * (1 - w['tax']))}",
                f"- Weights (market values): equity {f.amt(w['mcap'] / d['fx']) if _ok(w['mcap']) else 'n/a'} → **{_p(w['equity_weight'])}**, "
                f"debt {f.amt(w['debt'])} → **{_p(w['debt_weight'])}**",
                f"- **WACC = {_p(w['equity_weight'])} × {_p(w['cost_of_equity'])} + {_p(w['debt_weight'])} × {_p(w['cost_of_debt'])} × (1 - {_p(w['tax'])}) = {_p(w['wacc'])}**"
                + (f" → floored at terminal growth + 2% = **{_p(d['wacc'])}**" if d.get("wacc_floored") else ""),
                "",
                f"**Step 5 · Project and discount {d['years']} years of free cash flow**"),
            ("table", disp),
            _md(f"Sum of present values = **{f.amt(d['pv_fcf'])}**",
                "",
                "**Step 6 · Terminal value (everything after year 10)**",
                f"- TV = FCF year {d['years']} × (1 + g) ÷ (WACC - g) = {f.amt(last)} × {1 + d['terminal_growth']:.3f} ÷ ({_p(d['wacc'])} - {_p(d['terminal_growth'])}) = {f.amt(tv)}",
                f"- Present value = TV ÷ (1 + WACC)^{d['years']} = **{f.amt(d['pv_tv'])}**",
                f"- The terminal value is **{_p(d['tv_share'])} of the total**. "
                + ("Above 75% means the valuation leans heavily on the distant future - treat with caution." if d["tv_share"] > 0.75 else "A reasonable share."),
                "",
                "**Step 7 · From enterprise value to value per share**",
                f"- Enterprise value = {f.amt(d['pv_fcf'])} + {f.amt(d['pv_tv'])} = **{f.amt(d['ev'])}**",
                f"- + Cash {f.amt(d['cash'])} - Debt {f.amt(d['debt'])} = **equity value {f.amt(d['equity'])}**",
                f"- ÷ {d['shares']:,.0f} shares = {f.fs}{per_share_rep:,.2f} per share"
                + (f" × FX {d['fx']:.4f} (reporting → trading currency, e.g. for ADRs)" if abs(d["fx"] - 1) > 1e-6 else ""),
                f"- **DCF value = {f.ps(d['value'])}** vs price {f.ps(price)} → **{_p(d['value'] / price - 1, True)}**",
                f"- Sensitivity: WACC ±1% gives {a['dcf_range']} - small input changes move DCF values a lot. Try the sliders on the Valuation tab."),
        ]
        out.append({"title": f"DCF - discounted cash flow → {f.ps(d['value'])}", "blocks": blocks})
    else:
        out.append({"title": "DCF - discounted cash flow → not used", "blocks": [_md(
            f"Reason: **{d.get('note') or 'insufficient data'}**.",
            "For banks and other financials, debt is raw material rather than financing, so free cash flow is not meaningful. "
            "Analysts value them on book value (P/B), ROE and dividends instead.")]})

    # DDM
    if _ok(dd.get("value")):
        g_sus = dd["roe"] * (1 - dd["payout"]) if _ok(dd.get("roe")) and _ok(dd.get("payout")) else np.nan
        out.append({"title": f"Dividend discount model → {f.ps(dd['value'])}", "blocks": [_md(
            f"- Current annual dividend D₀ = **{f.ps(dd['d0'])}**",
            f"- Sustainable growth = ROE × (1 - payout) = {_p(dd['roe'])} × (1 - {_p(dd['payout'])}) = {_p(g_sus)}"
            + f" → limited to ≤ terminal growth + 3% and ≤ cost of equity - 2% = **{_p(dd['g'])}**",
            f"- **Value = D₀ × (1 + g) ÷ (cost of equity - g) = {f.ps(dd['d0'])} × {1 + dd['g']:.3f} ÷ ({_p(dd['ke'])} - {_p(dd['g'])}) = {f.ps(dd['value'])}**",
            "",
            ("✅ Used in the blend (payout ≥ 40%, so dividends are a meaningful part of the return)." if "ddm" in a["models_used"]
             else f"❌ Not used in the blend: payout ratio {_p(_n(inf.get('payoutRatio')))} is below 40%, so most value comes from reinvested profits, not dividends - DDM would understate it."))]})
    else:
        out.append({"title": "Dividend discount model → not applicable", "blocks": [_md(f"Reason: {dd.get('note') or 'no dividend'}.")]})

    # Relative
    lines = []
    if _ok(rel.get("eps")) and _ok(rel.get("sector_pe")):
        lines.append(f"- Forward EPS {f.ps(rel['eps'])} × {a['sector']} sector median forward P/E **{rel['sector_pe']:.1f}** = {f.ps(rel['eps'] * rel['sector_pe'])}")
    if _ok(rel.get("bv")) and _ok(rel.get("sector_pb")) and inf.get("sector") in valuation.FINANCIAL_SECTORS:
        lines.append(f"- Book value/share {f.ps(rel['bv'])} × sector median P/B **{rel['sector_pb']:.2f}** = {f.ps(rel['bv'] * rel['sector_pb'])}")
    if lines:
        out.append({"title": f"Relative valuation (peer multiples) → {f.ps(rel['value'])}", "blocks": [_md(
            "What would the stock be worth if it traded at the same multiple as its sector peers in the same market?", "", *lines,
            "" if len(lines) == 1 else f"- Average = **{f.ps(rel['value'])}**", "",
            "Peers come from the screener universe (large caps in the same sector and market). If the company deserves a premium "
            "(higher growth or ROE than peers), this model will understate its value - and vice versa.")]})
    else:
        out.append({"title": "Relative valuation → not available", "blocks": [_md("No positive EPS or no sector peers with data.")]})

    # Graham
    teps, bvps = _n(inf.get("trailingEps")), _n(inf.get("bookValue"))
    gn = a["m_graham"]
    if _ok(gn):
        pe = _n(inf.get("trailingPE"))
        out.append({"title": f"Graham number → {f.ps(gn)}", "blocks": [_md(
            f"**√(22.5 × EPS × Book value per share) = √(22.5 × {f.ps(teps)} × {f.ps(bvps)}) = {f.ps(gn)}**", "",
            "22.5 = Graham's maximum P/E of 15 × maximum P/B of 1.5 for a defensive investor.", "",
            ("✅ Used in the blend (P/E ≤ 25 - a value-style stock where Graham's test makes sense)." if "graham" in a["models_used"]
             else f"❌ Not used in the blend: P/E {_x(pe, 1)} is above 25. For growth companies Graham's formula ignores future growth and would massively understate value."))]})

    # Consensus
    tgt = a["m_analyst_target"]
    if _ok(tgt):
        n_an = inf.get("numberOfAnalystOpinions")
        out.append({"title": f"Analyst consensus target → {f.ps(tgt)}", "blocks": [_md(
            f"Average 12-month price target of {n_an or 'several'} sell-side analysts"
            + (f" (range {f.ps(_n(inf.get('targetLowPrice')))} - {f.ps(_n(inf.get('targetHighPrice')))})" if _ok(inf.get("targetLowPrice")) else "")
            + f" → {_p(tgt / price - 1, True)} from today. Included with a small weight as a cross-check on our own models.")]})

    # Blend
    weights = cfg["valuation_weights"]
    names = {"dcf": "DCF", "relative": "Relative", "analyst_target": "Analyst target", "ddm": "DDM", "graham": "Graham"}
    used = [m.strip() for m in a["models_used"].split(",") if m.strip()]
    rows, num, den = [], 0.0, 0.0
    for k, w_ in weights.items():
        v = a.get(f"m_{k}", np.nan)
        inc = k in used
        if inc:
            num += w_ * v
            den += w_
        rows.append({"Model": names.get(k, k), "Value": f.ps(v), "Base weight": f"{w_:.0%}", "Used": "✅" if inc else "—",
                     "Weight × value": f.ps(w_ * v) if inc else ""})
    tbl = pd.DataFrame(rows)
    out.append({"title": f"Blended fair value → {f.ps(a['fair'])}", "blocks": [
        _md("No model is perfect, so - like a research desk - we triangulate. Models that do not suit this business are dropped and the remaining weights are re-scaled to 100%."),
        ("table", tbl),
        _md(f"**Fair value = Σ(weight × value) ÷ Σ(weights used) = {f.ps(num)} ÷ {den:.2f} = {f.ps(a['fair'])}**" if den else "No usable model.",
            "",
            f"**Upside = fair value ÷ price - 1 = {f.ps(a['fair'])} ÷ {f.ps(price)} - 1 = {_p(a['upside'], True)}**" if _ok(a["upside"]) else "",
            "",
            f"A 25% margin of safety would mean buying below **{f.ps(a['fair'] * 0.75)}**." if _ok(a["fair"]) else "")]})
    return out


# ------------------------------------------------------------------ 4. quality
def _quality(symbol, a, inf, f: _Fmt):
    out = []
    pz = valuation.piotroski_explained(symbol)
    rows = [{"#": i + 1, "Test": n, "Check with actual numbers": t, "Result": "✅ +1" if ok else "❌ 0" if ok is False else "– no data"}
            for i, (n, ok, t) in enumerate(pz)]
    sc = sum(1 for _, ok, _ in pz if ok)
    nv = sum(1 for _, ok, _ in pz if ok is not None)
    out.append({"title": f"Piotroski F-score → {sc}/{nv}", "blocks": [
        _md("Nine pass/fail tests comparing the latest year with the previous one (amounts in reporting currency units):"),
        ("table", pd.DataFrame(rows)),
        _md(f"**Score {sc} of {nv} tests with data** → "
            + ("strong and improving fundamentals." if nv and sc / nv >= 0.75 else "weak fundamentals - be careful." if nv and sc / nv <= 0.35 else "average - a mix of improving and deteriorating signals."))]})
    az = valuation.altman_components(symbol, inf)
    if az:
        rows = [{"Component": n, "Ratio": f"{x:.3f}", "× weight": w, "= points": f"{w * x:.3f}", "Measures": m} for n, w, x, m in az["terms"]]
        z = az["z"]
        ins = " · ".join(f"{k} {f.amt(v)}" for k, v in az["inputs"].items())
        out.append({"title": f"Altman Z-score → {z:.2f}", "blocks": [
            _md(f"Inputs: {ins}"), ("table", pd.DataFrame(rows)),
            _md(f"**Z = sum of points = {z:.2f}** → "
                + ("**safe zone** (> 2.99): very low bankruptcy risk." if z > 2.99 else "**grey zone** (1.81-2.99): monitor leverage and profitability."
                   if z >= 1.81 else "**distress zone** (< 1.81): elevated risk of financial distress."))]})
    else:
        out.append({"title": "Altman Z-score → not applicable", "blocks": [_md(
            "Altman Z was designed for industrial companies. For banks and financials it is not meaningful (their liabilities are customer deposits), or data is missing.")]})
    return out


# ------------------------------------------------------------------ 5. technicals & risk
def _tech_risk(a, cfg, f: _Fmt):
    out = []
    p, s50, s200, rsi = a.get("t_price"), a.get("t_sma50"), a.get("t_sma200"), a.get("t_rsi14")
    if _ok(p):
        lines = [f"- Price **{f.ps(p)}**, 50-day average **{f.ps(s50)}**, 200-day average **{f.ps(s200)}**"]
        if _ok(s200):
            lines.append(f"- Rule: price > 200-DMA **and** 50-DMA > 200-DMA → uptrend; both below → downtrend; otherwise sideways. "
                         f"Here: price {'>' if p > s200 else '<'} 200-DMA, 50-DMA {'>' if s50 > s200 else '<'} 200-DMA → **{a.get('t_trend')}**")
        lines += [f"- **RSI(14) = {_x(rsi, 0)}** → " + ("overbought (> 70): wait for a pullback" if rsi > 70 else "oversold (< 30): selling may be overdone" if rsi < 30 else "neutral (30-70)"),
                  f"- **MACD** {'above' if a.get('t_macd_bullish') else 'below'} its signal line → momentum {'improving' if a.get('t_macd_bullish') else 'weakening'}",
                  f"- {_p(a.get('t_from_52w_high'), True)} from the 52-week high, {_p(a.get('t_from_52w_low'), True)} above the 52-week low",
                  f"- Returns: 1m {_p(a.get('t_ret_1m'), True)} · 3m {_p(a.get('t_ret_3m'), True)} · 6m {_p(a.get('t_ret_6m'), True)} · 12m {_p(a.get('t_ret_12m'), True)}"]
        out.append({"title": f"Technicals → {a.get('t_trend')}", "blocks": [_md(*lines)]})
    rf = cfg["markets"][a["market"]]["risk_free_rate"]
    r, v = a.get("r_ann_return"), a.get("r_volatility")
    if _ok(r) and _ok(v):
        var = a.get("r_var95_1d")
        lakh = 100000 if a["ccy"] == "INR" else 10000
        out.append({"title": "Risk - how bumpy is the ride?", "blocks": [_md(
            f"- **Annualised return** (2 years): {_p(r, True)} · **Volatility**: {_p(v)} (annualised standard deviation of daily returns)",
            f"- **Sharpe ratio** = (return - risk-free) ÷ volatility = ({_p(r)} - {_p(rf)}) ÷ {_p(v)} = **{_x(a.get('r_sharpe'))}** "
            + ("(excellent)" if a.get("r_sharpe", 0) > 1 else "(acceptable)" if a.get("r_sharpe", 0) > 0.5 else "(poor reward for the risk)"),
            f"- **Beta {_x(a['beta'])}**: when the market moves 1%, this stock tends to move {_x(a['beta'])}%.",
            f"- **Maximum drawdown {_p(a.get('r_max_drawdown'))}**: the worst peak-to-trough fall in 2 years. Could you have held through it?",
            f"- **1-day VaR 95% = {_p(var)}**: on about 1 trading day in 20, expect to lose at least this much. "
            f"On {f.ts}{lakh:,} invested that is ≈ {f.ts}{lakh * var:,.0f}." if _ok(var) else "")]})
    return out


# ------------------------------------------------------------------ 6. verdict
def _verdict(a, stt, f: _Fmt):
    tech = {"trend": a.get("t_trend"), "rsi14": a.get("t_rsi14")} if _ok(a.get("t_rsi14")) else {}
    parts = stock.rate_parts(a["upside"], tech, a["f_score"], a["f_n"], a["z"])
    tbl = pd.DataFrame([{"Factor": n, "Points": f"{p:+g}", "Why": r} for n, p, r in parts]) if parts else pd.DataFrame()
    total = sum(p for _, p, _ in parts)
    rt = financials.ratios(stt) if not stt["income"].empty else pd.DataFrame()
    strengths, concerns = [], []
    chk = lambda name: rt.loc[name].dropna().iloc[0] if name in rt.index and not rt.loc[name].dropna().empty else np.nan
    roe, opm, de, cc, rg = chk("ROE"), chk("Operating margin"), chk("Debt / Equity"), chk("Cash conversion (OCF/NI)"), chk("Revenue growth")
    (strengths if _ok(roe) and roe > 0.15 else concerns if _ok(roe) and roe < 0.08 else []).append(f"ROE {_p(roe)}")
    (strengths if _ok(opm) and opm > 0.18 else concerns if _ok(opm) and opm < 0.06 else []).append(f"operating margin {_p(opm)}")
    (strengths if _ok(de) and de < 0.5 else concerns if _ok(de) and de > 1.5 else []).append(f"debt/equity {_x(de)}")
    (strengths if _ok(cc) and cc >= 1 else concerns if _ok(cc) and cc < 0.8 else []).append(f"cash conversion {_x(cc)}x")
    (strengths if _ok(rg) and rg > 0.12 else concerns if _ok(rg) and rg < 0.03 else []).append(f"revenue growth {_p(rg, True)}")
    if _ok(a["upside"]):
        (strengths if a["upside"] > 0.1 else concerns if a["upside"] < -0.1 else []).append(f"valuation ({_p(a['upside'], True)} to fair value)")
    if _ok(a["z"]) and a["z"] < 1.81:
        concerns.append(f"Altman Z {a['z']:.2f} (distress zone)")
    blocks = [_md("The rating adds up points from valuation, trend, momentum and financial health:"),
              ("table", tbl) if not tbl.empty else _md("_No scoring factors available._"),
              _md(f"**Total score {total:+g}** → thresholds: ≥ 3 Strong Buy · ≥ 1.5 Buy/Accumulate · ≥ -1 Hold · > -2.5 Reduce · else Sell → **{stock.rating_of(total)}**",
                  "",
                  "#### Strengths", *(f"- 💪 {s}" for s in strengths or ["none stand out on these measures"]),
                  "", "#### Concerns", *(f"- ⚠️ {c}" for c in concerns or ["none flagged on these measures"]),
                  "",
                  "#### What a professional would check next (not in the numbers)",
                  "- Read the latest annual report's MD&A and the last 2 quarterly earnings calls: is management's guidance credible?",
                  "- Segment results: which business line drives growth and margins?",
                  "- Competitive position and industry outlook; any regulatory risks?",
                  "- Governance: auditor's opinion, related-party transactions"
                  + (", promoter holding and **pledged shares** (NSE/BSE shareholding pattern)." if a["market"] == "IN" else ", insider buying/selling (SEC Form 4)."),
                  "- Valuation vs its own 5-10 year history of P/E, not just vs today's peers.")]
    return [{"title": f"How the rating '{a['rating']}' was reached", "blocks": blocks}]


# ------------------------------------------------------------------ public
def explain(symbol: str, a: dict, inf: dict, cfg: dict, stt: dict) -> list:
    """Return [(group title, [section{title, blocks}])] walking through every number for `symbol`."""
    f = _Fmt(inf.get("financialCurrency") or a["ccy"], a["ccy"])
    return [
        ("1 · Statements", _statements(stt, f, inf)),
        ("2 · Ratios", _ratios(stt, a, inf, f)),
        ("3 · Fair value", _valuation(a, inf, cfg, f)),
        ("4 · Quality scores", _quality(symbol, a, inf, f)),
        ("5 · Technicals & risk", _tech_risk(a, cfg, f)),
        ("6 · Verdict", _verdict(a, stt, f)),
    ]
