# Design: Indian market conversion of the Trader skill

Date: 2026-10-26
Status: approved in brainstorming, awaiting written-spec review

## 1. Goal and scope

Convert the Trader skill pack from the US market to the Indian market (NSE, Zerodha Kite) and remove every US-specific piece.

- **User:** one person, investing on their own Zerodha account through the Kite MCP connector in Claude.
- **Instruments:** NSE equities and ETFs, delivery (CNC) and intraday (MIS). F&O, NRML, commodities and currency are out of scope and always blocked.
- **Live only:** Kite has no sandbox and the user chose no paper mode. Every order a ticket describes is a real-money order. Safety comes from cautious default limits, the three-gate approval model and fresh-data checks.
- **Removed entirely:** SEC EDGAR (13F, XBRL, 8-K), OpenFIGI, CUSIP mapping, House PTRs, the NYSE calendar, Alpaca and IBKR, US tax (wash sales, US holding periods), USD and notional orders, Yahoo RSS/chart feeds, and their fixtures, tests and docs.

Success criteria:
1. All 11 skills work end to end for NSE stocks, in rupees and IST.
2. No US data source, broker, calendar or tax rule remains in code, fixtures or docs.
3. No order can reach Kite without the three gates, and `check.py` blocks every rule violation listed in section 4.
4. `python3 -m unittest discover -s tests` passes offline after every phase.

## 2. Skill map

The pack stays at 11 skills. `trader-pelosi` is renamed `trader-insider`.

| Skill | Indian behaviour | Source |
|---|---|---|
| trader-copycat | `--investor NAME`: holdings of more than 1% from quarterly NSE shareholding patterns (partial portfolio; weights derived from holding value). `--fund NAME --file portfolio.csv`: full monthly AMC portfolio, with weights from % of NAV. Quarter (or month) diff: new, added, trimmed, sold. Writes `trader/targets.json`. | NSE, user CSV |
| trader-news | NSE corporate announcements for held and watched symbols, with categories (results, board meeting, dividend, pledge, acquisition) and the existing dedup state. | NSE |
| trader-insider | SEBI PIT insider trades (promoters, directors, KMP) and NSE bulk and block deals. Alerts once per new filing. Writes `trader/insider.json`. | NSE |
| trader-analyst | Quarterly results: revenue, net profit, EPS, operating margin, YoY and QoQ growth. Writes `trader/metrics.json`. | NSE integrated filing (financials) XBRL; the older results page stops at Dec 2024 |
| trader-screener | Same rule engine, rupee fields, reads Indian metrics. | none |
| trader-budget | Turns targets into whole-share quantities from Kite LTP, picks CNC or MIS, and estimates charges. Writes `trader/orders.json`. | Kite snapshot |
| trader-risk | PASS/BLOCK gate with the Indian rules in section 4. | Kite snapshot |
| trader-broker | Renders Kite `place_order` tickets marked LIVE and records the user's yes. Never calls Kite itself. | none (Claude calls Kite) |
| trader-tax | FIFO lots and Indian capital-gains rules (section 6). | Kite tradebook, lots.csv |
| trader-alerts | NSE session clock (09:15 to 15:30 IST), NSE holidays, MIS square-off warning, price targets and stops. Writes `trader/prices.json`. | Kite snapshot, NSE holidays |
| trader-rebalance | Same drift logic in rupees with whole shares. | Kite snapshot |

Shared conventions:
- Symbols are NSE trading symbols (`RELIANCE`), with `exchange: "NSE"` on orders. They resolve through a bundled copy of NSE `EQUITY_L.csv` (symbol, name, ISIN, series). Fund portfolios match by ISIN.
- Money is shown in rupees with Indian grouping (`Rs 1,25,000`, plus the rupee sign in rendered tickets). Amounts in JSON are strings.
- Times are in IST (`Asia/Kolkata`, a fixed +05:30 offset, so stdlib only and no tz database).

## 3. Data flow

### 3.1 Kite snapshot contract

Python scripts cannot call an MCP connector. Before running a script, Claude calls the Kite connector and saves the raw responses under `trader/kite/`:

| File | Kite connector call | Read by |
|---|---|---|
| `quotes.json` | quotes for the needed symbols (LTP, OHLC, upper and lower circuit) | budget, risk, alerts, rebalance, screener |
| `holdings.json` | holdings | risk, rebalance, tax, news |
| `positions.json` | positions (day and net) | risk, alerts |
| `margins.json` | margins (equity segment) | risk |
| `trades.json` | trades and orders for the day | risk (daily count, loss stop), tax |

Each file is wrapped as `{"fetched_at": "<ISO time, IST>", "data": <raw Kite response>}`. A small helper (`kite_snapshot.py`, copied into each skill folder that needs it, because skills cannot import from each other) loads a file, checks `fetched_at` against a maximum age, and raises a clear error naming the connector call to repeat. Max ages: quotes 120 s for risk checks, others 10 min.

