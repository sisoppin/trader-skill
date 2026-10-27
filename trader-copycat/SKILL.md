---
name: trader-copycat
description: >-
  The Reverse Engineer for Indian investors and mutual funds. For a famous
  individual investor, reads the quarterly NSE shareholding pattern of each
  stock you name and finds their stakes above 1% (the only stakes India
  makes public), with what they added, trimmed or dropped since the quarter
  before. For a mutual fund, reads the monthly portfolio sheet the fund
  house publishes (saved as CSV) with what changed since last month. Turns
  either into weights and writes trader/targets.json for /trader-budget.
  Use when the user says "copy Rekha Jhunjhunwala", "what does Damani own
  in", "copy Parag Parikh Flexi Cap", "copy this fund's top 10", "what did
  the fund buy this month", or names an Indian investor or a scheme.
argument-hint: "investor NAME --symbols ... | fund NAME --file sheet.csv"
---

# trader-copycat

Copying starts with what India makes public. A listed company names every
shareholder with more than 1% of it in its quarterly shareholding pattern.
A mutual fund publishes its whole portfolio every month. This skill reads
both and turns them into weights you can size.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/copycat.py" investor "Rekha Jhunjhunwala" --symbols TITAN CRISIL NCC
python3 "${CLAUDE_SKILL_DIR}/copycat.py" investor "Rekha Jhunjhunwala" --symbols TITAN CRISIL NCC --write
python3 "${CLAUDE_SKILL_DIR}/copycat.py" fund "Parag Parikh Flexi Cap" --file oct.csv --previous sep.csv --top 10 --write
python3 "${CLAUDE_SKILL_DIR}/nse_symbols.py" refresh          # the NSE symbol list the fund command needs
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/prices.json` | investor: prices for the value weights (written by `/trader-alerts` from Kite quotes) |
| `trader/cache/nse/EQUITY_L.csv` | fund: NSE's symbol list, to turn ISINs into symbols (`nse_symbols.py refresh`) |
| `trader/targets.json` | with `--write`: the weights for `/trader-budget` and `/trader-rebalance` |
| `targets.example.json` (this folder) | a real example: Rekha Jhunjhunwala in TITAN, NCC and CRISIL |

## An investor

There is no list of everything one person owns. The user names the stocks
to look in (`--symbols`). For each one the tool reads NSE's two newest
shareholding patterns,
`https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=<SYMBOL>`
and the XBRL file each links to, and adds up every entry carrying the
investor's name (one person often holds through two accounts). Entries that
only repeat a holding (persons acting in concert) are not counted twice.

- The name matches when every word of it appears in the filed name, so
  "Rekha Jhunjhunwala" matches "REKHA JHUNJHUNWALA" but not "Rajesh
  Jhunjhunwala". Use the name as filed.
- "not named" means the investor holds under 1% of that company, or none.
  "gone" means named last quarter but not now: sold, or fell under 1%.
- Weights are holding value (shares x price) scaled to 100. Save Kite
  quotes for the symbols and run `alerts.py quote <symbols> --write` first;
  without a price the tool shows the holdings but writes nothing.
- This is always a partial portfolio. Say so.

If NSE blocks a request, the tool exits 2 and names the URL. Ask the user
to open it in a browser, save it as `shp-<SYMBOL>.json`, open the two
newest XBRL links it shows and save each under its own name in the same
folder, and rerun with `--offline <folder>`.

## A mutual fund

The user downloads the scheme's monthly portfolio from the fund house's
website (an Excel file), opens the scheme's sheet and saves it as CSV. The
tool finds the header row by its column names (ISIN, instrument, quantity,
market value, % to NAV or % to net assets) and keeps only equity shares of
Indian companies. It skips bonds and debentures of the same companies,
TREPS, cash, derivatives and foreign stocks. Weights are % to NAV of the
top N holdings (`--top`, default 10; 0 for all) scaled to 100. `--previous`
with last month's sheet shows new, added, trimmed and sold.

A stock whose ISIN is not on the NSE list is shown and left out. If it
would have been in the top N, nothing is written: refresh the symbol list
(`nse_symbols.py refresh`) or pick a smaller `--top`.

## Steps

1. Ask who to copy: an investor (and which stocks) or a fund (and its
   sheet as CSV).
2. Run `copycat.py` without `--write` and show the holdings, the changes
   and the weights. Exit 0 means everything was read; 2 means something
   could not be read or priced: read the error, blocked or "not written"
   lines.
3. When the user is happy, rerun with `--write`. It refuses to save weights
   built from a partial read.
4. Hand over to `/trader-budget` to size the weights to their money. Every
   order still goes through `/trader-risk` and `/trader-broker`.

## Example

Rekha Jhunjhunwala, quarter ended 30 Sep 2026: TITAN 4,71,84,470 shares
(5.31% of the company, two accounts), NCC 7,83,33,266 shares (12.48%, two
categories; the repeated concert entries are not counted twice), CRISIL
37,99,000 shares (5.19%). All three unchanged since June. At the example
prices, TITAN is 79.22% of the copy, NCC 11.22% and CRISIL 9.57%.

## What it never does

It never guesses a holding under 1%, never writes weights from a partial
read, and never places an order.

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
