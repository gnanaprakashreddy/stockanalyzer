"""The Portfolio Analyst agent: gathers data, runs all models, forms a view and writes the daily report."""
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, report, risk, screener, stock, valuation
from .report import Section

RATING_ORDER = ["Strong Buy", "Buy / Accumulate", "Hold", "Reduce", "Sell"]


# ---------------------------------------------------------------- formatting
def pct(v, signed=True, d=1):
    if v is None or not np.isfinite(v):
        return "n/a"
    return f"{v:+.{d}%}" if signed else f"{v:.{d}%}"


def num(v, d=0):
    return "n/a" if v is None or not np.isfinite(v) else f"{v:,.{d}f}"


SYM = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}


def money(v, ccy, d=0):
    if v is None or not np.isfinite(v):
        return "n/a"
    return f"{'-' if v < 0 else ''}{SYM.get(ccy, ccy + ' ')}{abs(v):,.{d}f}"


class PortfolioAnalyst:
    def __init__(self, root: Path, config_path: Path, portfolio_path: Path | None = None, run_screener: bool | None = None):
        self.root = root
        self.cfg = json.loads(config_path.read_text(encoding="utf-8"))
        self.base = self.cfg["base_currency"]
        self.pf_path = portfolio_path or root / self.cfg["portfolio_file"]
        self.warnings = []
        self.run_screener = self.cfg["screener"]["enabled"] if run_screener is None else run_screener
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.log = lambda m: print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)

    # ------------------------------------------------------------ data
    def load_portfolio(self) -> pd.DataFrame:
        pf = stock.read_holdings(self.pf_path)
        if pf.empty:
            raise SystemExit(f"No holdings found in {self.pf_path}")
        return pf

    def _resolve_missing(self, pf: pd.DataFrame, px: pd.DataFrame) -> tuple:
        """Retry NSE symbols on BSE; drop holdings Yahoo cannot price, with a warning."""
        has = lambda s: s in px.columns and not px[s].dropna().empty
        missing = [s for s in pf.index if not has(s)]
        if not missing:
            return pf, px
        alt = {s: s[:-3] + ".BO" for s in missing if s.endswith(".NS")}
        if alt:
            extra = data.prices(list(alt.values()), period="2y")
            for s, a in alt.items():
                if a in extra.columns and not extra[a].dropna().empty:
                    px = px.join(extra[[a]], how="outer")
                    pf = pf.rename(index={s: a})
                    missing.remove(s)
        if missing:
            self.warnings.append(f"No market data for {', '.join(missing)} - excluded from analysis (check symbol mapping)")
            pf = pf.drop(index=missing)
        return pf, px

    def run(self) -> dict:
        cfg, base = self.cfg, self.base
        pf = self.load_portfolio()
        syms = list(pf.index)

        universe = [s for m in cfg["screener"]["universe"].values() for s in m] if self.run_screener else []
        self.log("Fetching company fundamentals ...")
        infos_df = screener.fetch_infos(syms + universe)
        sec_med = screener.sector_medians(infos_df)
        benches = {m: v["benchmark"] for m, v in cfg["markets"].items()}

        self.log("Fetching 2y price history ...")
        px = data.prices(syms + list(benches.values()) + universe, period="2y")
        pf, px = self._resolve_missing(pf, px)
        syms = list(pf.index)
        if not syms:
            raise SystemExit("None of the holdings could be priced.")
        self.log(f"Analysing {len(syms)} holdings: {', '.join(syms)}")

        # ---------------- per holding analysis
        rows = []
        rets_base = {}
        for s in syms:
            mkt_key = data.market_of(s)
            r = stock.analyse(s, cfg, sec_med, px[s], px[benches[mkt_key]])
            for k in ("dcf", "ddm", "rel"):
                r.pop(k)
            close = px[s].dropna()
            fx_now = data.fx_rate(r["ccy"], base)
            qty, cost = pf.loc[s, "quantity"], pf.loc[s, "avg_cost"]
            value_base = qty * r["price"] * fx_now
            rets_base[s] = (close * data.fx_series(r["ccy"], base, close.index)).pct_change()
            chg = r["chg_1d"] if np.isfinite(r["chg_1d"]) else 0.0
            rows.append(dict(r, broker=pf.loc[s, "broker"], qty=qty, avg_cost=cost, value=value_base,
                             cost_base=qty * cost * fx_now, day_pnl=value_base * chg / (1 + chg)))
        h = pd.DataFrame(rows).set_index("symbol")
        total = h["value"].sum()
        h["weight"] = h["value"] / total
        h["pnl"] = h["value"] - h["cost_base"]
        h["pnl_pct"] = h["pnl"] / h["cost_base"]

        # ---------------- portfolio level risk
        self.log("Running portfolio risk & optimisation models ...")
        R = pd.DataFrame(rets_base).dropna(how="all").fillna(0).iloc[1:]
        R = R[R.index >= R.index[-1] - pd.Timedelta(days=730)]
        port_r = (R * h["weight"]).sum(axis=1)
        base_rf = cfg["markets"]["IN" if base == "INR" else "US"]["risk_free_rate"]
        bench_base = {}
        for m, b in benches.items():
            bccy = "INR" if m == "IN" else "USD"
            bs = px[b].dropna()
            bench_base[b] = (bs * data.fx_series(bccy, base, bs.index)).pct_change()
        mkt_w = h.groupby("market")["weight"].sum()
        blend_r = sum(bench_base[benches[m]].reindex(port_r.index).fillna(0) * w for m, w in mkt_w.items())
        blend_name = "Blended benchmark (" + " / ".join(f"{benches[m]} {w:.0%}" for m, w in mkt_w.items()) + ")"
        bench_base[blend_name] = blend_r
        prm = risk.risk_metrics(port_r, base_rf, blend_r)
        bench_rm = {b: risk.risk_metrics(r.reindex(port_r.index).dropna(), base_rf) for b, r in bench_base.items()}
        rc = risk.risk_contribution(R, h["weight"])
        corr = R.corr()

        hist_ann = R.apply(lambda c: (1 + c).prod() ** (252 / len(c)) - 1).clip(-0.2, 0.4)
        val_impl = ((1 + h["upside"].clip(-0.5, 1.0)) ** (1 / 3) - 1).fillna(0) + h["capm"] * 0.5
        exp_ret = pd.concat([h["capm"], hist_ann, val_impl.clip(-0.2, 0.4)], axis=1).mean(axis=1)
        opt = risk.optimise(R, exp_ret, base_rf, cfg["optimization"]["max_weight"], cfg["optimization"]["simulations"])
        cur_stats = risk.portfolio_stats(h["weight"].reindex(R.columns).values, exp_ret.reindex(R.columns).values,
                                         R.cov().values * 252, base_rf)

        # ---------------- screener
        ideas = pd.DataFrame()
        if self.run_screener and universe:
            self.log("Screening universe for new growth ideas ...")
            uni = infos_df.loc[[s for s in infos_df.index if s in universe and s not in syms]]
            scored = screener.score(uni, px[[c for c in uni.index if c in px.columns]].iloc[-252:], cfg["screener"]["weights"])
            top = scored.groupby("market", group_keys=False).head(cfg["screener"]["top_n_per_market"])
            for s in top.index:
                inf = data.info(s)
                mkt = cfg["markets"][data.market_of(s)]
                b = valuation._num(inf.get("beta"))
                d = valuation.dcf(s, inf, mkt, cfg["dcf"], b)
                top.loc[s, "dcf_value"] = d["value"]
                top.loc[s, "dcf_upside"] = d["value"] / top.loc[s, "price"] - 1 if np.isfinite(d["value"]) else np.nan
            top["thesis"] = top.apply(screener.thesis, axis=1)
            ideas = top

        # ---------------- history (day-by-day tracking)
        hist_dir = self.root / cfg["history_dir"]
        hist_dir.mkdir(parents=True, exist_ok=True)
        prev = sorted(p for p in hist_dir.glob("*.json") if p.stem < self.today)
        prev_snap = json.loads(prev[-1].read_text()) if prev else None
        snap = {"date": self.today, "total_value": total, "total_cost": h["cost_base"].sum(),
                "holdings": {s: {"value": r.value, "price": r.price, "rating": r.rating, "fair": r.fair} for s, r in h.iterrows()}}
        (hist_dir / f"{self.today}.json").write_text(json.dumps(snap, indent=1, default=float))
        history = pd.Series({json.loads(p.read_text())["date"]: json.loads(p.read_text())["total_value"]
                             for p in sorted(hist_dir.glob("*.json"))})

        return self._write_report(h, total, prm, bench_rm, rc, corr, opt, cur_stats, exp_ret, ideas, prev_snap, history)

    # ------------------------------------------------------------ report
    def _write_report(self, h, total, prm, bench_rm, rc, corr, opt, cur_stats, exp_ret, ideas, prev_snap, history):
        base = self.base
        cost = h["cost_base"].sum()
        day_pnl = h["day_pnl"].sum()
        sections = []

        # Executive summary
        bullets = [
            f"Portfolio value: {money(total, base)} | Invested: {money(cost, base)} | Unrealised P&L: {money(total - cost, base)} ({pct((total - cost) / cost)})",
            f"Last-session move: {money(day_pnl, base)} ({pct(day_pnl / (total - day_pnl))})",
        ]
        if prev_snap:
            ch = total - prev_snap["total_value"]
            bullets.append(f"Since last report ({prev_snap['date']}): {money(ch, base)} ({pct(ch / prev_snap['total_value'])})")
            changes = [f"{s}: {prev_snap['holdings'][s]['rating']} → {r.rating}" for s, r in h.iterrows()
                       if s in prev_snap["holdings"] and prev_snap["holdings"][s]["rating"] != r.rating]
            if changes:
                bullets.append("Rating changes: " + "; ".join(changes))
        best, worst = h["chg_1d"].idxmax(), h["chg_1d"].idxmin()
        bullets.append(f"Top gainer (last session): {best} {pct(h.loc[best, 'chg_1d'])} | Top loser: {worst} {pct(h.loc[worst, 'chg_1d'])}")
        if prm:
            bullets.append(f"Risk: volatility {pct(prm['volatility'], False)}, Sharpe {prm['sharpe']:.2f}, 1-day 95% VaR {money(prm['var95_1d'] * total, base)}")

        actions = []
        for s, r in h.sort_values("score", ascending=False).iterrows():
            if r.rating in ("Strong Buy", "Buy / Accumulate"):
                actions.append(f"ADD {s} ({r.rating}): {r.why}")
            elif r.rating in ("Reduce", "Sell"):
                actions.append(f"{r.rating.upper()} {s}: {r.why}")
        for s, w in h["weight"].items():
            if w > self.cfg["optimization"]["max_weight"]:
                actions.append(f"TRIM {s}: concentration {pct(w, False)} exceeds {pct(self.cfg['optimization']['max_weight'], False, 0)} limit")
        sec_w = h.groupby("sector")["weight"].sum()
        for sec, w in sec_w.items():
            if w > 0.40:
                actions.append(f"DIVERSIFY: {sec} sector is {pct(w, False)} of portfolio")
        if not ideas.empty:
            actions.append("NEW IDEAS: " + ", ".join(ideas.index[:4]) + " (see 'New Growth Ideas')")
        bullets += [f"? {w}" for w in self.warnings]
        if (h["broker"] != "-").any():
            bw = h.groupby("broker")["value"].sum()
            bullets.append("By broker: " + ", ".join(f"{k} {money(v, base)} ({pct(v / total, False)})" for k, v in bw.items()))
        sections.append(Section("Executive Summary", bullets=bullets))
        sections.append(Section("Analyst Action List", bullets=actions or ["No action required - stay the course."]))

        if len(history) >= 2:
            sections.append(Section("Portfolio Value History (day-by-day)",
                                    html_extra=report.svg_line_chart(history, label=f"Value ({base})"),
                                    table=pd.DataFrame({"Value": history.map(lambda v: money(v, base)),
                                                        "Daily change": history.pct_change().map(pct)}).iloc[::-1].head(15)
                                    .rename_axis("Date")))

        # Holdings
        t = pd.DataFrame({
            "Name": h["name"], "Broker": h["broker"], "Qty": h["qty"].map(lambda x: num(x, 0 if float(x).is_integer() else 4)), "Avg cost": [money(r.avg_cost, r.ccy, 2) for _, r in h.iterrows()],
            "Price": [money(r.price, r.ccy, 2) for _, r in h.iterrows()], "Last session": h["chg_1d"].map(pct),
            f"Value ({base})": h["value"].map(lambda v: money(v, base)), "Weight": h["weight"].map(lambda v: pct(v, False)),
            "P&L": h["pnl_pct"].map(pct), "Rating": h["rating"],
        }).rename_axis("Symbol")
        sections.append(Section("Holdings Overview", table=t))

        # Valuation
        v = pd.DataFrame({
            "Price": [num(r.price, 2) for _, r in h.iterrows()],
            "DCF": h["m_dcf"].map(num), "DCF range (WACC ±1%)": h["dcf_range"], "DDM": h["m_ddm"].map(num),
            "Relative": h["m_relative"].map(num), "Graham": h["m_graham"].map(num),
            "Analyst tgt": h["m_analyst_target"].map(num), "Blended FV": h["fair"].map(num), "Upside": h["upside"].map(pct),
            "Models in blend": h["models_used"],
            "DCF assumptions": h["dcf_note"],
        }).rename_axis("Symbol")
        sections.append(Section("Valuation Models (per share, trading currency)", paragraphs=[
            "DCF: two-stage FCFF model, growth fades to terminal rate, discounted at WACC (CAPM cost of equity + after-tax cost of debt). "
            "DDM: Gordon growth on forward dividend with sustainable growth ROE×(1−payout). Relative: forward EPS × sector median forward P/E "
            "(P/B for financials). Graham: √(22.5×EPS×BVPS). Blended FV weights: "
            + ", ".join(f"{k} {w:.0%}" for k, w in self.cfg["valuation_weights"].items()) + " (renormalised over available models)."],
            table=v))

        # Fundamentals
        f = pd.DataFrame({
            "Sector": h["sector"], "P/E": h["pe"].map(lambda x: num(x, 1)), "Fwd P/E": h["fpe"].map(lambda x: num(x, 1)),
            "P/B": h["pb"].map(lambda x: num(x, 1)), "EV/EBITDA": h["ev_ebitda"].map(lambda x: num(x, 1)),
            "ROE": h["roe"].map(lambda x: pct(x, False)), "Net margin": h["margin"].map(lambda x: pct(x, False)),
            "Rev growth": h["rev_g"].map(pct), "D/E %": h["de"].map(num),
            "Piotroski": [f"{int(r.f_score)}/{int(r.f_n)}" for _, r in h.iterrows()],
            "Altman Z": h["z"].map(lambda x: "n/a" if not np.isfinite(x) else f"{x:.2f} ({'safe' if x > 2.99 else 'grey' if x > 1.81 else 'distress'})"),
            "Street view": h["reco"].astype(str).str.replace("_", " ").str.title(),
        }).rename_axis("Symbol")
        sections.append(Section("Fundamental Health & Multiples", table=f))

        # Technicals
        tc = pd.DataFrame({
            "Trend": h.get("t_trend"), "RSI14": h["t_rsi14"].map(lambda x: num(x, 0)),
            "MACD": h["t_macd_bullish"].map(lambda x: "Bullish" if x else "Bearish"),
            "1M": h["t_ret_1m"].map(pct), "3M": h["t_ret_3m"].map(pct), "6M": h["t_ret_6m"].map(pct), "12M": h["t_ret_12m"].map(pct),
            "vs 52W high": h["t_from_52w_high"].map(pct), "50 DMA": h["t_sma50"].map(num), "200 DMA": h["t_sma200"].map(num),
        }).rename_axis("Symbol")
        sections.append(Section("Technical & Momentum Signals", table=tc))

        # Risk
        rk = pd.DataFrame({
            "Beta": h["beta"].map(lambda x: num(x, 2)), "CAPM exp. return": h["capm"].map(lambda x: pct(x, False)),
            "Volatility": h["r_volatility"].map(lambda x: pct(x, False)), "Sharpe": h["r_sharpe"].map(lambda x: num(x, 2)),
            "Sortino": h["r_sortino"].map(lambda x: num(x, 2)), "Max DD": h["r_max_drawdown"].map(pct),
            "VaR95 1d": h["r_var95_1d"].map(lambda x: pct(x, False, 2)), "Risk contrib.": rc.reindex(h.index).map(lambda x: pct(x, False)),
            "Weight": h["weight"].map(lambda x: pct(x, False)),
        }).rename_axis("Symbol")
        rows = {"My portfolio": prm, **bench_rm}
        cmp_t = pd.DataFrame({k: {"Ann. return": pct(m.get("ann_return", np.nan)), "Volatility": pct(m.get("volatility", np.nan), False),
                                  "Sharpe": num(m.get("sharpe", np.nan), 2), "Sortino": num(m.get("sortino", np.nan), 2),
                                  "Max drawdown": pct(m.get("max_drawdown", np.nan)),
                                  "VaR95 1d": pct(m.get("var95_1d", np.nan), False, 2), "CVaR95 1d": pct(m.get("cvar95_1d", np.nan), False, 2)}
                              for k, m in rows.items() if m}).T.rename_axis(f"2y, in {base}")
        alloc = [f"{k}: {pct(w, False)}" for k, w in sec_w.sort_values(ascending=False).items()]
        mkt_w = h.groupby("market")["weight"].sum()
        pairs = [(a, b, corr.loc[a, b]) for i, a in enumerate(corr.columns) for b in corr.columns[i + 1:]]
        hi_corr = [f"{a}/{b} {c:.2f}" for a, b, c in sorted(pairs, key=lambda x: -x[2])[:3]]
        sections.append(Section("Risk Analysis", paragraphs=[
            "Sector allocation: " + ", ".join(alloc),
            "Country allocation: " + ", ".join(f"{'India' if k == 'IN' else 'US'} {pct(w, False)}" for k, w in mkt_w.items()),
            "Most correlated pairs (less diversification benefit): " + ", ".join(hi_corr),
            f"Portfolio beta vs country-weighted blended benchmark: {num(prm.get('beta', np.nan), 2)}. 1-day 95% VaR ≈ {money(prm.get('var95_1d', np.nan) * total, base)}, "
            f"CVaR ≈ {money(prm.get('cvar95_1d', np.nan) * total, base)}.",
        ], table=cmp_t))
        sections.append(Section("Per-Holding Risk", table=rk))

        # Optimisation
        if opt:
            o = pd.DataFrame({"Current": h["weight"], "Max Sharpe": opt["max_sharpe"], "Min Variance": opt["min_variance"],
                              "Exp. return": exp_ret}).reindex(h.index)
            o["Suggested change"] = (o["Max Sharpe"] - o["Current"]).map(lambda x: f"{x:+.1%}")
            for c in ("Current", "Max Sharpe", "Min Variance", "Exp. return"):
                o[c] = o[c].map(lambda x: pct(x, False))
            ms, mv = opt["max_sharpe_stats"], opt["min_variance_stats"]
            sections.append(Section("Portfolio Optimisation (Markowitz Mean-Variance)", paragraphs=[
                f"Expected returns blend CAPM, 2-year history and valuation-implied return. Max weight per stock "
                f"{pct(self.cfg['optimization']['max_weight'], False, 0)}.",
                f"Current: exp. return {pct(cur_stats[0], False)}, vol {pct(cur_stats[1], False)}, Sharpe {cur_stats[2]:.2f} | "
                f"Max-Sharpe: {pct(ms[0], False)}, vol {pct(ms[1], False)}, Sharpe {ms[2]:.2f} | "
                f"Min-Variance: {pct(mv[0], False)}, vol {pct(mv[1], False)}, Sharpe {mv[2]:.2f}",
            ], table=o.rename_axis("Symbol")))

        # Holding-by-holding analyst notes
        sections.append(Section("Analyst Notes per Holding", bullets=[
            f"{s} - {r.rating}: {r.why}. Fair value {num(r.fair)} vs price {num(r.price, 2)}." for s, r in h.iterrows()]))

        # Ideas
        if not ideas.empty:
            it = pd.DataFrame({
                "Name": ideas["shortName"], "Mkt": ideas["market"], "Sector": ideas["sector"], "Score": ideas["score"].map(lambda x: f"{x:.0f}/100"),
                "Price": [money(r.price, r.currency, 2) for _, r in ideas.iterrows()],
                "Rev g": ideas["revenueGrowth"].map(pct), "EPS g": ideas["earningsGrowth"].map(pct),
                "ROE": ideas["returnOnEquity"].map(lambda x: pct(x, False)), "Fwd P/E": ideas["forwardPE"].map(lambda x: num(x, 1)),
                "DCF upside": ideas["dcf_upside"].map(pct), "Analyst upside": ideas["analyst_upside"].map(pct),
                "6M": ideas["ret_6m"].map(pct), "Thesis": ideas["thesis"],
            }).rename_axis("Symbol")
            sections.append(Section("New Growth Ideas (multi-factor screen)", paragraphs=[
                "Ranked within each market by Growth (revenue & earnings growth), Quality (ROE, margins, leverage), "
                "Valuation (PEG, forward P/E, analyst upside) and Momentum (6/12-month return, 200-DMA). "
                "Edit the universe in config.json. Always do your own due diligence before buying."], table=it))

        sections.append(Section("Disclaimer", paragraphs=[
            "This report is generated automatically from public market data (Yahoo Finance) using quantitative models. "
            "Data can be delayed, incomplete or wrong. It is for educational/informational purposes only and is NOT investment advice. "
            "Consult a SEBI/SEC-registered adviser before making investment decisions."]))

        title = f"Portfolio Analyst Report - {self.today}"
        sub = f"Generated {datetime.now():%d %b %Y %H:%M} | Base currency {base} | {len(h)} holdings"
        out_dir = self.root / self.cfg["reports_dir"]
        out_dir.mkdir(parents=True, exist_ok=True)
        html_p, md_p = out_dir / f"report_{self.today}.html", out_dir / f"report_{self.today}.md"
        html_p.write_text(report.to_html(title, sub, sections), encoding="utf-8")
        md_p.write_text(report.to_markdown(title, sub, sections), encoding="utf-8")
        (out_dir / "latest.html").write_text(html_p.read_text(encoding="utf-8"), encoding="utf-8")
        self.log(f"Report written: {html_p}")
        return {"html": html_p, "markdown": md_p, "total_value": total}
