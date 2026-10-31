"""Annual-report style financial statements, ratios and auto-commentary."""
import numpy as np
import pandas as pd

from . import data

INCOME = [("Revenue", ["Total Revenue"]), ("Gross profit", ["Gross Profit"]), ("EBITDA", ["EBITDA", "Normalized EBITDA"]),
          ("Operating profit (EBIT)", ["EBIT", "Operating Income"]), ("Interest expense", ["Interest Expense"]),
          ("Net profit", ["Net Income", "Net Income Common Stockholders"]), ("EPS (diluted)", ["Diluted EPS", "Basic EPS"])]
BALANCE = [("Total assets", ["Total Assets"]), ("Total liabilities", ["Total Liabilities Net Minority Interest"]),
           ("Shareholders' equity", ["Stockholders Equity", "Common Stock Equity"]), ("Total debt", ["Total Debt"]),
           ("Cash & equivalents", ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"]),
           ("Current assets", ["Current Assets"]), ("Current liabilities", ["Current Liabilities"])]
CASHFLOW = [("Operating cash flow", ["Operating Cash Flow"]), ("Capital expenditure", ["Capital Expenditure"]),
            ("Free cash flow", ["Free Cash Flow"]), ("Dividends paid", ["Cash Dividends Paid", "Common Stock Dividend Paid"]),
            ("Share buybacks", ["Repurchase Of Capital Stock"])]


def unit(ccy: str) -> tuple:
    return (1e7, "₹ Cr") if ccy == "INR" else (1e6, f"{ccy} M")


def _extract(df: pd.DataFrame, spec, quarterly: bool = False) -> pd.DataFrame:
    rows = {}
    for label, names in spec:
        s = data.row(df, *names)
        if not s.empty:
            rows[label] = s
    out = pd.DataFrame(rows).T
    if out.empty:
        return out
    out = out[sorted(out.columns, reverse=True)]
    fmt = (lambda c: c.strftime("%b %Y")) if quarterly else (lambda c: f"FY{c.year} ({c.strftime('%b')})")
    out.columns = [fmt(c) if hasattr(c, "year") else str(c) for c in out.columns]
    return out


def statements(symbol: str, quarterly: bool = False) -> dict:
    p = "quarterly_" if quarterly else ""
    fin = data.statement(symbol, f"{p}financials")
    bs = data.statement(symbol, f"{p}balance_sheet")
    cf = data.statement(symbol, f"{p}cashflow")
    return {"income": _extract(fin, INCOME, quarterly), "balance": _extract(bs, BALANCE, quarterly),
            "cashflow": _extract(cf, CASHFLOW, quarterly)}


def scaled(df: pd.DataFrame, ccy: str) -> pd.DataFrame:
    div, _ = unit(ccy)
    out = df.copy().astype(float)
    mask = [i for i in out.index if not i.startswith("EPS")]
    out.loc[mask] = out.loc[mask] / div
    return out


def ratios(st: dict) -> pd.DataFrame:
    inc, bal, cf = st["income"], st["balance"], st["cashflow"]
    cols = list(inc.columns)
    g = lambda df, r: df.loc[r].reindex(cols) if r in df.index else pd.Series(np.nan, index=cols)
    rev, gp, ebit, ni = g(inc, "Revenue"), g(inc, "Gross profit"), g(inc, "Operating profit (EBIT)"), g(inc, "Net profit")
    intr = g(inc, "Interest expense").abs()
    ta, eq, debt = g(bal, "Total assets"), g(bal, "Shareholders' equity"), g(bal, "Total debt")
    ca, cl = g(bal, "Current assets"), g(bal, "Current liabilities")
    ocf, fcf = g(cf, "Operating cash flow"), g(cf, "Free cash flow")
    r = pd.DataFrame({
        "Revenue growth": rev / rev.shift(-1) - 1,
        "Profit growth": ni / ni.shift(-1) - 1,
        "Gross margin": gp / rev,
        "Operating margin": ebit / rev,
        "Net margin": ni / rev,
        "ROE": ni / eq,
        "ROA": ni / ta,
        "ROCE": ebit / (ta - cl),
        "Debt / Equity": debt / eq,
        "Current ratio": ca / cl,
        "Interest coverage (x)": ebit / intr.replace(0, np.nan),
        "Cash conversion (OCF/NI)": ocf / ni,
        "FCF margin": fcf / rev,
    }).T
    return r.replace([np.inf, -np.inf], np.nan).dropna(how="all")


def commentary(st: dict, rt: pd.DataFrame) -> list:
    """Plain-English observations an analyst would draw from the annual reports."""
    notes = []
    inc = st["income"]
    if "Revenue" in inc.index:
        rev = inc.loc["Revenue"].dropna()
        if len(rev) >= 2 and rev.iloc[-1] > 0:
            n = len(rev) - 1
            cagr = (rev.iloc[0] / rev.iloc[-1]) ** (1 / n) - 1
            notes.append(f"Revenue grew at a {cagr:.1%} CAGR over the last {n} years "
                         f"({'strong' if cagr > 0.15 else 'healthy' if cagr > 0.08 else 'modest' if cagr > 0 else 'declining'}).")
    if "Net profit" in inc.index:
        ni = inc.loc["Net profit"].dropna()
        if len(ni) >= 2 and ni.iloc[-1] > 0 and ni.iloc[0] > 0:
            n = len(ni) - 1
            notes.append(f"Net profit CAGR {((ni.iloc[0] / ni.iloc[-1]) ** (1 / n) - 1):.1%} over {n} years.")
        elif len(ni) and ni.iloc[0] < 0:
            notes.append("The company reported a net loss in the latest year.")

    def trend(name, good_up=True, fmt="{:.1%}"):
        if name not in rt.index:
            return
        s = rt.loc[name].dropna()
        if len(s) < 2:
            return
        d = s.iloc[0] - s.iloc[-1]
        word = "improved" if (d > 0) == good_up else "deteriorated"
        if abs(d) < (0.01 if "%" in fmt else 0.05):
            word = "was stable"
            notes.append(f"{name} {word} at {fmt.format(s.iloc[0])}.")
        else:
            notes.append(f"{name} {word} from {fmt.format(s.iloc[-1])} to {fmt.format(s.iloc[0])}.")

    trend("Operating margin")
    trend("Net margin")
    trend("ROE")
    trend("Debt / Equity", good_up=False, fmt="{:.2f}")
    if "Cash conversion (OCF/NI)" in rt.index:
        cc = rt.loc["Cash conversion (OCF/NI)"].dropna()
        if len(cc):
            m = cc.mean()
            notes.append(f"Average cash conversion {m:.2f}x - "
                         + ("profits are well backed by cash." if m >= 1 else "earnings quality needs a closer look (cash flow below profit)."))
    if "Interest coverage (x)" in rt.index:
        ic = rt.loc["Interest coverage (x)"].dropna()
        if len(ic) and ic.iloc[0] < 3:
            notes.append(f"Interest coverage is low at {ic.iloc[0]:.1f}x - debt servicing is a risk.")
    return notes


def report_links(symbol: str, inf: dict) -> list:
    """Where to read the full annual reports."""
    base = symbol.split(".")[0]
    links = []
    if symbol.endswith((".NS", ".BO")):
        links += [("Screener.in - annual reports & 10y financials", f"https://www.screener.in/company/{base}/consolidated/"),
                  ("NSE - annual reports", f"https://www.nseindia.com/get-quotes/equity?symbol={base}"),
                  ("BSE - corporate filings", f"https://www.bseindia.com/stock-share-price/x/{base}/")]
    else:
        links += [("SEC EDGAR - 10-K annual reports", f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&ticker={base}&type=10-K"),
                  ("SEC EDGAR - 10-Q quarterly reports", f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&ticker={base}&type=10-Q")]
    site = str(inf.get("website") or "")
    if site.startswith(("https://", "http://")):
        links.append(("Company investor website", site))
    return links