Each SKILL.md lists the exact connector calls to make before its script runs. Exact Kite MCP tool names and response shapes are confirmed against the live connector during phase 1 and recorded in the SKILL.md files and fixtures.

### 3.2 NSE fetchers

All NSE access goes through one pattern, copied into each fetching skill as `nse.py`:
- Get the cookie from an NSE page first, send a browser User-Agent and `Referer`, and pause at least 1 s between calls.
- Cache raw responses in `trader/cache/nse/` keyed by URL and date.
- If NSE returns 401, 403, 429 or 503, or the body is not the expected JSON, stop with exit code 2 and print the URL to open in a browser plus the `--file <saved file>` command to rerun. Every fetching command accepts `--file`.

A probe on 2026-10-26 found that the announcements, holiday-master and shareholding endpoints answered with cookies; bulk deals (503), BSE (403) and Yahoo `.NS` (429) did not. BSE and Yahoo are not used. The bundled 2026 and 2027 NSE holiday list is the fallback calendar.

### 3.3 AMC fund portfolios

The user downloads the AMC's monthly portfolio and saves the sheet as CSV. The parser finds the header row by matching column names (ISIN, instrument or company name, quantity, market value, % to NAV) case-insensitively and keeps only equity shares of Indian companies: an ISIN starting with `INE` whose security code (characters 8 and 9) is `01`. That skips bonds and debentures of the same companies, cash, TREPS, derivatives, foreign stocks and rows without a % of NAV. It stays standard-library only.

## 4. Orders and safety

### 4.1 Order shape (`trader/orders.json`)

```json
{"exchange": "NSE", "tradingsymbol": "INFY", "transaction_type": "BUY",
 "quantity": "6", "product": "CNC", "order_type": "LIMIT", "price": "1612.50",
 "validity": "DAY", "variety": "regular", "est_value": "9675.00", "est_charges": "11.42"}
```

Numbers are strings. `est_value` and `est_charges` are information only and are not sent to Kite.

### 4.2 Three gates (unchanged in spirit)

1. `trader-risk/check.py` PASSes the exact order, recorded by fingerprint in `trader/state/risk.json`.
2. The user types an explicit yes, recorded by `trader-broker/ticket.py approve --reply`.
3. The user approves the Kite connector's place-order card, which must be set to "Needs approval". The SKILL.md tells the user how to set this and refuses to proceed if they say it is set to always allow.

Every ticket begins with `LIVE ORDER: real money`, then the symbol, side, quantity, product, price, estimated value, estimated charges and total.

### 4.3 Risk rules

New or changed defaults in `trader-budget/config.example.json` (and read by `check.py`):

| Rule | Config key | Default |
|---|---|---|
| Max value per order | `max_order_value` | "10000" |
| Max orders per day (placed plus proposed) | `max_orders_per_day` | 5 |
| Allow MARKET orders | `allow_market_orders` | false |
| Max distance of LIMIT price from LTP | `max_limit_deviation_pct` | "2" |
| Price inside the circuit band | always on | |
| CNC sell quantity not above holding (no short delivery) | always on | |
| Allow MIS | `allow_mis` | false |
| No new MIS orders after | `mis_cutoff` | "15:00" |
| Max intraday exposure, % of available equity margin | `max_mis_exposure_pct` | "50" |
| Daily loss stop for new MIS orders | `daily_loss_limit` | "2000" |
| Allow intraday short (MIS SELL without a position) | `allow_short` | false |
| Outside market hours or on an NSE holiday | `allow_amo` | false (block) |
| F&O, NRML, other exchanges or segments | always blocked | |

Carried over unchanged: blocked tickers, minimum order value, max position % after the fill, cash buffer, malformed orders and duplicates. Any missing or stale snapshot that a rule needs is a BLOCK, never a skip. Exit code 0 means all orders passed and 1 means at least one was blocked, as today.

### 4.4 Charges estimate

Zerodha equity charges, held in config so they can be updated: brokerage (CNC zero; MIS 0.03% capped at Rs 20 per order), STT (CNC 0.1% on buy and sell; MIS 0.025% on sell), exchange transaction charges, SEBI fee, stamp duty on buys, and GST on brokerage plus exchange and SEBI charges. These defaults must be checked against Zerodha's published charges page when implemented.

## 5. Alerts and calendar

- Session: pre-open 09:00 to 09:15, normal 09:15 to 15:30 IST, Monday to Friday, minus NSE trading holidays (from the NSE holiday master, falling back to the bundled list).
- MIS warning at a configurable time (default 15:05) when MIS positions are open, because Zerodha squares off around 15:20.
- Price targets and stops are checked against `quotes.json` and written to `trader/prices.json`. GTT orders are out of scope.

