# The Trader skill

11 Claude skills for the Indian stock market that copy the investors you trust, watch NSE filings, size every trade to your rupee budget, and never place an order without your yes.

Free, MIT, no signup, no API key. You trade through your own Zerodha account
with Claude's Kite connector, and the tools are plain Python that read what
NSE publishes: corporate announcements, insider-trade disclosures, bulk and
block deals, quarterly results and shareholding patterns.

One copies an investor you trust: the stakes above 1% a famous investor holds
in the stocks you name, or a mutual fund's whole monthly portfolio. Another
watches every announcement your companies file. One manages your budget:
every rupee sized in whole shares, a cash buffer kept, Zerodha's charges
estimated, no stock over your cap. And one shows you when promoters and
directors buy or sell their own company's shares.

No trade goes through until you say yes. Nothing in this pack can place an
order on its own, and Kite has no paper account: every order is LIVE, with
real money.

## Install

Paste this into Claude:

```
https://github.com/sisoppin/trader-skill

install skill
```

Or as a plugin, in Claude Code:

```
/plugin marketplace add sisoppin/trader-skill
/plugin install trader-skill@trader-skill
```

Claude Code namespaces plugin skills, so installed as a plugin they show up as
`/trader-skill:trader-copycat` and so on. Copy the folders instead if you want
plain `/trader-copycat`:

```bash
git clone https://github.com/sisoppin/trader-skill.git
cp -r trader-skill/trader-* ~/.claude/skills/
```

Project-local instead of global: copy the same folders into your repo's
`.claude/skills/`. No Claude Code at all? Paste any single `SKILL.md` at the
top of a chat and it runs as a mode. You lose the Python tools, but the method
works.

The tools need Python 3.8 or newer. Nothing to pip install.

### Connect Kite

Prices, holdings, positions, funds and orders come from Zerodha's Kite
connector in Claude, logged in to your own account: connect Zerodha Kite in
Claude's connector settings (in Claude Code, `/mcp`). Claude saves what the
connector returns into `trader/kite/` and the tools read it from there, so
no tool ever holds your login. Set the connector's order tools (place,
modify, cancel) to "Needs approval", never "Always allow".

### When NSE says no

NSE often blocks scripts. When it does, the tool stops with exit code 2 and
prints the address to open in your browser. Save what the page shows and
rerun with `--file <saved file>` (or `--offline <folder>` for the tools that
read several files). Nothing guesses around a block.

## The eleven

| command | job | what it does |
| --- | --- | --- |
| `/trader-copycat` | Reverse Engineer | Finds an Indian investor's stakes above 1% in the NSE shareholding patterns of the stocks you name, or reads a mutual fund's monthly portfolio sheet, and turns either into weights you can copy, with what was added, trimmed and sold. |
| `/trader-news` | News Monitor | Watches NSE corporate announcements (results, dividends, board meetings, deals, pledges) for every stock you hold and shows each new one once. |
| `/trader-budget` | Budget Manager | Sizes every position to your rupee budget in whole NSE shares at the Kite price, keeps a cash buffer, caps any one stock and estimates Zerodha's charges. |
| `/trader-insider` | Smart Money Tracker | Reads SEBI insider-trade disclosures (promoters, directors, key people) and NSE bulk and block deals in your stocks, and alerts you once per new filing. |
| `/trader-analyst` | Earnings Analyst | Reads each company's quarterly results filed with NSE (revenue, net profit, EPS, margins, YoY and QoQ growth, TTM) and writes the metrics the screener reads. |
| `/trader-screener` | Stock Screener | Screens the analyst's metrics (or your own CSV) against your rules, with P/E from Kite prices, and ranks what passes. |
| `/trader-risk` | Risk Manager | Checks every LIVE order against your limits and fresh Kite data (hours, price band, cash, intraday rules) and blocks anything over them. |
| `/trader-broker` | Order Executor | Turns an approved order into the exact ticket the Kite connector receives, marked LIVE, and records your yes. It never places anything itself. |
| `/trader-tax` | Tax Optimizer | Builds FIFO lots from your Zerodha tradebook and works out STCG, LTCG and intraday income per financial year, with set-off, the yearly exemption and harvesting ideas. |
| `/trader-alerts` | Price Alerts | Rings when a price target, a stop, the opening bell or the MIS square-off hits, with the real NSE calendar and Kite quotes. |
| `/trader-rebalance` | Rebalancer | Brings the portfolio back to its target weights from your Kite holdings when it drifts past your band, in whole shares. |

