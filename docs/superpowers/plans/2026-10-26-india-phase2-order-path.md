# India Phase 2 (Order path) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the order path (trader-budget, trader-risk, trader-broker) to LIVE NSE orders in Kite `place_order` shape, with the spec's cautious risk defaults, Zerodha charge estimates and the three approval gates intact.

**Architecture:**
- trader-budget sizes whole shares at the Kite last price and writes LIMIT orders with an estimate of Zerodha's charges (`charges.py`).
- trader-risk is a pure `check(orders, cfg, data, now, cal)` over five Kite snapshots (quotes, holdings, positions, margins, orders). Any snapshot that a rule needs and that is missing or stale makes that rule BLOCK.
- trader-broker renders LIVE tickets with the exact `place_order` arguments, and refuses a risk check older than 10 minutes.
- The shared helpers from Phase 1, plus a new `rupees.py`, are copied byte-for-byte into each skill that imports them. Repo tests keep the copies identical and present.

**Tech Stack:** Python 3.8+, standard library only, `unittest` with offline fixtures.

**Spec:** `docs/superpowers/specs/2026-10-26-indian-market-design.md` (sections 4.1 to 4.4, 7 and 9, phase 2)

**Branch:** work on `feat/india-phase2`, branched from `feat/india-phase1`.

**Provenance:** all of the code in this plan was drafted and run in a scratch worktree first. The full suite passed under Python 3.12 and 3.8, ruff passed, and the CLI ran end to end (size, check, show, approve). Every expected value below comes from those runs.

## Global Constraints

- Python 3.8 or newer, standard library only. No `zoneinfo`, no `str.removeprefix`, no `list[str]` hints.
- No em dashes (U+2014) in any .md, .py, .json, .csv, .txt or .xml file.
- Every order is LIVE, real money: Kite has no paper account. No `"paper"` key anywhere.
- Kite has no fractional shares and no notional orders: quantities are whole numbers, sent as strings like `"6"`, and prices are strings like `"1612.50"`.
- Order fields are Kite's: `exchange`, `tradingsymbol`, `transaction_type`, `quantity`, `product`, `order_type`, `price`, `trigger_price`, `validity`, `variety`. The orders file also carries `est_value`, `est_charges` and `why`, which are not sent to Kite.
- Risk defaults (spec 4.3):
  - `max_order_value` "10000", `max_orders_per_day` 5, `max_limit_deviation_pct` "2", `mis_cutoff` "15:00", `max_mis_exposure_pct` "50", `daily_loss_limit` "2000".
  - `allow_market_orders`, `allow_mis`, `allow_short` and `allow_amo` are all false.
- F&O, NRML and SL/SL-M orders are never supported.
- Any snapshot that a rule needs and that is missing or stale makes that rule BLOCK, never a skipped rule.
- Shared helper files are copied unchanged from `trader-alerts/`, never edited per skill.
- Never run a tool from the repo root (it creates `trader/`). Lint with `--no-cache`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full check: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`

## Review Focus

1. **A US-shaped order** (`symbol`/`side`/`notional`) from a skill that is not converted yet (rebalance, tax) reaching `check.py`. It must BLOCK with format reasons, never crash or pass. Covered by Task 4 `test_a_us_shaped_order_is_blocked_not_crashed`.
2. **A missing snapshot for one kind** must block only the orders whose rules need it. A CNC buy does not need positions; an MIS order does. Covered by Task 4 `test_a_missing_snapshot_only_blocks_the_rules_that_need_it`.
3. **An MIS sell larger than the MIS long** flips the position to a short. It must count as opening a position, so the short and cutoff rules apply. Covered by Task 4 `test_selling_past_the_position_opens_a_short`.
4. **A risk check that passed more than 10 minutes ago** must not make a ticket READY, because prices move. Covered by Task 6 `test_an_old_risk_check_is_not_ready`.
5. **The default budget (Rs 50,000 at 25%) gives Rs 12,500 slices, which are over the Rs 10,000 max order.** The budget must cap at the lower of the two, so default proposals are not all blocked. Covered by Task 5 `test_the_example_budget_is_capped_by_the_max_order`.

---

### Task 1: Confirm the Kite connector's order tool and answer shapes (manual gate)

This is the same login as Phase 1's Task 1 and covers it too. Tasks 2 to 7 build and test offline without it. **The branch must not merge, and no live order may be placed, until this task is done.** Do not save real account data in the repo.

**Files:**
- Create or update: `docs/superpowers/notes/2026-10-26-kite-connector.md`

- [ ] **Step 1: Log in**

Run `ToolSearch` with query `+kite`. If only `mcp__claude_ai_kite__authenticate` is listed, ask the user to run `/mcp` and choose **claude.ai kite**. Do not continue with this task until they have.

- [ ] **Step 2: Record the tools**

List every Kite tool and its parameters. Pay particular attention to the order tool (expected name `place_order`) and its parameter names and types: are `quantity` and `price` strings or numbers? Is `variety` a parameter?

- [ ] **Step 3: Compare each read answer with what the code reads**

| Answer | Fields the code reads |
|---|---|
| quotes | `"NSE:INFY"` keys; `last_price`, `ohlc.close`, `upper_circuit_limit`, `lower_circuit_limit`, `timestamp`, `last_trade_time` |
| holdings | list of `tradingsymbol`, `quantity`, `t1_quantity`, `last_price` |
| positions | `net[]` and `day[]` with `tradingsymbol`, `product`, `quantity`, `last_price`, `pnl` |
| margins | `equity.net`, `equity.available.live_balance` (falling back to `cash`) |
| orders | list with `status` (REJECTED and CANCELLED are not counted) |

- [ ] **Step 4: Write the notes and gate**

Write the tool table, the place-order parameters and "matches" or the exact differences for each answer into the notes file. Use field names only, no account values.

If anything differs, change these to the real names and tell the user before continuing:
- `KITE_FIELDS` and `TOOL` in `trader-risk/check.py` and `trader-broker/ticket.py` (Tasks 4 and 6)
- `account()` in `check.py`
- the fixtures in Tasks 4 and 5

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/notes/2026-10-26-kite-connector.md
git commit -m "Record Kite connector tools and answer shapes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 2: Shared `rupees.py`, an `orders` snapshot kind, helper checks

**Files:**
- Create: `trader-alerts/rupees.py`, `tests/test_rupees.py`
- Modify: `trader-alerts/alerts.py` (use `rupees.inr`), `trader-alerts/kite_snapshot.py` (add `orders`), `tests/test_kite_snapshot.py`, `tests/test_repo.py`

**Interfaces:**
- Produces:
  - `rupees.inr(x) -> str` (moved out of `alerts.py`; `alerts.inr` still works through `from rupees import inr`)
  - `kite_snapshot.MAX_AGE["orders"] == 600`
  - `SHARED` in `test_repo.py` gains `"rupees.py"`
  - `test_every_imported_helper_is_in_the_same_skill`

- [ ] **Step 1: Write the failing tests**

`tests/test_rupees.py`:

```python
import unittest

from _load import load

ru = load("trader-alerts", "rupees")


class Inr(unittest.TestCase):
    def test_indian_grouping(self):
        self.assertEqual(ru.inr(125000), "Rs 1,25,000")
        self.assertEqual(ru.inr(1612.5), "Rs 1,612.50")
        self.assertEqual(ru.inr(1234567.891), "Rs 12,34,567.89")
        self.assertEqual(ru.inr(999), "Rs 999")
        self.assertEqual(ru.inr(-950), "-Rs 950")
        self.assertEqual(ru.inr(0.5), "Rs 0.50")
        self.assertEqual(ru.inr("10000"), "Rs 10,000")


if __name__ == "__main__":
    unittest.main()
```

In `tests/test_kite_snapshot.py`, class `Save`: the unknown-kind test must now use a kind that stays unknown, and a new test covers `orders`. Replace:

```python
    def test_unknown_kind(self):
        with self.assertRaises(ks.SnapshotError):
            ks.save("orders", {}, self.d)
```

with:

```python
    def test_orders_kind(self):
        ks.save("orders", [{"order_id": "1", "status": "COMPLETE"}], self.d, now=T0)
        self.assertEqual(ks.load("orders", self.d, now=T0 + 600 * SEC)[0]["status"], "COMPLETE")
        with self.assertRaises(ks.SnapshotError):
            ks.load("orders", self.d, now=T0 + 601 * SEC)

    def test_unknown_kind(self):
        with self.assertRaises(ks.SnapshotError):
            ks.save("gtt", {}, self.d)
```

In `tests/test_repo.py`, replace:

```python
SHARED = ["kite_snapshot.py", "nse.py", "nse_calendar.py", "nse_symbols.py"]
```

with:

```python
SHARED = ["kite_snapshot.py", "nse.py", "nse_calendar.py", "nse_symbols.py", "rupees.py"]
```

and add this method to `class Repo`, just before `def test_alerts_example_rules_are_nse(self):`:

```python
    def test_every_imported_helper_is_in_the_same_skill(self):
        names = {n[:-3] for n in SHARED}
        for s in SKILLS:
            folder = os.path.join(ROOT, s)
            for f in sorted(os.listdir(folder)):
                if not f.endswith(".py"):
                    continue
                with open(os.path.join(folder, f), encoding="utf-8") as fh:
                    used = set(re.findall(r"^(?:import|from) (\w+)", fh.read(), re.M))
                for mod in sorted(used & names):
                    self.assertTrue(os.path.isfile(os.path.join(folder, mod + ".py")),
                                    "%s/%s imports %s, which is not in %s" % (s, f, mod, s))
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p "test_[rk]*.py" -v`
Expected:
- `test_rupees` errors because `trader-alerts/rupees.py` does not exist.
- `test_orders_kind` fails with "unknown snapshot kind 'orders'".

- [ ] **Step 3: Implement**

Create `trader-alerts/rupees.py`:

```python
#!/usr/bin/env python3
"""Rupee amounts in Indian grouping for the trader skills. Standard library only.

    inr(125000)      -> "Rs 1,25,000"
    inr(1612.5)      -> "Rs 1,612.50"
    inr(-950)        -> "-Rs 950"

This file is copied into every skill that shows money. Keep the copies
identical: tests/test_repo.py checks.
"""


def inr(x):
    """1234567.891 -> 'Rs 12,34,567.89' (Indian grouping). Whole rupees drop the paise."""
    x = float(x)
    whole, paise = ("%.2f" % abs(x)).split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    text = ",".join(groups + [tail])
    if paise != "00":
        text += "." + paise
    return ("-Rs " if x < 0 else "Rs ") + text
```

In `trader-alerts/alerts.py`:
- Add `from rupees import inr` right after `import nse_symbols`.
- Delete the whole `# ---------------------------------------------------------------- money` section, which holds `def inr(x):` and its body, up to but not including `def _n(x):`.

In `trader-alerts/kite_snapshot.py`, replace:

```python
MAX_AGE = {"quotes": 120, "holdings": 600, "positions": 600, "margins": 600, "trades": 600}
```

with:

```python
MAX_AGE = {"quotes": 120, "holdings": 600, "positions": 600, "margins": 600, "orders": 600, "trades": 600}
```

and in the docstring replace `holdings, positions, margins and trades 600 s.` with `holdings, positions, margins, orders and trades 600 s.`.

- [ ] **Step 4: Run the full suite and lint**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`
Expected: `OK` and `All checks passed!` (`test_alerts.Money` still passes through the import).

- [ ] **Step 5: Commit**

```bash
git add trader-alerts/rupees.py trader-alerts/alerts.py trader-alerts/kite_snapshot.py tests/test_rupees.py tests/test_kite_snapshot.py tests/test_repo.py
git commit -m "Add shared rupees helper, orders snapshot kind, helper presence test" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 3: `charges.py`, Zerodha charges estimate

Rates are from https://zerodha.com/charges as read on 2026-10-26: NSE transaction charge 0.00307%, stamp duty 0.015% (CNC) or 0.003% (MIS) on buys, STT 0.1% (CNC both sides) or 0.025% (MIS sells), MIS brokerage 0.03% capped at Rs 20, SEBI Rs 10 per crore, GST 18%.

**Files:**
- Create: `trader-budget/charges.py`, `tests/test_charges.py`

**Interfaces:**
- Produces:
  - `charges.RATES` (dict)
  - `charges.ChargesError`
  - `charges.rates(overrides=None) -> dict`
  - `charges.estimate(product, side, value, overrides=None) -> {"brokerage", "stt", "transaction", "sebi", "stamp", "gst", "total"}`, with values in rupees rounded to the paisa

- [ ] **Step 1: Write the failing tests**

`tests/test_charges.py`:

```python
import unittest

from _load import load

ch = load("trader-budget", "charges")


class Estimate(unittest.TestCase):
    def test_delivery_buy_and_sell(self):
        buy = ch.estimate("CNC", "BUY", 9675)
        self.assertEqual(buy, {"brokerage": 0.0, "stt": 9.68, "transaction": 0.3, "sebi": 0.01,
                               "stamp": 1.45, "gst": 0.06, "total": 11.49})
        sell = ch.estimate("cnc", "sell", "9675")
        self.assertEqual((sell["stamp"], sell["total"]), (0.0, 10.04))

    def test_intraday_brokerage_is_capped_at_rs_20(self):
        self.assertEqual(ch.estimate("MIS", "BUY", 9675)["brokerage"], 2.9)
        big = ch.estimate("MIS", "SELL", 100000)
        self.assertEqual((big["brokerage"], big["stt"], big["total"]), (20.0, 25.0, 52.34))

    def test_config_overrides(self):
        self.assertEqual(ch.estimate("CNC", "BUY", 9675, {"gst_pct": "0"})["total"], 11.43)
        with self.assertRaises(ch.ChargesError):
            ch.estimate("CNC", "BUY", 9675, {"gst": 0})
        with self.assertRaises(ch.ChargesError):
            ch.estimate("CNC", "BUY", 9675, {"gst_pct": "lots"})

    def test_unsupported_products_and_sides(self):
        with self.assertRaises(ch.ChargesError):
            ch.estimate("NRML", "BUY", 1000)
        with self.assertRaises(ch.ChargesError):
            ch.estimate("CNC", "HOLD", 1000)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_charges.py -v`
Expected: an ERROR, because `trader-budget/charges.py` does not exist.

- [ ] **Step 3: Write `trader-budget/charges.py`**

