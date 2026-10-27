# India Phase 5 (Wrap-up) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the India conversion. That means:
- trader-screener reads the analyst's Indian metrics and rupee CSVs.
- The README is rewritten for NSE and Zerodha Kite.
- The pack is rebranded to `sisoppin/trader-skill`, with a new `ABOUT` string, manifests and LICENSE line.
- A test stops US-market terms from coming back.
- CLAUDE.md describes the finished pack.

**Architecture:**
- **Screener:** keeps its rule engine. It gains rupee units in `to_number`, a `partial(path)` reader that turns the analyst's `"complete": false` into a loud WARNING, and the analyst's per-stock `note` in the report.
- **Docs and manifests:** whole-file rewrites (README, plugin.json, marketplace.json, LICENSE) or exact replacements (CLAUDE.md, the new-trader-skill scaffold, test_repo.py).
- **US-term check:** a new `test_repo.py` test scans skill code, docs, manifests and fixtures. It skips `docs/` (the spec and the phase plans are history) and the test code.

**Tech Stack:** Python 3.8+, standard library only, `unittest`. Fixtures:
- The screener metrics are real trader-analyst rows for six NSE stocks, read live on 2026-10-27.
- The prices are illustrative and labelled as such.
- The CSV restates the same numbers with rupee units.

**Spec:** `docs/superpowers/specs/2026-10-26-indian-market-design.md`: section 2 (trader-screener row), section 8 (README, ABOUT, rebrand, LICENSE, the US-term check) and section 9 phase 5.

**Branch:** `feat/india-phase5`, branched from `feat/india-phase4b`.

**Provenance:**
- Every file and replacement below was drafted and run in a scratch worktree. The suite passed with 343 tests on Python 3.12 and 3.8, and ruff was clean.
- The README walk-through numbers come from running copycat and budget on the fixtures at the stated illustrative prices. They are 2 TITAN, 34 NCC and 1 CRISIL, with Rs 23,240 idle.

## Global Constraints

- Python 3.8 or newer, standard library only.
- No em dashes (U+2014) in any .md, .py, .json, .csv, .txt or .xml file, or in LICENSE.
- The skill count and `ABOUT` must agree everywhere:
  - the `ABOUT` string in `tests/test_repo.py`
  - the `description` in `.claude-plugin/plugin.json`
  - the README's first paragraph and its "## The eleven" heading
  - the README command table
