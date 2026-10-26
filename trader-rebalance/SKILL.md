---
name: trader-rebalance
description: >-
  Rebalancer for NSE stocks. Brings the portfolio back to its target weights
  when it drifts: values every Kite holding (including today's delivery buys
  and sells) at the Kite last price, works out each stock's drift from its
  target in percentage points, trades only the stocks outside a band
  (default 5 points), keeps the cash buffer and the per-stock cap, uses
  whole shares and LIMIT orders with Zerodha's charges estimated, lists
  sells before buys, and writes LIVE orders in Kite place_order shape to
  trader/orders.json as proposals. Use when the user says "rebalance", "my
  portfolio drifted", "bring it back to the targets", "I added money", "am I
  overweight", or on a schedule after /trader-copycat updates the targets.
argument-hint: "[band in points]"
---

# trader-rebalance

The Rebalancer keeps the portfolio looking like the plan. Prices move, new
money arrives and targets change; this skill finds the stocks that drifted
too far and proposes the trades that bring them back. It writes proposals
only: trader-risk checks them and trader-broker asks the user yes or no for
each one.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/kite_snapshot.py" save holdings --from raw.json   # and positions, margins, quotes
python3 "${CLAUDE_SKILL_DIR}/rebalance.py"                     # the drift table, no files written
python3 "${CLAUDE_SKILL_DIR}/rebalance.py" --band 5 --write    # proposals -> trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/rebalance.py" --sell-untracked    # also sell holdings not in the targets
python3 "${CLAUDE_SKILL_DIR}/rebalance.py" --json
```

## Fresh Kite data first

Right before a run, call the Kite connector and save each answer with
`kite_snapshot.py save <kind> --from <file>`:

| kind | Kite call | used for |
| --- | --- | --- |
| `holdings` | holdings | shares held (quantity plus T1) |
| `positions` | positions | today's delivery (CNC) buys and sells |
| `margins` | margins | available cash |
| `quotes` | quotes for every holding and target | prices |
| `orders` | the day's orders | open orders: a stock with one is skipped until it fills or is cancelled |

Quotes older than 120 seconds and the others older than 10 minutes are
refused. Never type prices or holdings in by hand.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/targets.json` | the target weights (trader-copycat writes it) |
| `trader/config.json` | cash buffer, cap, `min_order_value`, `max_order_value`, `max_orders_per_day`, `rebalance_band_pct` |
| `trader/kite/*.json` | the Kite snapshots above |
| `trader/orders.json` | the proposals it writes with `--write`, sells first |

## How it decides

- **Account value** = available cash + every holding at its Kite price.
- **Targets**: the weights renormalised over the stock sleeve (account minus
  the cash buffer), with no stock above `max_position_pct` of the account.
- **Drift** = current percent of the account minus target percent. Only
  stocks drifting more than the band trade, and a trade takes the stock all
  the way back to its target.
- **Whole shares** at the last price, as LIMIT orders, product CNC.
- **Sells first**, then buys. Buys spend only cash above the buffer,
  charges included. Sale proceeds are not counted the same day, the same
  rule trader-risk applies, so run it again after the sales settle.
- Orders under `min_order_value` are skipped, orders over `max_order_value`
  are cut to the max, and at most `max_orders_per_day` orders are proposed.
- **Untracked** holdings are left alone unless `--sell-untracked`.
- **Open orders**: a stock with an order still open in Kite's order book gets no new order; wait for it to fill or cancel it.

## Steps

1. Refresh the four Kite snapshots.
2. Run `rebalance.py` and explain the drift table in plain words: which
   stocks are over or under, by how many points, and what it would trade.
3. Before any sell, run trader-tax (`lots.py sell SYMBOL QTY`) and show what
   the sale would realise. Selling a winner can mean tax.
4. If the user wants the trades: `rebalance.py --write`, then
   `/trader-risk` (refresh its snapshots), then `/trader-broker`, one yes
   per order.

## Example

An account with Rs 20,000 cash, 14 INFY, 4 RELIANCE, 3 TCS, 6 HDFCBANK and
10 ITC (not in the targets), at INFY Rs 1,612.50, RELIANCE Rs 1,402.30, TCS
Rs 3,050.50, HDFCBANK Rs 1,650 and ITC Rs 410, is worth Rs 71,335.70. With
four equal targets, INFY is 9.15 points over, so it proposes SELL 4 INFY,
then BUY 2 HDFCBANK, 4 RELIANCE and 1 TCS, scaled to the Rs 12,866.43 free
above the buffer. ITC is left alone.

## What it never does

It never places an order, never trades inside the band, never sells
holdings outside the targets unless asked, and never says a rebalance will
improve returns.

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