```python
#!/usr/bin/env python3
"""Zerodha equity charges estimate for trader-budget. Standard library only.

An estimate only: the contract note is the real number. Rates for NSE
equity from https://zerodha.com/charges (read 2026-10-26):

                     delivery (CNC)              intraday (MIS)
  brokerage          zero                        0.03% or Rs 20 per executed order, lower
  STT                0.1% on buy and sell        0.025% on the sell side
  NSE transaction    0.00307%                    0.00307%
  SEBI               Rs 10 per crore             Rs 10 per crore
  stamp duty         0.015% on the buy side      0.003% on the buy side
  GST                18% on brokerage + SEBI + transaction charges

Override any rate with a "charges" block in trader/config.json, using the
keys of RATES. Rates change: check the page every financial year.
"""

RATES = {
    "brokerage_mis_pct": 0.03, "brokerage_mis_cap": 20.0,
    "stt_cnc_pct": 0.1, "stt_mis_sell_pct": 0.025,
    "nse_txn_pct": 0.00307, "sebi_per_crore": 10.0,
    "stamp_cnc_buy_pct": 0.015, "stamp_mis_buy_pct": 0.003,
    "gst_pct": 18.0,
}
CRORE = 1e7


class ChargesError(Exception):
    pass


def rates(overrides=None):
    r = dict(RATES)
    for k, v in (overrides or {}).items():
        if k not in RATES:
            raise ChargesError("unknown charge %r in the config (known: %s)" % (k, ", ".join(sorted(RATES))))
        try:
            r[k] = float(v)
        except (TypeError, ValueError):
            raise ChargesError("charge %s must be a number, got %r" % (k, v))
    return r


def estimate(product, side, value, overrides=None):
    """Rupee charges for one executed order: {brokerage, stt, transaction, sebi, stamp, gst, total}."""
    r = rates(overrides)
    product, side, value = str(product).upper(), str(side).upper(), float(value)
    if product not in ("CNC", "MIS"):
        raise ChargesError("charges are known for CNC and MIS only, not %s" % product)
    if side not in ("BUY", "SELL"):
        raise ChargesError("side must be BUY or SELL, not %s" % side)

    def pct(p):
        return value * p / 100.0

    if product == "CNC":
        brokerage = 0.0
        stt = pct(r["stt_cnc_pct"])
        stamp = pct(r["stamp_cnc_buy_pct"]) if side == "BUY" else 0.0
    else:
        brokerage = min(pct(r["brokerage_mis_pct"]), r["brokerage_mis_cap"])
        stt = pct(r["stt_mis_sell_pct"]) if side == "SELL" else 0.0
        stamp = pct(r["stamp_mis_buy_pct"]) if side == "BUY" else 0.0
    txn = pct(r["nse_txn_pct"])
    sebi = value * r["sebi_per_crore"] / CRORE
    gst = (brokerage + sebi + txn) * r["gst_pct"] / 100.0
    parts = {"brokerage": brokerage, "stt": stt, "transaction": txn, "sebi": sebi, "stamp": stamp, "gst": gst}
    out = {k: round(v, 2) for k, v in parts.items()}
    out["total"] = round(sum(parts.values()), 2)
    return out
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_charges.py -v`
Expected: all 4 tests pass.

- [ ] **Step 5: Run the full suite and lint, then commit**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`

```bash
git add trader-budget/charges.py tests/test_charges.py
git commit -m "Add Zerodha charges estimate for trader-budget" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 4: trader-risk on Kite snapshots, with the live config defaults

This task owns `trader-budget/config.example.json`, because both budget and risk read it, and it replaces the tests that read the old US config.
- `test_rebalance.py` loses its call into the old risk check. Rebalance stays US until Phase 3, which brings it back on Kite orders.
- `test_broker.py` loses its US `Flow` class. Task 6 replaces it with the Kite flow.

**Files:**
- Copy (unchanged): `trader-alerts/kite_snapshot.py`, `trader-alerts/nse_calendar.py` and `trader-alerts/rupees.py` into `trader-risk/`
- Modify (full rewrite): `trader-risk/check.py`, `tests/test_risk.py`, `trader-budget/config.example.json`
- Create: `tests/fixtures/trader-risk/kite/{quotes,holdings,positions,margins,orders}.json`, `tests/fixtures/trader-risk/orders-example.json`
- Delete: `tests/fixtures/trader-risk/orders-reel.json`
- Modify: `tests/test_repo.py`, `tests/test_rebalance.py`, `tests/test_broker.py`

**Interfaces:**
- Consumes:
  - `kite_snapshot.load`, `kite_snapshot.quotes` and `SnapshotError` (Phase 1, plus `orders` from Task 2)
  - `nse_calendar.parse_now`, `Calendar`, `load_holidays`, `IST` and `CACHE` (Phase 1)
  - `rupees.inr` (Task 2)
- Produces:
  - `check.KITE_FIELDS` and `check.fingerprint(order) -> 16 hex chars`; Task 6 must use the same fields
  - `check.config(cfg) -> (rules, warnings)`
  - `check.load_data(kite_dir, now) -> {kind: answer or error text}`
  - `check.check(orders, cfg, data, now, cal) -> {"checked_at", "date", "live", "market", "results", "pass", "block", "warnings", "cash_after"}`
  - Each result: `{"index", "symbol", "side", "product", "quantity", "amount", "value", "fingerprint", "verdict", "reasons", "warnings"}`
  - The CLI writes `trader/state/risk.json` with `checked_at` as ISO IST. Exit 0 when everything passes, 1 when anything is blocked or broken.

- [ ] **Step 1: Write the fixtures**

The example account has Rs 60,000 cash, 2 RELIANCE shares, no MIS positions, and one placed order plus one rejected order in Kite's book. All snapshots were saved at 10:00 IST on Monday 2026-10-26.

`tests/fixtures/trader-risk/kite/quotes.json`:

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

`tests/fixtures/trader-risk/kite/holdings.json`:

```json
{
  "fetched_at": "2026-10-26T10:00:00+05:30",
  "data": [
    {"tradingsymbol": "RELIANCE", "exchange": "NSE", "isin": "INE002A01018", "quantity": 2, "t1_quantity": 0, "average_price": 1380.0, "last_price": 1402.3}
  ]
}
```

`tests/fixtures/trader-risk/kite/positions.json`:

```json
{"fetched_at": "2026-10-26T10:00:00+05:30", "data": {"net": [], "day": []}}
```

`tests/fixtures/trader-risk/kite/margins.json`:

```json
{"fetched_at": "2026-10-26T10:00:00+05:30", "data": {"equity": {"net": 60000.0, "available": {"cash": 60000.0, "live_balance": 60000.0}, "utilised": {"debits": 0.0}}}}
```

`tests/fixtures/trader-risk/kite/orders.json`:

```json
{
  "fetched_at": "2026-10-26T10:00:00+05:30",
  "data": [
    {"order_id": "261026000000001", "status": "COMPLETE", "tradingsymbol": "ITC", "exchange": "NSE", "transaction_type": "BUY", "product": "CNC", "quantity": 10},
    {"order_id": "261026000000002", "status": "REJECTED", "tradingsymbol": "ITC", "exchange": "NSE", "transaction_type": "BUY", "product": "CNC", "quantity": 10}
  ]
}
```

`tests/fixtures/trader-risk/orders-example.json` holds the four orders trader-budget proposes for the example budget (Task 5 reproduces them):

```json
{
  "created_by": "trader-budget",
  "live": true,
  "orders": [
    {
      "exchange": "NSE",
      "tradingsymbol": "INFY",
      "transaction_type": "BUY",
      "quantity": "6",
      "product": "CNC",
      "order_type": "LIMIT",
      "price": "1612.50",
      "validity": "DAY",
      "variety": "regular",
      "est_value": "9675.00",
      "est_charges": "11.49",
      "why": "25.00% of the stock sleeve; capped at Rs 10,000, your Rs 10,000 max order"
    },
    {
      "exchange": "NSE",
      "tradingsymbol": "RELIANCE",
      "transaction_type": "BUY",
      "quantity": "7",
      "product": "CNC",
      "order_type": "LIMIT",
      "price": "1402.30",
      "validity": "DAY",
      "variety": "regular",
      "est_value": "9816.10",
      "est_charges": "11.66",
      "why": "25.00% of the stock sleeve; capped at Rs 10,000, your Rs 10,000 max order"
    },
    {
      "exchange": "NSE",
      "tradingsymbol": "TCS",
      "transaction_type": "BUY",
      "quantity": "3",
      "product": "CNC",
      "order_type": "LIMIT",
      "price": "3050.50",
      "validity": "DAY",
      "variety": "regular",
      "est_value": "9151.50",
      "est_charges": "10.87",
      "why": "25.00% of the stock sleeve; capped at Rs 10,000, your Rs 10,000 max order"
    },
    {
      "exchange": "NSE",
      "tradingsymbol": "HDFCBANK",
      "transaction_type": "BUY",
      "quantity": "6",
      "product": "CNC",
      "order_type": "LIMIT",
      "price": "1650.00",
      "validity": "DAY",
      "variety": "regular",
      "est_value": "9900.00",
      "est_charges": "11.76",
      "why": "25.00% of the stock sleeve; capped at Rs 10,000, your Rs 10,000 max order"
    }
  ]
}
```

```bash
git rm -q tests/fixtures/trader-risk/orders-reel.json
```

- [ ] **Step 2: Write the failing tests**

Replace `tests/test_risk.py` with:

