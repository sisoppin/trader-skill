---
name: trader-news
description: >-
  News Monitor for NSE stocks. Watches the corporate announcements NSE
  publishes for every stock you hold or plan to copy (results, dividends and
  bonuses, board meetings, acquisitions and mergers, pledges, insider and
  takeover filings, ratings, management changes, analyst meets) and shows
  each new one once, newest first, with the company's own attachment. Use
  when the user says "any news on my stocks", "what did INFY announce",
  "results out?", "check announcements", "corporate actions", "dividend
  news", or on a schedule during market hours.
argument-hint: "[symbols]"
---

# trader-news

The News Monitor reads what the companies themselves file with NSE, so the
user hears about results, dividends, deals and pledges from the source. It
prints only what is new since the last check.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py"                              # Kite holdings + trader/targets.json
python3 "${CLAUDE_SKILL_DIR}/news.py" --symbols INFY TCS
python3 "${CLAUDE_SKILL_DIR}/news.py" --symbols INFY --all --days 30
python3 "${CLAUDE_SKILL_DIR}/news.py" --symbols INFY --file announcements.json
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/kite/holdings.json` | the stocks you hold (any age; only the names are used) |
| `trader/targets.json` | the stocks you plan to copy |
| `trader/state/news.json` | which announcements you have seen (90 days), so each shows once |

## Where the news comes from

One request per stock to NSE's corporate announcements page:
`https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=<SYMBOL>`.
NSE often blocks scripts. When it does, the tool prints that address and
exits 2. Ask the user to open it in a browser, save what it shows, and run
again with `--file <saved file>` (one stock) or `--offline <folder>` holding
`announcements-<SYMBOL>.json` files.

## Categories

results, dividend (also bonus, split, buyback, record date), board meeting,
deal (acquisition, merger, scheme), pledge, insider (insider and takeover
filings), rating, management, analyst meet, and other. The category comes
from the title and the attachment text, so "Outcome of Board Meeting" with
financial results counts as results.

## Steps

1. Run `news.py` (or with `--symbols`). Exit 0 means something new, 1
   means nothing new, 2 means NSE blocked a request.
2. Tell the user each new item in one line: the stock, the category, what
   it says. Point to the attachment for anything that matters.
3. For results, offer `/trader-analyst`. For a dividend, mention the record
   date if the text gives it. For a pledge by promoters, say so plainly.
4. To run it on a schedule, use `/loop 30m /trader-news` during market
   hours.

## Example

For INFY on 26 Oct 2026, the last week shows "Outcome of Board Meeting"
(results, 23 Oct: financial results for the quarter and an interim
dividend) and "Copy of Newspaper Publication" (other, 24 Oct). A second run
shows "Nothing new."

## What it never does

It never trades, never summarises an attachment it has not read, and never
treats an announcement as a recommendation.

## Safety

- Education and tooling, not financial advice. An announcement is the company's own filing, not a signal.
- Nothing in this skill places an order. Orders go through trader-budget, trader-risk and trader-broker,
  with an explicit yes for each one.
