"""Self-paced lessons: reading financial statements and valuing a company like a professional analyst."""

LESSONS = [
    ("1 · How to read an annual report", """
An annual report is the company's own account of the year. Professional analysts read it in this order:

| Order | Section | What you are looking for |
|---|---|---|
| 1 | **Auditor's report** | An *unqualified / unmodified* opinion is normal. "Qualified opinion", "emphasis of matter" or "going concern" are red flags - read them first. |
| 2 | **Financial statements** (income statement, balance sheet, cash flow) | The numbers. Always use **consolidated** statements (parent + subsidiaries) rather than standalone. |
| 3 | **Notes to accounts** | Where the detail hides: debt maturity, contingent liabilities, related-party transactions, accounting policy changes, segment results. |
| 4 | **Management discussion & analysis (MD&A)** | Management's explanation of the numbers, outlook, capacity plans, risks. Compare last year's promises with this year's results. |
| 5 | **Chairman / CEO letter** | Tone and strategy. Useful, but it is marketing - verify against the numbers. |

**India specifics:** financial year ends 31 March (FY2025 = Apr 2024-Mar 2025); figures are in ₹ crore (1 Cr = 10 million); check promoter holding and **pledged shares** in the shareholding pattern (filed quarterly on NSE/BSE).
**US specifics:** the annual report is the **10-K** (quarterly: 10-Q) on SEC EDGAR; "Item 1A Risk Factors" and "Item 7 MD&A" are the key sections.

**Pro habit:** never judge a single year. Lay out at least 5 years side by side and look for *trends* and *breaks in trend*.
"""),
    ("2 · The income statement (profit & loss)", """
The income statement shows **performance over a period**: what came in, what it cost, what was left.

```
  Revenue (sales)
- Cost of goods sold (raw materials, direct labour)
= GROSS PROFIT                  -> pricing power & production efficiency
- Operating expenses (salaries, rent, marketing, R&D)
= EBITDA                        -> cash-like operating profit, before D&A
- Depreciation & amortisation (D&A)
= EBIT / OPERATING PROFIT       -> profit from the core business
- Interest expense
+ Other income
= PROFIT BEFORE TAX
- Tax
= NET PROFIT (PAT)              -> belongs to shareholders
÷ Shares outstanding
= EPS (earnings per share)
```

**Read it with margins, not absolute numbers** - divide every line by revenue:
- **Gross margin** = Gross profit / Revenue. High and stable (40%+) suggests pricing power (brands, software). Falling margins mean costs rising faster than prices.
- **Operating margin** = EBIT / Revenue. Shows operating leverage: if revenue grows 10% and EBIT grows 20%, fixed costs are being spread.
- **Net margin** = Net profit / Revenue.

**Red flags:** profit growing much faster than revenue for years (cost cutting runs out); large or recurring "exceptional items"; "other income" forming a big share of profit; rising receivables with flat sales.
"""),
    ("3 · The balance sheet", """
The balance sheet is a **snapshot on one date** of what the company owns and owes. It always balances:

> **Assets = Liabilities + Shareholders' equity**

| Assets (what it owns) | Liabilities + Equity (how it was funded) |
|---|---|
| **Current assets** - cash, receivables, inventory (turn into cash within 12 months) | **Current liabilities** - payables, short-term debt (due within 12 months) |
| **Non-current assets** - plant & equipment, intangibles, goodwill, long-term investments | **Non-current liabilities** - long-term debt, leases, provisions |
| | **Equity** - share capital + retained earnings (accumulated profits not paid out) |

Key questions an analyst asks:
1. **Can it pay its bills?** Current ratio = Current assets / Current liabilities. Above 1.5 comfortable; below 1 needs explanation (some retailers and FMCG companies run negative working capital deliberately).
2. **How much debt?** Debt / Equity. Below 0.5 conservative, above 1.5 aggressive (banks and utilities are exceptions). **Net debt** = Debt - Cash; negative means net cash.
3. **Quality of assets?** Large **goodwill** means past acquisitions - if they disappoint, it gets written off. Rising **receivables** or **inventory** faster than sales can signal channel stuffing or weak demand.
4. **Book value per share** = Equity / Shares. Used for P/B and the Graham number.

**Pro habit:** compare two balance sheets - the *change* tells you where money went this year.
"""),
    ("4 · The cash flow statement", """
Profit is an opinion (it depends on accounting choices); **cash is a fact**. The cash flow statement has three parts:

| Section | Contains | Healthy company |
|---|---|---|
| **Operating (CFO)** | Net profit + non-cash items (depreciation) ± working capital changes | Positive, roughly ≥ net profit |
| **Investing (CFI)** | Capex (new plants, equipment), acquisitions, investments | Negative (it is investing to grow) |
| **Financing (CFF)** | Borrowing / repaying debt, issuing shares, dividends, buybacks | Depends on stage: young firms raise, mature firms return cash |

**Free cash flow (FCF) = Operating cash flow - Capital expenditure.** This is the cash that could be paid to all investors without hurting the business, and it is the engine of the DCF model.

**Cash conversion = CFO / Net profit.** Consistently below ~0.8 means profits are not turning into cash - check receivables and inventory. This is one of the most reliable early warnings of aggressive accounting.

Patterns to recognise:
- **+ CFO, - CFI, - CFF**: mature, self-funding, returning cash. Ideal.
- **+ CFO, - CFI, + CFF**: growing faster than internal cash allows - fine if returns on capital are high.
- **- CFO, + CFF**: business burns cash and depends on investors/lenders. High risk.
"""),
    ("5 · How the three statements connect", """
1. **Net profit** (income statement) is the first line of the **cash flow statement**.
2. Net profit minus dividends is added to **retained earnings** (balance sheet equity).
3. **Capex** (cash flow) increases **property, plant & equipment** (balance sheet); **depreciation** (income statement) reduces it.
4. New **borrowing** (cash flow, financing) increases **debt** (balance sheet); its **interest** shows up in the income statement.
5. The net change in cash on the cash flow statement equals the change in **cash** on the balance sheet.

**DuPont analysis** links them to explain *why* ROE is what it is:

> **ROE = Net margin × Asset turnover × Equity multiplier**
> = (Net profit / Revenue) × (Revenue / Assets) × (Assets / Equity)

Two companies with 20% ROE can be very different: one earns it through high margins (quality), the other through high leverage (risk). The "Explain a stock" tab computes this for any company.
"""),
    ("6 · Ratios: the analyst's toolkit", """
| Category | Ratio | Formula | Rule of thumb |
|---|---|---|---|
| Growth | Revenue / profit growth | This year / last year - 1 | Compare with industry and inflation; consistency matters more than one big year |
| Profitability | ROE | Net profit / Equity | > 15% good, > 20% excellent (check leverage) |
| | ROCE | EBIT / (Total assets - Current liabilities) | Should exceed the cost of capital (≈ 12% India, ≈ 8% US) |
| | Margins | Gross / Operating / Net ÷ Revenue | Compare within the industry only |
| Leverage | Debt / Equity | Total debt / Equity | < 0.5 conservative, > 1.5 aggressive |
| | Interest coverage | EBIT / Interest expense | > 5x safe, < 3x risky, < 1.5x danger |
| Liquidity | Current ratio | Current assets / Current liabilities | 1.2-2 typical |
| Cash quality | Cash conversion | Operating cash flow / Net profit | ≈ 1 or above |
| | FCF margin | Free cash flow / Revenue | Higher = more cash-generative |
| Valuation | P/E | Price / EPS | Compare with growth (PEG = P/E ÷ growth %, < 1.5 reasonable) |
| | P/B | Price / Book value per share | Key for banks/financials |
| | EV/EBITDA | (Market cap + Debt - Cash) / EBITDA | Capital-structure neutral; good for comparing peers |
| | Dividend yield | Dividend per share / Price | Check payout is sustainable (< 70-80% of profit) |

**Never use a ratio alone.** A low P/E can mean "cheap" or "the market expects profits to fall". Always ask *why* the ratio is what it is.
"""),
    ("7 · Valuation models (how fair value is calculated)", """
**Cost of equity (CAPM)** - the return shareholders demand for the risk:
> Cost of equity = Risk-free rate + Beta × Equity risk premium

Beta measures how much the stock moves with the market (1.0 = same, 1.5 = 50% more volatile).

**WACC** - blended cost of all capital:
> WACC = (E / (D+E)) × Cost of equity + (D / (D+E)) × Cost of debt × (1 - tax rate)

**Discounted Cash Flow (DCF)** - a business is worth the cash it will produce, discounted to today:
1. Start from today's free cash flow.
2. Project it forward (here 10 years: high growth for 5 years, fading to long-term growth).
3. Discount each year: PV = FCF ÷ (1 + WACC)^year.
4. **Terminal value** for everything after year 10: FCF₁₀ × (1 + g) ÷ (WACC - g).
5. Enterprise value = sum of PVs + PV of terminal value.
6. Equity value = Enterprise value + Cash - Debt. Divide by shares → value per share.

DCF is very sensitive to WACC and growth - a 1% change can move value 15-25%. That is why we show a sensitivity range and the interactive sliders.

**Dividend Discount Model (Gordon growth)** - for steady dividend payers:
> Value = Next year's dividend ÷ (Cost of equity - Dividend growth), where sustainable growth = ROE × (1 - payout ratio).

**Relative valuation** - what similar companies trade at: Value = Forward EPS × sector median P/E (banks: Book value × sector P/B).

**Graham number** - Benjamin Graham's ceiling price for a defensive investor: √(22.5 × EPS × Book value per share) (22.5 = max P/E 15 × max P/B 1.5).

**Blended fair value** - no single model is right, so professionals triangulate. This app weights DCF 40%, relative 25%, analyst consensus 15%, DDM 10%, Graham 10%, using only the models that suit the business (DDM only for payout ≥ 40%, Graham only for P/E ≤ 25, no DCF for banks).
**Margin of safety:** buy meaningfully below fair value (20-30%), because every input is an estimate.
"""),
    ("8 · Quality & distress scores", """
**Piotroski F-score (0-9)** - nine yes/no tests on profitability, leverage/liquidity and efficiency, comparing this year with last year:

| # | Test | Passes if |
|---|---|---|
| 1 | Net income | > 0 |
| 2 | Return on assets | > 0 |
| 3 | Operating cash flow | > 0 |
| 4 | Earnings quality | Operating cash flow > Net income |
| 5 | Leverage | Long-term debt / assets fell |
| 6 | Liquidity | Current ratio rose |
| 7 | Dilution | No new shares issued |
| 8 | Margin | Gross margin rose |
| 9 | Efficiency | Asset turnover (revenue / assets) rose |

7-9 = strong and improving; 0-3 = weak. Best used to separate good from bad among *cheap* stocks.

**Altman Z-score** - predicts bankruptcy risk within ~2 years (manufacturing/industrial companies; not for banks):
> Z = 1.2·(Working capital/Assets) + 1.4·(Retained earnings/Assets) + 3.3·(EBIT/Assets) + 0.6·(Market cap/Liabilities) + 1.0·(Sales/Assets)

Z > 2.99 safe · 1.81-2.99 grey zone · < 1.81 distress.
"""),
    ("9 · Technicals & risk", """
Fundamentals tell you **what** to buy; technicals help with **when**.

- **Moving averages:** 50-day and 200-day average price. Price and 50-DMA above the 200-DMA = **uptrend**; both below = **downtrend**.
- **RSI (14)** - speed of recent moves, 0-100. Above 70 overbought (do not chase), below 30 oversold (possible entry if fundamentals are fine).
- **MACD** - 12-day EMA minus 26-day EMA; crossing above its 9-day signal line = momentum turning up.
- **52-week high/low distance** - context for where the price sits in its recent range.

Risk measures (from 2 years of daily returns):
- **Volatility** - annualised standard deviation of returns. Large caps ≈ 20-30%.
- **Beta** - sensitivity to the benchmark (Nifty 50 / S&P 500).
- **Sharpe ratio** = (Return - Risk-free rate) / Volatility. Return per unit of risk; > 1 is good.
- **Sortino** - like Sharpe but only penalises downside volatility.
- **Maximum drawdown** - worst peak-to-trough fall. Ask yourself: could I hold through this?
- **VaR 95% (1-day)** - on 1 trading day in 20 you should expect to lose at least this much.
"""),
    ("10 · The professional analyst's checklist", """
Work through this before buying anything:

**Business**
- [ ] Can I explain how it makes money in two sentences?
- [ ] What is its moat (brand, network effect, cost advantage, switching costs, licences)?
- [ ] Is the industry growing? Who are the 3 main competitors?

**Numbers (5+ years)**
- [ ] Revenue and profit growing consistently?
- [ ] ROE / ROCE above cost of capital, and stable or rising?
- [ ] Margins stable or expanding?
- [ ] Cash conversion ≈ 1; free cash flow positive?
- [ ] Debt / Equity reasonable; interest coverage > 5x?

**Management & governance**
- [ ] Clean auditor's report; no frequent auditor changes?
- [ ] Promoter / insider holding stable, **no pledging** (India)?
- [ ] Related-party transactions small? Capital allocation sensible (no empire-building acquisitions)?

**Valuation**
- [ ] Price below blended fair value with a margin of safety?
- [ ] P/E reasonable relative to growth (PEG) and to its own 5-year history?
- [ ] What has to go right for the current price to make sense? Is that realistic?

**Position**
- [ ] Position size ≤ 10-15% of the portfolio; sector exposure not excessive?
- [ ] What would make me sell (thesis broken), written down **before** buying?
"""),
]