## How to use it

Everything lands in a `trader/` folder in your project, and each skill reads
what the last one wrote:

```
copycat -> budget -> risk -> broker            (copy an investor or a fund)
news / insider / alerts                         (watch, on a schedule)
analyst -> screener -> budget -> risk -> broker (pick your own)
rebalance / tax -> risk -> broker               (maintain)
```

An example: copying Rekha Jhunjhunwala with Rs 50,000.

1. **`/trader-copycat`** "copy Rekha Jhunjhunwala in TITAN, NCC and CRISIL".
   It reads each company's shareholding pattern for the quarter ended 30 Sep
   2026: TITAN 4,71,84,470 shares (5.31% of the company, across two
   accounts), NCC 7,83,33,266 (12.48%), CRISIL 37,99,000 (5.19%), all
   unchanged since June. It shows the names as filed so you can confirm the
   person, then writes `trader/targets.json` weighted by holding value: at
   illustrative prices of Rs 3,400, Rs 290 and Rs 5,100 that is TITAN 79.22%,
   NCC 11.22%, CRISIL 9.57%.
2. **`/trader-budget`** with Rs 50,000, a 10% cash buffer and your Rs 10,000
   largest order: 2 TITAN (Rs 6,800), 34 NCC (Rs 9,860), 1 CRISIL (Rs 5,100),
   delivery (CNC), LIMIT at the Kite price, with Zerodha's charges estimated
   (Rs 8.07, Rs 11.71, Rs 6.06). Rs 23,240 stays idle because whole shares and
   the cap do not divide evenly, and it says so. It writes
   `trader/orders.json` as proposals.
3. **`/trader-risk`** checks each one against fresh Kite data and your limits:
   market hours and holidays, the price band, available funds, the order size,
   the number of orders today, blocked symbols. PASS or BLOCK, with the reason.
4. **`/trader-broker`** shows you each ticket, marked LIVE: "BUY 2 shares of
   TITAN, limit Rs 3,400, delivery (CNC), good for today". You type yes for
   that exact order. Claude calls the Kite
   connector's place-order tool, and its "Needs approval" card asks you once
   more.
5. On a schedule: **`/trader-news`** shows each new announcement from your
   companies, **`/trader-insider`** alerts you when an insider trade or bulk
   deal posts, and **`/trader-alerts`** rings on your price levels and before
   Zerodha squares off intraday positions.
6. Every quarter: **`/trader-copycat`** shows what changed in the new
   shareholding patterns, and **`/trader-rebalance`** proposes the trades to
   match again. **`/trader-tax`** keeps your STCG, LTCG and intraday income
   for the financial year in view.

## The tools

All standard-library Python. The data tools read NSE's public pages politely:
a browser-like cookie, a pause between requests, and a daily cache in
`trader/cache/nse/` for files that never change.

```bash
python3 trader-copycat/copycat.py investor "Rekha Jhunjhunwala" --symbols TITAN NCC # >1% stakes
python3 trader-copycat/copycat.py fund "Parag Parikh Flexi Cap" --file oct.csv      # a fund's sheet
python3 trader-news/news.py --symbols INFY TCS --days 7                  # NSE announcements
python3 trader-insider/insider.py --symbols INFY                       # insider trades + bulk/block deals
python3 trader-analyst/results.py --symbols INFY --write               # results -> trader/metrics.json
python3 trader-screener/screen.py trader/metrics.json --rules trader/rules.json
python3 trader-budget/size.py --budget 50000 --write                   # -> trader/orders.json
python3 trader-risk/check.py                                           # PASS / BLOCK per order
python3 trader-broker/ticket.py show                                   # the tickets, READY or not
python3 trader-tax/lots.py harvest --min-loss 1000                     # losses to book, exemption left
python3 trader-alerts/alerts.py clock                                  # NSE open or closed
python3 trader-rebalance/rebalance.py --band 5                         # the drift table
```

