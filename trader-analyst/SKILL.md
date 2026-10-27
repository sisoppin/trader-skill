---
name: trader-analyst
description: >-
  The Earnings Analyst for NSE stocks. Reads the quarterly financial results
  companies file with NSE (the XBRL behind each integrated filing) and sums
  up what changed: revenue, net profit, EPS, operating and net margin, each
  against the quarter before (QoQ) and the same quarter a year earlier
  (YoY), with the trailing twelve months. Handles banks and companies that
  file only standalone results. Writes trader/metrics.json for the
  screener. Use when the user says "how were Infosys's results", "analyze
  the results", "what changed this quarter", "is revenue growing", "Q2
  numbers", "compare margins", or "run the analyst on my holdings".
argument-hint: "[symbols]"
---

# trader-analyst

Results season moves stocks, and the press release puts the best number
first. This skill reads the numbers the company actually filed with NSE,
lines up the quarters and says plainly what changed.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/results.py"                          # Kite holdings + trader/targets.json
python3 "${CLAUDE_SKILL_DIR}/results.py" --symbols INFY TCS HDFCBANK
python3 "${CLAUDE_SKILL_DIR}/results.py" --symbols INFY --standalone
python3 "${CLAUDE_SKILL_DIR}/results.py" --symbols INFY --write   # -> trader/metrics.json
python3 "${CLAUDE_SKILL_DIR}/results.py" --symbols INFY --offline <folder>
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/kite/holdings.json`, `trader/targets.json` | the stocks to read when `--symbols` is not given |
| `trader/metrics.json` | with `--write`: one row per stock for `/trader-screener`; `complete` is false when a stock could not be read |
| `metrics.example.json` (this folder) | a real row: INFY, Q2 FY27 |

## Where the numbers come from

For each stock, NSE's integrated filing (financials) list,
`https://www.nseindia.com/api/integrated-filing-results?index=equities&symbol=<SYMBOL>&type=Integrated%20Filing-%20Financials`,
and the XBRL file each row links to. One XBRL file is one quarter, so the
tool reads the newest five: this quarter, the quarter before, the same
quarter last year, and four in a row for TTM. NSE keeps a daily cache in
`trader/cache/nse/`. Results filed before April 2025 used NSE's older page
and are not read, so TTM and YoY need filings from mid-2025 on.

If NSE blocks a request, the tool exits 2 and names the URL. Ask the user to
open the list URL in a browser and save it as `results-<SYMBOL>.json`, then
open each XBRL link it shows (the newest five quarters) and save each file
under its own name in the same folder, and rerun with `--offline <folder>`.

## The rules

- Consolidated (the whole group) by default; `--standalone` for the parent
  company alone. A company that files only standalone is read standalone,
  and the row says `basis: standalone`.
- A revised filing replaces the original for the same quarter.
- Revenue is revenue from operations; for a bank it is interest earned.
- Net profit is the profit attributable to the company's owners when the
  filing gives it (minority interest excluded).
- Operating margin is (profit before tax + finance costs - other income) /
  revenue. It is empty for banks.
- A growth figure is empty (`n/a`) when the comparison quarter is missing,
  never guessed.
- Quarters follow the Indian financial year (April to March): 30 Sep 2026
  is Q2 FY27.

## Steps

1. Run `results.py` for the stocks the user means (exit 0 all read, 2 when
   any stock could not be read: read the error or blocked lines).
2. Lead with what changed: revenue and net profit growth YoY and QoQ, then
   margins and EPS. Say "n/a" plainly when a comparison is missing.
3. If the user wants to screen, run with `--write` and hand
   `trader/metrics.json` to `/trader-screener`.

## Example

INFY, Q2 FY27 (quarter ended 30 Sep 2026, consolidated, filed 23 Oct 2026):
revenue Rs 49,244 cr (+10.7% YoY, +2.1% QoQ), net profit Rs 7,823 cr (+6.2%
YoY, +0.7% QoQ), EPS Rs 19.32 (+8.8% YoY), TTM EPS Rs 75.69, operating
margin 21.0%, net margin 15.9%.

## What it never does

It never forecasts, never fills a missing quarter with an estimate, and
never calls a result good or bad on its own: it reports the change.

## Safety

- Education and tooling, not financial advice. Nothing here is a recommendation to buy or sell.
- Every order in this pack is a LIVE order with real money on your Zerodha account: Kite has no paper account.
- Nothing in this pack places an order except through trader-broker, and only when all three hold:
  trader-risk passed that exact order in the last 10 minutes, the user typed an explicit yes for that
  one order in the chat, and the user approved the Kite connector's order card because its order tool
  is set to "Needs approval". Never set an order tool to "Always allow".
- No F&O, no NRML, no stop-loss orders. MIS (intraday), MARKET orders, short selling and after-market
  orders stay off unless the user turns them on in trader/config.json themselves.
- Kite logins live in the connector, never in the chat or in files.
