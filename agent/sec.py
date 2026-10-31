"""Official US fallback: annual statements + basic profile from SEC EDGAR XBRL "company facts" (free, no key).

Used when Yahoo Finance blocks/throttles a US stock. Output mimics yfinance (same row names, fiscal-year-end
columns newest first) so every model works unchanged. Indian stocks have no equivalent free official API."""
import os
import threading
import time
from functools import lru_cache

import numpy as np
import pandas as pd
import requests

# SEC asks for a contact in the User-Agent. Set SEC_USER_AGENT (env or Streamlit secret) to "Your Name you@mail.com".
DEFAULT_UA = "PortfolioAnalyst stockanalyzer@example.com"
_LOCK = threading.Lock()
_last = [0.0]


def _ua() -> str:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        try:
            import streamlit as st
            ua = st.secrets.get("SEC_USER_AGENT")
        except Exception:
            ua = None
    return ua or DEFAULT_UA


def _get(url: str):
    for ua in (_ua(), DEFAULT_UA):
        with _LOCK:  # SEC fair-access: max 10 requests/second
            time.sleep(max(0.0, 0.15 - (time.time() - _last[0])))
            _last[0] = time.time()
        try:
            r = requests.get(url, headers={"User-Agent": ua}, timeout=30)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return None


@lru_cache(maxsize=1)
def _tickers() -> dict:
    j = _get("https://www.sec.gov/files/company_tickers.json") or {}
    return {v["ticker"].upper(): (int(v["cik_str"]), v["title"]) for v in j.values()}


def cik(symbol: str):
    if symbol.upper().endswith((".NS", ".BO")):
        return None
    t = _tickers()
    s = symbol.upper()
    return (t.get(s) or t.get(s.replace(".", "-")) or t.get(s.replace("-", ".")) or (None,))[0]


@lru_cache(maxsize=256)
def _facts(c: int) -> dict:
    return _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c:010d}.json") or {}


@lru_cache(maxsize=256)
def _submissions(c: int) -> dict:
    return _get(f"https://data.sec.gov/submissions/CIK{c:010d}.json") or {}


ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}


def _series(facts: dict, tags, unit: str = "USD", duration: bool = True) -> pd.Series:
    """Annual values by fiscal-year-end date. Several tags are merged (companies switch tags over time)."""
    out = {}
    g = facts.get("facts", {})
    for tag in tags:
        ns, _, name = tag.rpartition(":")
        node = g.get(ns or "us-gaap", {}).get(name)
        if not node:
            continue
        rows = node.get("units", {}).get(unit, [])
        best = {}
        for r in rows:
            if r.get("form") not in ANNUAL_FORMS or "end" not in r:
                continue
            if duration:
                if "start" not in r:
                    continue
                days = (pd.Timestamp(r["end"]) - pd.Timestamp(r["start"])).days
                if not 350 <= days <= 380:
                    continue
            elif "start" in r:
                continue
            k = r["end"]
            if k not in best or r.get("filed", "") > best[k].get("filed", ""):
                best[k] = r
        for k, r in best.items():
            out.setdefault(pd.Timestamp(k), float(r["val"]))
    return pd.Series(out, dtype=float).sort_index(ascending=False)


