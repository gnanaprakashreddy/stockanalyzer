"""AI Portfolio Analyst - web app.  Run locally with:  streamlit run app.py"""
import hmac
import io
import json
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from agent import data, explain, financials, lessons, risk, screener, stock, valuation

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
EXCHANGES = {"NSI": "NSE", "BSE": "BSE", "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NYQ": "NYSE",
             "ASE": "NYSE American", "PCX": "NYSE Arca", "BTS": "BATS"}

st.set_page_config(page_title="AI Portfolio Analyst", page_icon="📈", layout="wide")


# ------------------------------------------------------------------ access control
def check_password() -> bool:
    try:
        secret = st.secrets.get("app_password", "")
    except Exception:
        secret = ""
    if not secret or st.session_state.get("auth_ok"):
        return True
    st.title("📈 AI Portfolio Analyst")
    pw = st.text_input("Password", type="password")
    if pw:
        if hmac.compare_digest(pw.encode(), str(secret).encode()):
            st.session_state["auth_ok"] = True
            st.rerun()
        st.error("Incorrect password")
    return False


if not check_password():
    st.stop()


# ------------------------------------------------------------------ caching
@st.cache_resource
def _cache_clock() -> dict:
    return {"t": time.time()}


def refresh_caches(force: bool = False):
    """data.py uses in-process lru caches; expire them hourly so prices/fundamentals stay fresh."""
    clk = _cache_clock()
    if force or time.time() - clk["t"] > 3600:
        for fn in (data.info, data.statement, data._ticker, data.fx_rate):
            fn.cache_clear()
        st.cache_data.clear()
        clk["t"] = time.time()


refresh_caches()


@st.cache_data(ttl=3600, show_spinner=False)
def search(q: str) -> list:
    try:
        quotes = yf.Search(q, max_results=15).quotes
    except Exception:
        return []
    out = []
    for x in quotes:
        if x.get("quoteType") == "EQUITY" and x.get("exchange") in EXCHANGES:
            out.append((x["symbol"], x.get("shortname") or x.get("longname") or x["symbol"], EXCHANGES[x["exchange"]]))
    order = {"NSE": 0, "BSE": 1}
    return sorted(out, key=lambda h: order.get(h[2], 2))


@st.cache_data(ttl=86400, show_spinner="Building sector benchmarks (once a day) ...")
def sector_medians() -> dict:
    universe = [s for m in CFG["screener"]["universe"].values() for s in m]
    return screener.sector_medians(screener.fetch_infos(universe))


@st.cache_data(ttl=3600, show_spinner=False)
def price_history(symbols: tuple, period: str = "5y") -> pd.DataFrame:
    return data.prices(list(symbols), period=period)


MODEL_VERSION = 2  # bump whenever agent/ models change shape, so cached results are recomputed


@st.cache_data(ttl=3600, show_spinner=False)
def _analyse(symbol: str, version: int) -> dict:
    bench = CFG["markets"][data.market_of(symbol)]["benchmark"]
    px = price_history((symbol, bench), "2y")
    if symbol not in px.columns or px[symbol].dropna().empty:
        return {}
    med = dict(sector_medians())
    inf = data.info(symbol)
    key = (data.market_of(symbol), inf.get("sector"))
    if key not in med:
        med.update(screener.sector_medians(screener.fetch_infos([symbol])))
    return stock.analyse(symbol, CFG, med, px[symbol], px[bench])


def analyse(symbol: str) -> dict:
    a = _analyse(symbol, MODEL_VERSION)
    if a and a.get("dcf") and "growth_cap" not in a["dcf"]:  # stale entry from older code
        _analyse.clear()
        a = _analyse(symbol, MODEL_VERSION)
    return a


@st.cache_data(ttl=3600, show_spinner=False)
def statements(symbol: str, quarterly: bool) -> dict:
    return financials.statements(symbol, quarterly)


@st.cache_data(ttl=3600, show_spinner=False)
def info(symbol: str) -> dict:
    return data.info(symbol)


@st.cache_data(ttl=3600, show_spinner=False)
def piotroski(symbol: str) -> list:
    return valuation.piotroski_detail(symbol)