- Shared helpers stay byte-identical (`test_shared_helpers_are_identical`). This plan changes none.
- Tests are fully offline. Never run a tool from the repo root. Lint with `--no-cache`.
- Commit messages end with a Co-Authored-By trailer.
- Full check: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`

## Review Focus

1. **A partial analyst metrics file.** The stocks the analyst could not read must not look like stocks that failed the screen: the screen names them in a WARNING. Covered by `test_a_partial_metrics_file_is_called_out`.
2. **Rupee values in a user's CSV** (`Rs`, `Rs.`, `INR`, the rupee sign, Indian 1,23,456 grouping) parse as numbers. Covered by `test_rupee_units` and `test_csv_with_units_and_nothing_passing`.
3. **A bank under an operating-margin rule** fails clearly, with "operating_margin is missing", unless the rules say `"skip"`. Covered by `test_the_example_screen` and `test_a_bank_can_skip_the_operating_margin_rule`.
4. **A half-done rebrand** (one manifest or README line still pointing at the old repo) fails a test. Covered by `test_plugin_manifest_points_at_the_root_skills` and `test_rebranded_with_the_original_credit_kept`.
5. **A US term creeping back in a later change** fails a test that names the file and line. The test allows India's correct "no wash-sale rule" statement. Covered by `test_no_us_terms_left`.

---

### Task 1: trader-screener on Indian metrics

**Files:**
- Replace:
  - `trader-screener/screen.py`, `trader-screener/rules.example.json`, `trader-screener/SKILL.md`
  - `tests/test_screener.py`
  - `tests/fixtures/trader-screener/{metrics.json,prices.json,companies.csv}`

**Interfaces:**
- Consumes the trader-analyst `trader/metrics.json` shape: `{as_of, complete, errors, blocked, companies: [{symbol, ..., eps_ttm, operating_margin, revenue_growth_yoy, note, ...}]}`
- Produces:
  - `screen.to_number(v)`, which accepts rupee units.
  - `screen.partial(path) -> [missing lines]`.
  - `screen.render(results, spec, top=None, prices_as_of=None, missing=())`.
  - A `metrics_missing` key in the shortlist JSON.

- [ ] **Step 1: Write the fixtures and the failing tests**

`tests/fixtures/trader-screener/metrics.json`:

```json
{
  "as_of": "2026-10-27T11:00:00+05:30",
  "complete": true,
  "errors": [],
  "blocked": [],
  "companies": [
    {
      "symbol": "INFY",
      "name": "Infosys Limited",
      "basis": "consolidated",
      "period_end": "2026-09-30",
      "quarter": "Q2 FY27",
      "filed": "2026-10-23",
      "bank": false,
      "revenue": 492440000000.0,
      "net_profit": 78230000000.0,
      "eps": 19.32,
      "operating_margin": 21.0,
      "net_margin": 15.9,
      "revenue_growth_yoy": 10.7,
      "revenue_growth_qoq": 2.1,
      "net_profit_growth_yoy": 6.2,
      "net_profit_growth_qoq": 0.7,
      "eps_growth_yoy": 8.8,
      "revenue_ttm": 1893360000000.0,
      "net_profit_ttm": 307470000000.0,
      "eps_ttm": 75.69,
      "shares": 4052000000.0,
      "note": null,
      "source": "NSE integrated filing (financials)"
    },
    {
      "symbol": "TCS",
      "name": "Tata Consultancy Services Limited",
      "basis": "consolidated",
      "period_end": "2026-09-30",
      "quarter": "Q2 FY27",
      "filed": "2026-10-08",
      "bank": false,
      "revenue": 731880000000.0,
      "net_profit": 138840000000.0,
      "eps": 38.37,
      "operating_margin": 24.0,
      "net_margin": 19.0,
      "revenue_growth_yoy": 11.2,
      "revenue_growth_qoq": 1.3,
      "net_profit_growth_yoy": 15.0,
      "net_profit_growth_qoq": 4.0,
      "eps_growth_yoy": 15.0,
      "revenue_ttm": 2832480000000.0,
      "net_profit_ttm": 516080000000.0,
      "eps_ttm": 142.64,
      "shares": 3620000000.0,
      "note": null,
      "source": "NSE integrated filing (financials)"
    },
    {
      "symbol": "HDFCBANK",
      "name": "HDFC Bank Limited",
      "basis": "consolidated",
      "period_end": "2026-09-30",
      "quarter": "Q2 FY27",
      "filed": "2026-10-17",
      "bank": true,
      "revenue": 951316300000.0,
      "net_profit": 207000300000.0,
      "eps": 13.43,
      "operating_margin": null,
      "net_margin": 21.8,
      "revenue_growth_yoy": 9.4,
      "revenue_growth_qoq": 5.0,
      "net_profit_growth_yoy": 5.6,
      "net_profit_growth_qoq": 1.6,
      "eps_growth_yoy": 5.1,
      "revenue_ttm": 3599564000000.0,
      "net_profit_ttm": 821245200000.0,
      "eps_ttm": 52.03,
      "shares": 15418600000.0,
      "note": null,
      "source": "NSE integrated filing (financials)"
    },
    {
      "symbol": "RELIANCE",
      "name": "Reliance Industries Limited",
      "basis": "consolidated",
      "period_end": "2026-06-30",
      "quarter": "Q1 FY27",
      "filed": "2026-07-17",
      "bank": false,
      "revenue": 3118500000000.0,
      "net_profit": 209460000000.0,
      "eps": 15.48,
      "operating_margin": 10.4,
      "net_margin": 6.7,
      "revenue_growth_yoy": 25.4,
      "revenue_growth_qoq": 4.4,
      "net_profit_growth_yoy": -22.4,
      "net_profit_growth_qoq": 23.4,
      "eps_growth_yoy": -22.4,
      "revenue_ttm": 11388650000000.0,
      "net_profit_ttm": 747270000000.0,
      "eps_ttm": 55.22,
      "shares": 13533000000.0,
      "note": null,
      "source": "NSE integrated filing (financials)"
    },
    {
      "symbol": "ITC",
      "name": "ITC Limited",
      "basis": "consolidated",
      "period_end": "2026-06-30",
      "quarter": "Q1 FY27",
      "filed": "2026-07-31",
      "bank": false,
      "revenue": 295233000000.0,
      "net_profit": 43941300000.0,
      "eps": 3.51,
      "operating_margin": 17.5,
      "net_margin": 14.9,
      "revenue_growth_yoy": 27.6,
      "revenue_growth_qoq": 23.9,
      "net_profit_growth_yoy": -16.2,
      "net_profit_growth_qoq": -18.4,
      "eps_growth_yoy": -16.2,
      "revenue_ttm": 963072800000.0,
      "net_profit_ttm": 198394000000.0,
      "eps_ttm": 15.84,
      "shares": 12529500000.0,
      "note": null,
      "source": "NSE integrated filing (financials)"
    },
    {
      "symbol": "M&M",
      "name": "Mahindra & Mahindra Limited",
      "basis": "consolidated",
      "period_end": "2026-06-30",
      "quarter": "Q1 FY27",
      "filed": "2026-07-30",
      "bank": false,
      "revenue": 581875700000.0,
      "net_profit": 54545400000.0,
      "eps": 48.8,
      "operating_margin": 15.1,
      "net_margin": 9.4,
      "revenue_growth_yoy": 27.8,
      "revenue_growth_qoq": 5.8,
      "net_profit_growth_yoy": 33.6,
      "net_profit_growth_qoq": 16.9,
      "eps_growth_yoy": 33.4,
      "revenue_ttm": 2113749000000.0,
      "net_profit_ttm": 184700700000.0,
      "eps_ttm": 165.32,
      "shares": 1117900000.0,
      "note": null,
      "source": "NSE integrated filing (financials)"
    }
  ]
}
```

`tests/fixtures/trader-screener/prices.json`:

```json
{
  "_note": "Illustrative prices for tests, not real quotes (prices come from Kite in use).",
  "as_of": "2026-10-27T15:30:00+05:30",
  "prices": {
    "INFY": 1500.0,
    "TCS": 3000.0,
    "HDFCBANK": 950.0,
    "RELIANCE": 1400.0,
    "ITC": 410.0,
    "M&M": 3400.0
  }
}
```

`tests/fixtures/trader-screener/companies.csv`:

```csv
symbol,name,revenue_growth_yoy,operating_margin,net_margin,eps_ttm,sector
INFY,"Infosys Limited",10.7%,21.0%,15.9%,Rs 75.69,"IT - Software"
TCS,"Tata Consultancy Services Limited",11.2%,24.0%,19.0%,₹142.64,"IT - Software"
HDFCBANK,"HDFC Bank Limited",9.4%,,21.8%,Rs 52.03,"Banks"
RELIANCE,"Reliance Industries Limited",25.4%,10.4%,6.7%,₹55.22,"Oil & Gas"
ITC,"ITC Limited",27.6%,17.5%,14.9%,Rs 15.84,"Diversified FMCG"
M&M,"Mahindra & Mahindra Limited",27.8%,15.1%,9.4%,₹165.32,"Automobiles"
```

Replace `tests/test_screener.py` with:

```python
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from _load import FIX, ROOT, load

