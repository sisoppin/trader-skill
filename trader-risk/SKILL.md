---
name: trader-risk
description: >-
  Risk Manager for LIVE NSE orders. Checks every proposed order against your
  limits and fresh Kite data before it can reach the broker, and blocks
  anything over them: market hours and NSE holidays, the price against the
  last price and the circuit band, max and min order value, cash and the cash
  buffer, max position percent, delivery sales of shares you do not hold,
  intraday (MIS) cutoff, exposure and daily loss stop, MARKET orders, F&O,
  duplicates and a daily order limit. Prints PASS or BLOCK with the reason
  for each order and records the verdicts so trader-broker only shows an
  order that passed. Use when the user says "check my orders", "is this
  safe", "risk check", "does this break my rules", "can I place this", or
  before /trader-broker, always.
argument-hint: "[path to orders.json]"
---

# trader-risk

The Risk Manager is the gate between a proposal and the broker. Every order
written by trader-budget passes through it. A BLOCK is final for that order:
it does not go to the user for a yes, and it does not go to the broker.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"                    # trader/ files, records the verdicts
python3 "${CLAUDE_SKILL_DIR}/check.py" --json
python3 "${CLAUDE_SKILL_DIR}/check.py" --no-write         # look without recording
python3 "${CLAUDE_SKILL_DIR}/kite_snapshot.py" show       # how old each Kite snapshot is
```

## Fresh Kite data first

Right before every check, call the Kite connector and save each answer with
`kite_snapshot.py save <kind> --from <file>`:

| kind | Kite call | used for |
| --- | --- | --- |
| `quotes` | quotes for every symbol in the orders | price, circuit band, order value |
| `holdings` | holdings | position size, delivery sales |
| `positions` | positions | today's delivery (CNC) trades, intraday exposure and the daily loss stop |
| `margins` | margins | available cash and equity margin |
| `orders` | the day's orders | the daily order limit |

Quotes older than 120 seconds and the others older than 10 minutes are
refused, and any rule that needs a refused snapshot BLOCKS the order.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders |
| `trader/config.json` | your limits (`trader-budget/config.example.json`) |
| `trader/kite/*.json` | the Kite snapshots above |
| `trader/state/risk.json` | the verdicts with a fingerprint of each order |

## The checks

- format: a bare NSE symbol, BUY or SELL, whole shares, LIMIT (or MARKET if
  allowed), DAY validity, regular (or amo if allowed). No SL or SL-M.
- product: CNC delivery, or MIS intraday only when `allow_mis` is true.
- hours: 09:15 to 15:30 IST on NSE trading days; a year without a loaded
  holiday list blocks too.
- price: within `max_limit_deviation_pct` of the last price and inside the
  circuit band.
- size, cash, buffer and position limits, with charges counted.
- short: no delivery sale beyond what you hold; no MIS short unless allowed.
- intraday: no new MIS positions after `mis_cutoff`, exposure capped, a
  daily loss stop.
- duplicates and `max_orders_per_day`, counting Kite's order book.

## Steps

1. Refresh the five Kite snapshots.
2. Run `check.py`. Show every BLOCK with its reasons in plain words.
3. If something is blocked, help the user fix the order or decide to change
   their own rule. Never loosen a rule for them.
4. When every order the user wants passed, hand over to `/trader-broker`
   within 10 minutes; after that the check must run again.

## Example

The four example orders from trader-budget (6 INFY, 7 RELIANCE, 3 TCS,
6 HDFCBANK) on an account with Rs 60,000 cash at 10:01 IST on a trading day
all PASS, leaving Rs 21,411.62 cash. A fifth order the same day hits the
five-a-day limit; at 16:00 every order is blocked because NSE is closed.

## What it never does

It never places an order, never skips a rule because data is missing, and
never changes the user's limits.

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