@st.cache_data(ttl=3600, show_spinner=False)
def fx(a: str, b: str) -> float:
    return data.fx_rate(a, b)


# ------------------------------------------------------------------ formatting helpers
def ok(v) -> bool:
    try:
        return v is not None and np.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def pct(v, signed=False):
    return (f"{v:+.1%}" if signed else f"{v:.1%}") if ok(v) else "–"


def num(v, d=2):
    return f"{v:,.{d}f}" if ok(v) else "–"


def sym(ccy):
    return {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(ccy, ccy + " ")


def money(v, ccy, d=2):
    return f"{sym(ccy)}{v:,.{d}f}" if ok(v) else "–"


RATING_COLOR = {"Strong Buy": "green", "Buy / Accumulate": "green", "Hold": "orange", "Reduce": "red", "Sell": "red"}


# ------------------------------------------------------------------ stock page
def pick_symbol(key: str):
    """Search box + match picker. Returns the chosen ticker or None."""
    q = st.text_input("Search", key=key, placeholder="Company name or ticker ...", label_visibility="collapsed")
    if not q:
        return None
    hits = search(q.strip())
    if hits:
        labels = [f"{n}  ·  {s}  ·  {e}" for s, n, e in hits]
        pick = st.selectbox("Matches", labels, index=0, key=f"{key}_pick_{q.strip().lower()}")
        return hits[labels.index(pick)][0]
    symbol = q.strip().upper()
    st.info(f"No search matches - trying ticker **{symbol}** directly (Indian stocks need .NS or .BO, e.g. RELIANCE.NS).")
    return symbol


def stock_page():
    st.title("🔍 Stock Analysis")
    st.caption("Search any NSE/BSE or US-listed company by name or ticker (e.g. *Reliance*, *TCS*, *Apple*, *NVDA*).")
    symbol = pick_symbol("query")
    if not symbol:
        st.markdown("#### What you get\n- **Analyst rating** with blended fair value (DCF, DDM, relative, Graham, consensus)\n"
                    "- **Annual reports**: income statement, balance sheet, cash flow, 10+ derived ratios and an analyst read\n"
                    "- **Fundamentals & quality**: Piotroski F-score, Altman Z, multiples vs sector\n"
                    "- **Interactive DCF**, technicals (RSI/MACD/DMA) and risk vs benchmark")
        return

    with st.spinner(f"Analysing {symbol} ..."):
        a = analyse(symbol)
    if not a:
        st.error(f"No market data found for **{symbol}**. Check the ticker.")
        return
    inf, ccy = info(symbol), a["ccy"]

    st.subheader(f"{a['name']}  ({symbol})")
    st.caption(f"{inf.get('sector', '–')} · {inf.get('industry', '–')} · {'India' if a['market'] == 'IN' else 'US'}")
    c = st.columns(5)
    c[0].metric("Price", money(a["price"], ccy), pct(a["chg_1d"], True))
    c[1].metric("Blended fair value", money(a["fair"], ccy), pct(a["upside"], True))
    c[2].metric("Analyst rating", a["rating"])
    c[3].metric("Piotroski F-score", f"{a['f_score']}/{a['f_n']}" if a["f_n"] else "–")
    c[4].metric("Street consensus", a["reco"].replace("_", " ").title() if a["reco"] and a["reco"] != "none" else "–")
    st.markdown(f"**Analyst view:** :{RATING_COLOR.get(a['rating'], 'gray')}[**{a['rating']}**] — {a['why'] or 'insufficient data'}")

    def _to_learn():
        st.session_state["learn_query"] = symbol
        st.session_state["page"] = "📚 Learn"

    st.button("📚 Explain how these numbers are calculated", on_click=_to_learn)

    tabs = st.tabs(["📊 Overview", "💰 Valuation", "📑 Annual Reports", "🏗 Fundamentals & Quality",
                    "📈 Technicals", "⚠ Risk", "🏢 Company"])
    with tabs[0]:
        overview_tab(symbol, a, inf)
    with tabs[1]:
        valuation_tab(a, inf)
    with tabs[2]:
        annual_tab(symbol, inf, ccy)
    with tabs[3]:
        quality_tab(symbol, a)
    with tabs[4]:
        technicals_tab(symbol, a)
    with tabs[5]:
        risk_tab(symbol, a)
    with tabs[6]:
        st.write(inf.get("longBusinessSummary") or "No description available.")
        mcap = valuation._num(inf.get("marketCap"))
        u, lab = financials.unit(ccy)
        prof = {"Industry": inf.get("industry"), "Employees": f"{inf['fullTimeEmployees']:,}" if inf.get("fullTimeEmployees") else None,
                "Headquarters": ", ".join(x for x in (inf.get("city"), inf.get("country")) if x),
                "Market cap": f"{money(mcap / u, ccy, 0)} {lab.split()[-1]}" if ok(mcap) else None}
        st.table(pd.Series({k: v for k, v in prof.items() if v}, name="").to_frame())
        for label, url in financials.report_links(symbol, inf):
            st.markdown(f"- [{label}]({url})")


def overview_tab(symbol, a, inf):
    c = st.columns(4)
    c[0].metric("P/E (trailing)", num(a["pe"], 1))
    c[1].metric("P/E (forward)", num(a["fpe"], 1))
    c[2].metric("P/B", num(a["pb"], 1))
    c[3].metric("EV/EBITDA", num(a["ev_ebitda"], 1))
    c = st.columns(4)
    c[0].metric("ROE", pct(a["roe"]))
    c[1].metric("Net margin", pct(a["margin"]))
    c[2].metric("Revenue growth (YoY)", pct(a["rev_g"], True))
    c[3].metric("Debt/Equity", num(a["de"] / 100 if ok(a["de"]) else np.nan))
    period = st.radio("Period", ["6mo", "1y", "2y", "5y", "max"], index=3, horizontal=True)
    px = price_history((symbol,), period)
    if symbol in px.columns:
        p = px[symbol].dropna()
        st.line_chart(pd.DataFrame({"Price": p, "50-DMA": p.rolling(50).mean(), "200-DMA": p.rolling(200).mean()}),
                      height=350)
    st.markdown("**Annual reports & filings**")
    for label, url in financials.report_links(symbol, inf):
        st.markdown(f"- [{label}]({url})")


def valuation_tab(a, inf):
    ccy = a["ccy"]
    rows = [("Discounted Cash Flow (FCFF)", a["m_dcf"], a["dcf_note"]),
            ("Dividend Discount (Gordon)", a["m_ddm"], a["ddm_note"]),
            ("Relative (sector multiples)", a["m_relative"], a["rel_note"]),
            ("Graham number", a["m_graham"], "√(22.5 × EPS × BVPS)"),
            ("Analyst consensus target", a["m_analyst_target"], "Mean sell-side target")]
    used = a["models_used"].split(", ")
    keymap = ["dcf", "ddm", "relative", "graham", "analyst_target"]
    df = pd.DataFrame([{"Model": m, "Fair value": money(v, ccy), "Upside": pct(v / a["price"] - 1, True) if ok(v) else "–",
                        "Used in blend": "✅" if k in used else "—", "Notes": n} for (m, v, n), k in zip(rows, keymap)])
    st.dataframe(df, hide_index=True, width="stretch")
    st.caption(f"Blended fair value **{money(a['fair'], ccy)}** ({pct(a['upside'], True)}) - weights {CFG['valuation_weights']}, "
               "re-normalised over applicable models. DDM counts only for payout ≥ 40%; Graham only for P/E ≤ 25.")

    d = a["dcf"]
    st.markdown("#### Interactive DCF")
    if not ok(d.get("value")):
        st.info(d.get("note") or "DCF not available.")
        return
    st.caption(f"Base free cash flow {money(d['base_fcf'] / financials.unit(inf.get('financialCurrency') or ccy)[0], inf.get('financialCurrency') or ccy, 0)} "
               f"{financials.unit(inf.get('financialCurrency') or ccy)[1].split()[-1]} · "
               f"CAPM cost of equity {pct(a['capm'])} · beta {num(a['beta'])} · sensitivity (WACC ±1%): {a['dcf_range']}")
    c = st.columns(3)
    g0 = c[0].slider("Initial growth %", -10.0, 40.0, round(d["growth"] * 100, 1), 0.5) / 100
    r = c[1].slider("Discount rate (WACC) %", 5.0, 20.0, round(d["wacc"] * 100, 1), 0.1) / 100
    gt = c[2].slider("Terminal growth %", 0.0, 8.0, round(d["terminal_growth"] * 100, 1), 0.1) / 100
    if r <= gt:
        st.warning("WACC must be above terminal growth.")
        return
    res = valuation.dcf_from_inputs(d["base_fcf"], g0, r, gt, d["years"], d["high_years"], d["cash"], d["debt"], d["shares"], d["fx"])
    c = st.columns(3)
    c[0].metric("DCF value / share", money(res["value"], ccy), pct(res["value"] / a["price"] - 1, True))
    c[1].metric("Terminal value share of EV", pct(res["pv_tv"] / res["ev"]) if res["ev"] else "–")
    c[2].metric("Margin of safety needed (25%) buy below", money(res["value"] * 0.75, ccy))
    proj = pd.DataFrame(res["projections"])
    if not proj.empty:
        u, lab = financials.unit(inf.get("financialCurrency") or ccy)
        for col in ("FCF", "PV of FCF"):
            proj[col] = proj[col] / u
        st.dataframe(proj.style.format({"Growth": "{:.1%}", "FCF": "{:,.0f}", "PV of FCF": "{:,.0f}"}),
                     hide_index=True, width="stretch")
        st.caption(f"Cash-flow figures in {lab}.")


def annual_tab(symbol, inf, ccy):
    fccy = inf.get("financialCurrency") or ccy
    _, lab = financials.unit(fccy)
    freq = st.radio("Frequency", ["Annual", "Quarterly"], horizontal=True)
    stt = statements(symbol, freq == "Quarterly")
    if all(v.empty for v in stt.values()):
        st.info("No financial statements available for this company.")
        return
    if freq == "Annual":
        rt = financials.ratios(stt)
        notes = financials.commentary(stt, rt)
        if notes:
            st.markdown("#### 🧠 Analyst read of the annual reports")
            st.markdown("\n".join(f"- {n}" for n in notes))
    inc = stt["income"]
    if {"Revenue", "Net profit"} <= set(inc.index):
        chart = financials.scaled(inc.loc[["Revenue", "Net profit"]], fccy).T.iloc[::-1]
        st.markdown(f"**Revenue vs net profit ({lab})**")
        st.bar_chart(chart, stack=False, height=300)
    for title, key in [("Income statement", "income"), ("Balance sheet", "balance"), ("Cash flow statement", "cashflow")]:
        df = stt[key]
        if df.empty:
            continue
        st.markdown(f"#### {title} ({lab}; EPS per share)")
        st.dataframe(financials.scaled(df, fccy).style.format("{:,.2f}", na_rep="–"), width="stretch")
    if freq == "Annual" and not rt.empty:
        st.markdown("#### Key ratios by year")
        fmt = {i: ("{:.2f}x" if i in ("Debt / Equity", "Current ratio", "Interest coverage (x)", "Cash conversion (OCF/NI)") else "{:.1%}")
               for i in rt.index}
        st.dataframe(pd.DataFrame({c: [fmt[i].format(v) if ok(v) else "–" for i, v in rt[c].items()] for c in rt.columns},
                                  index=rt.index), width="stretch")
        trend = rt.loc[[r for r in ("Operating margin", "Net margin", "ROE") if r in rt.index]].T.iloc[::-1]
        if not trend.empty:
            st.markdown("**Profitability trend**")
            st.line_chart(trend, height=260)


def quality_tab(symbol, a):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"#### Piotroski F-score: {a['f_score']}/{a['f_n']}")
        det = piotroski(symbol)
        st.dataframe(pd.DataFrame([{"Test": t, "Result": "✅ Pass" if p else "❌ Fail" if p is False else "– n/a"} for t, p in det]),
                     hide_index=True, width="stretch")
        st.caption("≥ 7 strong, ≤ 3 weak (score scaled to tests with data).")
    with c2:
        z = a["z"]
        st.markdown("#### Altman Z-score")
        if ok(z):
            zone = "Safe zone" if z > 2.99 else "Grey zone" if z >= 1.81 else "Distress zone"
            st.metric("Z-score", num(z), zone, delta_color="normal" if z > 2.99 else "off" if z >= 1.81 else "inverse")
        else:
            st.info("Not applicable (financial companies) or insufficient data.")
        st.markdown("#### Multiples vs sector median")
        rel = a["rel"]
        st.write(rel.get("note") or "–")
    st.markdown("#### Return & leverage snapshot")
    c = st.columns(4)
    c[0].metric("ROE", pct(a["roe"]))
    c[1].metric("Net margin", pct(a["margin"]))
    c[2].metric("Dividend yield", f"{a['div_yield']:.2f}%" if ok(a["div_yield"]) else "–")
    c[3].metric("CAPM required return", pct(a["capm"]))


