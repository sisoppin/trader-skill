---
name: trader-budget
description: >-
  Budget Manager for NSE stocks. Sizes every position to your rupee budget in
  whole shares at the Kite last price: keeps a cash buffer, caps any one stock
  (at max_position_pct of the budget or your max order, whichever is lower),
  drops slices under your minimum order, and estimates Zerodha's charges for
  each order. Writes proposed LIVE orders in Kite place_order shape to
  trader/orders.json for trader-risk and trader-broker. Use when the user
  says "how much of each", "size it", "split my budget", "I have 50,000 to
  invest", "how many shares", "what would that cost", or after trader-copycat
  produces target weights.
argument-hint: "[budget in rupees]"
---

# trader-budget

The Budget Manager turns "copy this portfolio with my 50,000" into exact
orders: how many shares of each stock, at what price, what it costs with
charges, and what stays in cash. It proposes; it never places anything.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/kite_snapshot.py" save quotes --from raw.json   # Kite quotes first
python3 "${CLAUDE_SKILL_DIR}/size.py"                                        # targets + config
python3 "${CLAUDE_SKILL_DIR}/size.py" --budget 50000 --write                 # -> trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --weights INFY=30,TCS=25,HDFCBANK=25,RELIANCE=20
python3 "${CLAUDE_SKILL_DIR}/size.py" --top 5 --json
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/targets.json` | target weights (from trader-copycat; `targets.example.json` here) |
| `trader/config.json` | your rules (`config.example.json` here: copy it and edit) |
| `trader/kite/quotes.json` | Kite quotes, saved by `kite_snapshot.py`, at most 120 seconds old |
| `trader/orders.json` | the proposed orders it writes with `--write` |

## Step 1: set the rules once

Copy `config.example.json` to `trader/config.json` and ask the user for the
numbers: budget (rupees), cash buffer percent, the most in any one stock, the
smallest order worth placing. The same file holds trader-risk's limits; the
defaults are cautious on purpose (max order Rs 10,000, five orders a day,
LIMIT only, no intraday). Charges can be adjusted under `"charges"`.

## Step 2: get prices from Kite

1. Call the Kite connector's quotes tool for every symbol in the targets
   (as `NSE:INFY`, `NSE:TCS` and so on).
2. Write its answer, unchanged, to a temp file and run
   `kite_snapshot.py save quotes --from <file>`.
3. Run `size.py` within two minutes. A missing or older snapshot stops it
   with the instrument names to fetch. Never type prices in by hand.

## Step 3: size it and show the user

Run `size.py --write` and show the table: each stock, its weight, price,
shares, rupees, and the orders with their estimated charges. Say plainly
what is left idle and why (whole shares do not divide evenly; a stock hit its
cap; a share costs more than its slice). Then hand over to `/trader-risk`.

## How the money is split

1. The cash buffer stays in cash.
2. Weights are renormalised over the stocks kept (blocked symbols dropped).
3. No stock gets more than the cap; the excess is shared out to the others.
4. Whole shares only: NSE has no fractional shares. Leftover money buys one
   more share at a time for the stock furthest below its slice.
5. A slice under the minimum order, or cheaper than one share, is dropped.

## Example

Budget Rs 50,000, buffer 10%, four stocks at 25% each, max order Rs 10,000:
the cap is Rs 10,000 per stock. With INFY at Rs 1,612.50, RELIANCE at
Rs 1,402.30, TCS at Rs 3,050.50 and HDFCBANK at Rs 1,650 it proposes 6 INFY
(Rs 9,675 plus about Rs 11.49 charges), 7 RELIANCE, 3 TCS and 6 HDFCBANK,
Rs 38,542.60 in all, with Rs 6,457.40 left idle.

## Orders it writes

Each order is a LIMIT order at the last price, product CNC (or MIS with
`--product MIS`, which trader-risk blocks unless intraday is turned on):
`exchange`, `tradingsymbol`, `transaction_type`, `quantity`, `product`,
`order_type`, `price`, `validity`, `variety`, plus `est_value`,
`est_charges` and `why` for the ticket. Numbers are strings.

## What it never does

It never places an order, never sizes from a price older than two minutes,
and never buys fractions of a share.

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