```python
import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

check = load("trader-risk", "check")
cal_mod = check.nse_calendar

CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
RDIR = os.path.join(FIX, "trader-risk")
KDIR = os.path.join(RDIR, "kite")
ORDERS_PATH = os.path.join(RDIR, "orders-example.json")
CAL = cal_mod.Calendar(dict(cal_mod.HOLIDAYS), cal_mod.YEARS)


def ist(text):
    return cal_mod.parse_now(text)


NOW = ist("2026-10-26T10:01")


def cfg(**over):
    with open(CFG_PATH) as fh:
        c = json.load(fh)
    c.update(over)
    return c


def example_orders():
    with open(ORDERS_PATH) as fh:
        return json.load(fh)["orders"]


def data(now=NOW, **over):
    d = check.load_data(KDIR, now)
    d.update(copy.deepcopy(over))
    return d


def order(sym="INFY", side="BUY", qty="6", price="1612.50", product="CNC", **over):
    o = {"exchange": "NSE", "tradingsymbol": sym, "transaction_type": side, "quantity": qty, "product": product,
         "order_type": "LIMIT", "price": price, "validity": "DAY", "variety": "regular"}
    o.update(over)
    return o


def run_check(orders, c=None, d=None, now=NOW):
    return check.check(orders, c if c is not None else cfg(), d if d is not None else data(now), now, CAL)


def why(res, i=0):
    return " | ".join(res["results"][i]["reasons"])


def verdicts(res):
    return [r["verdict"] for r in res["results"]]


class Example(unittest.TestCase):
    def test_the_example_orders_pass_on_the_example_account(self):
        res = run_check(example_orders())
        self.assertEqual(verdicts(res), ["PASS"] * 4, [r["reasons"] for r in res["results"]])
        self.assertEqual(res["cash_after"], 21411.62)
        self.assertIs(res["live"], True)
        self.assertEqual(res["results"][0]["amount"], "6 x Rs 1,612.50 = Rs 9,675")
        self.assertIn("LIVE", res["warnings"][0])
        self.assertEqual(res["date"], "2026-10-26")

    def test_a_fifth_order_hits_the_daily_limit_and_is_a_duplicate(self):
        res = run_check(example_orders() + [order(qty="1")])
        self.assertEqual(verdicts(res), ["PASS"] * 4 + ["BLOCK"])
        self.assertIn("daily limit: 1 orders in Kite's order book today plus 4 passed", why(res, 4))
        self.assertIn("duplicate:", why(res, 4))


class Format(unittest.TestCase):
    def test_each_malformed_order_is_blocked(self):
        cases = [
            (order(sym="INFY.NS"), "format: tradingsymbol must be the bare NSE symbol"),
            (order(exchange="BSE"), "asset: only NSE"),
            (order(sym="NIFTY26OCTFUT"), "F&O contract"),
            (order(sym="NIFTY26OCT25000CE"), "F&O contract"),
            (order(qty="1.5"), "format: quantity must be a whole number"),
            (order(qty="0"), "format: quantity"),
            (order(side="HOLD"), "format: transaction_type"),
            (order(order_type="SL"), "stop-loss"),
            (order(price=None), "a LIMIT order needs a price"),
            (order(validity="IOC"), "validity must be DAY"),
            (order(variety="co"), "variety must be regular"),
            (order(product="NRML"), "product: 'NRML' is not supported"),
        ]
        for o, text in cases:
            res = run_check([o])
            self.assertEqual(verdicts(res), ["BLOCK"], o)
            self.assertIn(text, why(res), o)

    def test_numbers_should_be_strings(self):
        res = run_check([order(qty=6)])
        self.assertEqual(verdicts(res), ["PASS"])
        self.assertIn("send quantity as a string", res["results"][0]["warnings"][0])

    def test_blocked_list(self):
        self.assertIn("blocked: INFY", why(run_check([order()], cfg(blocked=["INFY"]))))


class Hours(unittest.TestCase):
    def test_closed_market_blocks_unless_amo_is_allowed(self):
        late = ist("2026-10-26T15:30")
        d = data()
        res = run_check([order()], d=d, now=late)
        self.assertIn("hours: NSE is closed (after the close", why(res))
        res = run_check([order(variety="amo")], cfg(allow_amo=True), d, late)
        self.assertNotIn("hours:", why(res))
        self.assertIn("hours: an amo", why(run_check([order(variety="amo")], cfg(allow_amo=True))))

    def test_holiday_and_unknown_year(self):
        diwali = ist("2026-11-10T10:00")
        self.assertIn("Diwali-Balipratipada", why(run_check([order()], d=data(), now=diwali)))
        later = ist("2027-01-04T10:00")
        self.assertIn("holiday list for 2027 is not loaded", why(run_check([order()], d=data(), now=later)))


class Price(unittest.TestCase):
    def test_market_orders_are_off_by_default(self):
        mkt = order(order_type="MARKET", price=None)
        self.assertIn("price: MARKET orders are off", why(run_check([mkt])))
        self.assertEqual(verdicts(run_check([mkt], cfg(allow_market_orders=True))), ["PASS"])

    def test_limit_far_from_the_last_price(self):
        res = run_check([order(price="1700")])
        self.assertIn("price: limit Rs 1,700 is 5.43% from the last price Rs 1,612.50, over your 2% limit", why(res))

    def test_circuit_band(self):
        res = run_check([order(qty="5", price="1800")], cfg(max_limit_deviation_pct="20"))
        self.assertIn("price: Rs 1,800 is outside today's circuit band Rs 1,451.25 to Rs 1,773.75", why(res))

    def test_no_quote_for_the_symbol(self):
        self.assertIn("data: no fresh Kite quote for NSE:ITC", why(run_check([order(sym="ITC", price="400")])))


class Size(unittest.TestCase):
    def test_min_and_max(self):
        self.assertIn("size: Rs 16,125 is over your Rs 10,000 max order", why(run_check([order(qty="10")])))
        self.assertIn("under your Rs 2,000 minimum", why(run_check([order(qty="1")], cfg(min_order_value="2000"))))


class Cash(unittest.TestCase):
    def test_buffer_and_not_enough_cash(self):
        small = {"equity": {"net": 10000.0, "available": {"cash": 10000.0, "live_balance": 10000.0}}}
        res = run_check([order(est_charges="11.49")], d=data(margins=small))
        self.assertIn("cash: leaves Rs 313.51, under your 10% buffer of Rs 1,280.46", why(res))
        tiny = {"equity": {"net": 5000.0, "available": {"live_balance": 5000.0}}}
        self.assertIn("cash: needs Rs 9,686.49 with charges but only Rs 5,000 is available",
                      why(run_check([order(est_charges="11.49")], d=data(margins=tiny))))

    def test_position_cap(self):
        lots = [{"tradingsymbol": "RELIANCE", "exchange": "NSE", "quantity": 10, "t1_quantity": 0,
                 "last_price": 1402.3}]
        res = run_check([order("RELIANCE", qty="7", price="1402.30")], d=data(holdings=lots))
        self.assertIn("position: RELIANCE would be Rs 23,839.10", why(res))


class Short(unittest.TestCase):
    def test_delivery_sale_needs_the_shares(self):
        self.assertIn("short: selling 3 RELIANCE but you hold 2",
                      why(run_check([order("RELIANCE", "SELL", "3", "1402.30")])))
        self.assertEqual(verdicts(run_check([order("RELIANCE", "SELL", "2", "1402.30")])), ["PASS"])


class Intraday(unittest.TestCase):
    def mis(self, **over):
        return order(product="MIS", **over)

    def test_mis_is_off_by_default(self):
        self.assertIn("product: MIS (intraday) is off", why(run_check([self.mis()])))

    def test_mis_rules_when_allowed(self):
        on = cfg(allow_mis=True)
        self.assertEqual(verdicts(run_check([self.mis()], on)), ["PASS"])
        late = ist("2026-10-26T15:00")
        self.assertIn("intraday: no new MIS positions after 15:00 IST",
                      why(run_check([self.mis()], on, data(), late)))
        self.assertIn("short: this MIS sell would leave you short 6 INFY",
                      why(run_check([self.mis(transaction_type="SELL")], on)))
        self.assertEqual(verdicts(run_check([self.mis(transaction_type="SELL")], cfg(allow_mis=True, allow_short=True))),
                         ["PASS"])
        small = {"equity": {"net": 10000.0, "available": {"live_balance": 10000.0}}}
        self.assertIn("intraday: MIS exposure would be Rs 9,675, over 50% of your Rs 10,000 equity margin",
                      why(run_check([self.mis()], on, data(margins=small))))
        losing = {"net": [], "day": [{"tradingsymbol": "TCS", "product": "MIS", "quantity": 0, "pnl": -2500.0}]}
        self.assertIn("intraday: today's loss Rs 2,500 has reached your Rs 2,000 daily loss limit",
                      why(run_check([self.mis()], on, data(positions=losing))))

    def test_selling_past_the_position_opens_a_short(self):
        held = {"net": [{"tradingsymbol": "INFY", "product": "MIS", "quantity": 4, "last_price": 1612.5}], "day": []}
        res = run_check([self.mis(transaction_type="SELL")], cfg(allow_mis=True), data(positions=held))
        self.assertIn("short: this MIS sell would leave you short 2 INFY", why(res))

    def test_closing_an_mis_position_after_the_cutoff_is_allowed(self):
        held = {"net": [{"tradingsymbol": "INFY", "product": "MIS", "quantity": 6, "last_price": 1612.5}], "day": []}
        late = ist("2026-10-26T15:10")
        res = run_check([self.mis(transaction_type="SELL")], cfg(allow_mis=True),
                        data(positions=held), late)
        self.assertEqual(verdicts(res), ["PASS"], why(res))


class Data(unittest.TestCase):
    def test_missing_and_stale_snapshots_block(self):
        d = data(margins="no margins snapshot in trader/kite: call the Kite connector for margins")
        self.assertIn("data: no margins snapshot", why(run_check([order()], d=d)))
        stale = run_check(example_orders(), d=data(now=ist("2026-10-26T10:03")), now=ist("2026-10-26T10:03"))
        self.assertEqual(verdicts(stale), ["BLOCK"] * 4)
        self.assertIn("data: the quotes snapshot is", why(stale))

    def test_a_missing_snapshot_only_blocks_the_rules_that_need_it(self):
        d = data(positions="no positions snapshot in trader/kite: call the Kite connector for positions")
        self.assertEqual(verdicts(run_check([order()], d=d)), ["PASS"])
        self.assertIn("data: no positions snapshot", why(run_check([order(product="MIS")], cfg(allow_mis=True), d)))

    def test_a_us_shaped_order_is_blocked_not_crashed(self):
        us = {"symbol": "AAPL", "side": "buy", "notional": "1250", "type": "market", "time_in_force": "day"}
        res = run_check([us])
        self.assertEqual(verdicts(res), ["BLOCK"])
        for text in ("format: no tradingsymbol", "asset: only NSE", "format: transaction_type",
                     "format: quantity", "format: order_type"):
            self.assertIn(text, why(res))

    def test_config_problems(self):
        self.assertIn("ignored US-era config keys: paper",
                      " ".join(run_check([order()], cfg(paper=True))["warnings"]))
        with self.assertRaises(check.RiskError):
            run_check([order()], cfg(mis_cutoff="3pm"))
        with self.assertRaises(check.RiskError):
            run_check([order()], cfg(max_order_value="lots"))

    def test_fingerprint_covers_the_kite_fields_only(self):
        o = order()
        self.assertEqual(check.fingerprint(o), check.fingerprint(dict(o, why="x", est_value="1", est_charges="2")))
        self.assertNotEqual(check.fingerprint(o), check.fingerprint(dict(o, quantity="7")))


class Cli(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = check.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_writes_the_verdicts(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "risk.json")
            code, text, _ = self.run_main(["--orders", ORDERS_PATH, "--config", CFG_PATH, "--kite-dir", KDIR,
                                           "--holidays", os.path.join(d, "h.json"), "--now", "2026-10-26T10:01",
                                           "--out", out])
            self.assertEqual(code, 0, text)
            self.assertIn("PASS  #1 BUY INFY CNC 6 x Rs 1,612.50 = Rs 9,675", text)
            self.assertIn("LIVE account, real money", text)
            self.assertIn("not financial advice", text)
            with open(out) as fh:
                rec = json.load(fh)
            self.assertEqual(rec["checked_at"], "2026-10-26T10:01:00+05:30")
            self.assertEqual(len(rec["results"]), 4)

    def test_blocked_and_broken_runs_exit_1(self):
        with tempfile.TemporaryDirectory() as d:
            base = ["--config", CFG_PATH, "--kite-dir", KDIR, "--holidays", os.path.join(d, "h.json"), "--no-write"]
            code, text, _ = self.run_main(["--orders", ORDERS_PATH, "--now", "2026-10-26T16:00"] + base)
            self.assertEqual(code, 1)
            self.assertIn("BLOCK #1", text)
            code, _, err = self.run_main(["--orders", os.path.join(d, "none.json")] + base)
            self.assertEqual(code, 1)
            self.assertIn("no orders file", err)


if __name__ == "__main__":
    unittest.main()
```

In `tests/test_repo.py`, replace `test_paper_trading_is_the_default` with:

```python
    def test_live_defaults_are_cautious(self):
        with open(os.path.join(ROOT, "trader-budget", "config.example.json")) as fh:
            cfg = json.load(fh)
        for k in ("allow_mis", "allow_short", "allow_market_orders", "allow_amo"):
            self.assertIs(cfg[k], False, k)
        self.assertLessEqual(float(cfg["max_order_value"]), 10000)
        self.assertNotIn("paper", cfg)
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p "test_r[ie]*.py" -v`
Expected:
- `test_risk` errors at import (`module 'trader_check' has no attribute 'nse_calendar'`).
- `test_live_defaults_are_cautious` errors with `KeyError: 'allow_mis'`.

- [ ] **Step 4: Implement**

```bash
cp trader-alerts/kite_snapshot.py trader-alerts/nse_calendar.py trader-alerts/rupees.py trader-risk/
```

Replace `trader-budget/config.example.json` with:

```json
{
  "budget": "50000",
  "cash_buffer_pct": "10",
  "max_position_pct": "25",
  "min_order_value": "100",
  "product": "CNC",
  "max_order_value": "10000",
  "max_orders_per_day": 5,
  "allow_market_orders": false,
  "max_limit_deviation_pct": "2",
  "allow_mis": false,
  "mis_cutoff": "15:00",
  "max_mis_exposure_pct": "50",
  "daily_loss_limit": "2000",
  "allow_short": false,
  "allow_amo": false,
  "blocked": [],
  "charges": {}
}
```

Replace `trader-risk/check.py` with:

