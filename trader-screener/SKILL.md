---
name: trader-screener
description: >-
  The Stock Screener for NSE stocks. Checks a list of companies against the
  user's own rules (revenue growth, margins, EPS, P/E, earnings yield,
  sector, anything in the metrics file), says exactly which rule each
  company passes or fails and by how much, and ranks the ones that pass into
  a shortlist. Reads the metrics /trader-analyst writes from NSE results
  filings, or any CSV with rupee or percent values. Use when the user says
  "screen for stocks", "find me companies that", "filter my watchlist",
  "which of these pass my rules", "shortlist candidates", "rank these
  stocks", or "growing companies under 25 times earnings".
argument-hint: "[metrics file] [--rules rules.json]"
---

# trader-screener

A screen turns "I want profitable companies that are still growing and not
too expensive" into rules a computer can check, and shows its work: every
pass and every fail comes with the number and the threshold.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).
The tool is standard library Python and makes no network calls:

```bash
python3 "${CLAUDE_SKILL_DIR}/screen.py" --help
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/metrics.json` | from `/trader-analyst` (`results.py --write`), or any JSON list or CSV with a `symbol` column |
| `trader/prices.json` | optional, `{"prices": {"INFY": 1500.0}}`, written by `/trader-alerts` from Kite quotes |
| `trader/rules.json` | the user's rules; start from `rules.example.json` in this folder |
| `trader/shortlist.json` | with `--out`: who passed, their score and why, who failed and why |

- The price date shown is the oldest price used, so a symbol not re-quoted since an old run is visible.
- CSV numbers may carry `Rs`, `Rs.`, `INR` or the rupee sign, `%`, and
  commas in Indian (1,23,456) or international grouping.
- With prices it adds `price`, `pe` (price / TTM EPS, only when EPS is
  positive) and `earnings_yield`.
- When the analyst could not read every stock, the metrics file says so
  (`"complete": false`). The screen then prints a WARNING naming the
  missing stocks: they are not failures, they were never screened. The
  analyst's per-stock `note` (for example a split that left TTM EPS out)
  is shown under the company.

## The rules file

```json
{"name": "Growing, profitable, fairly priced",
 "rules": [{"metric": "revenue_growth_yoy", "op": ">=", "value": 10},
           {"metric": "operating_margin", "op": ">=", "value": 15},
           {"metric": "eps_ttm", "op": ">", "value": 0},
           {"metric": "pe", "op": "<=", "value": 30}],
 "rank":  [{"metric": "revenue_growth_yoy", "order": "desc", "weight": 2},
           {"metric": "pe", "order": "asc", "weight": 1},
           {"metric": "operating_margin", "order": "desc", "weight": 1}],
 "missing": "fail"}
```

Ops: `>`, `>=`, `<`, `<=`, `==`, `!=`, `between` ([low, high]), `in` and
`not in` (a list, for symbols or sectors to leave out). `"missing": "fail"`
fails a company that lacks a metric a rule needs; `"skip"` ignores that
rule for it and says so. Banks have no operating margin in their results
format, so a bank fails an operating-margin rule unless the user picks
`"skip"` or screens banks separately. Ranking scores each passing company 0
to 1 per rank metric and takes the weighted average.

Metric names come from `/trader-analyst`: `revenue_growth_yoy`,
`revenue_growth_qoq`, `net_profit_growth_yoy`, `net_profit_growth_qoq`,
`eps_growth_yoy`, `operating_margin`, `net_margin`, `eps`, `eps_ttm`,
`revenue_ttm`, `net_profit_ttm` (rupees), plus `price`, `pe` and
`earnings_yield` when prices are given.

## Steps

1. Turn the user's words into rules. Ask when a threshold is vague ("cheap"
   means what P/E?). Write them to `trader/rules.json`.
2. Get metrics for the candidates: run `/trader-analyst` on them with
   `--write` (`results.py --symbols INFY TCS ... --write`), or use the
   user's own CSV. For P/E, save Kite quotes for the same symbols and run
   `/trader-alerts` `quote ... --write` to refresh `trader/prices.json`.
3. Run the screen:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/screen.py" trader/metrics.json --rules trader/rules.json \
     --prices trader/prices.json --out trader/shortlist.json
   ```

   Exit code 1 means nothing passed: say so and show the closest misses.
   If the output has a WARNING line, say which stocks were never
   screened.
4. Report the shortlist with the reasons, the misses with the numbers that
   failed, and the dates the numbers are from (the quarter each company's
   numbers are for, the price date). Suggest `/trader-analyst` on the top
   names before anything else.

## Example

Real analyst metrics for INFY, TCS, HDFCBANK, RELIANCE, ITC and M&M (read
2026-10-27), illustrative prices, and `rules.example.json`:

```
Growing, profitable, fairly priced: 4 of 6 companies pass.
 1. PASS M&M        Mahindra & Mahindra Limited  score 0.67
 2. PASS TCS        Tata Consultancy Services Limite  score 0.50
 3. PASS INFY       Infosys Limited  score 0.42
 4. PASS ITC        ITC Limited  score 0.42
    FAIL RELIANCE   operating_margin 10.4, needs >= 15
    FAIL HDFCBANK   revenue_growth_yoy 9.4, needs >= 10; operating_margin is missing
```

Then the caveat a careful analyst adds: RELIANCE, ITC and M&M are still on
the June quarter while INFY, TCS and HDFCBANK have reported September, so
the numbers are not all from the same three months.

## What it never does

- Never calls a passing company a buy. A screen is a filter on reported
  numbers, not a recommendation.
- Never fills in a missing number or guesses a metric: missing means missing.
- Never sends anything to `/trader-budget` or an order path by itself.

## Safety

Education and tooling, not financial advice. This skill only filters numbers.
Nothing places an order except `/trader-broker`, after `/trader-risk` passes
that exact order and the user types an explicit yes for it, and the Kite
connector's own approval card asks once more.