def technicals_tab(symbol, a):
    px = price_history((symbol,), "1y")
    if symbol not in px.columns:
        return
    p = px[symbol].dropna()
    c = st.columns(5)
    c[0].metric("Trend", a.get("t_trend", "–"))
    c[1].metric("RSI (14)", num(a.get("t_rsi14"), 0))
    c[2].metric("MACD", "Bullish" if a.get("t_macd_bullish") else "Bearish")
    c[3].metric("From 52w high", pct(a.get("t_from_52w_high"), True))
    c[4].metric("From 52w low", pct(a.get("t_from_52w_low"), True))
    st.dataframe(pd.DataFrame({k: [pct(a.get(f"t_ret_{k}"), True)] for k in ("1m", "3m", "6m", "12m")}, index=["Return"]),
                 width="stretch")
    d = p.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    macd = p.ewm(span=12).mean() - p.ewm(span=26).mean()
    st.markdown("**RSI (14)** — above 70 overbought, below 30 oversold")
    st.line_chart(pd.DataFrame({"RSI": rsi, "70": 70.0, "30": 30.0}), height=200)
    st.markdown("**MACD (12, 26, 9)**")
    st.line_chart(pd.DataFrame({"MACD": macd, "Signal": macd.ewm(span=9).mean()}), height=200)