scr = load("trader-screener", "screen")
DIR = os.path.join(FIX, "trader-screener")
METRICS = os.path.join(DIR, "metrics.json")
PRICES = os.path.join(DIR, "prices.json")
RULES = os.path.join(ROOT, "trader-screener", "rules.example.json")


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = scr.main(args)
    return code, out.getvalue(), err.getvalue()


def companies(prices=True):
    rows = scr.load_metrics(METRICS)
    if prices:
        scr.add_prices(rows, PRICES)
    return rows


# metrics.json: real trader-analyst rows for six NSE stocks (results to the Sep or Jun 2026 quarter, read
# 2026-10-27); prices.json: illustrative prices, labelled as such; companies.csv: the same numbers as a CSV
# with rupee units.


class Prices(unittest.TestCase):
    def test_pe_and_earnings_yield(self):
        by = {c["ticker"]: c for c in companies()}
        self.assertEqual(by["INFY"]["pe"], 19.8)       # 1500 / 75.69
        self.assertEqual(by["TCS"]["pe"], 21.0)        # 3000 / 142.64
        self.assertEqual(by["HDFCBANK"]["earnings_yield"], 5.48)
        self.assertEqual(by["M&M"]["price"], 3400.0)

    def test_rupee_units(self):
        self.assertEqual([scr.to_number(v) for v in ("Rs. 1,23,456.50", "INR 12", "\u20b9 5", "rs 7%", "Rsx", "-")],
                         [123456.5, 12.0, 5.0, 7.0, "Rsx", None])

    def test_no_pe_for_losses(self):
        rows = [{"ticker": "LOSS", "eps_ttm": -1.0}]
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "prices.json")
            with open(p, "w") as fh:
                json.dump({"prices": {"LOSS": 10}}, fh)
            scr.add_prices(rows, p)
        self.assertNotIn("pe", rows[0])
        self.assertEqual(rows[0]["earnings_yield"], -10.0)


class Screen(unittest.TestCase):
    def setUp(self):
        self.spec = scr.load_rules(RULES)
        self.results = scr.screen(companies(), self.spec)

    def test_the_example_screen(self):
        passed = [(r["ticker"], r["score"]) for r in self.results if r["passed"]]
        self.assertEqual(passed, [("M&M", 0.667), ("TCS", 0.5), ("INFY", 0.417), ("ITC", 0.417)])
        fails = {r["ticker"]: r["fails"] for r in self.results if not r["passed"]}
        self.assertEqual(fails["RELIANCE"], ["operating_margin 10.4, needs >= 15"])
        self.assertEqual(fails["HDFCBANK"], ["revenue_growth_yoy 9.4, needs >= 10",
                                             "operating_margin is missing"])

    def test_a_bank_can_skip_the_operating_margin_rule(self):
        rules = [dict(r, value=9) if r["metric"] == "revenue_growth_yoy" else r for r in self.spec["rules"]]
        spec = dict(self.spec, rules=rules, missing="skip")
        res = {r["ticker"]: r for r in scr.screen(companies(), spec)}
        self.assertTrue(res["HDFCBANK"]["passed"])
        self.assertEqual(res["HDFCBANK"]["skipped"], ["operating_margin is missing"])
        self.assertIn("operating_margin", res["HDFCBANK"]["rank_gaps"])

    def test_every_op(self):
        c = {"ticker": "ITC", "sector": "Diversified FMCG", "pe": 28.3}
        cases = [({"metric": "pe", "op": "between", "value": [10, 30]}, True),
                 ({"metric": "pe", "op": "between", "value": [10, 20]}, False),
                 ({"metric": "pe", "op": "<", "value": 28.3}, False),
                 ({"metric": "pe", "op": "!=", "value": 1}, True),
                 ({"metric": "ticker", "op": "in", "value": ["itc", "hul"]}, True),
                 ({"metric": "ticker", "op": "not in", "value": ["ITC"]}, False),
                 ({"metric": "sector", "op": "==", "value": "diversified fmcg"}, True),
                 ({"metric": "sector", "op": ">", "value": 3}, False),
                 ({"metric": "beta", "op": "<", "value": 1}, None)]
        for rule, want in cases:
            self.assertEqual(scr.check(c, rule)[0], want, rule)

    def test_bad_rules_are_refused(self):
        for bad in ({"rules": [{"metric": "pe", "op": "~", "value": 1}]},
                    {"rules": [{"metric": "pe", "op": "between", "value": 3}]},
                    {"rules": [{"metric": "pe", "op": "<"}]},
                    {"rules": [], "rank": [{"metric": "pe", "order": "up"}]},
                    {"rules": [], "missing": "maybe"}):
            with self.assertRaises(scr.ScreenError):
                scr.check_rules(bad)