```python
#!/usr/bin/env python3
"""Pre-trade risk check for trader-risk. Standard library only, no network.

Every order in this pack is a LIVE order with real money: Kite has no paper
account. This check is the gate between a proposal and the broker. It reads
the proposed orders (trader/orders.json), your rules (trader/config.json)
and the Kite snapshots Claude saved just before (trader/kite/: quotes,
holdings, positions, margins, orders), and gives each order PASS or BLOCK
with the reasons. Orders are checked in file order as if each PASS had
filled, so buys that are fine one by one but break the cash buffer together
are caught. Sale proceeds are not counted as cash on the same day.

    python3 check.py                       # the trader/ files, writes trader/state/risk.json
    python3 check.py --orders trader/orders.json --json
    python3 check.py --no-write            # check without recording the verdicts

What blocks an order:

  format       not a bare NSE tradingsymbol; transaction_type not BUY or
               SELL; quantity not a whole number above 0; validity not DAY;
               variety not regular or amo; a LIMIT order without a price;
               SL and SL-M (stop-loss) orders, which this pack does not use
  asset        anything not on NSE; F&O contracts (always)
  product      anything but CNC (delivery) and MIS (intraday); MIS while
               "allow_mis" is false
  blocked      a symbol on your "blocked" list
  hours        outside 09:15 to 15:30 IST on an NSE trading day, unless
               "allow_amo" is true and the order is variety amo; any day
               in a year whose NSE holiday list is not loaded
  price        no fresh Kite quote; MARKET while "allow_market_orders" is
               false; a LIMIT price more than "max_limit_deviation_pct"
               from the last price; a price outside today's circuit band
  size         under "min_order_value" or over "max_order_value" (rupees)
  cash         a CNC buy plus its charges needs more than your available
               cash, or dips into your "cash_buffer_pct" buffer
  position     the stock would be over "max_position_pct" of the account
  short        a CNC sell of more than you hold; an MIS sell that would
               leave you short, unless "allow_short" is true
  intraday     a new MIS position after "mis_cutoff" (15:00 IST); MIS
               exposure over "max_mis_exposure_pct" of your equity margin;
               any new MIS position once the day's loss reaches
               "daily_loss_limit"
  duplicate    the same symbol, side and product twice in this batch
  daily limit  more than "max_orders_per_day" orders today (Kite's order
               book plus the ones passed earlier in this batch)
  data         a Kite snapshot a rule needs is missing or stale: that is a
               BLOCK, never a skipped rule

Exit code 0 when every order passes, 1 when any order is blocked or the
check could not run. The verdicts go to trader/state/risk.json with a
fingerprint of each order, so trader-broker only shows an order as ready
if THIS exact order passed.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import kite_snapshot
import nse_calendar
from rupees import inr

DEFAULTS = {
    "cash_buffer_pct": 10, "max_position_pct": 25, "max_order_value": 10000, "min_order_value": 100,
    "max_orders_per_day": 5, "allow_market_orders": False, "max_limit_deviation_pct": 2,
    "allow_mis": False, "mis_cutoff": "15:00", "max_mis_exposure_pct": 50, "daily_loss_limit": 2000,
    "allow_short": False, "allow_amo": False, "blocked": [],
}
NUMBERS = ("cash_buffer_pct", "max_position_pct", "max_order_value", "min_order_value", "max_orders_per_day",
           "max_limit_deviation_pct", "max_mis_exposure_pct", "daily_loss_limit")
LEGACY = ("paper", "max_order_usd", "min_order_usd", "allow_options", "allow_margin", "fractional", "broker")
KITE_FIELDS = ("exchange", "tradingsymbol", "transaction_type", "quantity", "product", "order_type",
               "price", "trigger_price", "validity", "variety")
FNO = re.compile(r"\d.*(FUT|CE|PE)$")
NOT_PLACED = {"REJECTED", "CANCELLED"}
PAISA = 0.005
SNAPSHOTS = ("quotes", "holdings", "positions", "margins", "orders")


class RiskError(Exception):
    pass


def read_json(path, what, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise RiskError("no %s at %s" % (what, path))
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise RiskError("%s is not valid JSON: %s" % (path, e))


def fingerprint(order):
    """Same function in trader-broker/ticket.py: the exact order that was checked."""
    core = {k: order[k] for k in KITE_FIELDS if k in order and order[k] is not None}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _qty(x):
    """A whole number of shares above 0, or None."""
    v = _f(x)
    if v is None or v <= 0 or v != int(v):
        return None
    return int(v)


def _pct(x):
    x = float(x)
    return str(int(x)) if x == int(x) else ("%.2f" % x)


def config(cfg):
    """Your rules merged over the cautious defaults, numbers parsed. Returns (rules, warnings)."""
    c = dict(DEFAULTS)
    c.update(cfg or {})
    for k in NUMBERS:
        v = _f(c[k])
        if v is None or v < 0:
            raise RiskError("config %s must be a number of at least 0, got %r" % (k, c[k]))
        c[k] = v
    try:
        c["mis_cutoff"] = datetime.datetime.strptime(str(c["mis_cutoff"]), "%H:%M").time()
    except ValueError:
        raise RiskError("config mis_cutoff wants a time like 15:00, got %r" % c["mis_cutoff"])
    warnings = []
    old = [k for k in LEGACY if k in (cfg or {})]
    if old:
        warnings.append("ignored US-era config keys: %s. Kite has no paper account and every order is live; "
                        "the limits are max_order_value and min_order_value in rupees" % ", ".join(old))
    return c, warnings


def _need(data, kind):
    """(snapshot, None) or (None, the BLOCK reason) for a snapshot a rule needs."""
    v = data.get(kind)
    if v is None or isinstance(v, str):
        return None, "data: %s" % (v or "no %s snapshot" % kind)
    return v, None


def account(data):
    """What the Kite snapshots say about the account. Missing pieces stay None."""
    acct = {"cash": None, "equity": None, "held": None, "held_value": None, "mis_net": None,
            "mis_exposure": None, "day_pnl": None, "placed": None}
    quotes = data.get("quotes") if isinstance(data.get("quotes"), dict) else {}
    m = data.get("margins")
    if isinstance(m, dict):
        eq = m.get("equity") or {}
        av = eq.get("available") or {}
        acct["cash"] = _f(av.get("live_balance", av.get("cash")))
        acct["equity"] = _f(eq.get("net"))
    h = data.get("holdings")
    if isinstance(h, list):
        held, value = {}, {}
        for row in h:
            sym = str(row.get("tradingsymbol", "")).upper()
            n = (_f(row.get("quantity")) or 0) + (_f(row.get("t1_quantity")) or 0)
            px = (quotes.get(sym) or {}).get("price") or _f(row.get("last_price")) or 0
            held[sym] = held.get(sym, 0) + n
            value[sym] = value.get(sym, 0) + n * px
        acct["held"], acct["held_value"] = held, value
    p = data.get("positions")
    if isinstance(p, dict):
        net, exposure = {}, 0.0
        for row in p.get("net") or []:
            if row.get("product") != "MIS":
                continue
            sym = str(row.get("tradingsymbol", "")).upper()
            n = _f(row.get("quantity")) or 0
            net[sym] = net.get(sym, 0) + n
            exposure += abs(n) * (_f(row.get("last_price")) or 0)
        acct["mis_net"], acct["mis_exposure"] = net, exposure
        acct["day_pnl"] = sum(_f(row.get("pnl")) or 0 for row in p.get("day") or [])
    o = data.get("orders")
    if isinstance(o, list):
        acct["placed"] = sum(1 for row in o if str(row.get("status", "")).upper() not in NOT_PLACED)
    return acct


def check(orders, cfg, data, now, cal):
    """Pure function. data maps each snapshot kind to its Kite answer (quotes already normalised by
    kite_snapshot.quotes) or to the error text that explains why it is missing. now is an aware
    datetime; cal is an nse_calendar.Calendar. Returns {"results": [...], "pass": n, "block": n, ...}."""
    c, top_warn = config(cfg)
    top_warn.insert(0, "LIVE: every order here is a real-money order on your Zerodha account")
    now = now.astimezone(nse_calendar.IST)
    st = cal.status(now)
    acct = account(data)
    quotes, quote_err = _need(data, "quotes")
    blocked = {str(b).strip().upper() for b in c.get("blocked") or []}
    seen, results = set(), []

    for i, o in enumerate(orders, 1):
        reasons, warns = [], []

        def need(kind):
            v, err = _need(data, kind)
            if err and err not in reasons:
                reasons.append(err)
            return v is not None

        sym = str(o.get("tradingsymbol") or "").strip()
        exch = str(o.get("exchange") or "").strip().upper()
        side = str(o.get("transaction_type") or "").strip().upper()
        product = str(o.get("product") or "").strip().upper()
        typ = str(o.get("order_type") or "").strip().upper()
        variety = str(o.get("variety") or "regular").strip().lower()
        qty = _qty(o.get("quantity"))
        price = _f(o.get("price"))

        # format and asset
        if not sym:
            reasons.append("format: no tradingsymbol")
        elif sym != sym.upper() or ":" in sym or sym.endswith(".NS") or " " in sym:
            reasons.append("format: tradingsymbol must be the bare NSE symbol in capitals, like INFY, not %r" % sym)
        if exch != "NSE":
            reasons.append("asset: only NSE orders are supported, not %r" % o.get("exchange"))
        if sym and FNO.search(sym.upper()):
            reasons.append("asset: %s looks like an F&O contract; F&O is not supported" % sym)
        if side not in ("BUY", "SELL"):
            reasons.append("format: transaction_type must be BUY or SELL, got %r" % o.get("transaction_type"))
        if qty is None:
            reasons.append("format: quantity must be a whole number of shares above 0, got %r" % o.get("quantity"))
        for k in ("quantity", "price"):
            if o.get(k) is not None and not isinstance(o.get(k), str):
                warns.append("send %s as a string (\"%s\"), the way the orders file writes it" % (k, o.get(k)))
        if typ in ("SL", "SL-M"):
            reasons.append("format: %s (stop-loss) orders are not supported by this pack" % typ)
        elif typ not in ("LIMIT", "MARKET"):
            reasons.append("format: order_type must be LIMIT or MARKET, got %r" % o.get("order_type"))
        if typ == "LIMIT" and not (price and price > 0):
            reasons.append("format: a LIMIT order needs a price above 0")
        if str(o.get("validity") or "DAY").strip().upper() != "DAY":
            reasons.append("format: validity must be DAY, got %r" % o.get("validity"))
        if variety not in ("regular", "amo"):
            reasons.append("format: variety must be regular (or amo), got %r" % o.get("variety"))
        if product not in ("CNC", "MIS"):
            reasons.append("product: %r is not supported: CNC (delivery) or MIS (intraday) only, no NRML or F&O"
                           % o.get("product"))
        if product == "MIS" and not c["allow_mis"]:
            reasons.append("product: MIS (intraday) is off (\"allow_mis\": false)")
        if sym.upper() in blocked:
            reasons.append("blocked: %s is on your blocked list" % sym)

        # market hours
        if not st["calendar_known"]:
            reasons.append("hours: NSE's holiday list for %s is not loaded (alerts.py holidays refresh), so the "
                           "market may be closed today" % st["date"][:4])
        elif st["open"]:
            if variety == "amo":
                reasons.append("hours: an amo (after-market) order while NSE is open; use variety regular")
        elif not (c["allow_amo"] and variety == "amo"):
            reasons.append("hours: NSE is closed (%s, %s IST); orders go in 09:15 to 15:30 IST on trading days"
                           % (st["reason"], st["now_ist"]))

        # price
        q = None
        if quote_err:
            reasons.append(quote_err)
        elif sym:
            q = quotes.get(sym.upper())
            if not q:
                reasons.append("data: no fresh Kite quote for NSE:%s; add it to the quotes call" % sym)
        if typ == "MARKET" and not c["allow_market_orders"]:
            reasons.append("price: MARKET orders are off (\"allow_market_orders\": false); use a LIMIT price")
        ref = price if typ == "LIMIT" else (q["price"] if q else None)
        if q and typ == "LIMIT" and price:
            dev = abs(price - q["price"]) / q["price"] * 100.0
            if dev > c["max_limit_deviation_pct"] + 1e-9:
                reasons.append("price: limit %s is %.2f%% from the last price %s, over your %s%% limit"
                               % (inr(price), dev, inr(q["price"]), _pct(c["max_limit_deviation_pct"])))
        if q and ref:
            lo, hi = q.get("lower_circuit"), q.get("upper_circuit")
            if lo is None or hi is None:
                warns.append("the Kite quote has no circuit limits for %s" % sym)
            elif ref < lo - PAISA or ref > hi + PAISA:
                reasons.append("price: %s is outside today's circuit band %s to %s" % (inr(ref), inr(lo), inr(hi)))
        value = qty * ref if (qty and ref) else None
        est_charges = _f(o.get("est_charges")) or 0.0

        # size
        if value is not None:
            if value < c["min_order_value"] - PAISA:
                reasons.append("size: %s is under your %s minimum order" % (inr(value), inr(c["min_order_value"])))
            if c["max_order_value"] and value > c["max_order_value"] + PAISA:
                reasons.append("size: %s is over your %s max order" % (inr(value), inr(c["max_order_value"])))

        # the account, simulated in order
        opening = None
        if product == "CNC" and side == "BUY" and value is not None:
            if need("margins") and need("holdings"):
                cash = acct["cash"]
                total = cash + sum(acct["held_value"].values())
                after = cash - value - est_charges
                buffer_rs = total * c["cash_buffer_pct"] / 100.0
                if after < -PAISA:
                    reasons.append("cash: needs %s with charges but only %s is available"
                                   % (inr(value + est_charges), inr(cash)))
                elif after < buffer_rs - PAISA:
                    reasons.append("cash: leaves %s, under your %s%% buffer of %s"
                                   % (inr(max(after, 0)), _pct(c["cash_buffer_pct"]), inr(buffer_rs)))
                pos_after = acct["held_value"].get(sym, 0.0) + value
                limit = total * c["max_position_pct"] / 100.0
                if total > 0 and pos_after > limit + PAISA:
                    reasons.append("position: %s would be %s, %.1f%% of the %s account, over your %s%% cap"
                                   % (sym, inr(pos_after), 100.0 * pos_after / total, inr(total),
                                      _pct(c["max_position_pct"])))
        if product == "CNC" and side == "SELL" and qty:
            if need("holdings"):
                have = acct["held"].get(sym, 0)
                if qty > have + 1e-9:
                    reasons.append("short: selling %d %s but you hold %d; a delivery sale needs the shares"
                                   % (qty, sym, int(have)))
        if product == "MIS" and side in ("BUY", "SELL") and qty:
            if need("positions") and need("margins"):
                net = acct["mis_net"].get(sym, 0)
                after_net = net + (qty if side == "BUY" else -qty)
                opening = abs(after_net) > abs(net) or after_net * net < 0
                if side == "SELL" and after_net < 0 and not c["allow_short"]:
                    reasons.append("short: this MIS sell would leave you short %d %s; short selling is off "
                                   "(\"allow_short\": false)" % (-after_net, sym))
                if opening:
                    if now.time() >= c["mis_cutoff"]:
                        reasons.append("intraday: no new MIS positions after %s IST; Zerodha squares MIS off "
                                       "from about 15:20" % c["mis_cutoff"].strftime("%H:%M"))
                    if value is not None and acct["equity"] is not None:
                        after = acct["mis_exposure"] + value
                        limit = acct["equity"] * c["max_mis_exposure_pct"] / 100.0
                        if after > limit + PAISA:
                            reasons.append("intraday: MIS exposure would be %s, over %s%% of your %s equity margin"
                                           % (inr(after), _pct(c["max_mis_exposure_pct"]), inr(acct["equity"])))
                    if c["daily_loss_limit"] and acct["day_pnl"] <= -c["daily_loss_limit"]:
                        reasons.append("intraday: today's loss %s has reached your %s daily loss limit; no new MIS "
                                       "positions today" % (inr(-acct["day_pnl"]), inr(c["daily_loss_limit"])))

        # duplicates and the daily limit
        key = (sym, side, product)
        if key in seen:
            reasons.append("duplicate: a second %s %s %s in this batch" % (side, sym, product))
        seen.add(key)
        if need("orders"):
            passed = sum(1 for r in results if r["verdict"] == "PASS")
            cap_n = int(c["max_orders_per_day"])
            if cap_n and acct["placed"] + passed >= cap_n:
                reasons.append("daily limit: %d orders in Kite's order book today plus %d passed earlier in this "
                               "batch, your limit is %d a day" % (acct["placed"], passed, cap_n))

        verdict = "BLOCK" if reasons else "PASS"
        if verdict == "PASS" and value is not None:
            if product == "CNC" and side == "BUY":
                acct["cash"] -= value + est_charges
                acct["held_value"][sym] = acct["held_value"].get(sym, 0.0) + value
                acct["held"][sym] = acct["held"].get(sym, 0) + qty
            elif product == "CNC":
                acct["held"][sym] = acct["held"].get(sym, 0) - qty
                acct["held_value"][sym] = max(acct["held_value"].get(sym, 0.0) - value, 0.0)
            else:
                acct["mis_net"][sym] = acct["mis_net"].get(sym, 0) + (qty if side == "BUY" else -qty)
                acct["mis_exposure"] = max(acct["mis_exposure"] + (value if opening else -value), 0.0)
        results.append({
            "index": i, "symbol": sym, "side": side, "product": product, "quantity": qty,
            "amount": ("%d x %s = %s" % (qty, inr(ref), inr(value))) if value is not None else str(o.get("quantity")),
            "value": round(value, 2) if value is not None else None,
            "fingerprint": fingerprint(o), "verdict": verdict, "reasons": reasons, "warnings": warns,
        })

    return {
        "checked_at": now.replace(microsecond=0).isoformat(), "date": st["date"], "live": True,
        "market": {k: st.get(k) for k in ("open", "reason", "now_ist", "calendar_known")},
        "results": results,
        "pass": sum(1 for r in results if r["verdict"] == "PASS"),
        "block": sum(1 for r in results if r["verdict"] == "BLOCK"),
        "warnings": top_warn,
        "cash_after": round(acct["cash"], 2) if acct["cash"] is not None else None,
    }


def report(res):
    lines = []
    for w in res["warnings"]:
        lines.append("WARNING: " + w)
    lines.append("")
    for r in res["results"]:
        lines.append("%-5s #%d %s %s %s %s" % (r["verdict"], r["index"], r["side"], r["symbol"], r["product"],
                                               r["amount"]))
        for x in r["reasons"]:
            lines.append("        - " + x)
        for x in r["warnings"]:
            lines.append("        ~ " + x)
    lines.append("")
    cash = (" Cash after the passed orders: %s." % inr(res["cash_after"])) if res["cash_after"] is not None else ""
    lines.append("%d passed, %d blocked.%s LIVE account, real money." % (res["pass"], res["block"], cash))
    if res["block"]:
        lines.append("Blocked orders do not go to the broker. Fix the order or your rules, then check again.")
    else:
        lines.append("Every order passed. trader-broker still asks you yes or no for each one.")
    lines.append("Education and tooling, not financial advice.")
    return "\n".join(lines)


def load_data(kite_dir, now):
    """Each Kite snapshot, or the error text saying why it cannot be used."""
    data = {}
    for kind in SNAPSHOTS:
        try:
            v = kite_snapshot.load(kind, kite_dir, now=now)
        except kite_snapshot.SnapshotError as e:
            data[kind] = str(e)
            continue
        data[kind] = kite_snapshot.quotes(v) if kind == "quotes" else v
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check proposed LIVE orders against your limits (trader-risk).")
    ap.add_argument("--orders", default="trader/orders.json")
    ap.add_argument("--config", default="trader/config.json")
    ap.add_argument("--kite-dir", default=kite_snapshot.DIR, help="where the Kite snapshots are")
    ap.add_argument("--holidays", default=nse_calendar.CACHE, help="the cached NSE holiday list")
    ap.add_argument("--now", help="pretend it is this time (ISO; no offset = IST)")
    ap.add_argument("--out", default="trader/state/risk.json", help="where the verdicts are recorded")
    ap.add_argument("--no-write", action="store_true", help="do not record the verdicts")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        doc = read_json(a.orders, "orders file (run trader-budget first)")
        orders = doc.get("orders", doc) if isinstance(doc, dict) else doc
        if not isinstance(orders, list) or not orders:
            raise RiskError("no orders in %s" % a.orders)
        cfg = read_json(a.config, "config", required=False) or {}
        now = nse_calendar.parse_now(a.now)
        cal = nse_calendar.Calendar(*nse_calendar.load_holidays(a.holidays))
        res = check(orders, cfg, load_data(a.kite_dir, now), now, cal)
        if not a.no_write:
            d = os.path.dirname(a.out)
            if d:
                os.makedirs(d, exist_ok=True)
            rec = dict(res)
            rec["orders_file"] = a.orders
            with open(a.out, "w", encoding="utf-8") as fh:
                json.dump(rec, fh, indent=2)
                fh.write("\n")
    except (RiskError, nse_calendar.CalendarError) as e:
        print("check.py: %s" % e, file=sys.stderr)
        return 1
    print(json.dumps(res, indent=2) if a.json else report(res))
    return 1 if res["block"] else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Remove the tests that exercised the US risk check**

In `tests/test_rebalance.py`:
- delete the line `check = load("trader-risk", "check")`
- in `test_bigger_deposit_buys_everything_and_keeps_the_buffer`, delete these two lines:

```python
        risk = check.check(rebalance.clean(res["orders"]), cfg, portfolio=pf, prices=px, today="2026-10-13")
        self.assertEqual(risk["block"], 0, risk["results"])
