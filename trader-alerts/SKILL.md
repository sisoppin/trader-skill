---
name: trader-alerts
description: >-
  Price Alerts for NSE stocks. Rings when a price target, a stop, a percent
  move from the previous close, the NSE opening bell or an open MIS position
  near Zerodha's 15:20 square-off hits, each ringing once so you are not
  spammed. Knows NSE hours in IST (09:15 to 15:30) and NSE trading holidays,
  reads live quotes and positions that Claude saves from the Kite connector,
  and writes trader/prices.json for the other skills. Use when the user says
  "alert me when", "tell me if INFY hits", "set a stop", "price target",
  "watch my stocks", "is the market open", "when does NSE open", "remind me
  to close my intraday", "get me prices", or to refresh prices before
  sizing, risk or tax.
argument-hint: "[symbol] [price]"
---

# trader-alerts

Price Alerts watches the numbers so the user does not have to. An alert is
information, never an order: when a stop rings, nothing is sold. If the user
wants to act, the normal path runs (size, risk, their yes).

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clock                         # NSE open or closed, next open
python3 "${CLAUDE_SKILL_DIR}/alerts.py" holidays refresh              # NSE holiday list into trader/cache
python3 "${CLAUDE_SKILL_DIR}/alerts.py" need                          # which Kite quotes a check needs
python3 "${CLAUDE_SKILL_DIR}/kite_snapshot.py" save quotes --from raw.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote INFY RELIANCE --write   # -> trader/prices.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol INFY --above 1700
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --stop 1350 --note "my stop"
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol TCS --pct 3
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --opening-bell
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --mis-warning --at 15:05
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check                         # 0 rang, 1 nothing, 2 no fresh data
python3 "${CLAUDE_SKILL_DIR}/alerts.py" list
python3 "${CLAUDE_SKILL_DIR}/alerts.py" reset infy-above-1700
```

## Getting prices from Kite

The script never fetches prices itself. Before every `quote` or `check`:

1. Run `alerts.py need` to get the Kite instruments (for example
   `NSE:INFY NSE:RELIANCE`) and whether positions are needed.
2. Call the Kite connector's quotes tool for exactly those instruments.
3. Write its answer, unchanged, to a temp file and run
   `kite_snapshot.py save quotes --from <file>`. It stamps the time.
4. If `need` says positions, call the connector's positions tool and
   `kite_snapshot.py save positions --from <file>` the same way.
5. Run `check` within two minutes. Quotes older than 120 seconds are
   refused, and so are positions older than 10 minutes.

If the connector is not logged in, ask the user to log in to Kite. Never
type prices in by hand.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/alerts.json` | the rules (`alerts.example.json` in this folder) |
| `trader/kite/quotes.json`, `trader/kite/positions.json` | Kite snapshots saved by `kite_snapshot.py` |
| `trader/cache/nse/holidays.json` | NSE's holiday list, saved by `holidays refresh` |
| `trader/state/alerts.json` | which rules rang and when, so each rings once |
| `trader/prices.json` | the latest prices in rupees, merged in, for the other skills |

## Rule types

| type | rings when | rings again |
| --- | --- | --- |
| `above` | price at or above `price` | after `reset`, or on its own if `"rearm": true` and the price fell back |
| `below` / `stop` | price at or below `price` | same |
| `pct_move` | moved `pct` percent from the previous close (or `ref`), optional `direction` up or down | once per day at most |
| `opening_bell` | NSE is open | once per trading day |
| `mis_warning` | an MIS position is still open at or after `at` (default 15:05 IST) | once per trading day |

## The NSE clock

Pre-open 09:00 to 09:15 and the normal session 09:15 to 15:30 IST, Monday to
Friday. NSE is closed on weekends and its trading holidays. The 2026 list is
built in (from NSE's holiday master, read 2026-10-26). `holidays refresh`
saves NSE's current list. If NSE blocks the request, open the URL it prints
in a browser, save the page, and run `holidays refresh --file <saved file>`.
For a year with no list loaded, `clock` says so: run the refresh once NSE
publishes the new year. Zerodha squares MIS positions off from about 15:20.
Muhurat trading on Diwali is not modelled.

## Steps

1. Ask what to watch, in the user's words ("tell me if Infosys drops under
   1,550"), and add the rule. Confirm it back: symbol, type, level in rupees.
2. Refresh the Kite snapshots (above) and run `check`. Run it again on a
   schedule if the user wants: every 15 minutes in market hours is plenty.
3. Tell the user what rang in one line each. If they want to act, send them
   to sizing and `/trader-risk`. Never act for them.

## Example

With the rules in `alerts.example.json`, a check at 15:30 IST on 2026-10-26
with INFY at Rs 1,612.50 and RELIANCE at Rs 1,402.30 rings nothing: INFY is
under 1,700 and RELIANCE is over its 1,350 stop. At 09:15 the next trading
day the opening bell rings once. On a day with an open MIS position, the MIS
warning rings once at 15:05.

## What it never does

It never places, cancels or changes an order, never makes up a price, and
never predicts where a price is going.

## Safety

- Education and tooling, not financial advice. An alert is a fact about a price, not a signal to trade.
- Every order in this pack is a LIVE order with real money: Kite has no paper account.
- Nothing in this pack places an order except through trader-broker, and only when all three hold:
  trader-risk passed that exact order, the user typed an explicit yes for that one order in the chat,
  and the user approved the Kite connector's order card because its order tool is set to "Needs
  approval". Never set an order tool to "Always allow".
- No F&O, no margin products other than MIS when the config allows it, and no short selling unless the
  config allows it and the user confirms.
- Kite logins live in the connector, never in the chat or in files.
