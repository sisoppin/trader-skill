---
name: trader-insider
description: >-
  Smart Money Tracker for NSE stocks. Reads SEBI insider-trading (PIT)
  disclosures for your stocks (promoters, promoter group, directors, key
  managerial people and their relatives) and NSE's daily bulk and block
  deals, tags market purchases and sales by insiders, and alerts once per
  new filing. Writes trader/insider.json for the other skills. Use when the
  user says "are promoters buying", "insider trades in INFY", "who bought
  TCS today", "bulk deals", "block deals", "smart money", or on a schedule
  after the close.
argument-hint: "[symbols]"
---

# trader-insider

The Smart Money Tracker shows what the people closest to a company, and
the biggest traders of the day, are doing in your stocks. These trades are
disclosed after the fact: they are information, not a signal to copy.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/insider.py"                         # both, Kite holdings + targets
python3 "${CLAUDE_SKILL_DIR}/insider.py" pit --symbols INFY --days 90
python3 "${CLAUDE_SKILL_DIR}/insider.py" pit --symbols INFY --file pit.json
python3 "${CLAUDE_SKILL_DIR}/insider.py" deals                   # today's bulk and block deals in your stocks
python3 "${CLAUDE_SKILL_DIR}/insider.py" deals --every-symbol
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/kite/holdings.json`, `trader/targets.json` | the stocks to watch |
| `trader/state/insider.json` | what you have seen (90 days), so each filing alerts once |
| `trader/insider.json` | the latest rows; `cmd` says which sources were read, and `complete` is false when a stock or source could not be read |

## Where the data comes from

- Insider trades: `https://www.nseindia.com/api/corporates-pit?index=equities&symbol=<SYMBOL>`,
  one request per stock. NSE often blocks scripts: the tool prints the
  address and exits 2. Ask the user to open it in a browser, save it, and
  run `pit --symbols <SYMBOL> --file <saved file>`.
- Bulk deals: `https://archives.nseindia.com/content/equities/bulk.csv` and
  block deals: `.../block.csv`, today only, no cookie needed. `--bulk-file`
  and `--block-file` take saved copies.
- Every run asks NSE again (no cache), so a schedule sees new filings the same day.

## How to read it

- `[market]` marks a market purchase or sale, the kind that tells you the
  most. ESOP allotments and off-market transfers are shown but untagged.
- `[insider]` marks a promoter, promoter group, director, key managerial
  person, designated person or a relative.
- A bulk deal is 0.5% or more of the company's shares in one day by one
  client. A block deal is a large trade in the block window.

## Steps

1. Run `insider.py` (exit 0 new, 1 nothing new, 2 when anything could not be checked: an error, or NSE
   blocked a request).
2. Report each new row in one line: who, buy or sell, how many shares, the
   value and what they hold after. Lead with `[market] [insider]` rows.
3. Never suggest copying a trade as if it were advice. If the user wants to
   act, the normal path runs: `/trader-budget`, `/trader-risk`, then
   `/trader-broker` with an explicit yes for each LIVE order.

## Example

For ABC (test data), a promoter-group market purchase of 50,000 shares on
20 Oct 2026 shows as `BUY ... Market Purchase, Promoter Group [market]
[insider]`, and a director's market sale of 1,200 shares the next day as a
SELL with the same tags. On 26 Oct 2026, APOLLO had two bulk-deal buys of
about 25 lakh shares each.

## What it never does

It never places an order, never calls a trade "smart" or "a signal", and
never hides that disclosures arrive days after the trade.

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