```

In `tests/test_broker.py`:
- delete `class Flow(unittest.TestCase):` and everything after it up to (not including) `if __name__ == "__main__":`
- delete the now-unused lines `import shutil` and `import tempfile`

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_risk.py -v`
Expected: all 26 tests pass.

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`
Expected: `OK` and `All checks passed!`. `test_shared_helpers_are_identical` now compares the trader-alerts and trader-risk copies.

- [ ] **Step 7: Commit**

```bash
git add -A trader-risk trader-budget/config.example.json tests/test_risk.py tests/test_repo.py tests/test_rebalance.py tests/test_broker.py tests/fixtures/trader-risk
git commit -m "Convert trader-risk to Kite snapshots and the live risk rules" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 5: trader-budget in whole NSE shares at the Kite price

The sizing maths in `size.py` (`normalise`, `allocate`, `round_to_unit` and `whole_shares`, the section from `# ---------------------------------------------------------------- the maths` to just before `def size(`) stays byte-for-byte as it is. Everything around it is replaced.

**Files:**
- Copy (unchanged): `trader-alerts/kite_snapshot.py`, `trader-alerts/nse.py`, `trader-alerts/nse_symbols.py` and `trader-alerts/rupees.py` into `trader-budget/`
- Modify: `trader-budget/size.py` (everything except the maths section), `trader-budget/targets.example.json`, `tests/test_budget.py` (full rewrite)
- Create: `tests/fixtures/trader-budget/kite/quotes.json`

**Interfaces:**
- Consumes: `charges.estimate` (Task 3); `kite_snapshot.load`, `quotes` and `IST`; `nse_symbols.normalize`; `rupees.inr`
- Produces:
  - `size.load_config(path)`, `size.parse_weights(data)` and `size.weights_from_arg(text)`
  - `size.quote_prices(kite_dir, now=None) -> {SYM: float}`
  - `size.size(rows, cfg, budget=None, prices=None, top=None) -> {..., "cap", "cap_by", "positions": [{"symbol", "name", "weight", "source_weight", "price", "shares", "rupees", "capped"}], "invested", "idle", "dropped"}`
  - `size.orders_from(result, cfg, product="CNC", source="") -> [Kite orders]`
  - `size.write_orders(path, orders, source="", now=None)`
  - The orders file has `"live": true`. The cap is the lower of `max_position_pct` of the budget and `max_order_value`.

- [ ] **Step 1: Write the fixture and the failing tests**

`tests/fixtures/trader-budget/kite/quotes.json`:

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

Replace `tests/test_budget.py` with:

```python
import datetime
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

size = load("trader-budget", "size")

BDIR = os.path.join(ROOT, "trader-budget")
KDIR = os.path.join(FIX, "trader-budget", "kite")
NOW = "2026-10-26T10:01"


def cfg(**over):
    c = size.load_config(os.path.join(BDIR, "config.example.json"))
    c.update(over)
    return c


def targets():
    with open(os.path.join(BDIR, "targets.example.json")) as fh:
        return size.parse_weights(json.load(fh))


def prices():
    return size.quote_prices(KDIR, datetime.datetime(2026, 10, 26, 10, 1, tzinfo=size.IST))


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = size.main(argv)
    return code, out.getvalue(), err.getvalue()


class Example(unittest.TestCase):
    def test_the_example_budget_is_capped_by_the_max_order(self):
        r = size.size(targets(), cfg(), None, prices())
        self.assertEqual((r["budget"], r["cash_buffer"], r["investable"], r["cap"]), (50000, 5000, 45000, 10000))
        self.assertEqual(r["cap_by"], "your Rs 10,000 max order")
        self.assertEqual([(p["symbol"], p["shares"], p["rupees"]) for p in r["positions"]],
                         [("INFY", 6, 9675.0), ("RELIANCE", 7, 9816.1), ("TCS", 3, 9151.5), ("HDFCBANK", 6, 9900.0)])
        self.assertEqual((r["invested"], r["idle"]), (38542.6, 6457.4))

    def test_orders_are_kite_place_order_shaped(self):
        r = size.size(targets(), cfg(), None, prices())
        o = size.orders_from(r, cfg())
        self.assertEqual(o[0], {
            "exchange": "NSE", "tradingsymbol": "INFY", "transaction_type": "BUY", "quantity": "6",
            "product": "CNC", "order_type": "LIMIT", "price": "1612.50", "validity": "DAY",
            "variety": "regular", "est_value": "9675.00", "est_charges": "11.49",
            "why": "25.00% of the stock sleeve; capped at Rs 10,000, your Rs 10,000 max order"})
        self.assertTrue(all(isinstance(x["quantity"], str) and isinstance(x["price"], str) for x in o))
        self.assertEqual({x["product"] for x in size.orders_from(r, cfg(), "mis")}, {"MIS"})


class Rules(unittest.TestCase):
    def test_bigger_budget_uses_the_position_cap_and_drops_blocked(self):
        r = size.size(targets(), cfg(max_order_value="0", blocked=["tcs.ns"]), 100000, prices())
        self.assertEqual((r["cap"], r["cap_by"]), (25000, "25% of the Rs 1,00,000 budget"))
        self.assertEqual(r["dropped"], [{"ticker": "TCS", "reason": "on your blocked list"}])
        self.assertEqual([(p["symbol"], p["shares"]) for p in r["positions"]],
                         [("INFY", 15), ("RELIANCE", 17), ("HDFCBANK", 15)])
        self.assertEqual((r["invested"], r["idle"]), (72776.6, 17223.4))

    def test_a_share_dearer_than_its_slice_is_dropped(self):
        r = size.size(size.parse_weights({"TCS": 50, "INFY": 50}),
                      cfg(max_order_value="2000", max_position_pct="50"), 5000, prices())
        self.assertEqual(r["dropped"], [{"ticker": "TCS",
                                         "reason": "one share costs Rs 3,050.50, more than its slice of Rs 2,000"}])
        self.assertEqual([(p["symbol"], p["shares"]) for p in r["positions"]], [("INFY", 1)])

    def test_nothing_affordable_is_an_error(self):
        with self.assertRaises(size.SizeError):
            size.size(targets(), cfg(), 2000, prices())

    def test_missing_quote_names_the_kite_instrument(self):
        with self.assertRaises(size.SizeError) as e:
            size.size(size.parse_weights({"INFY": 50, "M&M": 50}), cfg(), None, prices())
        self.assertIn("NSE:M&M", str(e.exception))

    def test_symbol_spellings_and_bad_input(self):
        self.assertEqual([r["ticker"] for r in size.parse_weights({"infy.ns": 1, "nse:tcs": 1})], ["INFY", "TCS"])
        with self.assertRaises(size.SizeError):
            size.parse_weights({"BSE:INFY": 1})
        with self.assertRaises(size.SizeError):
            size.parse_weights({"INFY": "lots"})
        with self.assertRaises(size.SizeError):
            size.size(targets(), cfg(budget=None), None, prices())


class Cli(unittest.TestCase):
    def test_write_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            code, text, _ = run(["--targets", os.path.join(BDIR, "targets.example.json"),
                                 "--config", os.path.join(BDIR, "config.example.json"),
                                 "--kite-dir", KDIR, "--now", NOW, "--write", out])
            self.assertEqual(code, 0)
            self.assertIn("BUY 6 INFY, CNC, LIMIT Rs 1,612.50, est. Rs 9,675 + Rs 11.49 charges", text)
            self.assertIn("LIVE", text)
            self.assertIn("not financial advice", text)
            with open(out) as fh:
                doc = json.load(fh)
            self.assertIs(doc["live"], True)
            self.assertEqual(doc["created_by"], "trader-budget")
            self.assertEqual(len(doc["orders"]), 4)

    def test_stale_quotes_stop_the_sizing(self):
        code, _, err = run(["--weights", "INFY=100", "--config", os.path.join(BDIR, "config.example.json"),
                            "--kite-dir", KDIR, "--now", "2026-10-26T10:03"])
        self.assertEqual(code, 1)
        self.assertIn("s old", err)

    def test_missing_targets(self):
        code, _, err = run(["--targets", os.path.join(FIX, "nope.json"), "--kite-dir", KDIR, "--now", NOW])
        self.assertEqual(code, 1)
        self.assertIn("no targets file", err)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_budget.py -v`
Expected: errors such as `AttributeError: module 'trader_size' has no attribute 'IST'` and `quote_prices`.

- [ ] **Step 3: Implement**

```bash
cp trader-alerts/kite_snapshot.py trader-alerts/nse.py trader-alerts/nse_symbols.py trader-alerts/rupees.py trader-budget/
```

Replace `trader-budget/targets.example.json` with:

```json
{
  "source": "an example: four large NSE stocks, equal weight",
  "as_of": "2026-10-26",
  "weights": [
    {"symbol": "INFY", "name": "Infosys", "weight": 25},
    {"symbol": "RELIANCE", "name": "Reliance Industries", "weight": 25},
    {"symbol": "TCS", "name": "Tata Consultancy Services", "weight": 25},
    {"symbol": "HDFCBANK", "name": "HDFC Bank", "weight": 25}
  ]
}
```

Rewrite `trader-budget/size.py` so that it is, in order:
1. the head below
2. the existing maths section, unchanged
3. the tail below

Head (from the first line up to the maths section):

```python
#!/usr/bin/env python3
"""Position sizing for trader-budget. Standard library only, no network.

Turns target weights (the portfolio you want to copy) and your rules (budget,
cash buffer, a cap on any one stock, a minimum order) into whole NSE shares
at the Kite last price, then into proposed orders shaped like Kite's
place_order. It never places anything: it writes proposals to
trader/orders.json, which trader-risk checks and trader-broker shows you
one by one. Every order is a LIVE order with real money: Kite has no paper
account.

    python3 size.py                                  # trader/targets.json + trader/config.json
    python3 size.py --budget 50000 --write           # write trader/orders.json
    python3 size.py --weights INFY=30,TCS=25,HDFCBANK=25,RELIANCE=20
    python3 size.py --product MIS                    # intraday (trader-risk blocks it unless allow_mis)
    python3 size.py --json

Prices come from the Kite quotes snapshot (trader/kite/quotes.json, saved
with kite_snapshot.py save quotes, at most 120 seconds old). Each order is a
LIMIT order at the last price; trader-risk checks it against the price again.

How the money is split:

  1. cash buffer   budget x cash_buffer_pct stays in cash, never invested
  2. weights       renormalised to 100 over the stocks you keep (blocked
                   symbols are dropped first; --top N keeps the N biggest)
  3. cap           no stock gets more than max_position_pct of the budget,
                   or max_order_value if that is lower (so trader-risk does
                   not block the order for size); anything over the cap is
                   shared out to the others by weight, again and again
                   until nobody is over
  4. whole shares  NSE has no fractional shares: each slice buys whole
                   shares, then what is left buys one share at a time for
                   the stock furthest below its slice
  5. min order     a slice under min_order_value (rupees) is dropped and its
                   weight shared out

Money that cannot be invested (every stock at its cap, or leftovers from
whole shares) is reported as "left idle", never hidden. Each order carries
an estimate of Zerodha's charges (charges.py).
"""

import argparse
import datetime
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import charges
import kite_snapshot
import nse_symbols
from rupees import inr

DEFAULTS = {
    "budget": None,
    "cash_buffer_pct": 10,
    "max_position_pct": 25,
    "min_order_value": 100,
    "product": "CNC",
    "blocked": [],
}
EPS = 1e-9
IST = kite_snapshot.IST


class SizeError(Exception):
    pass


# ---------------------------------------------------------------- inputs

def read_json(path, what):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise SizeError("no %s at %s" % (what, path))
    except json.JSONDecodeError as e:
        raise SizeError("%s is not valid JSON: %s" % (path, e))


def load_config(path):
    cfg = dict(DEFAULTS)
    if path and os.path.exists(path):
        cfg.update(read_json(path, "config"))
    return cfg


def _symbol(text):
    try:
        return nse_symbols.normalize(text)
    except nse_symbols.SymbolError as e:
        raise SizeError(str(e))


def parse_weights(data):
    """Accept targets.json, a {symbol: weight} dict or a list of rows.

    Returns [{"ticker", "name", "weight"}] with the NSE symbol in "ticker" and weight as a float."""
    if isinstance(data, dict) and "weights" in data:
        data = data["weights"]
    rows = []
    if isinstance(data, dict):
        for t, w in data.items():
            rows.append({"ticker": t, "name": "", "weight": w})
    elif isinstance(data, list):
        for i, r in enumerate(data):
            if not isinstance(r, dict):
                raise SizeError("weights[%d] is not an object" % i)
            t = r.get("symbol") or r.get("ticker")
            w = r.get("weight", r.get("weight_pct", r.get("pct")))
            if not t or w is None:
                raise SizeError("weights[%d] needs a symbol and a weight" % i)
            rows.append({"ticker": t, "name": r.get("name", ""), "weight": w})
    else:
        raise SizeError("weights must be a list or an object")
    out = []
    for r in rows:
        try:
            w = float(r["weight"])
        except (TypeError, ValueError):
            raise SizeError("weight for %s is not a number: %r" % (r["ticker"], r["weight"]))
        out.append({"ticker": _symbol(r["ticker"]), "name": r["name"] or "", "weight": w})
    return out


def weights_from_arg(text):
    """INFY=30,TCS=25 -> {symbol: weight}"""
    out = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise SizeError("--weights wants SYMBOL=WEIGHT pairs, got %r" % part)
        t, w = part.split("=", 1)
        out[t.strip().upper()] = w.strip()
    return out


def quote_prices(kite_dir, now=None):
    """{SYMBOL: last price} from the Kite quotes snapshot. A missing or stale snapshot stops the sizing."""
    try:
        snap = kite_snapshot.quotes(kite_snapshot.load("quotes", kite_dir, now=now))
    except kite_snapshot.SnapshotError as e:
        raise SizeError(str(e))
    return {s: q["price"] for s, q in snap.items()}
```

Tail (from `def size(` to the end of the file):