# yfinance row name -> (XBRL tags, unit, is_duration)
INCOME = {
    "Total Revenue": (["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                       "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet"], "USD", True),
    "Cost Of Revenue": (["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"], "USD", True),
    "Gross Profit": (["GrossProfit"], "USD", True),
    "Operating Income": (["OperatingIncomeLoss"], "USD", True),
    "Interest Expense": (["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"], "USD", True),
    "Pretax Income": (["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                       "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"], "USD", True),
    "Tax Provision": (["IncomeTaxExpenseBenefit"], "USD", True),
    "Net Income": (["NetIncomeLoss", "ProfitLoss"], "USD", True),
    "Net Income Common Stockholders": (["NetIncomeLossAvailableToCommonStockholdersBasic", "NetIncomeLoss"], "USD", True),
    "Basic EPS": (["EarningsPerShareBasic"], "USD/shares", True),
    "Diluted EPS": (["EarningsPerShareDiluted"], "USD/shares", True),
    "Diluted Average Shares": (["WeightedAverageNumberOfDilutedSharesOutstanding"], "shares", True),
    "Reconciled Depreciation": (["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                                 "DepreciationAmortizationAndAccretionNet", "Depreciation"], "USD", True),
}
BALANCE = {
    "Total Assets": (["Assets"], "USD", False),
    "Current Assets": (["AssetsCurrent"], "USD", False),
    "Current Liabilities": (["LiabilitiesCurrent"], "USD", False),
    "Total Liabilities Net Minority Interest": (["Liabilities"], "USD", False),
    "Stockholders Equity": (["StockholdersEquity"], "USD", False),
    "Total Equity": (["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"], "USD", False),
    "Retained Earnings": (["RetainedEarningsAccumulatedDeficit"], "USD", False),
    "Cash And Cash Equivalents": (["CashAndCashEquivalentsAtCarryingValue",
                                   "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"], "USD", False),
    "Short Term Investments": (["MarketableSecuritiesCurrent", "ShortTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"], "USD", False),
    "Long Term Debt": (["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "LongTermDebt"], "USD", False),
    "Current Debt": (["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings", "CommercialPaper"], "USD", False),
    "Ordinary Shares Number": (["CommonStockSharesOutstanding"], "shares", False),
}
CASHFLOW = {
    "Operating Cash Flow": (["NetCashProvidedByUsedInOperatingActivities",
                             "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"], "USD", True),
    "Capital Expenditure": (["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"], "USD", True),
    "Cash Dividends Paid": (["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"], "USD", True),
    "Repurchase Of Capital Stock": (["PaymentsForRepurchaseOfCommonStock"], "USD", True),
    "Depreciation And Amortization": (["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                                       "DepreciationAmortizationAndAccretionNet", "Depreciation"], "USD", True),
}
OUTFLOWS = {"Capital Expenditure", "Cash Dividends Paid", "Repurchase Of Capital Stock"}  # yfinance shows these negative


def _frame(facts: dict, spec: dict, years: int = 5) -> pd.DataFrame:
    rows = {name: _series(facts, tags, unit, dur) for name, (tags, unit, dur) in spec.items()}
    rows = {k: (-v.abs() if k in OUTFLOWS else v) for k, v in rows.items() if len(v)}
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).T
    key = next((k for k in ("Total Revenue", "Total Assets", "Operating Cash Flow", "Net Income") if k in df.index), None)
    cols = df.loc[key].dropna().index if key else df.columns
    df = df[sorted(cols, reverse=True)[:years]]
    return df


def _derive(kind: str, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    r = lambda n: df.loc[n] if n in df.index else pd.Series(np.nan, index=df.columns)
    add = {}
    if kind == "financials":
        if "Gross Profit" not in df.index:
            add["Gross Profit"] = r("Total Revenue") - r("Cost Of Revenue")
        add["EBIT"] = r("Operating Income")
        add["EBITDA"] = add["Normalized EBITDA"] = r("Operating Income") + r("Reconciled Depreciation")
        add["Interest Expense Non Operating"] = r("Interest Expense")
        add["Tax Rate For Calcs"] = (r("Tax Provision") / r("Pretax Income")).clip(0, 0.5)
    elif kind == "balance_sheet":
        add["Common Stock Equity"] = r("Stockholders Equity")
        add["Working Capital"] = r("Current Assets") - r("Current Liabilities")
        add["Cash Cash Equivalents And Short Term Investments"] = r("Cash And Cash Equivalents") + r("Short Term Investments").fillna(0)
        add["Total Debt"] = r("Long Term Debt").fillna(0) + r("Current Debt").fillna(0)
        if "Total Liabilities Net Minority Interest" not in df.index:
            add["Total Liabilities Net Minority Interest"] = r("Total Assets") - r("Total Equity")
        add["Share Issued"] = r("Ordinary Shares Number")
    elif kind == "cashflow":
        add["Free Cash Flow"] = r("Operating Cash Flow") + r("Capital Expenditure").fillna(0)
        add["Common Stock Dividend Paid"] = r("Cash Dividends Paid")
    for k, v in add.items():
        if k not in df.index and v.notna().any():
            df.loc[k] = v
    return df


def statement(symbol: str, kind: str) -> pd.DataFrame:
    """kind as in yfinance: 'financials' | 'balance_sheet' | 'cashflow' (annual only)."""
    spec = {"financials": INCOME, "balance_sheet": BALANCE, "cashflow": CASHFLOW}.get(kind)
    c = cik(symbol) if spec else None
    if not c:
        return pd.DataFrame()
    try:
        return _derive(kind, _frame(_facts(c), spec))
    except Exception:
        return pd.DataFrame()


def _sector(sic) -> str:
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return None
    ranges = [((6000, 6499), "Financial Services"), ((6500, 6799), "Real Estate"), ((7370, 7379), "Technology"),
              ((3570, 3579), "Technology"), ((3600, 3699), "Technology"), ((3820, 3829), "Technology"),
              ((2830, 2839), "Healthcare"), ((3840, 3851), "Healthcare"), ((8000, 8099), "Healthcare"),
              ((1300, 1399), "Energy"), ((2900, 2999), "Energy"), ((4900, 4949), "Utilities"),
              ((4800, 4899), "Communication Services"), ((7800, 7899), "Communication Services"),
              ((2000, 2199), "Consumer Defensive"), ((5400, 5499), "Consumer Defensive"),
              ((5000, 5999), "Consumer Cyclical"), ((3710, 3719), "Consumer Cyclical"), ((7000, 7099), "Consumer Cyclical"),
              ((1000, 1499), "Basic Materials"), ((2800, 2829), "Basic Materials"), ((3300, 3399), "Basic Materials"),
              ((1500, 1799), "Industrials"), ((3400, 3569), "Industrials"), ((3580, 3599), "Industrials"),
              ((3700, 3799), "Industrials"), ((4000, 4799), "Industrials")]
    return next((name for (lo, hi), name in ranges if lo <= s <= hi), "Industrials" if 2000 <= s < 4000 else None)


def info(symbol: str, price: float = np.nan) -> dict:
    """yfinance-style profile built from filings. Market-based fields use the supplied live price."""
    c = cik(symbol)
    if not c:
        return {}
    fin, bs, cf = (statement(symbol, k) for k in ("financials", "balance_sheet", "cashflow"))
    if fin.empty and bs.empty:
        return {}
    sub = _submissions(c)
    f = lambda df, n, i=0: float(df.loc[n].dropna().iloc[i]) if n in df.index and len(df.loc[n].dropna()) > i else np.nan
    ni, rev, rev1, ni1 = f(fin, "Net Income"), f(fin, "Total Revenue"), f(fin, "Total Revenue", 1), f(fin, "Net Income", 1)
    eq, debt, cash = f(bs, "Stockholders Equity"), f(bs, "Total Debt"), f(bs, "Cash Cash Equivalents And Short Term Investments")
    sh = f(bs, "Ordinary Shares Number")
    if not np.isfinite(sh):
        sh = f(fin, "Diluted Average Shares")
    eps = f(fin, "Diluted EPS")
    ebitda = f(fin, "EBITDA")
    div = -f(cf, "Cash Dividends Paid") if np.isfinite(f(cf, "Cash Dividends Paid")) else 0.0
    p = float(price) if price is not None and np.isfinite(price) else np.nan
    mcap = p * sh if np.isfinite(p) and np.isfinite(sh) else np.nan
    ev = mcap + debt - cash if np.isfinite(mcap) else np.nan
    q = lambda a, b: a / b if np.isfinite(a) and np.isfinite(b) and b else None
    out = {
        "longName": sub.get("name") or _tickers().get(symbol.upper(), (None, None))[1],
        "shortName": sub.get("name") or _tickers().get(symbol.upper(), (None, None))[1],
        "quoteType": "EQUITY", "currency": "USD", "financialCurrency": "USD",
        "sector": _sector(sub.get("sic")), "industry": (sub.get("sicDescription") or "").title() or None,
        "website": sub.get("website") or None, "country": "United States",
        "city": (sub.get("addresses", {}).get("business", {}) or {}).get("city"),
        "currentPrice": p if np.isfinite(p) else None, "marketCap": mcap if np.isfinite(mcap) else None,
        "enterpriseValue": ev if np.isfinite(ev) else None, "sharesOutstanding": sh if np.isfinite(sh) else None,
        "trailingEps": eps if np.isfinite(eps) else None, "trailingPE": q(p, eps) if np.isfinite(eps) and eps > 0 else None,
        "bookValue": q(eq, sh), "priceToBook": q(mcap, eq), "returnOnEquity": q(ni, eq), "profitMargins": q(ni, rev),
        "revenueGrowth": (q(rev, rev1) - 1) if q(rev, rev1) else None,
        "earningsGrowth": (q(ni, ni1) - 1) if q(ni, ni1) and ni1 > 0 else None,
        "debtToEquity": q(debt * 100, eq), "ebitda": ebitda if np.isfinite(ebitda) else None,
        "enterpriseToEbitda": q(ev, ebitda), "totalDebt": debt if np.isfinite(debt) else None,
        "totalCash": cash if np.isfinite(cash) else None,
        "payoutRatio": q(div, ni) if div and ni > 0 else 0.0,
        "dividendRate": q(div, sh) if div else None, "trailingAnnualDividendRate": q(div, sh) if div else None,
        "dividendYield": (q(div, mcap) * 100) if div and q(div, mcap) else None,
        "_source": "SEC EDGAR",
    }
    return {k: v for k, v in out.items() if v is not None}