def risk_tab(symbol, a):
    bench = CFG["markets"][a["market"]]["benchmark"]
    rows = {"Annualised return": pct(a.get("r_ann_return"), True), "Volatility": pct(a.get("r_volatility")),
            "Sharpe": num(a.get("r_sharpe")), "Sortino": num(a.get("r_sortino")), "Max drawdown": pct(a.get("r_max_drawdown")),
            "1-day VaR 95%": pct(a.get("r_var95_1d")), "1-day CVaR 95%": pct(a.get("r_cvar95_1d")), f"Beta vs {bench}": num(a["beta"])}
    px = price_history((symbol, bench), "2y")
    bm = risk.risk_metrics(px[bench].dropna().pct_change(), CFG["markets"][a["market"]]["risk_free_rate"]) if bench in px else {}
    bcol = {"Annualised return": pct(bm.get("ann_return"), True), "Volatility": pct(bm.get("volatility")), "Sharpe": num(bm.get("sharpe")),
            "Sortino": num(bm.get("sortino")), "Max drawdown": pct(bm.get("max_drawdown")), "1-day VaR 95%": pct(bm.get("var95_1d")),
            "1-day CVaR 95%": pct(bm.get("cvar95_1d")), f"Beta vs {bench}": "1.00"}
    st.dataframe(pd.DataFrame({symbol: rows, bench: bcol}), width="stretch")
    st.caption("Based on 2 years of daily returns.")
    if symbol in px.columns:
        p = px[[symbol, bench]].dropna()
        st.markdown("**Growth of 100 vs benchmark**")
        st.line_chart(100 * p / p.iloc[0], height=280)
        dd = p[symbol] / p[symbol].cummax() - 1
        st.markdown("**Drawdown**")
        st.area_chart(dd.rename("Drawdown"), height=200)