```python
def size(rows, cfg, budget=None, prices=None, top=None):
    """Pure function: weights + rules + prices -> the full sizing result (a dict), in whole shares."""
    budget = float(budget if budget is not None else (cfg.get("budget") or 0))
    if budget <= 0:
        raise SizeError("no budget: pass --budget or set \"budget\" (rupees) in trader/config.json")
    buf_pct = float(cfg.get("cash_buffer_pct", 10))
    cap_pct = float(cfg.get("max_position_pct", 25))
    min_order = float(cfg.get("min_order_value", 100) or 0)
    if not 0 <= buf_pct < 100:
        raise SizeError("cash_buffer_pct must be between 0 and 100")
    if not 0 < cap_pct <= 100:
        raise SizeError("max_position_pct must be above 0 and at most 100")
    prices = prices or {}
    blocked = []
    for b in cfg.get("blocked") or []:
        blocked.append(_symbol(b))

    keep, dropped = normalise(rows, blocked, top)
    if not keep:
        raise SizeError("nothing to size: no weights left after the blocked list")
    missing = [r["ticker"] for r in keep if not prices.get(r["ticker"])]
    if missing:
        raise SizeError("no Kite quote for: %s (add %s to the Kite quotes call, then kite_snapshot.py save quotes)"
                        % (", ".join(missing), " ".join("NSE:" + m for m in missing)))

    cash_buffer = round(budget * buf_pct / 100.0, 2)
    investable = round(budget - cash_buffer, 2)
    cap = round(budget * cap_pct / 100.0, 2)
    cap_by = "%s%% of the %s budget" % (_num(cap_pct), inr(budget))
    max_order = float(cfg.get("max_order_value") or 0)
    if max_order and max_order < cap:
        cap, cap_by = round(max_order, 2), "your %s max order" % inr(max_order)

    while True:
        live = [dict(r) for r in keep]
        tot = sum(r["source_weight"] for r in live)
        for r in live:
            r["weight"] = 100.0 * r["source_weight"] / tot
        exact, capped = allocate(live, investable, cap)
        order = [r["ticker"] for r in sorted(live, key=lambda r: -exact[r["ticker"]])]
        slices = round_to_unit(exact, capped, order, cap, 0.01)
        shares = whole_shares(slices, prices, order, cap, sum(slices.values()))
        rupees = {t: round(shares[t] * prices[t], 2) for t in order}
        small = [r for r in live if rupees[r["ticker"]] < min_order - EPS]
        if not small:
            break
        worst = min(small, key=lambda r: (r["source_weight"], r["ticker"]))
        if shares[worst["ticker"]] == 0:
            reason = ("one share costs %s, more than its slice of %s"
                      % (inr(prices[worst["ticker"]]), inr(slices[worst["ticker"]])))
        else:
            reason = "its %s is under your %s minimum order" % (inr(rupees[worst["ticker"]]), inr(min_order))
        dropped.append({"ticker": worst["ticker"], "reason": reason})
        keep = [r for r in keep if r["ticker"] != worst["ticker"]]
        if not keep:
            raise SizeError("no stock can be bought: every slice is under one share or your minimum order; "
                            "raise the budget or hold fewer stocks")

    positions = []
    for r in sorted(live, key=lambda r: -r["weight"]):
        t = r["ticker"]
        positions.append({"symbol": t, "name": r["name"], "weight": round(r["weight"], 2),
                          "source_weight": r["source_weight"], "price": prices[t], "shares": shares[t],
                          "rupees": rupees[t], "capped": t in capped})
    invested = round(sum(p["rupees"] for p in positions), 2)
    return {
        "budget": budget, "cash_buffer_pct": buf_pct, "cash_buffer": cash_buffer,
        "investable": investable, "max_position_pct": cap_pct, "cap": cap, "cap_by": cap_by,
        "min_order_value": min_order, "positions": positions, "invested": invested,
        "idle": round(investable - invested, 2), "dropped": dropped,
    }


# ---------------------------------------------------------------- orders

def _num(x):
    x = float(x)
    return str(int(x)) if x == int(x) else "%.2f" % x


def orders_from(result, cfg, product="CNC", source=""):
    """Proposed BUY orders, one per position, in Kite place_order shape (numbers as strings)."""
    product = str(product).upper()
    out = []
    for p in result["positions"]:
        if p["shares"] <= 0:
            continue
        value = p["shares"] * p["price"]
        try:
            est = charges.estimate(product, "BUY", value, cfg.get("charges"))
        except charges.ChargesError as e:
            raise SizeError(str(e))
        why = "%.2f%% of the stock sleeve" % p["weight"]
        if source:
            why = "%s, copying %s" % (why, source)
        if p["capped"]:
            why += "; capped at %s, %s" % (inr(result["cap"]), result["cap_by"])
        out.append({"exchange": "NSE", "tradingsymbol": p["symbol"], "transaction_type": "BUY",
                    "quantity": str(int(p["shares"])), "product": product, "order_type": "LIMIT",
                    "price": "%.2f" % p["price"], "validity": "DAY", "variety": "regular",
                    "est_value": "%.2f" % value, "est_charges": "%.2f" % est["total"], "why": why})
    return out


def write_orders(path, orders, source="", now=None):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    doc = {
        "created_by": "trader-budget",
        "created_at": (now or datetime.datetime.now(IST)).replace(microsecond=0).isoformat(),
        "status": "proposed",
        "live": True,
        "note": ("Proposals only. Every order is a LIVE order with real money. Nothing is placed until "
                 "trader-risk passes each order and you say yes to it in the chat."),
        "source": source,
        "orders": orders,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")


# ---------------------------------------------------------------- report

def report(result, orders, source=""):
    r = result
    lines = []
    if source:
        lines.append("Copying: %s" % source)
    lines.append("Budget %s, cash buffer %s%% = %s, investing %s, cap %s per stock (%s)"
                 % (inr(r["budget"]), _num(r["cash_buffer_pct"]), inr(r["cash_buffer"]),
                    inr(r["investable"]), inr(r["cap"]), r["cap_by"]))
    lines.append("")
    lines.append("%-12s %-22s %8s %12s %7s %14s  note" % ("symbol", "name", "weight", "price", "shares", "rupees"))
    for p in r["positions"]:
        row = "%-12s %-22s %7.2f%% %12s %7d %14s" % (p["symbol"], (p["name"] or "")[:22], p["weight"],
                                                     inr(p["price"]), p["shares"], inr(p["rupees"]))
        if p["capped"]:
            row += "  capped at %s" % inr(r["cap"])
        lines.append(row)
    for label, v in (("invested", r["invested"]), ("cash buffer", r["cash_buffer"]), ("left idle", r["idle"])):
        lines.append("%-12s %-22s %8s %12s %7s %14s" % ("", label, "", "", "", inr(v)))
    if r["idle"] >= 1:
        lines.append("")
        lines.append("Left idle %s: whole shares do not divide evenly%s." % (
            inr(r["idle"]), ", and some stocks are at their cap" if any(p["capped"] for p in r["positions"]) else ""))
    for d in r["dropped"]:
        lines.append("Dropped %s: %s" % (d["ticker"], d["reason"]))
    lines.append("")
    lines.append("Proposed LIVE orders (Kite place_order arguments; nothing has been placed):")
    for o in orders:
        lines.append("  %s %s %s, %s, LIMIT %s, est. %s + %s charges" % (
            o["transaction_type"], o["quantity"], o["tradingsymbol"], o["product"], inr(o["price"]),
            inr(o["est_value"]), inr(o["est_charges"])))
    lines.append("")
    lines.append("Next: trader-risk checks every order, then trader-broker asks you yes or no for each one.")
    lines.append("Education and tooling, not financial advice.")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Size positions to your budget in whole NSE shares (trader-budget).")
    ap.add_argument("--targets", default="trader/targets.json", help="target weights (default trader/targets.json)")
    ap.add_argument("--weights", help="inline weights instead of a file: INFY=30,TCS=25")
    ap.add_argument("--config", default="trader/config.json", help="rules (default trader/config.json)")
    ap.add_argument("--budget", type=float, help="override the budget (rupees) in the config")
    ap.add_argument("--top", type=int, help="keep only the N biggest weights")
    ap.add_argument("--product", choices=["CNC", "MIS"], help="CNC delivery (default) or MIS intraday")
    ap.add_argument("--kite-dir", default=kite_snapshot.DIR, help="where the Kite snapshots are")
    ap.add_argument("--now", help="pretend it is this time (ISO; no offset = IST), for the snapshot age")
    ap.add_argument("--write", nargs="?", const="trader/orders.json", metavar="PATH",
                    help="write the proposed orders (default trader/orders.json)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of the table")
    a = ap.parse_args(argv)
    try:
        cfg = load_config(a.config)
        source = ""
        if a.weights:
            rows = parse_weights(weights_from_arg(a.weights))
        else:
            data = read_json(a.targets, "targets file (run trader-copycat, or pass --weights)")
            rows = parse_weights(data)
            if isinstance(data, dict):
                source = data.get("source", "")
        now = None
        if a.now:
            t = datetime.datetime.fromisoformat(a.now.replace("Z", "+00:00"))
            now = t.replace(tzinfo=IST) if t.tzinfo is None else t.astimezone(IST)
        prices = quote_prices(a.kite_dir, now)
        result = size(rows, cfg, a.budget, prices, a.top)
        orders = orders_from(result, cfg, a.product or cfg.get("product", "CNC"), source)
        if a.write:
            write_orders(a.write, orders, source, now)
    except (SizeError, ValueError) as e:
        print("size.py: %s" % e, file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps({"result": result, "orders": orders}, indent=2))
    else:
        print(report(result, orders, source))
        if a.write:
            print("Wrote %d proposed orders to %s" % (len(orders), a.write))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_budget.py -v`
Expected: all 10 tests pass. The example budget gives 6 INFY, 7 RELIANCE, 3 TCS and 6 HDFCBANK, with Rs 38,542.60 invested and Rs 6,457.40 idle.

- [ ] **Step 5: Run the full suite and lint, then commit**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`
Expected: `OK` and `All checks passed!`. The orders `size.py` writes for the example match `tests/fixtures/trader-risk/orders-example.json`, except `source` and `why`: the fixture has no source line.

```bash
git add trader-budget tests/test_budget.py tests/fixtures/trader-budget
git commit -m "Convert trader-budget to whole NSE shares at the Kite price" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 6: trader-broker LIVE tickets for the Kite connector

**Files:**
- Copy (unchanged): `trader-alerts/nse_calendar.py` and `trader-alerts/rupees.py` into `trader-broker/`
- Modify (full rewrite): `trader-broker/ticket.py`, `tests/test_broker.py`
- Delete: `trader-broker/claude_desktop_config.example.json` (Alpaca)

**Interfaces:**
- Consumes:
  - `check.fingerprint` and `check.main` (Task 4); the broker's `fingerprint` must equal the risk check's
  - `nse_calendar.parse_now`, `rupees.inr`
- Produces:
  - Constants: `ticket.KITE_FIELDS`, `ticket.TOOL = "place_order"`, `ticket.RISK_MAX_AGE = 600`
  - Functions: `fingerprint`, `tool_input`, `plain`, `estimate` and `parse_yes`
  - CLI: `show`, `approve`, `decline`, `result` and `log`, all taking `--now` (ISO, IST). `fill` is removed: fills come from Kite's holdings and trades.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_broker.py` with:

```python
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

ticket = load("trader-broker", "ticket")
check = load("trader-risk", "check")

CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
RDIR = os.path.join(FIX, "trader-risk")
ORDERS_PATH = os.path.join(RDIR, "orders-example.json")
KDIR = os.path.join(RDIR, "kite")
INFY = {"exchange": "NSE", "tradingsymbol": "INFY", "transaction_type": "BUY", "quantity": "6", "product": "CNC",
        "order_type": "LIMIT", "price": "1612.50", "validity": "DAY", "variety": "regular",
        "est_value": "9675.00", "est_charges": "11.49", "why": "25.00% of the stock sleeve"}
BATCH = ["INFY", "RELIANCE", "TCS", "HDFCBANK"]


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = ticket.main(argv)
    return code, out.getvalue(), err.getvalue()


class ExplicitYes(unittest.TestCase):
    def yes(self, reply, order=INFY):
        return ticket.parse_yes(reply, order, BATCH)[0]

    def test_plain_yes_counts(self):
        for r in ("yes", "Yes.", "YES", "y", "yes place it", "Yes, buy it", "yes INFY", "yes 6 INFY",
                  "yes 6 shares at 1612.50", "yes 9,675"):
            self.assertTrue(self.yes(r), r)

    def test_anything_else_does_not(self):
        for r in ("", "sure", "ok", "okay", "go", "do it", "yeah", "haan", "absolutely", "send it",
                  "yes to all", "yes, all of them", "yes to the rest", "yes both",
                  "yes TCS", "yes HDFCBANK too", "yes 7", "yes but make it 5", "yes?", "no", "not yes",
                  "yes, wait", "yes if it is under 1600"):
            self.assertFalse(self.yes(r), r)


class TicketShape(unittest.TestCase):
    def test_plain_words_and_tool_input(self):
        self.assertEqual(ticket.plain(INFY), "BUY 6 shares of INFY, limit Rs 1,612.50, delivery (CNC), good for today")
        self.assertEqual(ticket.estimate(INFY), "estimated Rs 9,675 + Rs 11.49 charges = Rs 9,686.49 out")
        sell = dict(INFY, transaction_type="SELL", quantity="1", product="MIS", variety="amo")
        self.assertEqual(ticket.plain(sell),
                         "SELL 1 share of INFY, limit Rs 1,612.50, intraday (MIS), good for today, after-market order")
        self.assertIn("Rs 9,663.51 in", ticket.estimate(sell))
        self.assertEqual(set(ticket.tool_input(INFY)), set(ticket.KITE_FIELDS) - {"trigger_price"})
        self.assertNotIn("est_value", ticket.tool_input(INFY))

    def test_fingerprint_is_shared_with_the_risk_check(self):
        with open(ORDERS_PATH) as fh:
            for o in json.load(fh)["orders"]:
                self.assertEqual(check.fingerprint(o), ticket.fingerprint(o))


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.risk = os.path.join(d, "risk.json")
        self.state = os.path.join(d, "broker.json")
        self.hol = os.path.join(d, "h.json")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, now="2026-10-26T10:01", orders=ORDERS_PATH):
        with redirect_stdout(io.StringIO()):
            return check.main(["--orders", orders, "--config", CFG_PATH, "--kite-dir", KDIR,
                               "--holidays", self.hol, "--now", now, "--out", self.risk])

    def t(self, cmd, *args, now="2026-10-26T10:02", orders=ORDERS_PATH):
        return run([cmd, "--orders", orders, "--risk", self.risk, "--state", self.state, "--now", now] + list(args))

    def test_risk_pass_then_one_yes_then_the_result(self):
        self.assertEqual(self.check(), 0)
        code, text, _ = self.t("show")
        self.assertEqual(code, 0)
        self.assertIn("ORDER 1 of 4: LIVE ORDER, real money, Zerodha Kite", text)
        self.assertIn("READY: trader-risk PASS", text)
        self.assertIn("\"tradingsymbol\": \"INFY\"", text)
        self.assertIn("not financial advice", text)

        code, text, _ = self.t("approve", "--index", "1", "--reply", "yes to all")
        self.assertEqual(code, 1)
        self.assertIn("Not recorded", text)
        code, text, _ = self.t("approve", "--index", "1", "--reply", "yes 6 INFY")
        self.assertEqual(code, 0)
        self.assertIn("place_order", text)
        code, _, err = self.t("approve", "--index", "1", "--reply", "yes")
        self.assertEqual(code, 1)
        self.assertIn("APPROVED by you", err)

        code, text, _ = self.t("result", "--index", "1", "--status", "placed", "--broker-id", "261026000123456")
        self.assertEqual(code, 0)
        code, text, _ = run(["log", "--state", self.state, "--now", "2026-10-26T10:05"])
        self.assertIn("approved  BUY 6 shares of INFY", text)
        self.assertIn("id 261026000123456", text)
        self.assertIn("1 placed today", text)
        with open(self.state) as fh:
            recs = json.load(fh)["orders"]
        self.assertEqual([(r["status"], r["symbol"], r["side"]) for r in recs],
                         [("approved", "INFY", "BUY"), ("placed", "INFY", "BUY")])
        self.assertIs(recs[0]["live"], True)

    def test_an_old_risk_check_is_not_ready(self):
        self.check()
        code, text, _ = self.t("show", "--index", "1", now="2026-10-26T10:12")
        self.assertEqual(code, 1)
        self.assertIn("NOT READY: the risk check is from 2026-10-26T10:01:00+05:30, 11 minutes ago", text)

    def test_a_changed_order_and_a_blocked_order_are_not_ready(self):
        self.check()
        with open(ORDERS_PATH) as fh:
            doc = json.load(fh)
        doc["orders"][0]["quantity"] = "7"
        changed = os.path.join(self.tmp.name, "orders.json")
        with open(changed, "w") as fh:
            json.dump(doc, fh)
        self.assertIn("was not in the last risk check", self.t("show", "--index", "1", orders=changed)[1])
        self.assertEqual(self.check(orders=changed), 1)
        code, text, _ = self.t("show", "--index", "1", "--json", orders=changed)
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED by trader-risk", json.loads(text)["status"])

    def test_result_needs_an_approval_and_decline_records_a_no(self):
        self.check()
        code, _, err = self.t("result", "--index", "2", "--status", "placed")
        self.assertEqual(code, 1)
        self.assertIn("no yes recorded", err)
        code, text, _ = self.t("decline", "--index", "2")
        self.assertEqual(code, 0)
        self.assertIn("Nothing was sent", text)
        self.assertIn("DONE: declined", self.t("show", "--index", "2")[1])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_broker.py -v`