class Cli(unittest.TestCase):
    def test_text_report_and_shortlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "trader", "shortlist.json")
            code, text, err = run([METRICS, "--rules", RULES, "--prices", PRICES, "--out", out])
            self.assertEqual(code, 0, err)
            with open(out) as fh:
                sl = json.load(fh)
        self.assertIn("4 of 6 companies pass", text)
        self.assertIn("Prices as of 2026-10-27T15:30:00+05:30", text)
        self.assertIn("    FAIL RELIANCE   operating_margin 10.4, needs >= 15", text)
        self.assertIn("not a recommendation", text)
        self.assertNotIn("WARNING", text)
        self.assertNotIn(chr(0x2014), text)
        self.assertEqual([p["ticker"] for p in sl["passed"]], ["M&M", "TCS", "INFY", "ITC"])
        self.assertEqual((len(sl["failed"]), sl["metrics_missing"]), (2, []))

    def test_a_partial_metrics_file_is_called_out(self):
        with open(METRICS) as fh:
            doc = json.load(fh)
        doc["complete"], doc["errors"] = False, ["TCS: cannot read the results list"]
        doc["companies"] = [c for c in doc["companies"] if c["symbol"] != "TCS"]
        doc["companies"][0]["note"] = "share count changed by more than 5%"
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "metrics.json")
            with open(p, "w") as fh:
                json.dump(doc, fh)
            code, text, _ = run([p, "--rules", RULES, "--prices", PRICES])
            _, js, _ = run([p, "--rules", RULES, "--prices", PRICES, "--json"])
        self.assertIn("WARNING: the metrics file is partial", text)
        self.assertIn("    TCS: cannot read the results list", text)
        self.assertIn("        note  share count changed by more than 5%", text)
        self.assertEqual(json.loads(js)["metrics_missing"], ["TCS: cannot read the results list"])

    def test_csv_with_units_and_nothing_passing(self):
        csv_path = os.path.join(DIR, "companies.csv")
        rows = scr.load_metrics(csv_path)
        self.assertEqual((rows[0]["ticker"], rows[0]["eps_ttm"], rows[1]["eps_ttm"]), ("INFY", 75.69, 142.64))
        self.assertEqual(rows[0]["revenue_growth_yoy"], 10.7)
        self.assertIsNone(rows[2]["operating_margin"])
        code, text, _ = run([csv_path, "--rules", RULES])
        self.assertEqual(code, 1)   # no prices, so no pe: nothing passes
        self.assertIn("pe is missing", text)

    def test_bad_input_exit_2(self):
        code, _, err = run(["/nonexistent.json", "--rules", RULES])
        self.assertEqual(code, 2)
        self.assertIn("no such file", err)

    def test_top_limits_the_shortlist(self):
        code, text, _ = run([METRICS, "--rules", RULES, "--prices", PRICES, "--top", "1",
                             "--json"])
        self.assertEqual(code, 0)
        self.assertEqual([p["ticker"] for p in json.loads(text)["passed"]], ["M&M"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_screener.py -v`
Expected: failures and errors. The old `to_number` keeps "Rs", `partial` does not exist, and the US rules give different results.

- [ ] **Step 3: Implement**

Replace `trader-screener/screen.py` with:

```python
#!/usr/bin/env python3
"""Stock screener for trader-screener. Standard library only, no network.

Checks every company in a metrics file against your rules, says exactly why
each one passes or fails, and ranks the ones that pass.

    python3 screen.py trader/metrics.json --rules rules.example.json
    python3 screen.py trader/metrics.json --rules my-rules.json --prices trader/prices.json
    python3 screen.py companies.csv --rules my-rules.json --out trader/shortlist.json --json

Metrics: a JSON file ({"companies": [...]} as trader-analyst's results.py
--write saves it, or a plain list of objects) or a CSV with a header row.
Each company needs a "symbol" (or "ticker"); every other column is a metric.
Numbers in a CSV can carry Rs, Rs., INR or the rupee sign, %, and commas in
either Indian (1,23,456) or international grouping. When the analyst could
not read every stock it marks the file {"complete": false}; the screen then
says loudly which stocks are missing from it.

Prices (optional): trader/prices.json ({"prices": {"INFY": 1500.0}}), which
trader-alerts writes from Kite quotes. With prices, the screener adds:
    price          the price you gave it
    pe             price / eps_ttm (only when eps_ttm is above zero)
    earnings_yield 100 * eps_ttm / price, in %

Rules (see rules.example.json):
    {"name": "...",
     "rules": [{"metric": "net_margin", "op": ">=", "value": 15}, ...],
     "rank":  [{"metric": "revenue_growth_yoy", "order": "desc", "weight": 2}, ...],
     "missing": "fail",            # or "skip": a rule on a missing metric is ignored
     "top": 10}
    ops: > >= < <= == != between (value [low, high]) in / not in (a list)

Ranking: among the companies that pass, each rank metric gives a score from 0
(worst) to 1 (best); the final score is their weighted average. A company
missing a rank metric is scored on the others and the gap is shown.

Exit code 0 when at least one company passes, 1 when none do, 2 on bad input.
A screen is a filter, not a recommendation.
"""

import argparse
import csv
import json
import os
import sys

OPS = (">", ">=", "<", "<=", "==", "!=", "between", "in", "not in")
RUPEE = ("rs.", "rs", "inr", "\u20b9")


class ScreenError(Exception):
    pass


# ---------------------------------------------------------------- inputs

def to_number(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    if s == "" or s.lower() in ("na", "n/a", "none", "null", "-"):
        return None
    t = s.replace(",", "").replace("%", "").strip()
    low = t.lower()
    for unit in RUPEE:
        if low.startswith(unit):
            t = t[len(unit):].strip()
            break
    try:
        return float(t)
    except ValueError:
        return s


def load_metrics(path):
    if not os.path.isfile(path):
        raise ScreenError("no such file: %s" % path)
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = [{(k or "").strip(): to_number(v) for k, v in r.items()}
                    for r in csv.DictReader(fh)]
    else:
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except ValueError as exc:
                raise ScreenError("%s is not valid JSON: %s" % (path, exc))
        rows = data.get("companies", data.get("rows")) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ScreenError("%s: expected a list of companies or {\"companies\": [...]}" % path)
        rows = [dict(r) for r in rows]
    out = []
    for i, r in enumerate(rows):
        t = str(r.get("ticker") or r.get("symbol") or "").strip().upper()
        if not t:
            raise ScreenError("company #%d has no ticker" % (i + 1))
        r["ticker"] = t
        out.append(r)
    return out


def partial(path):
    """The stocks a metrics file says it is missing: trader-analyst writes {"complete": false, "errors": [...],
    "blocked": [...]} when it could not read every stock. [] when the file is complete or a CSV."""
    if path.lower().endswith(".csv"):
        return []
    with open(path, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except ValueError:
            return []
    if isinstance(data, dict) and data.get("complete") is False:
        missing = [str(e) for e in (data.get("errors") or []) + (data.get("blocked") or [])]
        return missing or ["the metrics file says it is incomplete"]
    return []


def add_prices(rows, prices_path):
    with open(prices_path, encoding="utf-8") as fh:
        data = json.load(fh)
    prices = {k.upper(): v for k, v in (data.get("prices", data) or {}).items()}
    for r in rows:
        p = to_number(prices.get(r["ticker"]))
        if not isinstance(p, (int, float)) or p <= 0:
            continue
        r["price"] = p
        eps = to_number(r.get("eps_ttm"))
        if isinstance(eps, (int, float)):
            r["earnings_yield"] = round(100.0 * eps / p, 2)
            if eps > 0:
                r["pe"] = round(p / eps, 1)
    return data.get("as_of")


def load_rules(path):
    with open(path, encoding="utf-8") as fh:
        try:
            spec = json.load(fh)
        except ValueError as exc:
            raise ScreenError("%s is not valid JSON: %s" % (path, exc))
    check_rules(spec)
    return spec


def check_rules(spec):
    if not isinstance(spec, dict) or not isinstance(spec.get("rules", []), list):
        raise ScreenError("rules must be {\"rules\": [...]}")
    for i, r in enumerate(spec.get("rules", [])):
        if "metric" not in r or "op" not in r or "value" not in r:
            raise ScreenError("rule #%d needs metric, op and value: %r" % (i + 1, r))
        if r["op"] not in OPS:
            raise ScreenError("rule #%d: unknown op %r (use one of %s)" % (i + 1, r["op"],
                                                                          ", ".join(OPS)))
        if r["op"] == "between" and not (isinstance(r["value"], list) and len(r["value"]) == 2):
            raise ScreenError("rule #%d: between needs [low, high]" % (i + 1))
        if r["op"] in ("in", "not in") and not isinstance(r["value"], list):
            raise ScreenError("rule #%d: %s needs a list" % (i + 1, r["op"]))
    for i, k in enumerate(spec.get("rank", [])):
        if "metric" not in k or k.get("order", "desc") not in ("asc", "desc"):
            raise ScreenError("rank #%d needs a metric and order asc or desc" % (i + 1))
    if spec.get("missing", "fail") not in ("fail", "skip"):
        raise ScreenError("missing must be \"fail\" or \"skip\"")


# ---------------------------------------------------------------- screening

def _fmt(v):
    if isinstance(v, float):
        return ("%.2f" % v).rstrip("0").rstrip(".")
    if isinstance(v, list):
        return "[%s]" % ", ".join(_fmt(x) for x in v)
    return str(v)


def check(company, rule):
    """(passed, reason). passed is None when the metric is missing."""
    m, op, want = rule["metric"], rule["op"], rule["value"]
    have = company.get(m)
    if have is None or have == "":
        return None, "%s is missing" % m
    if op in ("in", "not in"):
        bag = [str(x).upper() for x in want]
        inside = str(have).upper() in bag
        ok = inside if op == "in" else not inside
        return ok, "%s %s %s %s" % (m, _fmt(have), "is in" if inside else "is not in", _fmt(want))
    if op in ("==", "!=") and not isinstance(have, (int, float)):
        ok = (str(have).upper() == str(want).upper()) == (op == "==")
        return ok, "%s %s %s %s" % (m, _fmt(have), op, _fmt(want))
    if not isinstance(have, (int, float)):
        return False, "%s is %r, not a number" % (m, have)
    if op == "between":
        lo, hi = want
        ok = lo <= have <= hi
        return ok, "%s %s %s %s to %s" % (m, _fmt(have), "is within" if ok else "is outside",
                                          _fmt(lo), _fmt(hi))
    ok = {">": have > want, ">=": have >= want, "<": have < want, "<=": have <= want,
          "==": have == want, "!=": have != want}[op]
    if ok:
        return True, "%s %s %s %s" % (m, _fmt(have), op, _fmt(want))
    return False, "%s %s, needs %s %s" % (m, _fmt(have), op, _fmt(want))


def screen(companies, spec):
    """Every company with pass/fail and reasons; passing ones ranked."""
    rules = spec.get("rules", [])
    missing = spec.get("missing", "fail")
    results = []
    for c in companies:
        fails, passes, gaps = [], [], []
        for r in rules:
            ok, why = check(c, r)
            if ok is None:
                (fails if missing == "fail" else gaps).append(why)
            elif ok:
                passes.append(why)
            else:
                fails.append(why)
        results.append({"ticker": c["ticker"], "name": c.get("name"), "passed": not fails,
                        "fails": fails, "passes": passes, "skipped": gaps, "metrics": c})
    rank(results, spec.get("rank", []))
    results.sort(key=lambda r: (not r["passed"], -(r.get("score") or 0), len(r["fails"]),
                                r["ticker"]))
    return results


def rank(results, keys):
    winners = [r for r in results if r["passed"]]
    for r in winners:
        r["score"], r["rank_parts"] = 0.0, {}
    if not keys or not winners:
        for r in winners:
            r["score"] = None
        return
    for k in keys:
        m, desc = k["metric"], k.get("order", "desc") == "desc"
        vals = [(r, r["metrics"].get(m)) for r in winners]
        vals = [(r, v) for r, v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if not vals:
            continue
        ordered = sorted(v for _, v in vals)
        n = len(ordered)
        for r, v in vals:
            below = sum(1 for x in ordered if x < v)
            equal = sum(1 for x in ordered if x == v)
            pos = (below + (equal - 1) / 2.0) / (n - 1) if n > 1 else 1.0
            r["rank_parts"][m] = round(pos if desc else 1.0 - pos, 3)
    weights = {k["metric"]: float(k.get("weight", 1)) for k in keys}
    for r in winners:
        parts = r["rank_parts"]
        total = sum(weights[m] for m in parts)
        r["score"] = round(sum(parts[m] * weights[m] for m in parts) / total, 3) if total else None
        r["rank_gaps"] = [k["metric"] for k in keys if k["metric"] not in parts]


# ---------------------------------------------------------------- output

def render(results, spec, top=None, prices_as_of=None, missing=()):
    name = spec.get("name") or "screen"
    passed = [r for r in results if r["passed"]]
    out = ["%s: %d of %d companies pass." % (name, len(passed), len(results))]
    if prices_as_of:
        out.append("Prices as of %s." % prices_as_of)
    if missing:
        out.append("WARNING: the metrics file is partial, so these stocks are not in the screen at all:")
        for m in missing:
            out.append("    %s" % m)
    out.append("")
    shown = passed[:top] if top else passed
    for i, r in enumerate(shown, 1):
        score = "" if r.get("score") is None else "  score %.2f" % r["score"]
        out.append("%2d. PASS %-10s %s%s" % (i, r["ticker"], (r.get("name") or "")[:32], score))
        for why in r["passes"]:
            out.append("        ok    %s" % why)
        for why in r["skipped"]:
            out.append("        skip  %s" % why)
        if r.get("rank_gaps"):
            out.append("        not ranked on: %s" % ", ".join(r["rank_gaps"]))
        if r["metrics"].get("note"):
            out.append("        note  %s" % r["metrics"]["note"])
    if top and len(passed) > top:
        out.append("    ... %d more pass" % (len(passed) - top))
    failed = [r for r in results if not r["passed"]]
    if failed:
        out.append("")
        for r in failed:
            out.append("    FAIL %-10s %s" % (r["ticker"], "; ".join(r["fails"])))
            if r["metrics"].get("note"):
                out.append("        note  %s" % r["metrics"]["note"])
    out.append("")
    out.append("A screen is a filter on reported numbers, not a recommendation. Read the "
               "filings (/trader-analyst) before anything goes near /trader-budget.")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("metrics", help="metrics JSON or CSV (trader/metrics.json)")
    ap.add_argument("--rules", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                    "rules.example.json"))
    ap.add_argument("--prices", help="trader/prices.json, adds price, pe and earnings_yield")
    ap.add_argument("--top", type=int, help="show only the N best that pass")
    ap.add_argument("--out", help="write the shortlist JSON here (trader/shortlist.json)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        spec = load_rules(args.rules)
        companies = load_metrics(args.metrics)
        prices_as_of = add_prices(companies, args.prices) if args.prices else None
        missing = partial(args.metrics)
    except (ScreenError, OSError) as exc:
        print("screen: %s" % exc, file=sys.stderr)
        return 2
    results = screen(companies, spec)
    top = args.top or spec.get("top")
    passed = [r for r in results if r["passed"]]
    shortlist = {
        "name": spec.get("name"), "rules": spec.get("rules", []), "rank": spec.get("rank", []),
        "prices_as_of": prices_as_of, "metrics_missing": missing,
        "passed": [{"ticker": r["ticker"], "name": r.get("name"), "score": r.get("score"),
                    "why": r["passes"], "skipped": r["skipped"]}
                   for r in (passed[:top] if top else passed)],
        "failed": [{"ticker": r["ticker"], "why": r["fails"]} for r in results if not r["passed"]],
        "note": "A filter on reported numbers, not a recommendation.",
    }
    if args.json:
        print(json.dumps(shortlist, indent=2))
    else:
        sys.stdout.write(render(results, spec, top, prices_as_of, missing))
    if args.out:
        folder = os.path.dirname(args.out)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(shortlist, fh, indent=2)
            fh.write("\n")
        if not args.json:
            print("wrote %s" % args.out)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
```

Replace `trader-screener/rules.example.json` with:

```json
{
  "name": "Growing, profitable, fairly priced",
  "rules": [
    {"metric": "revenue_growth_yoy", "op": ">=", "value": 10},
    {"metric": "operating_margin", "op": ">=", "value": 15},
    {"metric": "eps_ttm", "op": ">", "value": 0},
    {"metric": "pe", "op": "<=", "value": 30}
  ],
  "rank": [
    {"metric": "revenue_growth_yoy", "order": "desc", "weight": 2},
    {"metric": "pe", "order": "asc", "weight": 1},
    {"metric": "operating_margin", "order": "desc", "weight": 1}
  ],
  "missing": "fail",
  "top": 10
}
```

Replace `trader-screener/SKILL.md` with:

````markdown
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
   If the output starts with a WARNING, say which stocks were never
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
````

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_screener.py -v`
Expected: all 12 tests pass. Then run `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`.

```bash
git add trader-screener tests/test_screener.py tests/fixtures/trader-screener
git commit -m "Convert trader-screener to Indian metrics: rupee units, partial-file warning, analyst notes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 2: README, ABOUT, manifests, LICENSE: the India rebrand

**Files:**
- Replace: `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `LICENSE`
- Modify: `tests/test_repo.py` (the `ABOUT` string, the new `REPO` constant, the install lines, the manifest URLs, and a new rebrand test), `CLAUDE.md` (the fork note)

**Interfaces:**
- Produces the new `ABOUT` string, which `plugin.json` `description` and the README's first paragraph must both equal, and `REPO = "sisoppin/trader-skill"`.

- [ ] **Step 1: Write the failing tests**

Each old text must match exactly once.

- In `tests/test_repo.py`, replace:

```
ABOUT = ("11 Claude skills that copy the investors you trust, watch the news and Congress, size every "
         "trade to your budget, and never place an order without your yes.")
```

  with:

```
ABOUT = ("11 Claude skills for the Indian stock market that copy the investors you trust, watch NSE filings, "
         "size every trade to your rupee budget, and never place an order without your yes.")
REPO = "sisoppin/trader-skill"
```

- In `tests/test_repo.py`, replace:

```
                     "https://github.com/Jakeschincariol/trader-skill install skill",
                     "/plugin marketplace add Jakeschincariol/trader-skill",
```

  with:

```
                     "https://github.com/%s install skill" % REPO,
                     "/plugin marketplace add %s" % REPO,
```

- In `tests/test_repo.py`, replace:

```
        self.assertEqual(market["plugins"][0]["name"], "trader-skill")
```

  with:

```
        self.assertEqual(market["plugins"][0]["name"], "trader-skill")
        for url in (plugin["homepage"], plugin["repository"], market["plugins"][0]["homepage"]):
            self.assertEqual(url, "https://github.com/" + REPO)

    def test_rebranded_with_the_original_credit_kept(self):
        for rel in ("README.md", "CLAUDE.md", os.path.join(".claude-plugin", "plugin.json"),
                    os.path.join(".claude-plugin", "marketplace.json")):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                self.assertNotIn("Jakeschincariol/", fh.read(), rel)
        with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as fh:
            lic = fh.read()
        self.assertIn("Copyright (c) 2026 Jake Schincariol", lic)
        self.assertIn("Copyright (c) 2026 sisoppin", lic)
```


- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_repo.py -v`
Expected: failures in `test_plugin_manifest_points_at_the_root_skills`, `test_readme_carries_the_reel_copy` and `test_rebranded_with_the_original_credit_kept`.

- [ ] **Step 3: Implement**

`README.md`:

````markdown
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
connector in Claude, logged in to your own account: in claude.ai under
Settings, Connectors; in Claude Code with `/mcp`. Claude saves what the
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
4. **`/trader-broker`** shows you each ticket, marked LIVE: "BUY 2 TITAN, CNC,
   LIMIT Rs 3,400". You type yes for that exact order. Claude calls the Kite
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
and Kite-shaped snapshots. The few synthetic files, such as the AMC sheets,
say so in their first line.

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
````

`.claude-plugin/plugin.json`:

```json
{
  "name": "trader-skill",
  "description": "11 Claude skills for the Indian stock market that copy the investors you trust, watch NSE filings, size every trade to your rupee budget, and never place an order without your yes.",
  "version": "2.0.0",
  "author": {
    "name": "sisoppin",
    "url": "https://github.com/sisoppin"
  },
  "homepage": "https://github.com/sisoppin/trader-skill",
  "repository": "https://github.com/sisoppin/trader-skill",
  "license": "MIT",
  "keywords": [
    "claude-code",
    "claude-skills",
    "investing",
    "india",
    "nse",
    "zerodha",
    "kite",
    "stock-market",
    "portfolio"
  ],
  "skills": "./"
}
```

`.claude-plugin/marketplace.json`:

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "trader-skill",
  "description": "The Trader skill pack for Claude, for the Indian stock market",
  "owner": {
    "name": "sisoppin",
    "url": "https://github.com/sisoppin"
  },
  "plugins": [
    {
      "name": "trader-skill",
      "description": "Eleven Claude skills for investing on NSE through Zerodha Kite: copy an investor's disclosed stakes or a mutual fund, watch NSE announcements, insider trades and bulk deals, read quarterly results, screen, size trades in whole shares, check risk, prepare LIVE Kite orders you approve, Indian capital-gains tax, price alerts and rebalancing.",
      "source": "./",
      "category": "productivity",
      "homepage": "https://github.com/sisoppin/trader-skill"
    }
  ]
}
```

`LICENSE`:

```
MIT License

Copyright (c) 2026 Jake Schincariol
Copyright (c) 2026 sisoppin

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- In `CLAUDE.md`, replace:

```
- This is a fork (`origin` = `sisoppin/trader-skill`). README, `plugin.json` and `test_repo.py` still hardcode `Jakeschincariol/trader-skill`, and a rebrand to sisoppin is planned. When rebranding, change README, `plugin.json`/`marketplace.json` and the `test_readme_carries_the_reel_copy` strings together.
```

  with:

```
- This is a fork of Jake Schincariol's US pack, now `sisoppin/trader-skill` (`origin`). The README install lines, `plugin.json` and `marketplace.json` (homepage, repository, author) and `test_repo.py` `REPO` all say `sisoppin/trader-skill`; change them together. LICENSE keeps the original copyright line above the new one.
```


- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_repo.py -v`
Expected: OK. Then run `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`.

```bash
git add README.md .claude-plugin/plugin.json .claude-plugin/marketplace.json LICENSE tests/test_repo.py CLAUDE.md
git commit -m "Rebrand to sisoppin/trader-skill and rewrite the README for NSE and Zerodha Kite" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 3: the US-term check, the last leftovers, and CLAUDE.md

**Files:**
- Modify:
  - `tests/test_repo.py` (adds `test_no_us_terms_left`)
  - `CLAUDE.md` (code rules, the scope note)
  - `.claude/skills/new-trader-skill/SKILL.md` (the data-source rule)
- Delete: `tests/fixtures/trader-budget/berkshire-q2-2026-top5.json` (a US 13F fixture that no test reads)

- [ ] **Step 1: Write the failing test**

- In `tests/test_repo.py`, replace:

```
    def test_shared_helpers_are_identical(self):
```

  with:

```
    def test_no_us_terms_left(self):
        # skill code, docs, manifests and fixtures; docs/ (the spec and the plans) and the test code are history
        terms = [re.compile(r"\bSEC\b"), re.compile(r"EDGAR"), re.compile(r"\b13F"), re.compile(r"CUSIP", re.I),
                 re.compile(r"Alpaca", re.I), re.compile(r"NYSE"), re.compile(r"(?<!no )wash[- ]sale", re.I),
                 re.compile(r"\bUSD\b")]
        hits = []
        for path in every_text_file():
            rel = os.path.relpath(path, ROOT)
            if rel.startswith("docs" + os.sep) or (rel.startswith("tests" + os.sep) and rel.endswith(".py")):
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                for n, line in enumerate(fh, 1):
                    hits += ["%s:%d: %s" % (rel, n, line.strip()[:80]) for t in terms if t.search(line)]
        self.assertEqual(hits, [])

    def test_shared_helpers_are_identical(self):
```


- [ ] **Step 2: Run it and confirm it fails**

Run: `cd tests && python3 -m unittest test_repo.Repo.test_no_us_terms_left -v; cd ..`
Expected: FAIL. The failure lists `CLAUDE.md` (its note that other skills "may still mention ... Alpaca"), `.claude/skills/new-trader-skill/SKILL.md` (the SEC User-Agent rule) and the Berkshire 13F fixture.

- [ ] **Step 3: Remove the leftovers**

```bash
git rm -q tests/fixtures/trader-budget/berkshire-q2-2026-top5.json
```

Each old text must match exactly once.

- In `CLAUDE.md`, replace:

```
- Python 3.8+, standard library only. No pip dependencies and no manifest files. `pdftotext` is an optional external binary.
```

  with:

```
- Python 3.8+, standard library only. No pip dependencies and no manifest files.
```

- In `CLAUDE.md`, replace:

```
- NSE calls go through `nse.Client` (cookie warm-up, a pause between requests, the daily cache in `trader/cache/nse/`). When NSE blocks a request, stop with exit code 2 and print the URL plus the `--file` or `--offline` rerun; never retry around a block.
```

  with:

```
- NSE calls go through `nse.Client` (cookie warm-up, a pause between requests, the daily cache in `trader/cache/nse/`). When NSE blocks a request, stop with exit code 2 and print the URL plus the `--file` or `--offline` rerun; never retry around a block.
- Kite data reaches the tools only as snapshots Claude saves from the Kite connector with `kite_snapshot.py save` into `trader/kite/`. Tools refuse stale ones (quotes over 120 seconds, holdings, positions, margins and orders over 10 minutes) and never call Kite themselves.
- A partial read never becomes output another skill acts on: a tool that could not read every stock exits 2, marks its file (`"complete": false`) or refuses `--write`.
```

- In `CLAUDE.md`, replace:

```
- The pack is being converted to India: see `docs/superpowers/specs/2026-10-26-indian-market-design.md` and the plans in `docs/superpowers/plans/`. Converted so far: trader-alerts (NSE clock, Kite quotes), the order path, trader-budget, trader-risk and trader-broker (Kite place_order shape, rupees, whole shares), the portfolio skills trader-rebalance and trader-tax (Kite holdings, Zerodha Console tradebook, Indian capital gains), trader-news and trader-insider (NSE announcements, SEBI insider trades, bulk and block deals; trader-pelosi was renamed trader-insider), and trader-analyst and trader-copycat (NSE results XBRL, NSE shareholding patterns, AMC portfolio sheets saved as CSV). The other skills are still US until their phase lands; their docs may still mention `ticket.py fill` or Alpaca. The shared helpers (`kite_snapshot.py`, `nse.py`, `nse_calendar.py`, `nse_symbols.py`, `rupees.py`, `charges.py` whose source copy is in trader-budget, and `watchlist.py` whose source copy is in trader-news) are copied into each skill that needs them and must stay byte-identical (`test_shared_helpers_are_identical`).
```

  with:

```
- The pack is for the Indian market (NSE, Zerodha Kite): see `docs/superpowers/specs/2026-10-26-indian-market-design.md` and the phase plans in `docs/superpowers/plans/`. All 11 skills are converted, and `test_no_us_terms_left` fails if a US-market term (its list is in the test) comes back into skill code, docs, manifests or fixtures (docs/ and the test code are exempt). The shared helpers (`kite_snapshot.py`, `nse.py`, `nse_calendar.py`, `nse_symbols.py`, `rupees.py`, `charges.py` whose source copy is in trader-budget, and `watchlist.py` whose source copy is in trader-news) are copied into each skill that needs them and must stay byte-identical (`test_shared_helpers_are_identical`).
```

- In `.claude/skills/new-trader-skill/SKILL.md`, replace:

```
- Network calls need a polite User-Agent and `time.sleep` pacing. SEC calls need `SEC_USER_AGENT`, and you must never invent one.
```

  with:

```
- NSE data goes through the shared `nse.py` client (copy it unchanged from `trader-alerts/`), and every fetch accepts `--file` or `--offline` for when NSE blocks; a block exits 2 with the URL. Kite data comes only from snapshots saved by `kite_snapshot.py`. Ask before adding any other data source.
- Copy shared helpers unchanged from their source copy (CLAUDE.md lists them). A new shared helper goes into `SHARED` in `tests/test_repo.py`.
```


- [ ] **Step 4: Verify and commit**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache . && ! grep -rl "$(printf '\342\200\224')" trader-* tests docs CLAUDE.md README.md .claude .claude-plugin LICENSE`
Expected: `OK` (343 tests), then `All checks passed!`, and no file names printed. Also run `~/.local/bin/uv run --no-project --python 3.8 python -m unittest discover -s tests` and expect `OK`.

```bash
git add -A tests/test_repo.py CLAUDE.md .claude/skills/new-trader-skill/SKILL.md tests/fixtures/trader-budget
git commit -m "Add the US-term check and remove the last US references" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