# ------------------------------------------------------------------ portfolio page
SAMPLE_CSV = "symbol,quantity,avg_cost,broker\nRELIANCE.NS,10,2400,Groww\nAAPL,5,170,Vested\n"


def load_holdings_text() -> str:
    if "holdings_csv" in st.session_state:
        return st.session_state["holdings_csv"]
    try:
        txt = st.secrets.get("portfolio_csv", "")
    except Exception:
        txt = ""
    if not txt and (ROOT / "portfolio.csv").exists():
        txt = (ROOT / "portfolio.csv").read_text(encoding="utf-8")
    return txt or SAMPLE_CSV


def portfolio_page():
    st.title("💼 My Portfolio")
    with st.expander("✏️ Edit / upload holdings", expanded=False):
        up = st.file_uploader("Upload holdings CSV (symbol, quantity, avg_cost, broker)", type="csv")
        if up is not None:
            st.session_state["holdings_csv"] = up.getvalue().decode("utf-8")
        base_df = pd.read_csv(io.StringIO(load_holdings_text()), comment="#")
        edited = st.data_editor(base_df, num_rows="dynamic", width="stretch", key="editor")
        c = st.columns(2)
        if c[0].button("Apply changes"):
            st.session_state["holdings_csv"] = edited.to_csv(index=False)
            st.rerun()
        c[1].download_button("⬇ Download CSV", edited.to_csv(index=False), "portfolio.csv", "text/csv")
        st.caption("Indian tickers end with **.NS** (NSE) or **.BO** (BSE); US tickers are plain (AAPL). "
                   "Changes here last for this browser session only - keep the downloaded CSV, or put it in the app's secrets.")
    try:
        pf = stock.read_holdings(io.StringIO(load_holdings_text()))
    except Exception as e:
        st.error(f"Could not read holdings: {e}")
        return
    if pf.empty:
        st.info("Add some holdings above.")
        return

    base = CFG["base_currency"]
    rows, bad = [], []
    prog = st.progress(0.0, "Analysing holdings ...")
    for i, s in enumerate(pf.index):
        a = analyse(s)
        if not a and s.endswith(".NS"):
            s2 = s[:-3] + ".BO"
            a = analyse(s2)
        if not a:
            bad.append(s)
            continue
        q, cost = pf.loc[s, "quantity"], pf.loc[s, "avg_cost"]
        rate = fx(a["ccy"], base)
        rows.append({"Symbol": a["symbol"], "Name": a["name"], "Broker": pf.loc[s, "broker"], "Market": a["market"],
                     "Sector": a["sector"], "Qty": q, "Avg cost": cost, "Price": a["price"], "Day %": a["chg_1d"],
                     "Value": q * a["price"] * rate, "Cost": q * cost * rate, "Fair value": a["fair"], "Upside": a["upside"],
                     "Rating": a["rating"], "Why": a["why"], "ccy": a["ccy"]})
        prog.progress((i + 1) / len(pf), f"Analysed {s}")
    prog.empty()
    if bad:
        st.warning(f"No market data for: {', '.join(bad)} - check the ticker symbols.")
    if not rows:
        return
    h = pd.DataFrame(rows)
    h["P&L"] = h["Value"] - h["Cost"]
    h["P&L %"] = h["P&L"] / h["Cost"]
    h["Weight"] = h["Value"] / h["Value"].sum()
    day = (h["Value"] * h["Day %"].fillna(0) / (1 + h["Day %"].fillna(0))).sum()

    c = st.columns(4)
    c[0].metric("Portfolio value", money(h["Value"].sum(), base, 0))
    c[1].metric("Invested", money(h["Cost"].sum(), base, 0))
    c[2].metric("Total P&L", money(h["P&L"].sum(), base, 0), pct(h["P&L"].sum() / h["Cost"].sum(), True))
    c[3].metric("Today", money(day, base, 0), pct(day / (h["Value"].sum() - day), True))

    show = h.copy()
    show["Avg cost"] = [money(v, c_) for v, c_ in zip(show["Avg cost"], show["ccy"])]
    show["Price"] = [money(v, c_) for v, c_ in zip(show["Price"], show["ccy"])]
    show["Fair value"] = [money(v, c_) for v, c_ in zip(show["Fair value"], show["ccy"])]
    for col in ("Value", "Cost", "P&L"):
        show[col] = show[col].map(lambda v: money(v, base, 0))
    for col in ("Day %", "Upside", "P&L %"):
        show[col] = show[col].map(lambda v: pct(v, True))
    show["Weight"] = show["Weight"].map(pct)
    st.dataframe(show[["Symbol", "Name", "Broker", "Qty", "Avg cost", "Price", "Day %", "Value", "P&L", "P&L %", "Weight",
                       "Fair value", "Upside", "Rating", "Why"]], hide_index=True, width="stretch")

    c = st.columns(3)
    for col, by in zip(c, ("Sector", "Market", "Broker")):
        col.markdown(f"**By {by.lower()}**")
        col.bar_chart(h.groupby(by)["Weight"].sum().sort_values(ascending=False), horizontal=True, height=220)

    st.markdown("#### Portfolio risk (2 years, in " + base + ")")
    px = price_history(tuple(h["Symbol"]), "2y")
    R = pd.DataFrame({s: (px[s].dropna() * data.fx_series(cc, base, px[s].dropna().index)).pct_change()
                      for s, cc in zip(h["Symbol"], h["ccy"]) if s in px}).dropna(how="all").fillna(0).iloc[1:]
    w = h.set_index("Symbol")["Weight"]
    port = (R * w.reindex(R.columns).fillna(0)).sum(axis=1)
    rf = CFG["markets"]["IN" if base == "INR" else "US"]["risk_free_rate"]
    m = risk.risk_metrics(port, rf)
    c = st.columns(5)
    c[0].metric("Annual return", pct(m.get("ann_return"), True))
    c[1].metric("Volatility", pct(m.get("volatility")))
    c[2].metric("Sharpe", num(m.get("sharpe")))
    c[3].metric("Max drawdown", pct(m.get("max_drawdown")))
    c[4].metric("1-day VaR 95%", pct(m.get("var95_1d")))
    st.line_chart((1 + port).cumprod().rename("Growth of 1 (current weights)"), height=250)
    rc = risk.risk_contribution(R, w.reindex(R.columns).fillna(0))
    st.markdown("**Risk contribution by holding**")
    st.bar_chart(rc.sort_values(ascending=False), height=220)

    c = st.columns([2, 1])
    pick = c[0].selectbox("Open detailed analysis for", h["Symbol"])
    def _jump():
        st.session_state["query"] = pick
        st.session_state["page"] = "🔍 Stock Analysis"

    c[1].button("🔍 Analyse", width="stretch", on_click=_jump)

    st.markdown("#### 📄 Full daily analyst report")
    st.caption("Runs every model (incl. portfolio optimisation and new-stock ideas). Takes 1-3 minutes.")
    if st.button("Generate full analyst report"):
        from agent.analyst import PortfolioAnalyst
        with st.spinner("Running the analyst agent ..."), tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "portfolio.csv").write_text(load_holdings_text(), encoding="utf-8")
            (tmp / "config.json").write_text(json.dumps(CFG), encoding="utf-8")
            res = PortfolioAnalyst(tmp, tmp / "config.json", tmp / "portfolio.csv").run()
            st.session_state["report_html"] = Path(res["html"]).read_text(encoding="utf-8")
    if "report_html" in st.session_state:
        st.download_button("⬇ Download report (HTML)", st.session_state["report_html"], "analyst_report.html", "text/html")
        st.components.v1.html(st.session_state["report_html"], height=900, scrolling=True)


