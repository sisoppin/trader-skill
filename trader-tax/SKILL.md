---
name: trader-tax
description: >-
  Tax Optimizer for Indian listed equity. Builds FIFO lots from your Zerodha
  Console tradebook, today's Kite trades and your opening lots, separates
  intraday round trips (speculative income) from delivery, and works out
  short-term (12 months or less) and long-term gains with the 31 Jan 2018
  grandfathering rule. Per financial year it sets off losses in the right
  order, applies the Rs 1,25,000 LTCG exemption, carries losses forward and
  estimates the tax. It shows what a sale would realise, finds losses to book
  and long-term gains that still fit the exemption, and writes harvest sells
  as LIVE proposals. Not tax advice. Use when the user says "what are my
  gains", "capital gains", "STCG", "LTCG", "tax harvest", "what would
  selling cost me in tax", "how much exemption is left", or before selling.
argument-hint: "[symbol]"
---

# trader-tax

The Tax Optimizer does the arithmetic on your trades so you can see the tax
side of a sale before you make it. It is not tax advice: rates change, your
slab and other income matter, and a tax professional decides what applies.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/lots.py" report                    # open lots, unrealised gain by term
python3 "${CLAUDE_SKILL_DIR}/lots.py" gains                     # per financial year
python3 "${CLAUDE_SKILL_DIR}/lots.py" gains --fy 2026-27
python3 "${CLAUDE_SKILL_DIR}/lots.py" sell INFY 4               # what selling 4 INFY now would realise
python3 "${CLAUDE_SKILL_DIR}/lots.py" harvest --min-loss 1000   # losses to book, exemption headroom
python3 "${CLAUDE_SKILL_DIR}/lots.py" harvest --write           # loss-harvest sells -> trader/orders.json
```

## Where the trades come from

Kite's API only returns today's trades, so the history comes from files:

| file | what |
| --- | --- |
| `trader/tradebook-<year>.csv` | Zerodha Console > Reports > Tradebook > Equity, downloaded as CSV (one per year is fine) |
| `trader/lots.csv` | holdings bought before the tradebook starts: `date,symbol,quantity,price` |
| `trader/fmv_2018.csv` | `symbol,fmv`: the 31 Jan 2018 price of any stock bought before 2018-02-01 |
| `trader/kite/trades.json` | today's Kite trades (`kite_snapshot.py save trades`) |
| `trader/kite/holdings.json` | Kite holdings, to check that the lots add up |
| `trader/kite/quotes.json` | Kite quotes, for unrealised gains and harvest prices |

If the lots do not match Kite's holdings, the report says which stock and
by how much: an earlier tradebook or a line in lots.csv is missing.
Splits, bonuses and other corporate actions are not in any tradebook, so a
stock that had one shows up as a mismatch, and its gains are off until the
user adjusts its lines in lots.csv by hand. Say so whenever it happens.

## The rules it applies

- **Intraday**: shares of a stock bought and sold on the same day are
  speculative business income (your slab rate), kept separate.
- **FIFO**: other sales close the oldest lots first, as demat accounts do.
- **Term**: held more than 12 months is long term. Bought 2025-01-10, sold
  2026-01-10 is short term; sold 2026-01-11 is long term.
- **2018 rule**: for shares bought before 2018-02-01, a long-term sale uses
  the higher of the actual cost and the 31 Jan 2018 price, capped at the
  sale price.
- **Rates** (defaults, change them under `"tax_rules"` in trader/config.json):
  STCG 20%, LTCG 12.5% above Rs 1,25,000 a year. Estimates start from FY
  2025-26; earlier years had other rates. Check the rates every year: the
  Income-tax Act 2025 applies from 1 April 2026.
- **Set-off**: short-term loss against short-term then long-term gain;
  long-term loss only against long-term gain; speculative loss only against
  speculative income. What is left carries forward 8 years (4 for
  speculative), only if that year's return was filed on time.
- **No wash-sale rule** in India: a loss stays a loss if you buy back, but
  the new shares start a new 12-month clock.

## Steps

1. Ask the user to download their Console tradebook(s) into `trader/`.
2. Refresh the trades, holdings and quotes snapshots from Kite.
3. Run `report` and `gains` and explain them in plain words.
4. Before any sell from another skill, run `sell SYMBOL QTY`.
5. For harvesting, run `harvest` and explain each candidate. Only with the
   user's agreement, run `harvest --write` (add `--include-gains` for the
   long-term gains inside the exemption), then `/trader-risk` and
   `/trader-broker`, one yes per order.
   Harvest skips any stock whose lots do not match Kite's holdings, never
   proposes a cut-down sale that would book the opposite of what it says
   (the oldest shares go first), and `--write` needs a fresh holdings
   snapshot.

## Example

With the sample trades, FY 2025-26 has a short-term gain of Rs 750, a
short-term loss of Rs 400 and a long-term gain of Rs 510: estimated tax
Rs 70 (20% of the net Rs 350; the Rs 510 is inside the exemption). An
intraday loss of Rs 100 in FY 2024-25 carries forward and Rs 20 of it is
used against FY 2026-27 intraday income.

## What it never does

It never files or calculates a return, never claims a rate is current
without telling the user to check it, and never sells anything itself.

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