Expected: errors and failures, for example `AttributeError: ... no attribute 'estimate'`, and the Flow tests failing on `--now`.

- [ ] **Step 3: Implement**

```bash
cp trader-alerts/nse_calendar.py trader-alerts/rupees.py trader-broker/
git rm -q trader-broker/claude_desktop_config.example.json
```

Replace `trader-broker/ticket.py` with:

```python
#!/usr/bin/env python3
"""Order tickets and the decision log for trader-broker. Standard library only.

This tool never talks to a broker and never places anything. Every order in
this pack is a LIVE order with real money on your Zerodha account: Kite has
no paper account. The tool does three things around the one moment that
matters, your yes:

  show      renders each proposed order as a plain-English ticket plus the
            exact arguments Claude will send to the Kite connector's
            place_order tool. An order is READY only if trader-risk passed
            THIS exact order (matched by fingerprint) in the last 10 minutes
            and nobody has decided on it yet.
  approve   records your explicit yes for ONE order, with your reply word for
            word. It refuses "yes to all", "sure", "ok", a yes that names a
            different stock, quantity or price, and any order that is not READY.
  decline   records a no.
  result    records what happened after the Kite connector's approval card:
            placed (with Kite's order id), denied, or failed.
  log       prints today's decisions.

    python3 ticket.py show                    # every order, READY or not
    python3 ticket.py show --index 1 --json   # one ticket as JSON
    python3 ticket.py approve --index 1 --reply "yes"
    python3 ticket.py result --index 1 --status placed --broker-id 261026000123456
    python3 ticket.py log

Everything is written to trader/state/broker.json (append only). Fills and
holdings come from Kite itself (holdings and trades), not from this log.
"""

import argparse
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import nse_calendar
from rupees import inr

KITE_FIELDS = ("exchange", "tradingsymbol", "transaction_type", "quantity", "product", "order_type",
               "price", "trigger_price", "validity", "variety")
TOOL = "place_order"  # the Kite connector's order tool
PRODUCT_WORDS = {"CNC": "delivery (CNC)", "MIS": "intraday (MIS)"}
RISK_MAX_AGE = 600  # seconds: an older risk check has stale prices behind it
YES_WORDS = ("yes", "y")
BATCH_WORDS = {"all", "every", "everything", "rest", "remaining", "them", "both", "batch", "each"}
DOUBT_WORDS = {"no", "not", "dont", "don't", "wait", "cancel", "stop", "but", "maybe", "later",
               "hold", "unless", "if"}


class TicketError(Exception):
    pass


# ---------------------------------------------------------------- files

def read_json(path, what, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise TicketError("no %s at %s" % (what, path))
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise TicketError("%s is not valid JSON: %s" % (path, e))


def write_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def rec_day(rec):
    """The trading day a decision belongs to: its "date", else the day of "at"."""
    return str(rec.get("date") or str(rec.get("at", ""))[:10])


# ---------------------------------------------------------------- the order

def fingerprint(order):
    """Same function as trader-risk/check.py: identifies the exact order."""
    core = {k: order[k] for k in KITE_FIELDS if k in order and order[k] is not None}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def tool_input(order):
    """The exact arguments for the Kite connector's place_order tool: Kite's parameter names, as written."""
    return {k: order[k] for k in KITE_FIELDS if k in order and order[k] is not None}


def plain(order):
    """BUY 6 shares of INFY, limit Rs 1,612.50, delivery (CNC), good for today"""
    side = str(order.get("transaction_type", "")).upper()
    q = str(order.get("quantity"))
    what = "%s share%s of %s" % (q, "" if q == "1" else "s", order.get("tradingsymbol", "?"))
    if str(order.get("order_type", "")).upper() == "LIMIT":
        how = "limit %s" % inr(order.get("price"))
    else:
        how = "at market"
    product = PRODUCT_WORDS.get(str(order.get("product", "")).upper(), str(order.get("product")))
    text = "%s %s, %s, %s, good for today" % (side, what, how, product)
    if str(order.get("variety", "regular")).lower() == "amo":
        text += ", after-market order"
    return text


def estimate(order):
    """'estimated Rs 9,675 + Rs 11.49 charges = Rs 9,686.49 out' (a sale: proceeds less charges)."""
    try:
        value, cost = float(order["est_value"]), float(order.get("est_charges") or 0)
    except (KeyError, TypeError, ValueError):
        return ""
    if str(order.get("transaction_type", "")).upper() == "SELL":
        return "estimated %s - %s charges = %s in" % (inr(value), inr(cost), inr(value - cost))
    return "estimated %s + %s charges = %s out" % (inr(value), inr(cost), inr(value + cost))


def amount_numbers(order):
    nums = []
    for k in ("quantity", "price", "est_value"):
        try:
            nums.append(float(order[k]))
        except (KeyError, TypeError, ValueError):
            pass
    return nums


def parse_yes(reply, order, batch_symbols=()):
    """Is this reply an explicit yes for THIS one order? Returns (ok, why)."""
    raw = (reply or "").strip()
    if not raw:
        return False, "the reply is empty"
    if "?" in raw:
        return False, "the reply is a question, not a yes"
    words = re.findall(r"[a-z']+", raw.lower())
    if not words or words[0] not in YES_WORDS:
        return False, "only a reply that starts with \"yes\" counts (not ok, sure, go, do it)"
    if BATCH_WORDS & set(words):
        return False, "a yes covers one order at a time, not a batch"
    if DOUBT_WORDS & set(words[1:]):
        return False, "the reply has a condition or a doubt in it; ask again"
    sym = str(order.get("tradingsymbol", "")).upper()
    tokens = set(re.findall(r"[A-Z][A-Z0-9&\-]{1,19}", raw.upper()))
    others = {str(s).upper() for s in batch_symbols} - {sym}
    named = tokens & others
    if named:
        return False, "the reply names %s, but this order is for %s" % (", ".join(sorted(named)), sym)
    nums = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", raw)]
    if nums:
        want = amount_numbers(order)
        if not any(abs(n - w) < 0.005 for n in nums for w in want):
            return False, "the reply says %s, but this order is %s" % (
                ", ".join("%g" % n for n in nums), plain(order))
    return True, "explicit yes for %s" % plain(order)


# ---------------------------------------------------------------- state

def load_state(path):
    return read_json(path, "broker state", required=False) or {"orders": []}


def latest(state, fp, today):
    """The latest decision recorded today for this fingerprint, or None."""
    found = None
    for rec in state.get("orders", []):
        if rec.get("fingerprint") == fp and rec_day(rec) == today:
            found = rec
    return found


def risk_verdict(risk, fp, now):
    if not risk:
        return None, "trader-risk has not checked these orders (run check.py)"
    try:
        checked = nse_calendar.parse_now(risk.get("checked_at"))
    except nse_calendar.CalendarError:
        checked = None
    if not risk.get("checked_at") or checked is None:
        return None, "the risk check has no time on it; run check.py again"
    age = (now - checked).total_seconds()
    if age > RISK_MAX_AGE or age < -60:
        return None, "the risk check is from %s, %d minutes ago; prices move, run check.py again" % (
            risk["checked_at"], age // 60)
    for r in risk.get("results", []):
        if r.get("fingerprint") == fp:
            return r, None
    return None, "this exact order was not in the last risk check (it changed or is new); run check.py again"


def status_of(order, risk, state, now):
    """(ready, label, risk_result)"""
    fp = fingerprint(order)
    rv, why = risk_verdict(risk, fp, now)
    if rv is None:
        return False, "NOT READY: " + why, None
    if rv.get("verdict") != "PASS":
        return False, "BLOCKED by trader-risk: " + "; ".join(rv.get("reasons", [])), rv
    rec = latest(state, fp, now.date().isoformat())
    if rec:
        st = rec.get("status")
        if st == "approved":
            return False, "APPROVED by you at %s, waiting for the %s call" % (rec.get("at"), TOOL), rv
        return False, "DONE: %s at %s" % (st, rec.get("at")), rv
    return True, "READY: trader-risk PASS, waiting for your yes", rv


# ---------------------------------------------------------------- rendering

def render(order, idx, total, risk, state, now):
    ready, label, rv = status_of(order, risk, state, now)
    lines = ["ORDER %d of %d: LIVE ORDER, real money, Zerodha Kite" % (idx, total), "  " + plain(order)]
    est = estimate(order)
    if est:
        lines.append("  " + est)
    if order.get("why"):
        lines.append("  why: " + order["why"])
    lines.append("  " + label)
    for w in (rv or {}).get("warnings", []):
        lines.append("  note: " + w)
    lines.append("  Claude will call the Kite connector's %s tool with exactly:" % TOOL)
    for line in json.dumps(tool_input(order), indent=2).splitlines():
        lines.append("    " + line)
    if ready:
        lines.append("  Reply \"yes\" to place this one order, or \"no\" to skip it.")
        lines.append("  The Kite connector's own approval card then asks again: approve places it, deny stops it.")
    return "\n".join(lines), ready


def ticket_json(order, idx, risk, state, now):
    ready, label, rv = status_of(order, risk, state, now)
    return {"index": idx, "ready": ready, "status": label, "plain": plain(order), "estimate": estimate(order),
            "fingerprint": fingerprint(order), "live": True, "broker": "kite", "tool": TOOL,
            "tool_input": tool_input(order), "why": order.get("why", "")}


# ---------------------------------------------------------------- commands

def _load(a):
    doc = read_json(a.orders, "orders file (run trader-budget first)")
    orders = doc.get("orders", doc) if isinstance(doc, dict) else doc
    if not isinstance(orders, list) or not orders:
        raise TicketError("no orders in %s" % a.orders)
    risk = read_json(a.risk, "risk check", required=False)
    state = load_state(a.state)
    try:
        now = nse_calendar.parse_now(a.now)
    except nse_calendar.CalendarError as e:
        raise TicketError(str(e))
    return orders, risk, state, now


def _pick(orders, index):
    if index is None:
        raise TicketError("say which order: --index N")
    if not 1 <= index <= len(orders):
        raise TicketError("there is no order %d (there are %d)" % (index, len(orders)))
    return orders[index - 1]


def _record(order, index, now, status, **extra):
    rec = {"at": now.replace(microsecond=0).isoformat(), "date": now.date().isoformat(), "index": index,
           "fingerprint": fingerprint(order), "symbol": str(order.get("tradingsymbol", "")).upper(),
           "side": str(order.get("transaction_type", "")).upper(), "plain": plain(order), "status": status}
    rec.update(extra)
    return rec


def cmd_show(a):
    orders, risk, state, now = _load(a)
    picks = [(a.index, _pick(orders, a.index))] if a.index else list(enumerate(orders, 1))
    if a.json:
        out = [ticket_json(o, i, risk, state, now) for i, o in picks]
        print(json.dumps(out[0] if a.index else out, indent=2))
        return 0 if any(t["ready"] for t in out) else 1
    blocks, any_ready = [], False
    for i, o in picks:
        text, ready = render(o, i, len(orders), risk, state, now)
        blocks.append(text)
        any_ready = any_ready or ready
    print("\n\n".join(blocks))
    print("\nOne order at a time: a yes covers one ticket, never the batch. Education and tooling, "
          "not financial advice.")
    return 0 if any_ready else 1


def cmd_approve(a):
    orders, risk, state, now = _load(a)
    order = _pick(orders, a.index)
    ready, label, rv = status_of(order, risk, state, now)
    if not ready:
        raise TicketError("order %d is not ready: %s" % (a.index, label))
    ok, why = parse_yes(a.reply, order, [o.get("tradingsymbol", "") for o in orders])
    if not ok:
        print("Not recorded: %s. Ask the user again with the ticket for order %d." % (why, a.index))
        return 1
    state.setdefault("orders", []).append(_record(order, a.index, now, "approved", reply=a.reply, live=True,
                                                  broker="kite"))
    write_json(a.state, state)
    print("Recorded your yes for order %d: %s." % (a.index, plain(order)))
    print("Now call the Kite connector's %s tool with exactly:" % TOOL)
    print(json.dumps(tool_input(order), indent=2))
    print("The connector's approval card asks again. Then: ticket.py result --index %d --status "
          "placed|denied|failed --broker-id <Kite order id>" % a.index)
    return 0


def cmd_decline(a):
    orders, risk, state, now = _load(a)
    order = _pick(orders, a.index)
    state.setdefault("orders", []).append(_record(order, a.index, now, "declined", reply=a.reply or "no"))
    write_json(a.state, state)
    print("Recorded: you said no to order %d (%s). Nothing was sent." % (a.index, plain(order)))
    return 0


def cmd_result(a):
    orders, risk, state, now = _load(a)
    order = _pick(orders, a.index)
    rec = latest(state, fingerprint(order), now.date().isoformat())
    if not rec or rec.get("status") != "approved":
        raise TicketError("order %d has no yes recorded today; a result can only follow an approval" % a.index)
    extra = {}
    if a.broker_id:
        extra["broker_order_id"] = a.broker_id
    if a.note:
        extra["note"] = a.note
    state["orders"].append(_record(order, a.index, now, a.status, **extra))
    write_json(a.state, state)
    print("Recorded order %d as %s." % (a.index, a.status))
    if a.status == "placed":
        print("Kite's holdings and trades are the record of the fill: refresh those snapshots before the next check.")
    return 0


def cmd_log(a):
    state = load_state(a.state)
    try:
        today = nse_calendar.parse_now(a.now).date().isoformat()
    except nse_calendar.CalendarError as e:
        raise TicketError(str(e))
    rows = [r for r in state.get("orders", []) if a.all or rec_day(r) == today]
    if not rows:
        print("No decisions recorded%s." % ("" if a.all else " today"))
        return 1
    for r in rows:
        extra = (" id " + r["broker_order_id"]) if r.get("broker_order_id") else ""
        reply = (' reply "%s"' % r["reply"]) if r.get("reply") and r["status"] in ("approved", "declined") else ""
        print("%s  #%s %-9s %s%s%s" % (r.get("at"), r.get("index"), r.get("status"), r.get("plain"), reply, extra))
    placed = sum(1 for r in rows if r.get("status") == "placed")
    print("%d placed%s." % (placed, "" if a.all else " today"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="LIVE order tickets and your yes (trader-broker). Never places orders.")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--orders", default="trader/orders.json")
        p.add_argument("--risk", default="trader/state/risk.json")
        p.add_argument("--state", default="trader/state/broker.json")
        p.add_argument("--now", help="pretend it is this time (ISO; no offset = IST)")

    p = sub.add_parser("show", help="render the tickets")
    common(p)
    p.add_argument("--index", type=int)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("approve", help="record the user's explicit yes for one order")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--reply", required=True, help="the user's reply, word for word")
    p = sub.add_parser("decline", help="record a no")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--reply")
    p = sub.add_parser("result", help="record what happened after the Kite approval card")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--status", required=True, choices=["placed", "denied", "failed"])
    p.add_argument("--broker-id", help="Kite's order id")
    p.add_argument("--note")
    p = sub.add_parser("log", help="today's decisions")
    p.add_argument("--state", default="trader/state/broker.json")
    p.add_argument("--now")
    p.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"show": cmd_show, "approve": cmd_approve, "decline": cmd_decline, "result": cmd_result,
                "log": cmd_log}[a.cmd](a)
    except TicketError as e:
        print("ticket.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_broker.py -v`
