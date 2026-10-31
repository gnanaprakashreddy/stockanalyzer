# AI Portfolio Analyst Agent (India + US)

A quantitative "sell-side analyst" for your portfolio. Every weekday it pulls market data from Yahoo Finance, runs a set of valuation, risk and portfolio models, and writes an HTML + Markdown report with ratings, actions and new stock ideas.

It runs in two ways, both free and with no broker API keys:
- **Web app** (`app.py`): a search bar for detailed analysis of any Indian or US stock, a portfolio dashboard and new stock ideas. Use it locally or host it free on Streamlit Community Cloud.
- **Daily report** (`run_agent.py`): a Windows scheduled task that writes an HTML + Markdown report every weekday.

## Your holdings (`portfolio.csv`)
```
symbol,quantity,avg_cost,broker
RELIANCE.NS,10,1250,Groww      # NSE -> .NS, BSE -> .BO, cost in INR
AAPL,5,190,Vested              # US tickers as-is, cost in USD
```
`broker` is optional (used only for the "by broker" breakdown). Duplicate symbols are merged at a weighted average cost.
This file is git-ignored so it is never uploaded.

## Web app
Run locally: `.\.venv\Scripts\python.exe -m streamlit run app.py`, then open http://localhost:8501.

| Page | What you get |
|---|---|
| 🔍 **Stock Analysis** | Search by company name or ticker. Shows the analyst rating, blended fair value and reasons, plus these tabs: **Overview** (key multiples, 5y price with 50/200-DMA), **Valuation** (every model plus an interactive DCF with sliders), **Annual Reports** (income statement, balance sheet and cash flow, annual or quarterly; 13 derived ratios by year; an auto-written analyst read; links to full annual reports on Screener.in/NSE/BSE or SEC EDGAR), **Fundamentals & Quality** (Piotroski breakdown, Altman Z), **Technicals** (RSI, MACD, returns), **Risk** (vs benchmark, drawdown), **Company** profile |
| 💼 **My Portfolio** | Holdings with live value in INR, P&L, today's change, weights, fair value and rating. Sector/market/broker allocation, portfolio risk and risk contribution. Edit, upload or download the CSV in the browser. One click generates the full analyst report. |
| 💡 **New Ideas** | Top stocks per market from the multi-factor screen, each with a short thesis |
| 📚 **Learn** | 10 lessons on reading financial statements like a pro, plus **Explain a stock**: every number on the analysis page (statements, ratios, DuPont, WACC/DCF, DDM, multiples, Graham, Piotroski, Altman, technicals, risk, rating) worked through step by step with the company's real figures |

Holdings source, in priority order: edits or uploads made in the browser (current session only), then the `portfolio_csv` secret, then the local `portfolio.csv`.

### Free hosting on Streamlit Community Cloud
1. Push this folder to a **private** GitHub repository. `.gitignore` keeps out `portfolio.csv`, reports and secrets.
2. Go to https://share.streamlit.io, sign in with GitHub, click **Create app** and pick the repo, branch `main` and file `app.py`. Under **Advanced settings**, choose Python **3.12**.
3. In **Advanced settings -> Secrets**, paste the contents of `.streamlit/secrets.toml.example`, then edit it:
   - `app_password`: the password that protects the app.
   - `portfolio_csv`: your holdings.
4. Deploy. You get a URL like `https://<name>.streamlit.app`. Bookmark it on your phone.

Notes:
- Free apps sleep after a few days without visits; the first visit wakes them in about a minute.
- To update holdings, edit the `portfolio_csv` secret, or use the in-app editor and download the CSV.
- Data is cached for 1 hour; use **🔄 Refresh market data** to force fresh data.

## Daily report (local)
1. Run it: `.\.venv\Scripts\python.exe run_agent.py --open`
2. The scheduled task runs automatically at 08:00 Mon-Fri. To change the time: `powershell -ExecutionPolicy Bypass -File .\setup_scheduler.ps1 -Time "18:30"`.
3. Open `reports\latest.html` for the newest report. Logs go to `reports\agent.log`.

Options: `--no-screener` (faster, holdings only), `--portfolio other.csv`, `--config other.json`.

## What the analyst does
| Area | Models |
|---|---|
| Intrinsic value | Two-stage **DCF** (FCFF, WACC from CAPM + after-tax cost of debt, growth fade, terminal value, ±1% WACC sensitivity), **Dividend Discount Model** (Gordon), **Graham Number** |
| Relative value | Forward EPS × same-market sector median P/E (P/B for banks), consensus analyst target |
| Fair value | Weighted blend of applicable models (DDM only for payout ≥ 40%, Graham only for P/E ≤ 25, DCF skipped for financials) |
| Quality | **Piotroski F-score**, **Altman Z-score**, ROE, margins, leverage |
| Technicals | 50/200-DMA trend, RSI(14), MACD, 1/3/6/12-month momentum, distance from 52-week high |
| Risk | Beta, CAPM expected return, volatility, Sharpe, Sortino, max drawdown, historical **VaR/CVaR**, risk contribution, correlations, sector/country concentration, vs Nifty 50 / S&P 500 / blended benchmark (all in INR) |
| Portfolio construction | **Markowitz mean-variance** (Monte-Carlo frontier): max-Sharpe and min-variance weights with a per-stock cap and suggested changes |
| New ideas | Multi-factor screen (Growth, Quality, Valuation, Momentum) over an editable India + US universe, with DCF upside and a written thesis |
| Day-by-day tracking | Daily snapshot in `data\history`, value history chart, change since last report, rating changes |

Each holding gets a rating (Strong Buy / Buy-Accumulate / Hold / Reduce / Sell) from valuation upside, trend, RSI and financial-health scores.

## Customising (`config.json`)
- `markets`: risk-free rate, equity risk premium, terminal growth and tax rate per market (update these periodically).
- `valuation_weights`: weights of each model in the blended fair value.
- `optimization.max_weight`: per-stock concentration limit.
- `screener.universe`: tickers scanned for new ideas; `top_n_per_market` controls how many are shown.

## Disclaimer
Educational tool only, not investment advice. Yahoo Finance data can be delayed or wrong, and model outputs depend on the assumptions in `config.json`.
