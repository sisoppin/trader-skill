# India Phase 3 (Portfolio) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert trader-rebalance to Kite holdings and LIVE Kite orders, and rebuild trader-tax for Indian listed equity: FIFO lots from the Zerodha Console tradebook, intraday versus delivery, STCG and LTCG with the 2018 rule, per-financial-year set-off, the exemption, carry-forward, an estimate and harvesting.

**Architecture:**
- **trader-rebalance** reads the holdings, positions (today's CNC), margins and quotes snapshots.
  - It keeps its drift and capping maths.
  - It writes whole-share LIMIT orders with estimated charges.
  - Buys spend only cash above the buffer, the same rule trader-risk applies (no same-day sale proceeds).
- **trader-tax** is split into four focused modules:
  - `tradebook.py`: Console CSV, Kite trades and opening lots, merged by trade id
  - `ledger.py`: intraday, FIFO lots, term, the 2018 rule
  - `india_tax.py`: financial years, set-off, exemption, carry-forward, estimate
  - `lots.py`: the CLI, the report and harvesting
- `charges.py` becomes a shared helper (its source copy is in trader-budget).

**Tech Stack:** Python 3.8+, standard library only, `unittest` with offline fixtures.

**Spec:** `docs/superpowers/specs/2026-10-26-indian-market-design.md` (sections 2, 6 and 9, phase 3)

**Branch:** work on `feat/india-phase3`, branched from `feat/india-phase2`.

**Provenance:** all the code in this plan was drafted and run in a scratch worktree first. The suite passed with 271 tests under Python 3.12 and 3.8, and ruff was clean. Every expected value below comes from those runs.

**Spec refinement (flag at review):** spec section 6 says the tax inputs are `trader/kite/trades.json` and `lots.csv`. Kite's API only returns the current day's trades, so the history comes from the Zerodha Console tradebook CSV. Today's Kite trades and `lots.csv` (opening lots) are added on top, all merged by trade id.

## Global Constraints

- Python 3.8 or newer, standard library only. No em dashes (U+2014) in any .md, .py, .json, .csv, .txt or .xml file.
- Every order is LIVE, real money. Orders use Kite fields with string quantities and prices, plus `est_value`, `est_charges` and `why`. trader-risk requires `est_charges` of at least 0 and circuit limits in the quotes.
- **Shared helpers:**
  - `kite_snapshot.py`, `nse.py`, `nse_calendar.py`, `nse_symbols.py` and `rupees.py` are copied unchanged from `trader-alerts/`.
  - `charges.py` is copied unchanged from `trader-budget/`.
  - `tests/test_repo.py` checks that the copies are identical and that every helper a script imports is in the same folder.
- `--now` works only when `TRADER_TEST_CLOCK=1`, which `tests/_load.py` sets.
- Tax defaults, all in config (`tax_rules`):
  - STCG 20%, LTCG 12.5% above Rs 1,25,000 a year
  - carry-forward 8 years (4 for speculative)
  - estimates from FY 2025-26
  - more than 12 months is long term; financial years run 1 April to 31 March
- Never run a tool from the repo root (it creates `trader/`). Lint with `--no-cache`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full check: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`

## Review Focus

1. **The same tradebook downloaded twice, or overlapping years:** every trade id counts once. Covered by Task 6 `test_the_same_tradebook_twice_counts_once`.
2. **Splits, bonuses or a missing earlier tradebook:** the lots disagree with Kite holdings, and the report must say so per stock instead of silently computing wrong gains. Covered by Task 6 `test_lots_that_do_not_match_kite_are_flagged`.
3. **The exact 12-month boundary:** bought 2025-01-10, sold 2026-01-10 is short term; sold 2026-01-11 is long term. Covered by Task 4 `test_more_than_twelve_months_is_long_term`.
4. **Rebalance buys funded by same-day sales:** trader-risk would block them, so rebalance must spend only cash above the buffer. Covered by Task 2 `test_sells_first_then_buys_within_free_cash` and `test_the_orders_pass_the_risk_check`.
5. **A harvest gain sell over the max order:** cut to `max_order_value`, with a note, so trader-risk does not block it. Covered by Task 6 `test_losses_and_long_term_headroom`.

---

### Task 1: Confirm Kite and Console formats (manual gate)

The Kite login and checks from Phase 1 and Phase 2 Task 1 cover this too. **Nothing merges, and no live order may be placed, until this is done.** Do not commit real account data.

**Files:**
- Update: `docs/superpowers/notes/2026-10-26-kite-connector.md`

- [ ] **Step 1:** Log in to the Kite connector (`ToolSearch` `+kite`; the user runs `/mcp` and picks **claude.ai kite**).
- [ ] **Step 2:** Call the trades tool and compare its fields with what `tradebook.kite_trades` reads: `trade_id`, `exchange`, `tradingsymbol`, `transaction_type`, `quantity`, `average_price`, `fill_timestamp`. Also confirm the holdings fields: `tradingsymbol`, `quantity`, `t1_quantity`.
- [ ] **Step 3:** Ask the user to download one Zerodha Console equity tradebook (CSV). Check that its header contains `symbol, trade_date, exchange, segment, trade_type, quantity, price, trade_id`. Write the header only, not the rows, into the notes file.
- [ ] **Step 4:** If anything differs, update `tradebook.py` (Task 3) and its fixtures before continuing, and tell the user.
- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/notes/2026-10-26-kite-connector.md
git commit -m "Record Kite trades and Console tradebook formats" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 2: trader-rebalance on Kite holdings

This task also makes `charges.py` a shared helper and adds the `rebalance_band_pct` and `tax_rules` config keys.

**Files:**
- Copy (unchanged):
  - `trader-alerts/{kite_snapshot,nse,nse_symbols,rupees}.py` into `trader-rebalance/`
  - `trader-budget/charges.py` into `trader-rebalance/`
- Modify: `trader-rebalance/rebalance.py` (everything except `capped_targets`), `trader-budget/config.example.json` (two new keys), `tests/test_repo.py` (`SHARED`)
- Replace: `tests/test_rebalance.py`
- Delete: `tests/fixtures/trader-rebalance/{config,portfolio,prices,targets}.json`
- Create: `tests/fixtures/trader-rebalance/targets.json`, `tests/fixtures/trader-rebalance/kite/{holdings,positions,margins,orders,quotes}.json`

**Interfaces:**
- Consumes: `charges.estimate`, `kite_snapshot.load/quotes/IST`, `nse_symbols.normalize`, `rupees.inr`. The tests also use `check.check`, `check.load_data` and `check.nse_calendar` from trader-risk.
- Produces:
  - `rebalance.parse_targets(doc, blocked=()) -> {SYM: pct}`
  - `rebalance.account(snap) -> (cash, {SYM: shares})`
  - `rebalance.load_snapshots(kite_dir, now=None) -> {"holdings", "positions", "margins", "quotes"}`
  - `rebalance.plan(cash, held, prices, weights, cfg, band=None, sell_untracked=False) -> {"account_value", "cash", "cash_buffer", "cap", "band", "rows", "orders", "notes", "cash_after_buys"}`
  - Each order is in Kite shape with `est_value`, `est_charges` and `why`.

- [ ] **Step 1: Write the fixtures**

```bash
git rm -q tests/fixtures/trader-rebalance/config.json tests/fixtures/trader-rebalance/portfolio.json tests/fixtures/trader-rebalance/prices.json tests/fixtures/trader-rebalance/targets.json
```

`tests/fixtures/trader-rebalance/targets.json`:

```json
{"source": "an example: four large NSE stocks, equal weight", "weights": [
  {"symbol": "INFY", "weight": 25}, {"symbol": "RELIANCE", "weight": 25},
  {"symbol": "TCS", "weight": 25}, {"symbol": "HDFCBANK", "weight": 25}
]}
```

`tests/fixtures/trader-rebalance/kite/holdings.json`:

```json
{"fetched_at": "2026-10-26T10:00:00+05:30", "data": [
  {"tradingsymbol": "INFY", "exchange": "NSE", "quantity": 14, "t1_quantity": 0, "last_price": 1612.5},
  {"tradingsymbol": "RELIANCE", "exchange": "NSE", "quantity": 4, "t1_quantity": 0, "last_price": 1402.3},
  {"tradingsymbol": "TCS", "exchange": "NSE", "quantity": 3, "t1_quantity": 0, "last_price": 3050.5},
  {"tradingsymbol": "HDFCBANK", "exchange": "NSE", "quantity": 6, "t1_quantity": 0, "last_price": 1650.0},
  {"tradingsymbol": "ITC", "exchange": "NSE", "quantity": 10, "t1_quantity": 0, "last_price": 410.0}
]}
```

`tests/fixtures/trader-rebalance/kite/positions.json`:

```json
{"fetched_at": "2026-10-26T10:00:00+05:30", "data": {"net": [], "day": []}}
```

`tests/fixtures/trader-rebalance/kite/margins.json`:

```json
{"fetched_at": "2026-10-26T10:00:00+05:30", "data": {"equity": {"net": 20000.0, "available": {"cash": 20000.0, "live_balance": 20000.0}}}}
```

`tests/fixtures/trader-rebalance/kite/orders.json`:

```json
{"fetched_at": "2026-10-26T10:00:00+05:30", "data": []}
```

`tests/fixtures/trader-rebalance/kite/quotes.json`:

```json
{
  "fetched_at": "2026-10-26T10:00:00+05:30",
  "data": {
    "NSE:INFY": {
      "timestamp": "2026-10-26 09:59:58",
      "last_trade_time": "2026-10-26 09:59:57",
      "last_price": 1612.5,
      "lower_circuit_limit": 1451.25,
      "upper_circuit_limit": 1773.75,
      "ohlc": {
        "open": 1598.0,
        "high": 1620.0,
        "low": 1590.1,
        "close": 1590.0
      }
    },
    "NSE:RELIANCE": {
      "timestamp": "2026-10-26 09:59:59",
      "last_trade_time": "2026-10-26 09:59:58",
      "last_price": 1402.3,
      "lower_circuit_limit": 1274.95,
      "upper_circuit_limit": 1558.25,
      "ohlc": {
        "open": 1415.0,
        "high": 1419.9,
        "low": 1398.0,
        "close": 1416.6
      }
    },
    "NSE:TCS": {
      "timestamp": "2026-10-26 09:59:59",
      "last_trade_time": "2026-10-26 09:59:56",
      "last_price": 3050.5,
      "lower_circuit_limit": 2745.45,
      "upper_circuit_limit": 3355.55,
      "ohlc": {
        "open": 3040.0,
        "high": 3062.0,
        "low": 3031.0,
        "close": 3035.0
      }
    },
    "NSE:HDFCBANK": {
      "timestamp": "2026-10-26 09:59:59",
      "last_trade_time": "2026-10-26 09:59:59",
      "last_price": 1650.0,
      "lower_circuit_limit": 1485.0,
      "upper_circuit_limit": 1815.0,
      "ohlc": {
        "open": 1642.0,
        "high": 1655.0,
        "low": 1640.5,
        "close": 1645.0
      }
    },
    "NSE:ITC": {
      "timestamp": "2026-10-26 09:59:59",
      "last_trade_time": "2026-10-26 09:59:58",
      "last_price": 410.0,
      "lower_circuit_limit": 369.0,
      "upper_circuit_limit": 451.0,
      "ohlc": {
        "open": 408.0,
        "high": 412.0,
        "low": 406.5,
        "close": 409.0
      }
    }
  }
}
```


- [ ] **Step 2: Write the failing tests**

Replace `tests/test_rebalance.py` with:

```python
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

rebalance = load("trader-rebalance", "rebalance")
check = load("trader-risk", "check")

RDIR = os.path.join(FIX, "trader-rebalance")
KDIR = os.path.join(RDIR, "kite")
TARGETS = os.path.join(RDIR, "targets.json")
CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
NOW = "2026-10-26T10:01"


def cfg(**over):
    with open(CFG_PATH) as fh:
        c = json.load(fh)
    c.update(over)
    return c


def setup(**over):
    snap = rebalance.load_snapshots(KDIR, check.nse_calendar.parse_now(NOW))
    cash, held = rebalance.account(snap)
    prices = {s: q["price"] for s, q in snap["quotes"].items()}
    with open(TARGETS) as fh:
        weights = rebalance.parse_targets(json.load(fh), over.get("blocked"))
    return cash, held, prices, weights, cfg(**over)


def orders(res):
    return [(o["transaction_type"], o["tradingsymbol"], o["quantity"]) for o in res["orders"]]


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = rebalance.main(argv)
    return code, out.getvalue(), err.getvalue()


class Example(unittest.TestCase):
    def test_sells_first_then_buys_within_free_cash(self):
        res = rebalance.plan(*setup())
        self.assertEqual(res["account_value"], 71335.7)
        self.assertEqual([(r["symbol"], r["action"]) for r in res["rows"]],
                         [("HDFCBANK", "buy"), ("INFY", "sell"), ("RELIANCE", "buy"), ("TCS", "buy"),
                          ("ITC", "untracked, left alone")])
        self.assertEqual(orders(res), [("SELL", "INFY", "4"), ("BUY", "HDFCBANK", "2"), ("BUY", "RELIANCE", "4"),
                                       ("BUY", "TCS", "1")])
        self.assertEqual(res["cash_after_buys"], 8026.1)
        self.assertGreater(res["cash_after_buys"], res["cash_buffer"])
        self.assertIn("buys scaled to 55%", res["notes"][0])
        o = res["orders"][0]
        self.assertEqual((o["product"], o["order_type"], o["price"], o["est_value"], o["est_charges"]),
                         ("CNC", "LIMIT", "1612.50", "6450.00", "6.69"))

    def test_the_orders_pass_the_risk_check(self):
        res = rebalance.plan(*setup())
        now = check.nse_calendar.parse_now(NOW)
        cal = check.nse_calendar.Calendar(dict(check.nse_calendar.HOLIDAYS), check.nse_calendar.YEARS)
        risk = check.check(res["orders"], cfg(), check.load_data(KDIR, now), now, cal)
        self.assertEqual([r["verdict"] for r in risk["results"]], ["PASS"] * 4, risk["results"])


class Rules(unittest.TestCase):
    def test_sell_untracked_and_blocked(self):
        res = rebalance.plan(*setup(), sell_untracked=True)
        self.assertEqual(orders(res)[1], ("SELL", "ITC", "10"))
        res = rebalance.plan(*setup(blocked=["infy.ns"]))
        self.assertEqual([r["action"] for r in res["rows"] if r["symbol"] == "INFY"], ["untracked, left alone"])

    def test_band(self):
        self.assertEqual(rebalance.plan(*setup(), band=15)["orders"], [])
        res = rebalance.plan(*setup(), band=10)
        self.assertEqual(orders(res), [("BUY", "RELIANCE", "7")])
        self.assertIn("RELIANCE buy cut to your Rs 10,000 max order", " ".join(res["notes"]))

    def test_max_order_and_order_count(self):
        res = rebalance.plan(*setup(max_order_value="3000"))
        self.assertEqual(orders(res)[0], ("SELL", "INFY", "1"))
        self.assertIn("INFY sell cut to your Rs 3,000 max order", " ".join(res["notes"]))
        res = rebalance.plan(*setup(max_orders_per_day=2))
        self.assertEqual(len(res["orders"]), 2)
        self.assertIn("kept the first 2 (sells first)", res["notes"][-1])

    def test_todays_delivery_trades_count_as_held(self):
        snap = {"holdings": [{"tradingsymbol": "INFY", "quantity": 14, "t1_quantity": 0}],
                "positions": {"net": [{"tradingsymbol": "INFY", "product": "CNC", "quantity": -4},
                                      {"tradingsymbol": "TCS", "product": "MIS", "quantity": 5}], "day": []},
                "margins": {"equity": {"available": {"live_balance": 100.0}}}}
        self.assertEqual(rebalance.account(snap), (100.0, {"INFY": 10}))
        with self.assertRaises(rebalance.RebalanceError):
            rebalance.account(dict(snap, margins={"commodity": {}}))

    def test_missing_quote_and_bad_config(self):
        cash, held, prices, weights, c = setup()
        del prices["TCS"]
        with self.assertRaises(rebalance.RebalanceError) as e:
            rebalance.plan(cash, held, prices, weights, c)
        self.assertIn("NSE:TCS", str(e.exception))
        with self.assertRaises(rebalance.RebalanceError):
            rebalance.plan(*setup(cash_buffer_pct="nan"))


class Cli(unittest.TestCase):
    def base(self):
        return ["--targets", TARGETS, "--config", CFG_PATH, "--kite-dir", KDIR]

    def test_write_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            code, text, _ = run(self.base() + ["--now", NOW, "--write", out])
            self.assertEqual(code, 0)
            self.assertIn("Proposed LIVE orders", text)
            self.assertIn("not financial advice", text)
            with open(out) as fh:
                doc = json.load(fh)
            self.assertEqual((doc["created_by"], doc["live"], len(doc["orders"])), ("trader-rebalance", True, 4))
            code, text, _ = run(self.base() + ["--now", NOW, "--band", "15"])
            self.assertEqual(code, 1)
            self.assertIn("Nothing is outside the band", text)

    def test_stale_snapshots_and_the_test_clock(self):
        code, _, err = run(self.base() + ["--now", "2026-10-26T10:05"])
        self.assertEqual(code, 1)
        self.assertIn("quotes snapshot is", err)
        saved = os.environ.pop("TRADER_TEST_CLOCK")
        try:
            code, _, err = run(self.base() + ["--now", NOW])
        finally:
            os.environ["TRADER_TEST_CLOCK"] = saved
        self.assertEqual(code, 1)
        self.assertIn("for tests only", err)


if __name__ == "__main__":
    unittest.main()
```

In `tests/test_repo.py`, replace:

```python
SHARED = ["kite_snapshot.py", "nse.py", "nse_calendar.py", "nse_symbols.py", "rupees.py"]
```

with:

```python
SHARED = ["kite_snapshot.py", "nse.py", "nse_calendar.py", "nse_symbols.py", "rupees.py", "charges.py"]
```

In `trader-budget/config.example.json`, add these two keys after `"charges": {}` (keep the other keys exactly as they are):

```json
  "rebalance_band_pct": "5",
  "tax_rules": {}
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_rebalance.py -v`
Expected: errors, because `rebalance` has no `load_snapshots`/`account` and the fixtures are new.

- [ ] **Step 4: Implement**

```bash
cp trader-alerts/kite_snapshot.py trader-alerts/nse.py trader-alerts/nse_symbols.py trader-alerts/rupees.py trader-rebalance/
cp trader-budget/charges.py trader-rebalance/
```

Rewrite `trader-rebalance/rebalance.py` as three parts, in order:
1. the head below
2. the existing `def capped_targets(...)` function, unchanged except its docstring, which becomes `"""Rupee target per symbol, proportional to weight, none above the cap."""`
3. the tail below

Head (from the first line up to `def capped_targets`):

```python
#!/usr/bin/env python3
"""Rebalancer for trader-rebalance. Standard library only, no network.

Compares what you hold, from the Kite snapshots (holdings, today's delivery
positions, margins for cash, quotes for prices), with your target weights
(trader/targets.json, capped by your rules) and proposes the LIVE orders that
bring every stock outside the band back to its target. It never places
anything: trader-risk checks each order and trader-broker asks for your yes.

    python3 rebalance.py                      # report only
    python3 rebalance.py --band 5 --write     # write trader/orders.json (proposals)
    python3 rebalance.py --sell-untracked     # also sell holdings that are not in the targets
    python3 rebalance.py --json

The rules:
  value         account = available cash + every holding at its Kite price
  targets       weights renormalised to 100 over the stock sleeve, which is the
                account minus your cash buffer; no stock over max_position_pct
                of the account (the excess is shared out, like trader-budget)
  drift         current % of the account minus target %, in percentage points
  band          only stocks drifting MORE than the band trade (default 5
                points, or "rebalance_band_pct" in the config); a trade takes
                the stock all the way back to its target
  whole shares  NSE has no fractional shares; every order is a LIMIT order at
                the Kite last price, with Zerodha's charges estimated
  sells first   sells are listed before buys
  cash          buys spend only cash above your buffer, charges included; sale
                proceeds are NOT counted the same day (trader-risk does the
                same), so run it again after the sales settle
  min / max     orders under min_order_value are skipped; an order over
                max_order_value is cut to the max (run it again later)
  order count   at most max_orders_per_day orders (sells first); trader-risk
                also counts what Kite's order book already shows today
  untracked     holdings not in the targets are left alone and listed, unless
                --sell-untracked

Exit code 0 when there are orders to propose, 1 when nothing is outside the band.
"""

import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import charges
import kite_snapshot
import nse_symbols
from rupees import inr

DEFAULTS = {"cash_buffer_pct": 10, "max_position_pct": 25, "max_order_value": 10000, "min_order_value": 100,
            "max_orders_per_day": 5, "blocked": [], "rebalance_band_pct": 5}
EPS = 1e-9


class RebalanceError(Exception):
    pass


def read_json(path, what, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise RebalanceError("no %s at %s" % (what, path))
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise RebalanceError("%s is not valid JSON: %s" % (path, e))


def _symbol(text):
    try:
        return nse_symbols.normalize(text)
    except nse_symbols.SymbolError as e:
        raise RebalanceError(str(e))


def _num(v, what):
    try:
        x = float(v)
    except (TypeError, ValueError):
        x = None
    if x is None or x != x or x in (float("inf"), float("-inf")) or x < 0:
        raise RebalanceError("config %s must be a number of at least 0, got %r" % (what, v))
    return x


def parse_targets(doc, blocked=()):
    rows = doc.get("weights", doc) if isinstance(doc, dict) else doc
    if isinstance(rows, dict):
        rows = [{"symbol": k, "weight": v} for k, v in rows.items()]
    blocked = {_symbol(b) for b in blocked or []}
    out = {}
    for r in rows or []:
        t = _symbol(r.get("symbol") or r.get("ticker"))
        w = _num(r.get("weight", 0) or 0, "weight for %s" % t)
        if w > 0 and t not in blocked:
            out[t] = out.get(t, 0.0) + w
    tot = sum(out.values())
    if not tot:
        raise RebalanceError("no target weights (run trader-copycat, or write trader/targets.json)")
    return {t: 100.0 * w / tot for t, w in out.items()}
```

Tail (from `def account(snap):` to the end of the file):

```python
def account(snap):
    """(cash, {SYM: shares}) from the Kite holdings, positions (today's CNC) and margins snapshots."""
    m = snap["margins"]
    av = ((m or {}).get("equity") or {}).get("available") or {}
    cash = av.get("live_balance", av.get("cash"))
    try:
        cash = float(cash)
    except (TypeError, ValueError):
        raise RebalanceError("the margins snapshot has no equity cash (Kite answer changed?)")
    held = {}
    for r in snap["holdings"] or []:
        s = str(r.get("tradingsymbol", "")).upper()
        held[s] = held.get(s, 0) + int(float(r.get("quantity") or 0) + float(r.get("t1_quantity") or 0))
    for r in (snap["positions"] or {}).get("net") or []:
        if r.get("product") == "CNC":
            s = str(r.get("tradingsymbol", "")).upper()
            held[s] = held.get(s, 0) + int(float(r.get("quantity") or 0))
    return cash, {s: n for s, n in held.items() if n}


def _order(sym, side, qty, price, cfg, why):
    value = qty * price
    est = charges.estimate("CNC", side, value, cfg.get("charges"))
    return {"exchange": "NSE", "tradingsymbol": sym, "transaction_type": side, "quantity": str(int(qty)),
            "product": "CNC", "order_type": "LIMIT", "price": "%.2f" % price, "validity": "DAY",
            "variety": "regular", "est_value": "%.2f" % value, "est_charges": "%.2f" % est["total"], "why": why}


def plan(cash, held, prices, weights, cfg, band=None, sell_untracked=False):
    """Pure function: the drift table and the proposed Kite orders."""
    c = dict(DEFAULTS)
    c.update(cfg or {})
    band = _num(c["rebalance_band_pct"] if band is None else band, "rebalance_band_pct")
    buf_pct, cap_pct = _num(c["cash_buffer_pct"], "cash_buffer_pct"), _num(c["max_position_pct"], "max_position_pct")
    min_o, max_o = _num(c["min_order_value"], "min_order_value"), _num(c["max_order_value"], "max_order_value")
    max_n = int(_num(c["max_orders_per_day"], "max_orders_per_day"))
    need = sorted(set(held) | set(weights), key=lambda t: (-weights.get(t, 0.0), t))
    missing = [t for t in need if not prices.get(t)]
    if missing:
        raise RebalanceError("no Kite quote for %s: add %s to the quotes call, then kite_snapshot.py save quotes"
                             % (", ".join(missing), " ".join("NSE:" + m for m in missing)))
    value = {t: held.get(t, 0) * prices[t] for t in need}
    total = cash + sum(value.values())
    if total <= 0:
        raise RebalanceError("the account is empty: nothing to rebalance (trader-budget sizes a first buy)")
    buf = total * buf_pct / 100.0
    cap = total * cap_pct / 100.0
    target = capped_targets(weights, total - buf, cap)

    rows, sells, buys, notes = [], [], [], []
    for t in need:
        tracked = t in weights
        tgt = target.get(t, 0.0)
        cur_pct, tgt_pct = 100.0 * value[t] / total, 100.0 * tgt / total
        drift = cur_pct - tgt_pct
        row = {"symbol": t, "shares": held.get(t, 0), "price": prices[t], "value": round(value[t], 2),
               "current_pct": round(cur_pct, 2), "target_pct": round(tgt_pct, 2),
               "drift": round(drift, 2) if abs(drift) >= 0.005 else 0.0, "target_value": round(tgt, 2),
               "tracked": tracked, "action": "hold"}
        rows.append(row)
        if not tracked:
            if sell_untracked and held.get(t, 0) > 0:
                sells.append((t, held[t], "not in your targets; selling the whole position (--sell-untracked)"))
                row["action"] = "sell all"
            else:
                row["action"] = "untracked, left alone"
            continue
        if abs(drift) <= band + EPS:
            continue
        why = "drifted %+.1f points from its %.1f%% target (band %s)" % (drift, tgt_pct, _n(band))
        delta = tgt - value[t]
        if delta < 0:
            sells.append((t, min(int(-delta // prices[t]), held.get(t, 0)), why))
            row["action"] = "sell"
        else:
            buys.append((t, delta, why))
            row["action"] = "buy"

    orders = []
    for t, qty, why in sells:
        p = prices[t]
        if max_o and qty * p > max_o + EPS:
            qty = int(max_o // p)
            notes.append("%s sell cut to your %s max order; run again later" % (t, inr(max_o)))
        if qty < 1 or qty * p < min_o - EPS:
            notes.append("%s sell of %s is under one share or your %s minimum order: skipped"
                         % (t, inr(qty * p), inr(min_o)))
            continue
        orders.append(_order(t, "SELL", qty, p, c, why))

    spendable = max(cash - buf, 0.0)
    want = sum(d for _, d, _ in buys)
    scale = 1.0
    if want > spendable + EPS:
        scale = spendable / want if want else 0.0
        notes.append("buys scaled to %.0f%%: only %s is free above your %s cash buffer (sale proceeds count "
                     "after they settle)" % (100 * scale, inr(spendable), inr(buf)))
    for t, delta, why in buys:
        p = prices[t]
        rupees = delta * scale
        if max_o and rupees > max_o + EPS:
            rupees = max_o
            notes.append("%s buy cut to your %s max order; run again later" % (t, inr(max_o)))
        qty = int(rupees // p)
        while qty and qty * p + charges.estimate("CNC", "BUY", qty * p, c.get("charges"))["total"] > rupees + EPS:
            qty -= 1
        if qty < 1 or qty * p < min_o - EPS:
            notes.append("%s buy of %s does not reach one whole share or your %s minimum: skipped"
                         % (t, inr(rupees), inr(min_o)))
            continue
        orders.append(_order(t, "BUY", qty, p, c, why))

    if max_n and len(orders) > max_n:
        notes.append("%d orders proposed; kept the first %d (sells first) for your %d-a-day limit, run again "
                     "tomorrow for the rest" % (len(orders), max_n, max_n))
        orders = orders[:max_n]
    spent = sum(float(o["est_value"]) + float(o["est_charges"]) for o in orders if o["transaction_type"] == "BUY")
    return {"account_value": round(total, 2), "cash": round(cash, 2), "cash_buffer": round(buf, 2),
            "cap": round(cap, 2), "band": band, "rows": rows, "orders": orders, "notes": notes,
            "cash_after_buys": round(cash - spent, 2)}


def _n(x):
    x = float(x)
    return str(int(x)) if x == int(x) else "%.2f" % x


def report(res):
    lines = ["Account %s (cash %s, buffer %s, cap %s per stock), band %s points"
             % (inr(res["account_value"]), inr(res["cash"]), inr(res["cash_buffer"]), inr(res["cap"]),
                _n(res["band"])), ""]
    lines.append("%-12s %7s %12s %14s %8s %9s %8s  %s" % ("symbol", "shares", "price", "value", "now %",
                                                         "target %", "drift", "action"))
    for r in res["rows"]:
        lines.append("%-12s %7d %12s %14s %7.2f%% %8.2f%% %+8.2f  %s"
                     % (r["symbol"], r["shares"], inr(r["price"]), inr(r["value"]), r["current_pct"],
                        r["target_pct"], r["drift"], r["action"]))
    lines.append("")
    if res["orders"]:
        lines.append("Proposed LIVE orders, sells first (Kite place_order arguments; nothing has been placed):")
        for o in res["orders"]:
            lines.append("  %s %s %s, CNC, LIMIT %s, est. %s + %s charges" % (
                o["transaction_type"], o["quantity"], o["tradingsymbol"], inr(o["price"]), inr(o["est_value"]),
                inr(o["est_charges"])))
        lines.append("Cash after the buys, if they fill: about %s (sale proceeds not counted)."
                     % inr(res["cash_after_buys"]))
    else:
        lines.append("Nothing is outside the band. No trades.")
    for n in res["notes"]:
        lines.append("Note: " + n)
    lines.append("")
    lines.append("Selling can realise a taxable gain: check trader-tax (lots.py sell) first. Then trader-risk "
                 "checks every order and trader-broker asks you yes or no for each one.")
    lines.append("Education and tooling, not financial advice.")
    return "\n".join(lines)


def load_snapshots(kite_dir, now=None):
    snap = {}
    for kind in ("holdings", "positions", "margins", "quotes"):
        try:
            v = kite_snapshot.load(kind, kite_dir, now=now)
        except kite_snapshot.SnapshotError as e:
            raise RebalanceError(str(e))
        snap[kind] = kite_snapshot.quotes(v) if kind == "quotes" else v
    if not isinstance(snap["holdings"], list) or not isinstance(snap["positions"], dict):
        raise RebalanceError("the holdings or positions snapshot is not in Kite's shape (Kite answer changed?)")
    return snap


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bring the portfolio back to its target weights (trader-rebalance).")
    ap.add_argument("--targets", default="trader/targets.json")
    ap.add_argument("--config", default="trader/config.json")
    ap.add_argument("--kite-dir", default=kite_snapshot.DIR, help="where the Kite snapshots are")
    ap.add_argument("--now", help="pretend it is this time (ISO, IST; tests only, needs TRADER_TEST_CLOCK=1)")
    ap.add_argument("--band", type=float, help="drift band in percentage points (default 5)")
    ap.add_argument("--sell-untracked", action="store_true", help="sell holdings that are not in the targets")
    ap.add_argument("--write", nargs="?", const="trader/orders.json", metavar="PATH",
                    help="write the proposals (default trader/orders.json)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        now = None
        if a.now:
            if os.environ.get("TRADER_TEST_CLOCK") != "1":
                raise RebalanceError("--now is for tests only (set TRADER_TEST_CLOCK=1 to simulate)")
            t = datetime.datetime.fromisoformat(a.now.replace("Z", "+00:00"))
            now = t.replace(tzinfo=kite_snapshot.IST) if t.tzinfo is None else t.astimezone(kite_snapshot.IST)
        cfg = read_json(a.config, "config", required=False) or {}
        snap = load_snapshots(a.kite_dir, now)
        cash, held = account(snap)
        prices = {s: q["price"] for s, q in snap["quotes"].items()}
        weights = parse_targets(read_json(a.targets, "targets"), cfg.get("blocked"))
        res = plan(cash, held, prices, weights, cfg, a.band, a.sell_untracked)
        if a.write and res["orders"]:
            d = os.path.dirname(a.write)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(a.write, "w", encoding="utf-8") as fh:
                json.dump({"created_by": "trader-rebalance",
                           "created_at": (now or datetime.datetime.now(kite_snapshot.IST)).replace(microsecond=0)
                           .isoformat(), "status": "proposed", "live": True,
                           "note": ("Proposals only, sells first. Every order is a LIVE order with real money. "
                                    "Nothing is placed until trader-risk passes each order and you say yes to it."),
                           "orders": res["orders"]}, fh, indent=2)
                fh.write("\n")
    except (RebalanceError, ValueError, charges.ChargesError) as e:
        print("rebalance.py: %s" % e, file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print(report(res))
        if a.write and res["orders"]:
            print("Wrote %d proposed order(s) to %s." % (len(res["orders"]), a.write))
    return 0 if res["orders"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_rebalance.py -v`
Expected: all 9 tests pass. The example proposes SELL 4 INFY, then BUY 2 HDFCBANK, 4 RELIANCE and 1 TCS, leaving Rs 8,026.10 cash.

- [ ] **Step 6: Run the full suite and lint, then commit**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`

```bash
git add -A trader-rebalance trader-budget/config.example.json tests/test_rebalance.py tests/test_repo.py tests/fixtures/trader-rebalance
git commit -m "Convert trader-rebalance to Kite holdings and LIVE whole-share orders" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 3: `tradebook.py`, trades from Console, Kite and opening lots

**Files:**
- Copy (unchanged): `trader-alerts/nse.py` and `trader-alerts/nse_symbols.py` into `trader-tax/`
- Create: `trader-tax/tradebook.py`, `tests/test_tradebook.py`, plus the tax fixtures below

**Interfaces:**
- Produces:
  - `tradebook.TradeError`
  - `read_tradebook(path) -> (trades, skipped)`
  - `kite_trades(data) -> trades`
  - `read_lots(path) -> trades`
  - `read_fmv(path) -> {SYM: price}`
  - `merge(*lists) -> trades` (dedupe by `id`, then a stable sort by date)
  - `_symbol(text, where)`
  - A trade is `{"date": date, "symbol", "side": "BUY"|"SELL", "qty": int, "price": float, "id", "source"}`.

- [ ] **Step 1: Write the fixtures** (`tests/fixtures/trader-tax/`; `kite/quotes.json` is the trader-budget quotes fixture)

`tests/fixtures/trader-tax/tradebook-sample.csv`:

```
symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,trade_id,order_id,order_execution_time
TCS,INE467B01029,2024-03-01,NSE,EQ,EQ,buy,false,5.000000,3400.000000,T1,O1,2024-03-01T10:01:00
HDFCBANK,INE040A01034,2024-07-10,NSE,EQ,EQ,buy,false,10.000000,1600.000000,T2,O2,2024-07-10T10:02:00
NIFTY24JUL24500CE,,2024-07-10,NSE,FO,,buy,false,25.000000,120.000000,T99,O99,2024-07-10T11:00:00
RELIANCE,INE002A01018,2025-01-10,NSE,EQ,EQ,buy,false,10.000000,1250.000000,T3,O3,2025-01-10T10:03:00
ITC,INE154A01025,2025-02-03,NSE,EQ,EQ,buy,false,20.000000,460.000000,T4,O4,2025-02-03T09:20:00
ITC,INE154A01025,2025-02-03,NSE,EQ,EQ,sell,false,20.000000,455.000000,T5,O5,2025-02-03T14:50:00
TCS,INE467B01029,2025-03-03,NSE,EQ,EQ,sell,false,5.000000,4100.000000,T6,O6,2025-03-03T11:00:00
HDFCBANK,INE040A01034,2025-06-02,NSE,EQ,EQ,sell,false,4.000000,1500.000000,T7,O7,2025-06-02T11:00:00
RELIANCE,INE002A01018,2026-01-10,NSE,EQ,EQ,sell,false,5.000000,1400.000000,T8,O8,2026-01-10T11:00:00
RELIANCE,INE002A01018,2026-01-12,NSE,EQ,EQ,sell,false,3.000000,1420.000000,T9,O9,2026-01-12T11:00:00
INFY,INE009A01021,2026-05-04,NSE,EQ,EQ,sell,false,4.000000,1600.000000,T10,O10,2026-05-04T10:00:00
INFY,INE009A01021,2026-05-04,NSE,EQ,EQ,buy,false,2.000000,1590.000000,T11,O11,2026-05-04T14:00:00
TCS,INE467B01029,2026-08-03,NSE,EQ,EQ,buy,false,3.000000,3300.000000,T12,O12,2026-08-03T10:00:00
```

`tests/fixtures/trader-tax/lots.csv`:

```
date,symbol,quantity,price
2017-06-15,INFY,10,480.00
```

`tests/fixtures/trader-tax/fmv_2018.csv`:

```
symbol,fmv
INFY,1150.00
```

`tests/fixtures/trader-tax/kite/trades.json`:

```json
{"fetched_at": "2026-10-26T10:00:00+05:30", "data": [
  {"trade_id": "K1", "order_id": "OK1", "exchange": "NSE", "tradingsymbol": "HDFCBANK", "product": "CNC", "transaction_type": "SELL", "quantity": 2, "average_price": 1650.0, "fill_timestamp": "2026-10-26 09:45:12"}
]}
```

`tests/fixtures/trader-tax/kite/holdings.json`:

```json
{"fetched_at": "2026-10-26T10:00:00+05:30", "data": [
  {"tradingsymbol": "INFY", "exchange": "NSE", "quantity": 8, "t1_quantity": 0, "last_price": 1612.5},
  {"tradingsymbol": "HDFCBANK", "exchange": "NSE", "quantity": 4, "t1_quantity": 0, "last_price": 1650.0},
  {"tradingsymbol": "RELIANCE", "exchange": "NSE", "quantity": 2, "t1_quantity": 0, "last_price": 1402.3},
  {"tradingsymbol": "TCS", "exchange": "NSE", "quantity": 3, "t1_quantity": 0, "last_price": 3050.5}
]}
```

`tests/fixtures/trader-tax/kite/quotes.json`:

```json
{
  "fetched_at": "2026-10-26T10:00:00+05:30",
  "data": {
    "NSE:INFY": {"timestamp": "2026-10-26 09:59:58", "last_trade_time": "2026-10-26 09:59:57", "last_price": 1612.5, "lower_circuit_limit": 1451.25, "upper_circuit_limit": 1773.75, "ohlc": {"open": 1598.0, "high": 1620.0, "low": 1590.1, "close": 1590.0}},
    "NSE:RELIANCE": {"timestamp": "2026-10-26 09:59:59", "last_trade_time": "2026-10-26 09:59:58", "last_price": 1402.3, "lower_circuit_limit": 1274.95, "upper_circuit_limit": 1558.25, "ohlc": {"open": 1415.0, "high": 1419.9, "low": 1398.0, "close": 1416.6}},
    "NSE:TCS": {"timestamp": "2026-10-26 09:59:59", "last_trade_time": "2026-10-26 09:59:56", "last_price": 3050.5, "lower_circuit_limit": 2745.45, "upper_circuit_limit": 3355.55, "ohlc": {"open": 3040.0, "high": 3062.0, "low": 3031.0, "close": 3035.0}},
    "NSE:HDFCBANK": {"timestamp": "2026-10-26 09:59:59", "last_trade_time": "2026-10-26 09:59:59", "last_price": 1650.0, "lower_circuit_limit": 1485.0, "upper_circuit_limit": 1815.0, "ohlc": {"open": 1642.0, "high": 1655.0, "low": 1640.5, "close": 1645.0}}
  }
}
```


- [ ] **Step 2: Write the failing tests**

`tests/test_tradebook.py`:

```python
import datetime
import json
import os
import tempfile
import unittest

from _load import load, FIX

tb = load("trader-tax", "tradebook")

TDIR = os.path.join(FIX, "trader-tax")
BOOK = os.path.join(TDIR, "tradebook-sample.csv")
HEADER = "symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,trade_id,order_id,order_execution_time\n"


def write(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w") as fh:
        fh.write(text)
    return p


class Tradebook(unittest.TestCase):
    def test_reads_the_console_csv(self):
        trades, skipped = tb.read_tradebook(BOOK)
        self.assertEqual((len(trades), skipped), (12, 1))
        self.assertEqual(trades[0], {"date": datetime.date(2024, 3, 1), "symbol": "TCS", "side": "BUY", "qty": 5,
                                     "price": 3400.0, "id": "T1", "source": "tradebook-sample.csv"})
        self.assertEqual({t["side"] for t in trades}, {"BUY", "SELL"})

    def test_not_a_tradebook(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "x.csv", "symbol,quantity\nINFY,1\n")
            with self.assertRaises(tb.TradeError) as e:
                tb.read_tradebook(p)
            self.assertIn("no trade_date", str(e.exception))

    def test_bad_rows_name_the_line(self):
        rows = {
            "TCS,,2024-03-01,NSE,EQ,EQ,buy,false,1.5,3400,T1,O1,\n": "quantity must be a whole number",
            "TCS,,2024-03-01,NSE,EQ,EQ,buy,false,1,0,T1,O1,\n": "price must be a rupee amount",
            "TCS,,2024-03-01,NSE,EQ,EQ,hold,false,1,3400,T1,O1,\n": "trade_type must be buy or sell",
            "TCS,,yesterday,NSE,EQ,EQ,buy,false,1,3400,T1,O1,\n": "is not a date",
            "TCS,,2024-03-01,NSE,EQ,EQ,buy,false,nan,3400,T1,O1,\n": "quantity must be a whole number",
        }
        with tempfile.TemporaryDirectory() as d:
            for row, text in rows.items():
                p = write(d, "b.csv", HEADER + row)
                with self.assertRaises(tb.TradeError) as e:
                    tb.read_tradebook(p)
                self.assertIn("b.csv line 2", str(e.exception))
                self.assertIn(text, str(e.exception))

    def test_dd_mm_yyyy_dates(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "b.csv", HEADER + "TCS,,01-03-2024,NSE,EQ,EQ,BUY,false,1,3400,T1,O1,\n")
            self.assertEqual(tb.read_tradebook(p)[0][0]["date"], datetime.date(2024, 3, 1))


class OtherSources(unittest.TestCase):
    def test_kite_trades(self):
        with open(os.path.join(TDIR, "kite", "trades.json")) as fh:
            data = json.load(fh)["data"]
        data.append({"trade_id": "B1", "exchange": "BSE", "tradingsymbol": "INFY", "transaction_type": "BUY",
                     "quantity": 1, "average_price": 1600, "fill_timestamp": "2026-10-26 10:00:00"})
        self.assertEqual(tb.kite_trades(data), [{"date": datetime.date(2026, 10, 26), "symbol": "HDFCBANK",
                                                 "side": "SELL", "qty": 2, "price": 1650.0, "id": "K1",
                                                 "source": "kite"}])

    def test_lots_and_fmv(self):
        lots = tb.read_lots(os.path.join(TDIR, "lots.csv"))
        self.assertEqual([(t["date"], t["symbol"], t["side"], t["qty"], t["price"]) for t in lots],
                         [(datetime.date(2017, 6, 15), "INFY", "BUY", 10, 480.0)])
        self.assertEqual(tb.read_fmv(os.path.join(TDIR, "fmv_2018.csv")), {"INFY": 1150.0})
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(tb.TradeError):
                tb.read_lots(write(d, "l.csv", "symbol,quantity\nINFY,1\n"))

    def test_merge_dedupes_by_trade_id_and_keeps_day_order(self):
        a = [{"date": datetime.date(2026, 5, 4), "id": "T10", "side": "SELL"},
             {"date": datetime.date(2026, 5, 4), "id": "T11", "side": "BUY"}]
        b = [{"date": datetime.date(2026, 1, 1), "id": "T1", "side": "BUY"}, dict(a[0], side="BUY")]
        merged = tb.merge(a, b)
        self.assertEqual([(t["id"], t["side"]) for t in merged], [("T1", "BUY"), ("T10", "SELL"), ("T11", "BUY")])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_tradebook.py -v`
Expected: an ERROR, because `trader-tax/tradebook.py` does not exist.

- [ ] **Step 4: Implement**

```bash
cp trader-alerts/nse.py trader-alerts/nse_symbols.py trader-tax/
```

`trader-tax/tradebook.py`:

```python
#!/usr/bin/env python3
"""Trades for trader-tax: Zerodha Console tradebooks, today's Kite trades, opening lots.

Kite's API only returns today's trades, so the history comes from Zerodha
Console (Reports > Tradebook > Equity, downloaded as CSV, one file per year
is fine). Today's trades come from the Kite trades snapshot. Holdings bought
before the tradebook starts go in trader/lots.csv:

    date,symbol,quantity,price
    2017-06-15,INFY,10,480.25

Every trade becomes {"date", "symbol", "side", "qty", "price", "id", "source"}.
Only NSE equity (segment EQ) trades are kept; others are counted and skipped.
"""

import csv
import datetime
import io
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import nse_symbols

TRADEBOOK_COLUMNS = ("symbol", "trade_date", "exchange", "segment", "trade_type", "quantity", "price", "trade_id")
LOTS_COLUMNS = ("date", "symbol", "quantity", "price")


class TradeError(Exception):
    pass


def _rows(path):
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            text = fh.read()
    except OSError as e:
        raise TradeError("cannot read %s: %s" % (path, e.strerror))
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for r in reader:
        rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in r.items() if k is not None})
    return [c.strip().lower() for c in (reader.fieldnames or [])], rows


def _date(text, where):
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    raise TradeError("%s: %r is not a date like 2026-10-26" % (where, text))


def _qty(text, where):
    try:
        v = float(text)
    except ValueError:
        v = None
    if v is None or not math.isfinite(v) or v <= 0 or v != int(v):
        raise TradeError("%s: quantity must be a whole number above 0, got %r" % (where, text))
    return int(v)


def _price(text, where):
    try:
        v = float(str(text).replace(",", ""))
    except ValueError:
        v = None
    if v is None or not math.isfinite(v) or v <= 0:
        raise TradeError("%s: price must be a rupee amount above 0, got %r" % (where, text))
    return v


def _symbol(text, where):
    try:
        return nse_symbols.normalize(text)
    except nse_symbols.SymbolError as e:
        raise TradeError("%s: %s" % (where, e))


def read_tradebook(path):
    """(trades, skipped) from a Zerodha Console equity tradebook CSV."""
    cols, rows = _rows(path)
    missing = [c for c in TRADEBOOK_COLUMNS if c not in cols]
    if missing:
        raise TradeError("%s is not a Zerodha Console tradebook: no %s column" % (path, ", ".join(missing)))
    trades, skipped = [], 0
    for i, r in enumerate(rows, 2):
        where = "%s line %d" % (os.path.basename(path), i)
        if r["exchange"].upper() != "NSE" or r["segment"].upper() != "EQ":
            skipped += 1
            continue
        side = r["trade_type"].upper()
        if side not in ("BUY", "SELL"):
            raise TradeError("%s: trade_type must be buy or sell, got %r" % (where, r["trade_type"]))
        trades.append({"date": _date(r["trade_date"], where), "symbol": _symbol(r["symbol"], where), "side": side,
                       "qty": _qty(r["quantity"], where), "price": _price(r["price"], where),
                       "id": r["trade_id"] or "%s:%d" % (path, i), "source": os.path.basename(path)})
    return trades, skipped


def kite_trades(data):
    """Today's trades from the Kite trades snapshot (NSE only)."""
    trades = []
    for i, r in enumerate(data or []):
        if not isinstance(r, dict) or str(r.get("exchange", "")).upper() != "NSE":
            continue
        where = "Kite trade %s" % (r.get("trade_id") or i)
        when = str(r.get("fill_timestamp") or r.get("exchange_timestamp") or r.get("order_timestamp") or "")
        side = str(r.get("transaction_type", "")).upper()
        if side not in ("BUY", "SELL"):
            raise TradeError("%s: transaction_type must be BUY or SELL" % where)
        trades.append({"date": _date(when, where), "symbol": _symbol(r.get("tradingsymbol"), where), "side": side,
                       "qty": _qty(str(r.get("quantity")), where), "price": _price(r.get("average_price"), where),
                       "id": str(r.get("trade_id") or "kite:%d" % i), "source": "kite"})
    return trades


def read_lots(path):
    """Opening lots (bought before the tradebook starts) as BUY trades."""
    cols, rows = _rows(path)
    missing = [c for c in LOTS_COLUMNS if c not in cols]
    if missing:
        raise TradeError("%s needs the columns date,symbol,quantity,price (missing %s)" % (path, ", ".join(missing)))
    out = []
    for i, r in enumerate(rows, 2):
        where = "%s line %d" % (os.path.basename(path), i)
        out.append({"date": _date(r["date"], where), "symbol": _symbol(r["symbol"], where), "side": "BUY",
                    "qty": _qty(r["quantity"], where), "price": _price(r["price"], where),
                    "id": "lots:%d" % i, "source": os.path.basename(path)})
    return out


def read_fmv(path):
    """{SYMBOL: price on 31 Jan 2018} from a CSV with columns symbol,fmv."""
    cols, rows = _rows(path)
    if "symbol" not in cols or "fmv" not in cols:
        raise TradeError("%s needs the columns symbol,fmv" % path)
    out = {}
    for i, r in enumerate(rows, 2):
        where = "%s line %d" % (os.path.basename(path), i)
        out[_symbol(r["symbol"], where)] = _price(r["fmv"], where)
    return out


def merge(*lists):
    """All trades, each trade id once (the first source wins), in date order (stable)."""
    seen, out = set(), []
    for trades in lists:
        for t in trades:
            if t["id"] in seen:
                continue
            seen.add(t["id"])
            out.append(t)
    return sorted(out, key=lambda t: t["date"])
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_tradebook.py -v`
Expected: all 7 tests pass. Then run `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`.

```bash
git add trader-tax/tradebook.py trader-tax/nse.py trader-tax/nse_symbols.py tests/test_tradebook.py tests/fixtures/trader-tax/tradebook-sample.csv tests/fixtures/trader-tax/lots.csv tests/fixtures/trader-tax/fmv_2018.csv tests/fixtures/trader-tax/kite
git commit -m "Add trader-tax tradebook reader: Console CSV, Kite trades, opening lots" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 4: `ledger.py`, intraday, FIFO lots, term, the 2018 rule

**Files:**
- Create: `trader-tax/ledger.py`, `tests/test_ledger.py`

**Interfaces:**
- Consumes: `tradebook.read_tradebook`, `kite_trades`, `read_lots` and `merge` (Task 3)
- Produces:
  - `ledger.anniversary(d)`, `term(acquired, sold) -> "STCG"|"LTCG"` and `close(lot, qty, price, sold, fmv=None) -> gain`
  - `build(trades, fmv=None) -> {"lots": {SYM: [lot]}, "realised", "speculative", "problems"}`
  - `what_if(lots, qty, price, sold, fmv=None) -> (gains, shortfall)`
  - A gain is `{"symbol", "kind", "sold", "acquired", "qty", "buy_price", "sell_price", "cost", "proceeds", "gain", "grandfathered"}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_ledger.py`:

```python
import datetime
import os
import unittest

from _load import load, FIX

tb = load("trader-tax", "tradebook")
ledger = load("trader-tax", "ledger")

TDIR = os.path.join(FIX, "trader-tax")
D = datetime.date


def all_trades():
    import json
    book, _ = tb.read_tradebook(os.path.join(TDIR, "tradebook-sample.csv"))
    with open(os.path.join(TDIR, "kite", "trades.json")) as fh:
        kite = tb.kite_trades(json.load(fh)["data"])
    return tb.merge(tb.read_lots(os.path.join(TDIR, "lots.csv")), book, kite)


def trade(d, sym, side, qty, price, tid):
    return {"date": d, "symbol": sym, "side": side, "qty": qty, "price": price, "id": tid, "source": "t"}


class Terms(unittest.TestCase):
    def test_more_than_twelve_months_is_long_term(self):
        self.assertEqual(ledger.term(D(2025, 1, 10), D(2026, 1, 10)), "STCG")
        self.assertEqual(ledger.term(D(2025, 1, 10), D(2026, 1, 11)), "LTCG")
        self.assertEqual(ledger.anniversary(D(2024, 2, 29)), D(2025, 3, 1))


class Build(unittest.TestCase):
    def setUp(self):
        self.book = ledger.build(all_trades(), {"INFY": 1150.0})

    def test_realised_gains_by_kind(self):
        got = [(g["symbol"], g["kind"], g["sold"], g["qty"], g["gain"]) for g in self.book["realised"]]
        self.assertEqual(got, [
            ("TCS", "LTCG", D(2025, 3, 3), 5, 3500.0),
            ("HDFCBANK", "STCG", D(2025, 6, 2), 4, -400.0),
            ("RELIANCE", "STCG", D(2026, 1, 10), 5, 750.0),
            ("RELIANCE", "LTCG", D(2026, 1, 12), 3, 510.0),
            ("INFY", "LTCG", D(2026, 5, 4), 2, 900.0),
            ("HDFCBANK", "LTCG", D(2026, 10, 26), 2, 100.0),
        ])
        infy = self.book["realised"][4]
        self.assertTrue(infy["grandfathered"])
        self.assertEqual(infy["buy_price"], 1150.0)

    def test_same_day_buy_and_sell_is_intraday(self):
        got = [(g["symbol"], g["sold"], g["qty"], g["gain"]) for g in self.book["speculative"]]
        self.assertEqual(got, [("ITC", D(2025, 2, 3), 20, -100.0), ("INFY", D(2026, 5, 4), 2, 20.0)])

    def test_open_lots(self):
        lots = {s: [(l["date"], l["qty"]) for l in ls] for s, ls in self.book["lots"].items()}
        self.assertEqual(lots, {"INFY": [(D(2017, 6, 15), 8)], "HDFCBANK": [(D(2024, 7, 10), 4)],
                                "RELIANCE": [(D(2025, 1, 10), 2)], "TCS": [(D(2026, 8, 3), 3)]})
        self.assertEqual(self.book["problems"], [])


class Rules(unittest.TestCase):
    def test_2018_rule_is_capped_at_the_sale_price_and_never_below_cost(self):
        old = [trade(D(2017, 6, 15), "INFY", "BUY", 10, 480.0, "a")]
        high = ledger.build(old + [trade(D(2026, 5, 4), "INFY", "SELL", 1, 1000.0, "b")], {"INFY": 1150.0})
        self.assertEqual(high["realised"][0]["gain"], 0.0)
        low = ledger.build(old + [trade(D(2026, 5, 4), "INFY", "SELL", 1, 1000.0, "b")], {"INFY": 300.0})
        self.assertEqual((low["realised"][0]["gain"], low["realised"][0]["grandfathered"]), (520.0, False))
        none = ledger.build(old + [trade(D(2026, 5, 4), "INFY", "SELL", 1, 1000.0, "b")], {})
        self.assertIn("no 31 Jan 2018 price for INFY", none["problems"][0])

    def test_fifo_across_lots_and_overselling(self):
        t = [trade(D(2025, 1, 1), "TCS", "BUY", 2, 3000.0, "a"), trade(D(2025, 6, 1), "TCS", "BUY", 2, 3500.0, "b"),
             trade(D(2026, 3, 1), "TCS", "SELL", 5, 4000.0, "c")]
        book = ledger.build(t)
        self.assertEqual([(g["kind"], g["qty"], g["gain"]) for g in book["realised"]],
                         [("LTCG", 2, 2000.0), ("STCG", 2, 1000.0)])
        self.assertIn("sold 1 more TCS on 2026-03-01", book["problems"][0])

    def test_what_if(self):
        lots = ledger.build(all_trades(), {"INFY": 1150.0})["lots"]
        gains, short = ledger.what_if(lots["INFY"], 3, 1612.5, D(2026, 10, 26), {"INFY": 1150.0})
        self.assertEqual(([(g["kind"], g["gain"], g["grandfathered"]) for g in gains], short),
                         ([("LTCG", 1387.5, True)], 0))
        self.assertEqual(ledger.what_if(lots["INFY"], 20, 1612.5, D(2026, 10, 26))[1], 12)
        self.assertEqual(lots["INFY"][0]["qty"], 8)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_ledger.py -v`
Expected: an ERROR (no ledger.py).

- [ ] **Step 3: Implement**

`trader-tax/ledger.py`:

```python
#!/usr/bin/env python3
"""FIFO lots and realised gains for trader-tax (Indian listed equity). Standard library only.

Not tax advice: arithmetic on your trades.

  intraday     on any day, the shares of a stock you both bought and sold
               that day are an intraday round trip: speculative business
               income, matched first-in first-out within the day
  lots         the rest of a day's buys open lots (date, quantity, price)
  sales        the rest of a day's sells close the OLDEST lots first (FIFO,
               as demat accounts require)
  term         a lot sold MORE than 12 months after it was bought is long
               term (LTCG); otherwise short term (STCG). Bought 2025-01-10:
               sold 2026-01-10 is short term, 2026-01-11 long term.
  2018 rule    for shares bought before 2018-02-01, the cost of a long-term
               sale is the higher of the actual cost and the 31 Jan 2018
               price, but never above the sale price (grandfathering)
"""

import datetime

GRANDFATHER_BEFORE = datetime.date(2018, 2, 1)
EPS = 1e-9


def anniversary(d):
    """The same date a year later (29 Feb becomes 1 Mar)."""
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return datetime.date(d.year + 1, 3, 1)


def term(acquired, sold):
    return "LTCG" if sold > anniversary(acquired) else "STCG"


def _gain(kind, symbol, sold, acquired, qty, buy, sell, grandfathered=False):
    cost, proceeds = qty * buy, qty * sell
    return {"symbol": symbol, "kind": kind, "sold": sold, "acquired": acquired, "qty": qty,
            "buy_price": round(buy, 4), "sell_price": round(sell, 4), "cost": round(cost, 2),
            "proceeds": round(proceeds, 2), "gain": round(proceeds - cost, 2), "grandfathered": grandfathered}


def close(lot, qty, price, sold, fmv=None):
    """The gain from selling qty shares of one lot at price on date sold, with the 2018 rule."""
    kind = term(lot["date"], sold)
    buy, gf = lot["price"], False
    if lot["date"] < GRANDFATHER_BEFORE and kind == "LTCG" and lot["symbol"] in (fmv or {}):
        buy = max(lot["price"], min(fmv[lot["symbol"]], price))
        gf = buy != lot["price"]
    return _gain(kind, lot["symbol"], sold, lot["date"], qty, buy, price, gf)


def build(trades, fmv=None):
    """Trades (from tradebook.merge) -> {"lots": {SYM: [lot]}, "realised": [gain], "speculative": [gain],
    "problems": [text]}. A lot is {"symbol", "date", "qty", "price", "id"}."""
    fmv = fmv or {}
    lots, realised, speculative, problems = {}, [], [], []
    days = {}
    order = []
    for t in trades:
        key = (t["date"], t["symbol"])
        if key not in days:
            days[key] = {"BUY": [], "SELL": []}
            order.append(key)
        days[key][t["side"]].append([t["qty"], t["price"], t["id"]])
    order.sort(key=lambda k: k[0])
    warned_fmv = set()
    for d, sym in order:
        buys, sells = days[(d, sym)]["BUY"], days[(d, sym)]["SELL"]
        intraday = min(sum(b[0] for b in buys), sum(s[0] for s in sells))
        if intraday:
            left, cost, proceeds = intraday, 0.0, 0.0
            bi = si = 0
            while left:
                take = min(left, buys[bi][0], sells[si][0])
                cost += take * buys[bi][1]
                proceeds += take * sells[si][1]
                buys[bi][0] -= take
                sells[si][0] -= take
                left -= take
                if not buys[bi][0]:
                    bi += 1
                if not sells[si][0]:
                    si += 1
            speculative.append(_gain("SPECULATIVE", sym, d, d, intraday, cost / intraday, proceeds / intraday))
        for qty, price, tid in buys:
            if qty:
                lots.setdefault(sym, []).append({"symbol": sym, "date": d, "qty": qty, "price": price, "id": tid})
        for qty, price, tid in sells:
            open_lots = lots.get(sym, [])
            while qty and open_lots:
                lot = open_lots[0]
                take = min(qty, lot["qty"])
                g = close(lot, take, price, d, fmv)
                if g["kind"] == "LTCG" and lot["date"] < GRANDFATHER_BEFORE and sym not in fmv and sym not in warned_fmv:
                    warned_fmv.add(sym)
                    problems.append("no 31 Jan 2018 price for %s in fmv_2018.csv: its pre-2018 lots use the "
                                    "actual cost, which may overstate the gain" % sym)
                realised.append(g)
                lot["qty"] -= take
                qty -= take
                if not lot["qty"]:
                    open_lots.pop(0)
            if qty:
                problems.append("sold %d more %s on %s than the trades show you held: add the earlier tradebook or "
                                "the opening lots (lots.csv); that part is left out" % (qty, sym, d.isoformat()))
    lots = {s: ls for s, ls in lots.items() if ls}
    return {"lots": lots, "realised": realised, "speculative": speculative, "problems": problems}


def what_if(lots, qty, price, sold, fmv=None):
    """The gains selling qty shares from these lots (FIFO) at price on date sold would realise, without
    changing them. Returns (gains, shortfall)."""
    out, left = [], qty
    for lot in lots:
        if not left:
            break
        take = min(left, lot["qty"])
        out.append(close(lot, take, price, sold, fmv))
        left -= take
    return out, left
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_ledger.py -v`
Expected: all 7 tests pass. Then run `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`.

```bash
git add trader-tax/ledger.py tests/test_ledger.py
git commit -m "Add trader-tax ledger: intraday, FIFO lots, terms, 2018 rule" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 5: `india_tax.py`, financial years, set-off, exemption, carry-forward

**Files:**
- Copy (unchanged): `trader-alerts/rupees.py` into `trader-tax/`
- Create: `trader-tax/india_tax.py`, `tests/test_india_tax.py`

**Interfaces:**
- Consumes: gains with `kind`, `sold` and `gain` (Task 4)
- Produces:
  - `india_tax.RULES`, `TaxRuleError`, `fy_of(d) -> "2026-27"` and `rules(overrides=None)`
  - `summarise(realised, speculative, overrides=None) -> [year]`. Each year has `fy`, `stcg`, `stcl`, `ltcg`, `ltcl`, `speculative`, `st_net`, `lt_net`, `speculative_net`, `st_taxable`, `lt_taxable`, `exemption_used`, `exemption_left`, `carry_forward` (each entry `{fy, kind: ST|LT|SPEC, amount, last_fy}`), `estimate` (`{stcg, ltcg, total}` or None) and `notes`.

- [ ] **Step 1: Write the failing tests**

`tests/test_india_tax.py`:

```python
import datetime
import unittest

from _load import load

tax = load("trader-tax", "india_tax")

D = datetime.date


def g(kind, sold, gain):
    return {"kind": kind, "sold": sold, "gain": float(gain)}


class FinancialYear(unittest.TestCase):
    def test_april_to_march(self):
        self.assertEqual(tax.fy_of(D(2026, 3, 31)), "2025-26")
        self.assertEqual(tax.fy_of(D(2026, 4, 1)), "2026-27")
        self.assertEqual(tax.fy_of(D(2099, 12, 1)), "2099-00")


class Summarise(unittest.TestCase):
    def test_the_example_years(self):
        realised = [g("LTCG", D(2025, 3, 3), 3500), g("STCG", D(2025, 6, 2), -400), g("STCG", D(2026, 1, 10), 750),
                    g("LTCG", D(2026, 1, 12), 510), g("LTCG", D(2026, 5, 4), 900), g("LTCG", D(2026, 10, 26), 100)]
        spec = [g("SPECULATIVE", D(2025, 2, 3), -100), g("SPECULATIVE", D(2026, 5, 4), 20)]
        years = tax.summarise(realised, spec)
        self.assertEqual([y["fy"] for y in years], ["2024-25", "2025-26", "2026-27"])
        y24, y25, y26 = years
        self.assertIsNone(y24["estimate"])
        self.assertIn("no tax estimate for 2024-25", y24["notes"][0])
        self.assertEqual([(c["kind"], c["amount"], c["last_fy"]) for c in y24["carry_forward"]],
                         [("SPEC", 100.0, "2028-29")])
        self.assertEqual((y25["st_net"], y25["lt_net"], y25["estimate"]),
                         (350.0, 510.0, {"stcg": 70.0, "ltcg": 0.0, "total": 70.0}))
        self.assertEqual((y25["exemption_used"], y25["exemption_left"]), (510.0, 124490.0))
        self.assertEqual((y26["lt_net"], y26["speculative_net"], y26["exemption_left"]), (1000.0, 0.0, 124000.0))
        self.assertEqual([c["amount"] for c in y26["carry_forward"]], [80.0])
        self.assertIn("speculative loss carried from 2024-25: Rs 20 used against speculative income", y26["notes"])

    def test_set_off_order(self):
        y = tax.summarise([g("STCG", D(2026, 5, 1), 200), g("STCG", D(2026, 5, 2), -1000),
                           g("LTCG", D(2026, 5, 3), 5000)], [])[0]
        self.assertEqual((y["st_net"], y["lt_net"]), (0.0, 4200.0))
        self.assertIn("short-term loss Rs 800 set off against long-term gain", y["notes"])
        y = tax.summarise([g("STCG", D(2026, 5, 1), 1000), g("LTCG", D(2026, 5, 2), -500)], [])[0]
        self.assertEqual((y["st_net"], y["lt_net"], y["estimate"]["stcg"]), (1000.0, -500.0, 200.0))
        self.assertEqual([(c["kind"], c["amount"]) for c in y["carry_forward"]], [("LT", 500.0)])
        y = tax.summarise([g("STCG", D(2026, 5, 1), 1000)], [g("SPECULATIVE", D(2026, 5, 2), -400)])[0]
        self.assertEqual((y["st_net"], y["speculative_net"]), (1000.0, -400.0))

    def test_exemption_and_rates(self):
        y = tax.summarise([g("LTCG", D(2026, 5, 1), 200000)], [])[0]
        self.assertEqual((y["lt_taxable"], y["estimate"]["ltcg"], y["exemption_left"]), (75000.0, 9375.0, 0.0))
        y = tax.summarise([g("STCG", D(2026, 5, 1), 1000)], [], {"stcg_pct": "15"})[0]
        self.assertEqual(y["estimate"]["stcg"], 150.0)

    def test_carried_losses_are_used_oldest_first_and_expire(self):
        years = tax.summarise([g("STCG", D(2024, 5, 1), -1000), g("LTCG", D(2026, 5, 1), 600),
                               g("STCG", D(2027, 5, 1), 300)], [])
        self.assertEqual([y["fy"] for y in years], ["2024-25", "2026-27", "2027-28"])
        self.assertEqual((years[1]["lt_net"], years[1]["carry_forward"][0]["amount"]), (0.0, 400.0))
        self.assertEqual((years[2]["st_net"], years[2]["carry_forward"][0]["amount"]), (0.0, 100.0))
        late = tax.summarise([g("STCG", D(2024, 5, 1), -1000), g("STCG", D(2033, 5, 1), 300)], [])
        self.assertEqual([y["fy"] for y in late], ["2024-25", "2033-34"])
        self.assertEqual(late[1]["st_net"], 300.0)

    def test_bad_rules(self):
        for bad in ({"gst": 1}, {"stcg_pct": "nan"}, {"ltcg_pct": -1}, {"estimate_from_fy": "2025"}):
            with self.assertRaises(tax.TaxRuleError):
                tax.rules(bad)

    def test_nothing_realised(self):
        self.assertEqual(tax.summarise([], []), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_india_tax.py -v`
Expected: an ERROR (no india_tax.py).

- [ ] **Step 3: Implement**

```bash
cp trader-alerts/rupees.py trader-tax/
```

`trader-tax/india_tax.py`:

```python
#!/usr/bin/env python3
"""Indian capital-gains arithmetic for trader-tax, per financial year. Standard library only.

Not tax advice. The rates below are the defaults in RULES and can be
changed with a "tax_rules" block in trader/config.json. Check them every
year (the Income-tax Act 2025 applies from 1 April 2026):

  financial year   1 April to 31 March, named like 2026-27
  STCG             listed equity held 12 months or less: 20%
  LTCG             held more than 12 months: 12.5% on the part above the
                   yearly exemption of Rs 1,25,000
  speculative      intraday round trips: business income at your slab
                   rate, kept separate (no estimate here)
  set-off          short-term loss against short-term gain, then against
                   long-term gain; long-term loss only against long-term
                   gain; speculative loss only against speculative income
  carry forward    what is still a loss carries forward 8 years (4 for
                   speculative), used oldest first, but only if that year's
                   return was filed on time
  estimate         from financial year "estimate_from_fy" on; earlier years
                   had other rates, so they show gains without an estimate
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from rupees import inr

RULES = {"stcg_pct": 20.0, "ltcg_pct": 12.5, "ltcg_exemption": 125000.0, "carry_years": 8,
         "speculative_carry_years": 4, "estimate_from_fy": "2025-26"}


class TaxRuleError(Exception):
    pass


def fy_of(d):
    """date -> '2026-27' (the financial year that starts on 1 April)."""
    start = d.year if d.month >= 4 else d.year - 1
    return "%d-%02d" % (start, (start + 1) % 100)


def _fy_start(fy):
    return int(fy[:4])


def rules(overrides=None):
    r = dict(RULES)
    for k, v in (overrides or {}).items():
        if k not in RULES:
            raise TaxRuleError("unknown tax rule %r (known: %s)" % (k, ", ".join(sorted(RULES))))
        if k == "estimate_from_fy":
            if not (isinstance(v, str) and len(v) == 7 and v[4] == "-" and v[:4].isdigit()):
                raise TaxRuleError("estimate_from_fy wants a year like 2025-26, got %r" % (v,))
            r[k] = v
            continue
        try:
            num = float(v)
        except (TypeError, ValueError):
            raise TaxRuleError("tax rule %s must be a number, got %r" % (k, v))
        if not math.isfinite(num) or num < 0:
            raise TaxRuleError("tax rule %s must be a number of at least 0, got %r" % (k, v))
        r[k] = int(num) if k.endswith("carry_years") else num
    return r


def _sum(gains, kind, sign):
    return sum(g["gain"] for g in gains if g["kind"] == kind and (g["gain"] > 0) == (sign > 0) and g["gain"])


def summarise(realised, speculative, overrides=None):
    """Per financial year, oldest first: gains by kind, set-off, carry-forward and the tax estimate."""
    r = rules(overrides)
    by_fy = {}
    for g in list(realised) + list(speculative):
        by_fy.setdefault(fy_of(g["sold"]), []).append(g)
    if not by_fy:
        return []
    first, last = min(by_fy), max(by_fy)
    carry = []  # [{"fy", "kind": ST|LT|SPEC, "amount", "last_fy"}]
    years = []
    for start in range(_fy_start(first), _fy_start(last) + 1):
        fy = "%d-%02d" % (start, (start + 1) % 100)
        gs = by_fy.get(fy, [])
        stcg, stcl = _sum(gs, "STCG", 1), -_sum(gs, "STCG", -1)
        ltcg, ltcl = _sum(gs, "LTCG", 1), -_sum(gs, "LTCG", -1)
        sp = sum(g["gain"] for g in gs if g["kind"] == "SPECULATIVE")
        st, lt = stcg - stcl, ltcg - ltcl
        notes = []
        if st < 0 and lt > 0:
            use = min(-st, lt)
            lt -= use
            st += use
            notes.append("short-term loss %s set off against long-term gain" % inr(use))
        carry = [c for c in carry if _fy_start(c["last_fy"]) >= start]
        used_carry = 0.0
        for c in sorted(carry, key=lambda c: c["fy"]):
            targets = {"ST": ("st", "lt"), "LT": ("lt",), "SPEC": ("sp",)}[c["kind"]]
            for tname in targets:
                avail = {"st": st, "lt": lt, "sp": sp}[tname]
                if avail <= 0 or c["amount"] <= 0:
                    continue
                use = min(avail, c["amount"])
                c["amount"] -= use
                used_carry += use
                if tname == "st":
                    st -= use
                elif tname == "lt":
                    lt -= use
                else:
                    sp -= use
                notes.append("%s loss carried from %s: %s used against %s" % (
                    {"ST": "short-term", "LT": "long-term", "SPEC": "speculative"}[c["kind"]], c["fy"], inr(use),
                    {"st": "short-term gain", "lt": "long-term gain", "sp": "speculative income"}[tname]))
        carry = [c for c in carry if c["amount"] > 0.005]
        for kind, value, years_n in (("ST", st, r["carry_years"]), ("LT", lt, r["carry_years"]),
                                     ("SPEC", sp, r["speculative_carry_years"])):
            if value < -0.005:
                carry.append({"fy": fy, "kind": kind, "amount": -value,
                              "last_fy": "%d-%02d" % (start + years_n, (start + years_n + 1) % 100)})
        st_taxable = max(st, 0.0)
        lt_pos = max(lt, 0.0)
        exemption_used = min(lt_pos, r["ltcg_exemption"])
        lt_taxable = lt_pos - exemption_used
        estimate = None
        if start >= _fy_start(r["estimate_from_fy"]):
            st_tax = st_taxable * r["stcg_pct"] / 100.0
            lt_tax = lt_taxable * r["ltcg_pct"] / 100.0
            estimate = {"stcg": round(st_tax, 2), "ltcg": round(lt_tax, 2), "total": round(st_tax + lt_tax, 2)}
        elif gs:
            notes.append("no tax estimate for %s: the rates before FY %s were different" % (fy, r["estimate_from_fy"]))
        if not gs and not used_carry:
            continue
        years.append({
            "fy": fy, "stcg": round(stcg, 2), "stcl": round(stcl, 2), "ltcg": round(ltcg, 2), "ltcl": round(ltcl, 2),
            "speculative": round(sum(g["gain"] for g in gs if g["kind"] == "SPECULATIVE"), 2),
            "st_net": round(st, 2), "lt_net": round(lt, 2), "speculative_net": round(sp, 2),
            "st_taxable": round(st_taxable, 2), "lt_taxable": round(lt_taxable, 2),
            "exemption_used": round(exemption_used, 2),
            "exemption_left": round(r["ltcg_exemption"] - exemption_used, 2),
            "carry_forward": [dict(c, amount=round(c["amount"], 2)) for c in carry],
            "estimate": estimate, "notes": notes,
        })
    return years
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_india_tax.py -v`
Expected: all 7 tests pass. Then run `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`.

```bash
git add trader-tax/india_tax.py trader-tax/rupees.py tests/test_india_tax.py
git commit -m "Add trader-tax Indian capital-gains rules per financial year" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 6: `lots.py`, the trader-tax CLI

**Files:**
- Copy (unchanged): `trader-alerts/kite_snapshot.py` and `trader-alerts/nse_calendar.py` into `trader-tax/`; `trader-budget/charges.py` into `trader-tax/`
- Replace: `trader-tax/lots.py`, `tests/test_tax.py`
- Delete: `trader-tax/portfolio.example.json`, `tests/fixtures/trader-tax/portfolio.json`, `tests/fixtures/trader-tax/prices.json`

**Interfaces:**
- Consumes: Tasks 3 to 5; `charges.estimate`; `kite_snapshot.load` and `quotes`; `nse_calendar.parse_now`; trader-risk `check` (the test only)
- Produces:
  - CLI commands: `report`, `gains [--fy]`, `sell SYMBOL QTY [--price]` and `harvest [--min-loss] [--include-gains] [--write]`
  - Common options: `--tradebook` (repeatable), `--lots`, `--fmv`, `--kite-dir`, `--config` and `--now`
  - Harvest orders are CNC SELL LIMIT orders in Kite shape, each cut to `max_order_value`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_tax.py` with:

```python
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

lots = load("trader-tax", "lots")
check = load("trader-risk", "check")

TDIR = os.path.join(FIX, "trader-tax")
KDIR = os.path.join(TDIR, "kite")
CFG = os.path.join(ROOT, "trader-budget", "config.example.json")
NOW = "2026-10-26T10:01"


def args(kite_dir=KDIR, now=NOW):
    return ["--tradebook", os.path.join(TDIR, "tradebook-sample.csv"), "--lots", os.path.join(TDIR, "lots.csv"),
            "--fmv", os.path.join(TDIR, "fmv_2018.csv"), "--kite-dir", kite_dir, "--config", CFG, "--now", now]


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = lots.main(argv)
    return code, out.getvalue(), err.getvalue()


class Gains(unittest.TestCase):
    def test_every_year(self):
        code, text, _ = run(["gains"] + args())
        self.assertEqual(code, 0)
        for line in ("FY 2024-25", "FY 2025-26", "FY 2026-27",
                     "estimated tax: short term Rs 70 + long term Rs 0 = Rs 70",
                     "carried forward: speculative loss Rs 80 from 2024-25, usable until FY 2028-29",
                     "1 non-equity or non-NSE tradebook rows skipped",
                     "Not tax advice"):
            self.assertIn(line, text)

    def test_the_same_tradebook_twice_counts_once(self):
        once = run(["gains", "--json"] + args())[1]
        twice = run(["gains", "--json", "--tradebook", os.path.join(TDIR, "tradebook-sample.csv")] + args())[1]
        self.assertEqual(json.loads(once)["years"], json.loads(twice)["years"])

    def test_one_year_and_a_year_with_nothing(self):
        code, text, _ = run(["gains", "--fy", "2026-27", "--json"] + args())
        self.assertEqual(code, 0)
        self.assertEqual([y["fy"] for y in json.loads(text)["years"]], ["2026-27"])
        code, _, err = run(["gains", "--fy", "2019-20"] + args())
        self.assertEqual(code, 1)
        self.assertIn("no realised gains or losses in FY 2019-20", err)


class Report(unittest.TestCase):
    def test_open_lots(self):
        code, text, _ = run(["report"] + args())
        self.assertEqual(code, 0)
        self.assertIn("31 Jan 2018 price used as cost", text)
        self.assertRegex(text, r"TCS\s+2026-08-03\s+3\s+Rs 3,300\s+Rs 3,050.50\s+-Rs 748.50  short term, "
                               r"long term from 2027-08-04")
        self.assertNotIn("incomplete", text)

    def test_lots_that_do_not_match_kite_are_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            kd = os.path.join(d, "kite")
            shutil.copytree(KDIR, kd)
            with open(os.path.join(kd, "holdings.json")) as fh:
                doc = json.load(fh)
            doc["data"][0]["quantity"] = 9
            with open(os.path.join(kd, "holdings.json"), "w") as fh:
                json.dump(doc, fh)
            _, text, _ = run(["report"] + args(kd))
            self.assertIn("INFY: the trades give 8 shares but Kite holds 9", text)

    def test_stale_quotes(self):
        code, _, err = run(["report"] + args(now="2026-10-26T10:05"))
        self.assertEqual(code, 1)
        self.assertIn("quotes snapshot is", err)


class Sell(unittest.TestCase):
    def test_what_a_sale_would_realise(self):
        code, text, _ = run(["sell", "infy.ns", "3"] + args())
        self.assertEqual(code, 0)
        self.assertIn("3 INFY bought 2017-06-15 at Rs 1,150: long term Rs 1,387.50 (31 Jan 2018 price used)", text)
        code, _, err = run(["sell", "INFY", "20"] + args())
        self.assertEqual(code, 1)
        self.assertIn("you hold only 8 INFY", err)
        code, _, err = run(["sell", "WIPRO", "1"] + args())
        self.assertIn("no WIPRO held", err)


class Harvest(unittest.TestCase):
    def test_losses_and_long_term_headroom(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            code, text, _ = run(["harvest", "--min-loss", "500", "--write", out] + args())
            self.assertEqual(code, 0)
            self.assertIn("SELL 3 TCS at Rs 3,050.50: loss Rs 748.50", text)
            self.assertIn("SELL 8 INFY at Rs 1,612.50: long-term gain Rs 3,700", text)
            self.assertIn("no wash-sale rule", text)
            with open(out) as fh:
                doc = json.load(fh)
            self.assertIs(doc["live"], True)
            self.assertEqual([o["tradingsymbol"] for o in doc["orders"]], ["TCS"])
            code, text, _ = run(["harvest", "--min-loss", "500", "--include-gains", "--write", out] + args())
            with open(out) as fh:
                orders = json.load(fh)["orders"]
            self.assertEqual([(o["tradingsymbol"], o["quantity"]) for o in orders],
                             [("TCS", "3"), ("HDFCBANK", "4"), ("INFY", "6"), ("RELIANCE", "2")])
            self.assertIn("INFY: selling 6 of 8 now keeps the order under your Rs 10,000 max order", text)
            self.assertEqual(orders[2]["why"], "book Rs 2,775 of long-term gain inside the yearly exemption")

    def test_nothing_to_harvest(self):
        code, text, _ = run(["harvest", "--min-loss", "5000"] + args())
        self.assertIn("No position would book a loss of Rs 5,000 or more", text)

    def test_a_harvest_sell_passes_the_risk_check(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            run(["harvest", "--min-loss", "500", "--write", out] + args())
            with open(out) as fh:
                orders = json.load(fh)["orders"]
        now = check.nse_calendar.parse_now(NOW)
        data = check.load_data(KDIR, now)
        data.update(positions={"net": [], "day": []}, orders=[],
                    margins={"equity": {"net": 50000.0, "available": {"live_balance": 50000.0}}})
        cal = check.nse_calendar.Calendar(dict(check.nse_calendar.HOLIDAYS), check.nse_calendar.YEARS)
        with open(CFG) as fh:
            res = check.check(orders, json.load(fh), data, now, cal)
        self.assertEqual([r["verdict"] for r in res["results"]], ["PASS"], res["results"])


class Inputs(unittest.TestCase):
    def test_no_trades_explains_where_to_get_them(self):
        with tempfile.TemporaryDirectory() as d:
            here = os.getcwd()
            os.chdir(d)
            try:
                code, _, err = run(["gains", "--kite-dir", os.path.join(d, "kite"), "--now", NOW])
            finally:
                os.chdir(here)
        self.assertEqual(code, 1)
        self.assertIn("Zerodha Console tradebook", err)

    def test_missing_kite_trades_is_a_note(self):
        with tempfile.TemporaryDirectory() as d:
            _, text, _ = run(["gains"] + args(os.path.join(d, "kite")))
        self.assertIn("today's Kite trades are not included", text)
        self.assertNotIn("FY 2026-27\n  short term: gains Rs 0, losses Rs 0, net after set-off Rs 0\n  long term:  "
                         "gains Rs 1,000", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_tax.py -v`
Expected: errors and failures (the old US lots.py has other commands).

- [ ] **Step 3: Implement**

```bash
cp trader-alerts/kite_snapshot.py trader-alerts/nse_calendar.py trader-tax/
cp trader-budget/charges.py trader-tax/
git rm -q trader-tax/portfolio.example.json tests/fixtures/trader-tax/portfolio.json tests/fixtures/trader-tax/prices.json
```

Replace `trader-tax/lots.py` with:

```python
#!/usr/bin/env python3
"""Indian capital gains on your NSE trades, for trader-tax. Standard library only, no network.

Not tax advice: arithmetic on your trades. A tax professional decides what
applies to you.

    python3 lots.py report                       # open lots, unrealised gain by term
    python3 lots.py gains                        # realised gains, set-off, carry-forward, estimate per FY
    python3 lots.py gains --fy 2026-27
    python3 lots.py sell INFY 4                  # what selling 4 INFY now would realise (FIFO)
    python3 lots.py harvest --min-loss 1000      # losses to book, and LTCG headroom
    python3 lots.py harvest --write              # loss-harvest sells -> trader/orders.json

Inputs (see tradebook.py):
  trader/tradebook*.csv   Zerodha Console equity tradebooks (all your history)
  trader/lots.csv         opening lots bought before the tradebook starts
  trader/fmv_2018.csv     31 Jan 2018 prices for shares bought before 2018-02-01
  trader/kite/trades.json today's Kite trades (kite_snapshot.py save trades)
  trader/kite/holdings.json   Kite holdings, to check the lots add up
  trader/kite/quotes.json     Kite quotes, for unrealised gains

The rules are in ledger.py (lots, terms, the 2018 rule) and india_tax.py
(financial years, set-off, exemption, carry-forward). India has no wash-sale
rule: a loss stays a loss if you buy back, but the new shares start a new
12-month clock.
"""

import argparse
import datetime
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import charges
import india_tax
import kite_snapshot
import ledger
import nse_calendar
import tradebook
from rupees import inr

NOT_ADVICE = ("Not tax advice: arithmetic on your trades. Check the rates each year and ask a tax professional "
              "what applies to you. Education and tooling, not financial advice.")
KIND_WORDS = {"STCG": "short term", "LTCG": "long term", "SPECULATIVE": "intraday (speculative)"}


class TaxError(Exception):
    pass


def _now(a):
    try:
        return nse_calendar.parse_now(a.now)
    except nse_calendar.CalendarError as e:
        raise TaxError(str(e))


def _today(a):
    return _now(a).date()


def _config(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as e:
        raise TaxError("%s is not valid JSON: %s" % (path, e))


def load_inputs(a):
    """{"book": ledger.build result, "notes": [...], "cfg": {...}} from the files and snapshots."""
    notes = []
    files = a.tradebook or sorted(glob.glob(os.path.join("trader", "tradebook*.csv")))
    lists, skipped = [], 0
    if a.lots and os.path.exists(a.lots):
        lists.append(tradebook.read_lots(a.lots))
    for f in files:
        trades, n = tradebook.read_tradebook(f)
        lists.append(trades)
        skipped += n
    if skipped:
        notes.append("%d non-equity or non-NSE tradebook rows skipped (F&O, BSE, ...)" % skipped)
    try:
        lists.append(tradebook.kite_trades(kite_snapshot.load("trades", a.kite_dir, now=_now(a), max_age=86400)))
    except kite_snapshot.SnapshotError as e:
        notes.append("today's Kite trades are not included (%s)" % e)
    if not lists:
        raise TaxError("no trades: download your Zerodha Console tradebook to trader/tradebook-<year>.csv "
                       "(or pass --tradebook), and put older holdings in trader/lots.csv")
    fmv = tradebook.read_fmv(a.fmv) if a.fmv and os.path.exists(a.fmv) else {}
    book = ledger.build(tradebook.merge(*lists), fmv)
    book["fmv"] = fmv
    return {"book": book, "notes": notes + book["problems"], "cfg": _config(a.config)}


def quote_prices(kite_dir, now=None):
    try:
        snap = kite_snapshot.quotes(kite_snapshot.load("quotes", kite_dir, now=now))
    except kite_snapshot.SnapshotError as e:
        raise TaxError(str(e))
    return {s: q["price"] for s, q in snap.items()}


def reconcile(lots, kite_dir, now=None):
    """Warnings where the lots do not match Kite's holdings (quantity + T1)."""
    try:
        hold = kite_snapshot.load("holdings", kite_dir, now=now)
    except kite_snapshot.SnapshotError as e:
        return ["could not check the lots against Kite holdings (%s)" % e]
    kite = {}
    for r in hold if isinstance(hold, list) else []:
        sym = str(r.get("tradingsymbol", "")).upper()
        kite[sym] = kite.get(sym, 0) + int(float(r.get("quantity") or 0) + float(r.get("t1_quantity") or 0))
    mine = {s: sum(l["qty"] for l in ls) for s, ls in lots.items()}
    out = []
    for s in sorted(set(kite) | set(mine)):
        if kite.get(s, 0) != mine.get(s, 0):
            out.append("%s: the trades give %d shares but Kite holds %d; the tradebook or lots.csv is incomplete"
                       % (s, mine.get(s, 0), kite.get(s, 0)))
    return out


def unrealised(lots, prices, today, fmv=None):
    """One row per lot: what selling it today at the Kite price would realise."""
    rows = []
    for sym in sorted(lots):
        for lot in lots[sym]:
            if sym not in prices:
                rows.append({"symbol": sym, "lot": lot, "price": None, "gain": None, "kind": None})
                continue
            g = ledger.close(lot, lot["qty"], prices[sym], today, fmv)
            rows.append({"symbol": sym, "lot": lot, "price": prices[sym], "gain": g["gain"], "kind": g["kind"],
                         "grandfathered": g["grandfathered"],
                         "long_term_from": ledger.anniversary(lot["date"]) + datetime.timedelta(days=1)})
    return rows


def cmd_report(a):
    inp = load_inputs(a)
    lots = inp["book"]["lots"]
    today = _today(a)
    rows = unrealised(lots, quote_prices(a.kite_dir, _now(a)), today, inp["book"]["fmv"])
    notes = inp["notes"] + reconcile(lots, a.kite_dir, _now(a))
    if a.json:
        print(json.dumps({"lots": rows, "notes": notes}, indent=2, default=str))
        return 0
    print("%-12s %-10s %6s %12s %12s %14s  %s" % ("symbol", "bought", "qty", "cost", "price", "unrealised", "term"))
    for r in rows:
        lot = r["lot"]
        if r["price"] is None:
            print("%-12s %-10s %6d %12s %12s %14s  no Kite quote" % (r["symbol"], lot["date"], lot["qty"],
                                                                     inr(lot["price"]), "", ""))
            continue
        when = "" if r["kind"] == "LTCG" else ", long term from %s" % r["long_term_from"]
        if r.get("grandfathered"):
            when += ", 31 Jan 2018 price used as cost"
        print("%-12s %-10s %6d %12s %12s %14s  %s%s" % (r["symbol"], lot["date"], lot["qty"], inr(lot["price"]),
                                                       inr(r["price"]), inr(r["gain"]), KIND_WORDS[r["kind"]], when))
    for n in notes:
        print("Note: " + n)
    print(NOT_ADVICE)
    return 0


def cmd_gains(a):
    inp = load_inputs(a)
    book = inp["book"]
    years = india_tax.summarise(book["realised"], book["speculative"], inp["cfg"].get("tax_rules"))
    if a.fy:
        years = [y for y in years if y["fy"] == a.fy]
        if not years:
            raise TaxError("no realised gains or losses in FY %s" % a.fy)
    if a.json:
        print(json.dumps({"years": years, "notes": inp["notes"]}, indent=2, default=str))
        return 0
    for y in years:
        print("FY %s" % y["fy"])
        print("  short term: gains %s, losses %s, net after set-off %s" % (inr(y["stcg"]), inr(y["stcl"]),
                                                                          inr(y["st_net"])))
        print("  long term:  gains %s, losses %s, net after set-off %s (exemption used %s, left %s)"
              % (inr(y["ltcg"]), inr(y["ltcl"]), inr(y["lt_net"]), inr(y["exemption_used"]), inr(y["exemption_left"])))
        print("  intraday (speculative, slab rate): %s, net %s" % (inr(y["speculative"]), inr(y["speculative_net"])))
        if y["estimate"]:
            e = y["estimate"]
            print("  estimated tax: short term %s + long term %s = %s (plus cess and surcharge if any)"
                  % (inr(e["stcg"]), inr(e["ltcg"]), inr(e["total"])))
        for c in y["carry_forward"]:
            print("  carried forward: %s loss %s from %s, usable until FY %s"
                  % ({"ST": "short-term", "LT": "long-term", "SPEC": "speculative"}[c["kind"]], inr(c["amount"]),
                     c["fy"], c["last_fy"]))
        for n in y["notes"]:
            print("  - " + n)
    for n in inp["notes"]:
        print("Note: " + n)
    print("Carried-forward losses count only if that year's return was filed on time.")
    print(NOT_ADVICE)
    return 0


def cmd_sell(a):
    inp = load_inputs(a)
    sym = tradebook._symbol(a.symbol, "symbol")
    lots = inp["book"]["lots"].get(sym, [])
    if not lots:
        raise TaxError("the trades show no %s held" % sym)
    price = a.price if a.price is not None else quote_prices(a.kite_dir, _now(a)).get(sym)
    if not price:
        raise TaxError("no Kite quote for NSE:%s: add it to the quotes call, or pass --price" % sym)
    gains, short = ledger.what_if(lots, a.qty, price, _today(a), inp["book"]["fmv"])
    if short:
        raise TaxError("you hold only %d %s by the trades" % (a.qty - short, sym))
    if a.json:
        print(json.dumps({"gains": gains}, indent=2, default=str))
        return 0
    for g in gains:
        print("%d %s bought %s at %s: %s %s%s" % (g["qty"], sym, g["acquired"], inr(g["buy_price"]),
                                                  KIND_WORDS[g["kind"]], inr(g["gain"]),
                                                  " (31 Jan 2018 price used)" if g["grandfathered"] else ""))
    print("Total: %s. Shares are sold oldest first (FIFO)." % inr(sum(g["gain"] for g in gains)))
    print(NOT_ADVICE)
    return 0


def harvest(lots, prices, today, years, min_loss, fmv=None, exemption=125000.0):
    """(losses, gains): selling a whole position that books at least min_loss of loss, and long-term gains
    that still fit this FY's unused exemption."""
    fy = india_tax.fy_of(today)
    this = [y for y in years if y["fy"] == fy]
    left = this[0]["exemption_left"] if this else exemption
    losses, gains = [], []
    for sym in sorted(lots):
        if sym not in prices:
            continue
        qty = sum(l["qty"] for l in lots[sym])
        res, _ = ledger.what_if(lots[sym], qty, prices[sym], today, fmv)
        net = sum(g["gain"] for g in res)
        if net <= -min_loss:
            losses.append({"symbol": sym, "qty": qty, "price": prices[sym], "loss": round(-net, 2),
                           "by_term": {k: round(sum(g["gain"] for g in res if g["kind"] == k), 2)
                                       for k in ("STCG", "LTCG")}})
        n, booked = 0, 0.0
        for lot in lots[sym]:
            g = ledger.close(lot, lot["qty"], prices[sym], today, fmv)
            if g["kind"] != "LTCG" or g["gain"] <= 0:
                break
            per = g["gain"] / lot["qty"]
            fit = min(lot["qty"], int((left - booked) // per)) if per > 0 else 0
            n += fit
            booked += fit * per
            if fit < lot["qty"]:
                break
        if n:
            gains.append({"symbol": sym, "qty": n, "price": prices[sym], "gain": round(booked, 2)})
            left -= booked
    return losses, gains


def sell_orders(cands, cfg, why, notes):
    """Kite SELL orders for the candidates, each cut to max_order_value (trader-risk blocks bigger orders)."""
    try:
        max_value = float(cfg.get("max_order_value", 10000) or 0)
    except (TypeError, ValueError):
        raise TaxError("config max_order_value must be a number of rupees")
    out = []
    for c in cands:
        qty = c["qty"]
        if max_value and qty * c["price"] > max_value:
            qty = int(max_value // c["price"])
            notes.append("%s: selling %d of %d now keeps the order under your %s max order; sell the rest later"
                         % (c["symbol"], qty, c["qty"], inr(max_value)))
        if qty < 1:
            continue
        value = qty * c["price"]
        est = charges.estimate("CNC", "SELL", value, cfg.get("charges"))
        out.append({"exchange": "NSE", "tradingsymbol": c["symbol"], "transaction_type": "SELL",
                    "quantity": str(qty), "product": "CNC", "order_type": "LIMIT", "price": "%.2f" % c["price"],
                    "validity": "DAY", "variety": "regular", "est_value": "%.2f" % value,
                    "est_charges": "%.2f" % est["total"], "why": why(c, qty / float(c["qty"]))})
    return out


def cmd_harvest(a):
    inp = load_inputs(a)
    book = inp["book"]
    today = _today(a)
    tax_rules = india_tax.rules(inp["cfg"].get("tax_rules"))
    years = india_tax.summarise(book["realised"], book["speculative"], inp["cfg"].get("tax_rules"))
    losses, gains = harvest(book["lots"], quote_prices(a.kite_dir, _now(a)), today, years, a.min_loss, book["fmv"],
                            tax_rules["ltcg_exemption"])
    notes = inp["notes"]
    orders = sell_orders(losses, inp["cfg"], lambda c, part: "book a %s loss (trader-tax harvest)" % inr(c["loss"] * part), notes)
    if a.include_gains:
        orders += sell_orders(gains, inp["cfg"], lambda c, part: "book %s of long-term gain inside the yearly "
                              "exemption" % inr(c["gain"] * part), notes)
    if a.write and orders:
        d = os.path.dirname(a.write)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(a.write, "w", encoding="utf-8") as fh:
            json.dump({"created_by": "trader-tax", "created_at": datetime.datetime.now(kite_snapshot.IST)
                       .replace(microsecond=0).isoformat(), "status": "proposed", "live": True,
                       "note": "Proposals only. Every order is a LIVE order with real money. Nothing is placed until "
                               "trader-risk passes each order and you say yes to it in the chat.",
                       "orders": orders}, fh, indent=2)
            fh.write("\n")
    if a.json:
        print(json.dumps({"losses": losses, "gains": gains, "orders": orders, "notes": inp["notes"]}, indent=2))
        return 0 if orders else 1
    print("FY %s, today %s." % (india_tax.fy_of(today), today))
    if losses:
        print("Losses you could book (selling the whole position, oldest shares first):")
        for c in losses:
            print("  SELL %d %s at %s: loss %s (short term %s, long term %s)" % (
                c["qty"], c["symbol"], inr(c["price"]), inr(c["loss"]), inr(c["by_term"]["STCG"]),
                inr(c["by_term"]["LTCG"])))
    else:
        print("No position would book a loss of %s or more." % inr(a.min_loss))
    if gains:
        print("Long-term gains that still fit this year's exemption (tax free up to the limit):")
        for c in gains:
            print("  SELL %d %s at %s: long-term gain %s" % (c["qty"], c["symbol"], inr(c["price"]), inr(c["gain"])))
    if a.write and orders:
        print("Wrote %d proposed LIVE order(s) to %s. trader-risk checks them next." % (len(orders), a.write))
    print("India has no wash-sale rule, but shares you buy back start a new 12-month clock.")
    for n in inp["notes"]:
        print("Note: " + n)
    print(NOT_ADVICE)
    return 0 if (losses or gains) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Indian capital gains on your NSE trades (trader-tax). Not tax advice.")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--tradebook", action="append", help="a Zerodha Console tradebook CSV (repeat for more)")
        p.add_argument("--lots", default="trader/lots.csv")
        p.add_argument("--fmv", default="trader/fmv_2018.csv")
        p.add_argument("--kite-dir", default=kite_snapshot.DIR)
        p.add_argument("--config", default="trader/config.json")
        p.add_argument("--now", help="pretend it is this time (ISO, IST; tests only, needs TRADER_TEST_CLOCK=1)")
        p.add_argument("--json", action="store_true")

    common(sub.add_parser("report", help="open lots and unrealised gains"))
    p = sub.add_parser("gains", help="realised gains per financial year")
    common(p)
    p.add_argument("--fy", help="one financial year, like 2026-27")
    p = sub.add_parser("sell", help="what selling now would realise")
    common(p)
    p.add_argument("symbol")
    p.add_argument("qty", type=int)
    p.add_argument("--price", type=float)
    p = sub.add_parser("harvest", help="losses to book and long-term gain headroom")
    common(p)
    p.add_argument("--min-loss", type=float, default=1000.0)
    p.add_argument("--include-gains", action="store_true", help="also write the long-term gain sells")
    p.add_argument("--write", nargs="?", const="trader/orders.json", metavar="PATH")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"report": cmd_report, "gains": cmd_gains, "sell": cmd_sell, "harvest": cmd_harvest}[a.cmd](a)
    except (TaxError, tradebook.TradeError, india_tax.TaxRuleError, charges.ChargesError) as e:
        print("lots.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_tax.py -v`
Expected: all 12 tests pass. Then run `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`; the full suite is 271 tests.

```bash
git add -A trader-tax tests/test_tax.py tests/fixtures/trader-tax
git commit -m "Rebuild trader-tax CLI for Indian capital gains and harvesting" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 7: Docs for rebalance and tax, and the LIVE-docs repo test

**Files:**
- Replace: `trader-rebalance/SKILL.md`, `trader-tax/SKILL.md`
- Modify: `tests/test_repo.py`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: Write the failing repo test**

In `tests/test_repo.py`, in `test_converted_order_path_skills_say_live`, replace:

```python
        for s in ("trader-budget", "trader-risk", "trader-broker"):
```

with:

```python
        for s in ("trader-budget", "trader-risk", "trader-broker", "trader-rebalance", "trader-tax"):
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m unittest discover -s tests -p test_repo.py -v`
Expected: FAIL with `'real money' not found` for trader-rebalance.

- [ ] **Step 3: Rewrite both SKILL.md files**

`trader-rebalance/SKILL.md`:

````markdown
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
````

`trader-tax/SKILL.md`:

````markdown
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
````

- [ ] **Step 4: README.md and CLAUDE.md**

- In `README.md`, replace:

  `| `/trader-tax` | Tax Optimizer | Tracks cost-basis lots, gains and losses, tax-loss harvesting candidates and wash sales. |`

  with:

  `| `/trader-tax` | Tax Optimizer | Builds FIFO lots from your Zerodha tradebook and works out STCG, LTCG and intraday income per financial year, with set-off, the yearly exemption and harvesting ideas. |`

- In `README.md`, replace:

  `| `/trader-rebalance` | Rebalancer | Brings the portfolio back to its target weights when it drifts past your band. |`

  with:

  `| `/trader-rebalance` | Rebalancer | Brings the portfolio back to its target weights from your Kite holdings when it drifts past your band, in whole shares. |`

- In `README.md`, replace:

  `python3 trader-tax/lots.py harvest --min-loss 100                      # with wash-sale checks`

  with:

  `python3 trader-tax/lots.py harvest --min-loss 1000                     # losses to book, exemption left`

- In `README.md`, replace:

  `**Taxes.** `/trader-tax` does the arithmetic on lots and wash-sale windows. It`

  with:

  `**Taxes.** `/trader-tax` does the arithmetic on lots, terms and set-off for Indian listed equity. It`

- In `README.md`, replace:

  `trader-tax/        SKILL.md, lots.py, portfolio.example.json`

  with:

  `trader-tax/        SKILL.md, lots.py, tradebook.py, ledger.py, india_tax.py`

- In `CLAUDE.md`, replace:

  `and the order path, trader-budget, trader-risk and trader-broker (Kite place_order shape, rupees, whole shares).`

  with:

  `the order path, trader-budget, trader-risk and trader-broker (Kite place_order shape, rupees, whole shares), and the portfolio skills trader-rebalance and trader-tax (Kite holdings, Zerodha Console tradebook, Indian capital gains).`

- In `CLAUDE.md`, replace:

  ``nse_symbols.py`, `rupees.py`) are copied`

  with:

  ``nse_symbols.py`, `rupees.py`, and `charges.py` whose source copy is in trader-budget) are copied`

- [ ] **Step 5: Verify, smoke-test and commit**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache . && ! grep -rl "$(printf '\342\200\224')" trader-* tests docs CLAUDE.md README.md`
Expected: `OK` with 271 tests, `All checks passed!`, and no file names printed.

Smoke test, outside the repo:

```bash
R=/home/ubuntu/stock-market/trader-skill; T=$(mktemp -d) && cd "$T" && export TRADER_TEST_CLOCK=1
python3 "$R/trader-rebalance/rebalance.py" --targets "$R/tests/fixtures/trader-rebalance/targets.json" --config "$R/trader-budget/config.example.json" --kite-dir "$R/tests/fixtures/trader-rebalance/kite" --now 2026-10-26T10:01 --write
python3 "$R/trader-risk/check.py" --config "$R/trader-budget/config.example.json" --kite-dir "$R/tests/fixtures/trader-rebalance/kite" --now 2026-10-26T10:01; echo "check exit $?"
F="$R/tests/fixtures/trader-tax"; python3 "$R/trader-tax/lots.py" gains --tradebook "$F/tradebook-sample.csv" --lots "$F/lots.csv" --fmv "$F/fmv_2018.csv" --kite-dir "$F/kite" --now 2026-10-26T10:01
```

Expected:
- `rebalance.py` writes 4 orders.
- `check.py` prints 4 PASS lines and exits 0.
- `gains` prints FY 2024-25, 2025-26 and 2026-27, with "estimated tax: short term Rs 70".

Report the output in the task summary.

```bash
git add trader-rebalance/SKILL.md trader-tax/SKILL.md tests/test_repo.py README.md CLAUDE.md
git commit -m "Document Indian rebalance and tax; LIVE-docs test covers them" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