```bash
python3 -m unittest discover -s tests -v
```

The tests run offline, on fixtures cut from real NSE answers (announcements,
insider trades, bulk deals, results and shareholding XBRL, the holiday list)
and Kite-shaped snapshots. A few are made up for cases real data lacks: the
AMC sheets and a promoter insider trade say so in their first line, and the
tax lots, the tradebook and the screener prices and CSV are hand-built
examples.

## Fine print

**Not financial advice.** This is software that reads public data and does
arithmetic. It does not know your situation, it cannot see the future, and
copying an investor does not copy their results. You can lose money. Decide for
yourself, and talk to a SEBI-registered adviser if you need advice.

**No trade goes through until you say yes.** Only `/trader-broker` can lead to
an order, and only when all three hold: `/trader-risk` passed that exact order
in the last 10 minutes, you typed yes for it in the chat, and you approved the
Kite connector's own card because its order tools are set to "Needs approval".
The defaults are cautious: Rs 10,000 per order, five orders a day, LIMIT
orders only. Intraday (MIS), MARKET orders, short selling and after-market
orders stay off until you turn them on in `trader/config.json` yourself. F&O,
NRML and stop-loss orders are not supported.

**Every order is live.** Kite has no paper account. Start small.

**Disclosed holdings are partial and late.** A shareholding pattern names
only holders above 1% of a company, once a quarter, up to 21 days after the
quarter ends. A fund's portfolio is monthly. You see what they held, not
what they hold today.

**Insider trades and bulk deals are public, after the fact.** SEBI's insider
rules make promoters, directors and key people disclose their trades within
days. The insider skill reads those public filings; it has no access to
anything that is not public.

**The data comes from free public sources.** NSE's website and archives, which
can change or block scripts, and your own Kite account through the
connector. Check anything that matters in Kite before you act on it.

**Taxes and charges change.** `/trader-tax` does the arithmetic on lots, the
12-month line, set-off and the yearly LTCG exemption for listed Indian
equity, and `/trader-budget` estimates Zerodha's charges. Both use built-in
rates for FY 2026-27 that you can override in `trader/config.json`
(`tax_rules`, `charges`): check them each financial year. It is not tax
advice.

## Files

```
trader-copycat/    SKILL.md, copycat.py, shp.py, amc.py, targets.example.json
trader-news/       SKILL.md, news.py, watchlist.py
trader-budget/     SKILL.md, size.py, charges.py, config.example.json, targets.example.json
trader-insider/    SKILL.md, insider.py
trader-analyst/    SKILL.md, results.py, metrics.example.json
trader-screener/   SKILL.md, screen.py, rules.example.json
trader-risk/       SKILL.md, check.py
trader-broker/     SKILL.md, ticket.py
trader-tax/        SKILL.md, lots.py, tradebook.py, ledger.py, india_tax.py
trader-alerts/     SKILL.md, alerts.py, alerts.example.json
trader-rebalance/  SKILL.md, rebalance.py
tests/             unittest suite + offline fixtures
```

The shared helpers (`nse.py`, `kite_snapshot.py`, `nse_calendar.py`,
`nse_symbols.py`, `rupees.py`, `charges.py`, `watchlist.py`) are copied into
each skill that uses them, so every skill folder works on its own.

MIT. Originally made by [Jake Schincariol](https://opusjake.ai) for the US
market; converted to the Indian market by [sisoppin](https://github.com/sisoppin).