# ------------------------------------------------------------------ ideas page
@st.cache_data(ttl=86400, show_spinner="Screening the universe (once a day) ...")
def ideas() -> pd.DataFrame:
    universe = [s for m in CFG["screener"]["universe"].values() for s in m]
    df = screener.fetch_infos(universe)
    px = data.prices(list(df.index), period="1y")
    scored = screener.score(df, px[[c for c in df.index if c in px.columns]].iloc[-252:], CFG["screener"]["weights"])
    scored["thesis"] = scored.apply(screener.thesis, axis=1)
    return scored


def ideas_page():
    st.title("💡 New Stock Ideas")
    st.caption("Multi-factor screen (growth, quality, valuation, momentum) over a curated universe of large Indian and US "
               "companies, ranked within each market. Edit the universe in config.json.")
    df = ideas()
    n = st.slider("Ideas per market", 3, 15, CFG["screener"]["top_n_per_market"])
    for mkt, label in (("IN", "🇮🇳 India"), ("US", "🇺🇸 US")):
        g = df[df["market"] == mkt].head(n)
        st.markdown(f"#### {label}")
        st.dataframe(pd.DataFrame({"Symbol": g.index, "Name": g["shortName"], "Sector": g["sector"], "Score": g["score"].round(0),
                                   "Rev growth": g["revenueGrowth"].map(lambda v: pct(v, True)),
                                   "ROE": g["returnOnEquity"].map(pct), "Fwd P/E": g["forwardPE"].map(lambda v: num(v, 1)),
                                   "6m return": g["ret_6m"].map(lambda v: pct(v, True)), "Thesis": g["thesis"]}),
                     hide_index=True, width="stretch")
    st.caption("Screens are a starting point for research, not recommendations.")