## 6. Tax

All rates, thresholds and dates are in a `tax_rules` block in config, not in code. The spec values below must be checked against current law at implementation time (the Income-tax Act 2025 is in force from 1 April 2026).

- Financial year April to March, with reports per FY.
- FIFO lot matching.
- Listed equity delivery held more than 12 months is LTCG at 12.5% above the yearly exemption of Rs 1,25,000. Held 12 months or less is STCG at 20%.
- Same-day buy and sell of a stock (any product) is speculative business income, as the exchange nets it for delivery; it is reported separately with no exemption.
- Grandfathering for shares bought before 2018-02-01: the cost is the higher of the actual cost and the 2018-01-31 FMV, capped at the sale price. FMV comes from a user-supplied CSV (`fmv_2018.csv`) and is not bundled.
- Set-off: STCL against STCG then LTCG, LTCL against LTCG only, speculative loss against speculative income only. Carry-forward is tracked (8 years, and 4 for speculative).
- Carried losses are used oldest first, across kinds.
- Harvest view: unrealised losses that could be booked, and unused LTCG exemption headroom. There is no wash-sale logic, because India has no wash-sale rule. Suggestions become proposed orders that go through risk and broker.
- STT appears in each proposed order's est_charges; it is not deducted from gains.
- Inputs: Zerodha Console equity tradebook CSVs (the history; Kite's API returns only today's trades), today's Kite trades snapshot, and trader/lots.csv for opening lots, merged by trade id.

## 7. Repo-wide changes

Each item lands in the phase that touches it (section 9). For example, the config-default test changes in phase 2, and the rebrand happens in phase 5.

- README rewritten for India, with Indian examples, the live-only warning, Kite connector setup and the `--file` fallback.
- New `ABOUT` string, with `plugin.json`, `marketplace.json` and the README updated to match.
- Rebrand references from `Jakeschincariol/trader-skill` to `sisoppin/trader-skill`, including the `test_repo.py` strings. The MIT license keeps the original copyright line and adds the new one.
- `test_repo.py`:
  - `trader-pelosi` becomes `trader-insider` in `SKILLS` and `ORDER_PATH`.
  - Order-path skills must also contain "live" and "real money".
  - `test_paper_trading_is_the_default` becomes a test that the example config keeps `allow_mis`, `allow_short`, `allow_market_orders` and `allow_amo` false and `max_order_value` at "10000" or less.
  - `docs` is added to the root allowlist.
- `trader-broker/claude_desktop_config.example.json` (Alpaca) is replaced by Kite connector setup notes in `trader-broker/SKILL.md`.
- `CLAUDE.md` updated to India, live only, the Kite snapshot contract and the `--file` fallback.

## 8. Testing

- Offline unittest, as today. NSE fixtures are real responses captured once. Kite fixtures are written in the confirmed connector shapes.
- `check.py` has a test for every BLOCK reason in section 4.3, including stale and missing snapshots, the MIS cutoff, the circuit band, holidays, the loss stop, CNC oversell and F&O.
- Tax tests cover the LTCG/STCG boundary at exactly 12 months, the exemption, grandfathering, set-off order, speculative separation and FY boundaries.
- `test_repo.py` checks that no US terms remain in skill code and docs: `SEC`, `EDGAR`, `13F`, `CUSIP`, `Alpaca`, `NYSE`, `wash sale` and `USD`. The exceptions are this spec and the git history.

## 9. Phasing

Each phase is its own implementation plan and PR and leaves all tests passing.

1. **Foundation:** confirm the Kite connector tool names and shapes; build `kite_snapshot.py`, the symbol master and the IST/NSE calendar in trader-alerts.
2. **Order path:** trader-budget, trader-risk, trader-broker and the new config defaults.
3. **Portfolio:** trader-rebalance and trader-tax.
4. **Disclosures:** `nse.py`, trader-news, trader-insider (rename), trader-analyst and trader-copycat.
5. **Wrap-up:** trader-screener, README, manifests, rebrand, the `test_repo.py` US-term check and CLAUDE.md.

During phases 1 to 4 the US skills that have not been converted yet still exist, so tests stay green. Each phase removes the US code of the skills it converts.

## 10. Risks and open items

- NSE endpoints are unofficial and may block scripted access at any time. The `--file` fallback keeps every skill usable.
- Kite connector tool names and shapes are not confirmed yet (the connector needs a login). Phase 1 confirms them before any other phase depends on them.
- Tax rates and Zerodha charges change. Both live in config, and the README says to check them each FY.
- Live-only trading means a bug in risk or broker could cost money. Mitigations: cautious defaults, BLOCK on any missing data, and the Kite approval card as the final human gate.