Expected: all 8 tests pass.

- [ ] **Step 5: Run the full suite and lint, then commit**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`

```bash
git add -A trader-broker tests/test_broker.py
git commit -m "Convert trader-broker to LIVE Kite place_order tickets" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 7: Docs for the order path, and an end-to-end smoke test

**Files:**
- Modify (full rewrite): `trader-budget/SKILL.md`, `trader-risk/SKILL.md`, `trader-broker/SKILL.md`
- Modify: `README.md` (three table rows, one example line, two layout lines), `CLAUDE.md`, `tests/test_repo.py`

- [ ] **Step 1: Write the failing repo test**

Add to `class Repo` in `tests/test_repo.py`, before `def test_every_imported_helper_is_in_the_same_skill(self):`:

```python
    def test_converted_order_path_skills_say_live(self):
        for s in ("trader-budget", "trader-risk", "trader-broker"):
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            low = " ".join(text.lower().split())
            self.assertIn("live", low, s)
            self.assertIn("real money", low, s)
            self.assertNotIn("alpaca", low, s)
            self.assertNotIn("paper trading", low, s)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m unittest discover -s tests -p test_repo.py -v`
Expected: `test_converted_order_path_skills_say_live` FAILS with `'real money' not found` for trader-budget.

- [ ] **Step 3: Rewrite the three SKILL.md files**

`trader-budget/SKILL.md`:

````markdown
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
````

`trader-risk/SKILL.md`:

````markdown
---
name: trader-risk
description: >-
  Risk Manager for LIVE NSE orders. Checks every proposed order against your
  limits and fresh Kite data before it can reach the broker, and blocks
  anything over them: market hours and NSE holidays, the price against the
  last price and the circuit band, max and min order value, cash and the cash
  buffer, max position percent, delivery sales of shares you do not hold,
  intraday (MIS) cutoff, exposure and daily loss stop, MARKET orders, F&O,
  duplicates and a daily order limit. Prints PASS or BLOCK with the reason
  for each order and records the verdicts so trader-broker only shows an
  order that passed. Use when the user says "check my orders", "is this
  safe", "risk check", "does this break my rules", "can I place this", or
  before /trader-broker, always.
argument-hint: "[path to orders.json]"
---

# trader-risk

The Risk Manager is the gate between a proposal and the broker. Every order
written by trader-budget passes through it. A BLOCK is final for that order:
it does not go to the user for a yes, and it does not go to the broker.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"                    # trader/ files, records the verdicts
python3 "${CLAUDE_SKILL_DIR}/check.py" --json
python3 "${CLAUDE_SKILL_DIR}/check.py" --no-write         # look without recording
python3 "${CLAUDE_SKILL_DIR}/kite_snapshot.py" show       # how old each Kite snapshot is
```

## Fresh Kite data first

Right before every check, call the Kite connector and save each answer with
`kite_snapshot.py save <kind> --from <file>`:

| kind | Kite call | used for |
| --- | --- | --- |
| `quotes` | quotes for every symbol in the orders | price, circuit band, order value |
| `holdings` | holdings | position size, delivery sales |
| `positions` | positions | intraday exposure and the daily loss stop |
| `margins` | margins | available cash and equity margin |
| `orders` | the day's orders | the daily order limit |

Quotes older than 120 seconds and the others older than 10 minutes are
refused, and any rule that needs a refused snapshot BLOCKS the order.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders |
| `trader/config.json` | your limits (`trader-budget/config.example.json`) |
| `trader/kite/*.json` | the Kite snapshots above |
| `trader/state/risk.json` | the verdicts with a fingerprint of each order |

## The checks

- format: a bare NSE symbol, BUY or SELL, whole shares, LIMIT (or MARKET if
  allowed), DAY validity, regular (or amo if allowed). No SL or SL-M.
- product: CNC delivery, or MIS intraday only when `allow_mis` is true.
- hours: 09:15 to 15:30 IST on NSE trading days; a year without a loaded
  holiday list blocks too.
- price: within `max_limit_deviation_pct` of the last price and inside the
  circuit band.
- size, cash, buffer and position limits, with charges counted.
- short: no delivery sale beyond what you hold; no MIS short unless allowed.
- intraday: no new MIS positions after `mis_cutoff`, exposure capped, a
  daily loss stop.
- duplicates and `max_orders_per_day`, counting Kite's order book.

## Steps

1. Refresh the five Kite snapshots.
2. Run `check.py`. Show every BLOCK with its reasons in plain words.
3. If something is blocked, help the user fix the order or decide to change
   their own rule. Never loosen a rule for them.
4. When every order the user wants passed, hand over to `/trader-broker`
   within 10 minutes; after that the check must run again.

## Example

The four example orders from trader-budget (6 INFY, 7 RELIANCE, 3 TCS,
6 HDFCBANK) on an account with Rs 60,000 cash at 10:01 IST on a trading day
all PASS, leaving Rs 21,411.62 cash. A fifth order the same day hits the
five-a-day limit; at 16:00 every order is blocked because NSE is closed.

## What it never does

It never places an order, never skips a rule because data is missing, and
never changes the user's limits.

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

`trader-broker/SKILL.md`:

````markdown
---
name: trader-broker
description: >-
  Order Executor for Zerodha Kite. Places APPROVED orders through the Kite
  connector, one at a time, and never without your explicit yes. Shows each
  order as a plain ticket marked LIVE ORDER, real money, with the estimated
  cost and the exact arguments for the Kite connector's place_order tool,
  records your yes word for word, then the connector's own approval card asks
  again. Covers connecting the Kite connector in Claude and setting its order
  tool to "Needs approval". Use when the user says "place the orders", "buy
  it", "execute", "send it to Zerodha", "connect Kite", or after
  /trader-risk passes.
argument-hint: "[order number]"
---

# trader-broker

The Order Executor is the one place where an order can leave this pack, and
it only ever does it for one order, after one yes. The script never talks to
Kite: Claude makes the call through the Kite connector, and the connector's
approval card is the last human check.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show                     # every ticket, READY or not
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show --index 1 --json
python3 "${CLAUDE_SKILL_DIR}/ticket.py" approve --index 1 --reply "yes"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" decline --index 2
python3 "${CLAUDE_SKILL_DIR}/ticket.py" result --index 1 --status placed --broker-id 261026000123456
python3 "${CLAUDE_SKILL_DIR}/ticket.py" log
```

## Setup: the Kite connector

1. In Claude, open Customize > Connectors and connect Zerodha Kite. Log in
   to Zerodha in the window it opens. The login stays in the connector.
2. In the connector's tool permissions, set the order tools (place, modify,
   cancel) to "Needs approval". Read tools such as quotes, holdings and
   positions can stay allowed.
3. If the user says the order tool is set to "Always allow", stop and ask
   them to change it before any order. Never place an order without that card.

## Steps, for each order

1. Run `ticket.py show --index N`. Only a READY ticket can go further: risk
   passed this exact order in the last 10 minutes and nobody decided on it.
2. Show the ticket in the chat: LIVE ORDER, real money, the plain sentence,
   the estimated cost, why.
3. Ask for a yes for that one order. Record the reply word for word with
   `ticket.py approve --index N --reply "<reply>"`. A reply that is not an
   explicit yes for this order is not recorded: ask again.
4. Call the Kite connector's `place_order` tool with exactly the arguments
   the ticket printed. The connector's card asks the user again.
5. Record what happened: `ticket.py result --index N --status placed
   --broker-id <Kite order id>`, or `denied`, or `failed` with `--note`.
6. Move to the next order. Never batch: one yes covers one order.

## What counts as a yes

"yes", "Yes, buy it", "yes 6 INFY" count. "ok", "sure", "haan", "yes to
all", "yes TCS" for an INFY ticket, a different quantity or price, a
question or a yes with a condition do not.

## Example

After trader-risk passes the four example orders, ticket 1 reads "BUY 6
shares of INFY, limit Rs 1,612.50, delivery (CNC), good for today",
estimated Rs 9,675 + Rs 11.49 charges = Rs 9,686.49 out. The user says
"yes", Claude records it, calls place_order, the user approves the card, and
`result` records Kite's order id.

## What it never does

It never places an order itself, never sends an order that is not READY,
never treats one yes as covering several orders, and never sends anything
but the exact arguments on the ticket.

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

- [ ] **Step 4: Update README.md and CLAUDE.md**

In `README.md`, replace these lines (one per bullet):

- `| `/trader-budget` | Budget Manager | Sizes every position to your budget, keeps a cash buffer and caps any one stock. |`

  with:

  `| `/trader-budget` | Budget Manager | Sizes every position to your rupee budget in whole NSE shares at the Kite price, keeps a cash buffer, caps any one stock and estimates Zerodha's charges. |`

- `| `/trader-risk` | Risk Manager | Checks every proposed order against your limits and blocks anything over them. |`

  with:

  `| `/trader-risk` | Risk Manager | Checks every LIVE order against your limits and fresh Kite data (hours, price band, cash, intraday rules) and blocks anything over them. |`

- `| `/trader-broker` | Order Executor | Turns an approved order into the exact ticket your brokerage connector receives, and records your yes. It never places anything itself. |`

  with:

  `| `/trader-broker` | Order Executor | Turns an approved order into the exact ticket the Kite connector receives, marked LIVE, and records your yes. It never places anything itself. |`

- `python3 trader-budget/size.py --budget 5000 --write                    # -> trader/orders.json`

  with:

  `python3 trader-budget/size.py --budget 50000 --write                   # -> trader/orders.json`

- `trader-budget/     SKILL.md, size.py, config.example.json, targets.example.json`

  with:

  `trader-budget/     SKILL.md, size.py, charges.py, config.example.json, targets.example.json`

- `trader-broker/     SKILL.md, ticket.py, claude_desktop_config.example.json`

  with:

  `trader-broker/     SKILL.md, ticket.py`


In `CLAUDE.md`:

- Replace the line `- `trader-budget/config.example.json` must keep `"paper": true` and options off.` with:

  - `trader-budget/config.example.json` must keep `allow_mis`, `allow_short`, `allow_market_orders` and `allow_amo` false, `max_order_value` at Rs 10,000 or less, and no `"paper"` key (`test_live_defaults_are_cautious`).

- Replace `- Order amounts are strings (Alpaca `notional` format).` with:

  - Order quantities and prices are strings, in Kite `place_order` field names.

- Replace gate 3 and the paragraph after it (from `3. The broker MCP tool's` through `never in chat, code or `trader/`.`) with:

  3. The Kite connector's order tool set to "Needs approval", so its card asks once more.

  Kite has no paper account: every order is LIVE, real money. `ticket.py` also refuses a risk check older than 10 minutes. The defaults are cautious (max order Rs 10,000, five orders a day, LIMIT only; MIS, MARKET, shorts and after-market orders off) and F&O, NRML and stop-loss orders are never supported. Never bypass a gate, auto-approve or loosen a limit for the user. Kite logins belong only in the connector, never in chat, code or `trader/`.

- In the first bullet under "## Scope and fork notes", replace the text from `trader-alerts is converted` through `are copied` with:

  Converted so far: trader-alerts (NSE clock, Kite quotes) and the order path, trader-budget, trader-risk and trader-broker (Kite place_order shape, rupees, whole shares). The other skills are still US until their phase lands; their docs may still mention `ticket.py fill` or Alpaca. The shared helpers (`kite_snapshot.py`, `nse.py`, `nse_calendar.py`, `nse_symbols.py`, `rupees.py`) are copied


- [ ] **Step 5: Run the full suite, lint and the em-dash check**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache . && ! grep -rl "$(printf '\342\200\224')" trader-* tests docs CLAUDE.md README.md`
Expected: `OK`, `All checks passed!`, and no file names printed.

- [ ] **Step 6: Smoke-test the CLI end to end, outside the repo**

```bash
R=/home/ubuntu/stock-market/trader-skill; T=$(mktemp -d) && cd "$T" && mkdir trader
cp "$R/trader-budget/config.example.json" trader/config.json
cp "$R/trader-budget/targets.example.json" trader/targets.json
cp -r "$R/tests/fixtures/trader-risk/kite" trader/kite
python3 "$R/trader-budget/size.py" --now 2026-10-26T10:01 --write
python3 "$R/trader-risk/check.py" --now 2026-10-26T10:01; echo "check exit $?"
python3 "$R/trader-broker/ticket.py" show --index 1 --now 2026-10-26T10:02; echo "show exit $?"
python3 "$R/trader-broker/ticket.py" approve --index 1 --reply "yes" --now 2026-10-26T10:02
```

Expected:
- `size.py` writes 4 orders.
- `check.py` prints 4 PASS lines, "Cash after the passed orders: Rs 21,411.62. LIVE account, real money.", and exits 0.
- `ticket.py show` prints "ORDER 1 of 4: LIVE ORDER, real money, Zerodha Kite" and "READY", and exits 0.
- `approve` records the yes and prints the `place_order` arguments.

Report the output in the task summary.

- [ ] **Step 6b (only after Task 1): a live dry run with real Kite data, no order**

1. Refresh the five snapshots from the Kite connector into a temp `trader/kite/`, using `kite_snapshot.py save <kind> --from <file>`.
2. Size one share of a cheap NSE stock, then run `check.py` and `ticket.py show --index 1`.
3. **Stop at the ticket.** Do not approve it or call `place_order` unless the user explicitly asks to place that order.
4. Report whether the real snapshots pass through without data errors.

- [ ] **Step 7: Commit**

```bash
git add trader-budget/SKILL.md trader-risk/SKILL.md trader-broker/SKILL.md README.md CLAUDE.md tests/test_repo.py
git commit -m "Document the Indian order path; repo test that converted order-path skills say LIVE" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