# ------------------------------------------------------------------ learn page
def _render_blocks(blocks):
    for kind, obj in blocks:
        if kind == "md":
            st.markdown(obj.replace("$", "\\$"))
        elif kind == "table":
            st.dataframe(obj, hide_index=isinstance(obj.index, pd.RangeIndex), width="stretch")


def learn_page():
    st.title("📚 Learn to Analyse Like a Pro")
    t1, t2 = st.tabs(["🔬 Explain a stock, step by step", "📖 Lessons"])
    with t2:
        st.caption("Work through these in order - each builds on the previous one. Then use **Explain a stock** to see every concept applied to a real company.")
        for i, (title, body) in enumerate(lessons.LESSONS):
            with st.expander(title, expanded=(i == 0)):
                st.markdown(body)
    with t1:
        st.caption("Pick any stock and see exactly how every number on the Stock Analysis page is calculated - "
                   "with the company's real figures plugged into each formula.")
        symbol = pick_symbol("learn_query")
        if not symbol:
            st.markdown("Try **TCS**, **HDFC Bank** (a bank - see how the method changes), **Apple** or **NVIDIA**.")
            return
        with st.spinner(f"Working through {symbol} ..."):
            a = analyse(symbol)
            if not a:
                st.error(f"No market data found for **{symbol}**.")
                return
            inf = info(symbol)
            groups = explain.explain(symbol, a, inf, CFG, statements(symbol, False))
        st.subheader(f"{a['name']} ({symbol})")
        st.markdown(f"Price **{money(a['price'], a['ccy'])}** · Fair value **{money(a['fair'], a['ccy'])}** "
                    f"({pct(a['upside'], True)}) · Rating **{a['rating']}**".replace("$", "\\$"))
        tabs = st.tabs([g for g, _ in groups])
        for tab, (_, sections) in zip(tabs, groups):
            with tab:
                for i, sec in enumerate(sections):
                    with st.expander(sec["title"].replace("$", "\\$"), expanded=(i == 0)):
                        _render_blocks(sec["blocks"])
        st.caption("Figures from Yahoo Finance; statement amounts in the company's reporting currency. Educational use only.")


# ------------------------------------------------------------------ navigation
PAGES = {"🔍 Stock Analysis": stock_page, "💼 My Portfolio": portfolio_page, "💡 New Ideas": ideas_page, "📚 Learn": learn_page}
with st.sidebar:
    st.markdown("## 📈 AI Portfolio Analyst")
    page = st.radio("Go to", list(PAGES), key="page", label_visibility="collapsed")
    st.divider()
    if st.button("🔄 Refresh market data"):
        refresh_caches(force=True)
        st.rerun()
    st.caption("Data: Yahoo Finance (may be delayed). Educational use only - not investment advice.")
PAGES[page]()
