# India Phase 1 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared Indian-market building blocks (Kite snapshots, NSE client, NSE calendar, NSE symbol list) and fully convert trader-alerts to NSE hours and Kite quotes.

**Architecture:**
- Four small standard-library helper modules live in `trader-alerts/`: `kite_snapshot.py`, `nse.py`, `nse_calendar.py` and `nse_symbols.py`. Later phases copy them byte-for-byte into other skills, and a repo test keeps the copies identical.
- `alerts.py` is rewritten on top of these helpers. It reads prices only from `trader/kite/quotes.json`, which Claude saves from the Kite connector.
- `alerts.py` keeps writing `trader/prices.json` in the same `{"prices": {SYM: float}}` shape, so the skills that have not been converted yet still read it.

**Tech Stack:** Python 3.8+, standard library only, `unittest` with offline fixtures.

**Spec:** `docs/superpowers/specs/2026-10-26-indian-market-design.md` (sections 2, 3.1, 3.2, 5 and 9, phase 1)

**Branch:** work on `feat/india-phase1`, branched from `feat/india-design`.

## Global Constraints

- Python 3.8 or newer, standard library only. No `zoneinfo` (3.9+), no `str.removeprefix`, no `list[str]` hints.
- No em dashes (U+2014) in any .md, .py, .json, .csv, .txt or .xml file (`tests/test_repo.py`).
- Times are IST, a fixed `+05:30` offset (`datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")`).
- Money is shown with Indian grouping, as in `Rs 1,25,000`.
- Tests are fully offline. Fixtures go in `tests/fixtures/trader-alerts/`, and outputs go in temp dirs.
- Never run a tool from the repo root. It would create `trader/`, which breaks `test_root_matches_the_reel`.
- Helper modules carry the docstring line "Keep the copies identical: tests/test_repo.py checks."
- Every SKILL.md keeps `name: <folder>`, frontmatter over 200 chars and a body over 60 lines. trader-alerts is an order-path skill, so it must also contain "not financial advice" and "yes".
- Commit messages end with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full suite: `python3 -m unittest discover -s tests -v`. One file: `python3 -m unittest discover -s tests -p test_nse.py -v`. Lint: `ruff check --select F,E9 --target-version py38 .`

## Review Focus

1. A rule watches a symbol that is not in the Kite quotes snapshot: report it as an error naming `NSE:<SYM>` to add to the quotes call, never skip it silently. Covered by the Task 6 test `test_snapshot_quotes_and_missing_symbols`.
2. A snapshot whose `fetched_at` is in the future (clock skew): refuse it, never treat it as fresh. Covered by the Task 2 test `test_future`.
3. NSE answers 200 with an HTML block page: raise `NseBlocked` with the `--file` hint and do not cache the page. Covered by the Task 3 test `test_block_page_with_200_is_blocked_and_not_cached`.
4. A date in a year with no NSE holiday list yet (2027 until NSE publishes it): set `calendar_known: false` and have `clock` print how to refresh. Covered by Task 4 `test_unknown_year` and Task 6 `test_clock`.
5. Symbol spellings `infy`, `INFY.NS`, `nse:infy` and `m&m` must give the same key everywhere: rules, prices.json and Kite keys. Covered by Task 5 `test_forms` and Task 6 `test_a_day_of_alerts` (adds `infy.ns`).

---

### Task 1: Confirm the Kite connector tools and shapes

This task is manual and gates every later task. It needs the user to log in to Kite. Do not save real holdings, positions or margins to the repo, because they are the user's private data.

**Files:**
- Create: `docs/superpowers/notes/2026-10-26-kite-connector.md`

- [ ] **Step 1: Log in to the connector**

Load the tools: `ToolSearch` with query `+kite`. Then call `mcp__claude_ai_kite__authenticate`. The user completes the Zerodha login in the browser, then call `mcp__claude_ai_kite__complete_authentication` if the flow asks for it. If login fails, stop and tell the user.

- [ ] **Step 2: List the tools**

Run `ToolSearch` with query `+kite` again (max_results 30) and write down every tool's name and parameters.

- [ ] **Step 3: Call each read tool once and compare the field names**

Call the quotes tool for `NSE:INFY`, `NSE:RELIANCE` and `NSE:M&M`, then the positions, holdings and margins tools. Check that the answers use these names. Later tasks depend on them:

| Answer | Fields the code reads |
|---|---|
| quotes | keyed `"NSE:INFY"`; `last_price`, `ohlc.open/high/low/close` (close = previous close), `upper_circuit_limit`, `lower_circuit_limit`, `last_trade_time`, `timestamp` |
| positions | `{"net": [...], "day": [...]}`, each row has `tradingsymbol`, `exchange`, `product` (`CNC`/`MIS`), `quantity` |
| holdings | list of rows with `tradingsymbol`, `exchange`, `isin`, `quantity`, `t1_quantity`, `average_price`, `last_price` |
| margins | `equity.net`, `equity.available.cash`, `equity.available.live_balance`, `equity.utilised` |

Also note whether the answer comes bare or wrapped as `{"status": "success", "data": ...}`, and whether it comes as JSON text.

- [ ] **Step 4: Write the notes**

Create `docs/superpowers/notes/2026-10-26-kite-connector.md`:
- a table of every tool (name, purpose, parameters)
- the place-order tool's name and parameters (phase 2 needs them)
- for each answer above: "matches" or the exact differences
- the wrapping form

Use field names and made-up values only. No real account data.

- [ ] **Step 5: Gate**

If every field matches, continue. If any field differs, stop: update `kite_snapshot.quotes()` in Task 2, `mis_positions()` in Task 7 and the fixtures in Tasks 2 and 6 to the real names, and tell the user before continuing.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/notes/2026-10-26-kite-connector.md
git commit -m "Record Kite connector tools and answer shapes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `kite_snapshot.py`, stamped Kite snapshots

**Files:**
- Create: `trader-alerts/kite_snapshot.py`
- Create: `tests/fixtures/trader-alerts/kite/quotes-raw.json`
- Test: `tests/test_kite_snapshot.py`

**Interfaces:**
- Produces:
  - `IST`, `DIR = "trader/kite"`, and `MAX_AGE = {"quotes": 120, "holdings": 600, "positions": 600, "margins": 600, "trades": 600}`
  - `class SnapshotError(Exception)`
  - `now_ist() -> datetime` (aware)
  - `unwrap(raw) -> data`
  - `save(kind, raw, d=DIR, now=None) -> path`
  - `load(kind, d=DIR, now=None, max_age=None) -> data`
  - `age(kind, d=DIR, now=None) -> float or None`
  - `quotes(data) -> {SYM: {"symbol", "exchange", "price", "prev_close", "open", "high", "low", "upper_circuit", "lower_circuit", "time"}}`
  - `main(argv) -> int`
  - Quote values are floats or None, and `time` is a string. NSE symbols are keyed bare (`"INFY"`); other exchanges keep `"BSE:INFY"`.

- [ ] **Step 1: Write the fixture**

`tests/fixtures/trader-alerts/kite/quotes-raw.json` (made-up values in the Kite quote shape):

```json
{
  "status": "success",
  "data": {
    "NSE:INFY": {"instrument_token": 408065, "timestamp": "2026-10-26 15:29:58", "last_trade_time": "2026-10-26 15:29:57", "last_price": 1612.5, "last_quantity": 3, "volume": 5123456, "average_price": 1605.2, "net_change": 0, "lower_circuit_limit": 1451.25, "upper_circuit_limit": 1773.75, "ohlc": {"open": 1598.0, "high": 1620.0, "low": 1590.1, "close": 1590.0}},
    "NSE:RELIANCE": {"instrument_token": 738561, "timestamp": "2026-10-26 15:29:59", "last_trade_time": "2026-10-26 15:29:58", "last_price": 1402.3, "last_quantity": 10, "volume": 8123000, "average_price": 1408.75, "net_change": 0, "lower_circuit_limit": 1274.95, "upper_circuit_limit": 1558.25, "ohlc": {"open": 1415.0, "high": 1419.9, "low": 1398.0, "close": 1416.6}},
    "NSE:M&M": {"instrument_token": 519937, "timestamp": "2026-10-26 15:29:59", "last_trade_time": "2026-10-26 15:29:55", "last_price": 3250.0, "last_quantity": 1, "volume": 1450000, "average_price": 3231.4, "net_change": 0, "lower_circuit_limit": 2880.0, "upper_circuit_limit": 3520.0, "ohlc": {"open": 3205.0, "high": 3262.0, "low": 3198.5, "close": 3200.0}}
  }
}
```

- [ ] **Step 2: Write the failing tests**

`tests/test_kite_snapshot.py`:

```python
import datetime
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

ks = load("trader-alerts", "kite_snapshot")

KDIR = os.path.join(FIX, "trader-alerts", "kite")
T0 = datetime.datetime(2026, 10, 26, 15, 29, 0, tzinfo=ks.IST)
SEC = datetime.timedelta(seconds=1)


def raw(name):
    with open(os.path.join(KDIR, name)) as fh:
        return json.load(fh)


class Save(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_stamps_and_unwraps(self):
        p = ks.save("quotes", raw("quotes-raw.json"), self.d, now=T0)
        with open(p) as fh:
            doc = json.load(fh)
        self.assertEqual(doc["fetched_at"], "2026-10-26T15:29:00+05:30")
        self.assertIn("NSE:INFY", doc["data"])
        self.assertNotIn("status", doc["data"])

    def test_bare_answer_is_kept(self):
        ks.save("positions", {"net": [], "day": []}, self.d, now=T0)
        self.assertEqual(ks.load("positions", self.d, now=T0), {"net": [], "day": []})

    def test_kite_error_is_refused(self):
        with self.assertRaises(ks.SnapshotError) as c:
            ks.save("quotes", {"status": "error", "message": "Incorrect api_key or access_token."}, self.d)
        self.assertIn("access_token", str(c.exception))

    def test_unknown_kind(self):
        with self.assertRaises(ks.SnapshotError):
            ks.save("orders", {}, self.d)


class Load(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        ks.save("quotes", raw("quotes-raw.json"), self.d, now=T0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh(self):
        self.assertIn("NSE:INFY", ks.load("quotes", self.d, now=T0 + 120 * SEC))

    def test_stale(self):
        with self.assertRaises(ks.SnapshotError) as c:
            ks.load("quotes", self.d, now=T0 + 121 * SEC)
        self.assertIn("121 s old", str(c.exception))
        self.assertIn("kite_snapshot.py save quotes", str(c.exception))

    def test_max_age_override(self):
        self.assertIn("NSE:INFY", ks.load("quotes", self.d, now=T0 + 500 * SEC, max_age=600))

    def test_missing(self):
        with self.assertRaises(ks.SnapshotError) as c:
            ks.load("margins", self.d, now=T0)
        self.assertIn("no margins snapshot", str(c.exception))

    def test_future(self):
        with self.assertRaises(ks.SnapshotError) as c:
            ks.load("quotes", self.d, now=T0 - 61 * SEC)
        self.assertIn("future", str(c.exception))

    def test_not_a_snapshot(self):
        with open(os.path.join(self.d, "quotes.json"), "w") as fh:
            json.dump({"NSE:INFY": {}}, fh)
        with self.assertRaises(ks.SnapshotError) as c:
            ks.load("quotes", self.d, now=T0)
        self.assertIn("not a snapshot", str(c.exception))


class Quotes(unittest.TestCase):
    def test_normalised(self):
        q = ks.quotes(ks.unwrap(raw("quotes-raw.json")))
        self.assertEqual(sorted(q), ["INFY", "M&M", "RELIANCE"])
        i = q["INFY"]
        self.assertEqual((i["price"], i["prev_close"], i["open"]), (1612.5, 1590.0, 1598.0))
        self.assertEqual((i["upper_circuit"], i["lower_circuit"]), (1773.75, 1451.25))
        self.assertEqual(i["time"], "2026-10-26 15:29:57")
        self.assertEqual(i["exchange"], "NSE")

    def test_ltp_only_and_other_exchanges(self):
        q = ks.quotes({"BSE:INFY": {"last_price": 1611}, "NSE:TCS": {"last_price": "3050.5"},
                       "NSE:BAD": {"last_price": None}})
        self.assertEqual(sorted(q), ["BSE:INFY", "TCS"])
        self.assertEqual(q["TCS"]["price"], 3050.5)
        self.assertIsNone(q["TCS"]["prev_close"])


class Cli(unittest.TestCase):
    def test_save_and_show(self):
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                code = ks.main(["save", "quotes", "--from", os.path.join(KDIR, "quotes-raw.json"), "--dir", d])
            self.assertEqual(code, 0)
            out = io.StringIO()
            with redirect_stdout(out):
                ks.main(["show", "--dir", d])
            self.assertRegex(out.getvalue(), r"quotes\s+\d+ s old")
            self.assertRegex(out.getvalue(), r"margins\s+none")

    def test_save_rejects_non_json(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.txt")
            with open(bad, "w") as fh:
                fh.write("Kite says hi")
            err = io.StringIO()
            with redirect_stderr(err):
                code = ks.main(["save", "quotes", "--from", bad, "--dir", d])
            self.assertEqual(code, 1)
            self.assertIn("not JSON", err.getvalue())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_kite_snapshot.py -v`
Expected: an ERROR, because `trader-alerts/kite_snapshot.py` does not exist (FileNotFoundError from `_load`).

- [ ] **Step 4: Write `trader-alerts/kite_snapshot.py`**

```python
#!/usr/bin/env python3
"""Kite snapshots for the trader skills. Standard library only.

The scripts cannot call the Kite connector, so Claude does: it calls the
connector, then saves the raw answer here. This script stamps the time it was
saved, and every reader refuses a snapshot that is too old.

    python3 kite_snapshot.py save quotes --from raw.json    # or pipe the JSON on stdin
    python3 kite_snapshot.py save positions --from raw.json
    python3 kite_snapshot.py show                           # age of every snapshot

Each file is trader/kite/<kind>.json:
    {"fetched_at": "2026-10-26T15:29:00+05:30", "data": <the Kite answer>}

How old a snapshot may be before a reader refuses it: quotes 120 s;
holdings, positions, margins and trades 600 s.

This file is copied into every skill that reads Kite data. Keep the copies
identical: tests/test_repo.py checks.
"""

import argparse
import datetime
import json
import os
import sys

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
DIR = os.path.join("trader", "kite")
MAX_AGE = {"quotes": 120, "holdings": 600, "positions": 600, "margins": 600, "trades": 600}
SKEW = 60  # seconds a snapshot may look "from the future" before the clock is suspect


class SnapshotError(Exception):
    pass


def now_ist():
    return datetime.datetime.now(IST).replace(microsecond=0)


def _kind(kind):
    if kind not in MAX_AGE:
        raise SnapshotError("unknown snapshot kind %r (one of %s)" % (kind, ", ".join(sorted(MAX_AGE))))
    return kind


def unwrap(raw):
    """The Kite answer without the REST envelope {"status": ..., "data": ...}."""
    if isinstance(raw, dict) and "status" in raw:
        if raw.get("status") != "success" or "data" not in raw:
            raise SnapshotError("Kite answered %s: %s" % (raw.get("status"), raw.get("message", "no message")))
        return raw["data"]
    return raw


def path(kind, d=DIR):
    return os.path.join(d, _kind(kind) + ".json")


def save(kind, raw, d=DIR, now=None):
    p = path(kind, d)
    doc = {"fetched_at": (now or now_ist()).isoformat(), "data": unwrap(raw)}
    os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    return p


def _read(kind, d):
    p = path(kind, d)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
    except ValueError as e:
        raise SnapshotError("%s is not valid JSON: %s" % (p, e))
    if not isinstance(doc, dict) or "fetched_at" not in doc or "data" not in doc:
        raise SnapshotError("%s is not a snapshot: save it with kite_snapshot.py save %s" % (p, kind))
    return doc


def _fetched(doc, kind):
    try:
        t = datetime.datetime.fromisoformat(doc["fetched_at"])
    except (TypeError, ValueError):
        raise SnapshotError("the %s snapshot has a bad fetched_at: %r" % (kind, doc.get("fetched_at")))
    if t.tzinfo is None:
        raise SnapshotError("the %s snapshot's fetched_at has no UTC offset" % kind)
    return t


def age(kind, d=DIR, now=None):
    """Seconds since the snapshot was saved, or None if there is none."""
    doc = _read(kind, d)
    if doc is None:
        return None
    return ((now or now_ist()) - _fetched(doc, kind)).total_seconds()


def load(kind, d=DIR, now=None, max_age=None):
    """The Kite answer saved for kind. Refuses a missing, stale or future snapshot."""
    doc = _read(kind, d)
    if doc is None:
        raise SnapshotError("no %s snapshot in %s: call the Kite connector for %s, then "
                            "kite_snapshot.py save %s" % (kind, d, kind, kind))
    secs = ((now or now_ist()) - _fetched(doc, kind)).total_seconds()
    limit = MAX_AGE[kind] if max_age is None else max_age
    if secs < -SKEW:
        raise SnapshotError("the %s snapshot is from the future (%s): check this computer's clock"
                            % (kind, doc["fetched_at"]))
    if secs > limit:
        raise SnapshotError("the %s snapshot is %d s old (limit %d s): refresh it with the Kite connector "
                            "and kite_snapshot.py save %s" % (kind, secs, limit, kind))
    return doc["data"]


def _f(x):
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def quotes(data):
    """Kite quotes {"NSE:INFY": {...}} -> {"INFY": {symbol, exchange, price, prev_close, open, high,
    low, upper_circuit, lower_circuit, time}}. NSE symbols are keyed bare, others as EXCH:SYM."""
    out = {}
    for key, q in (data or {}).items():
        if not isinstance(q, dict) or _f(q.get("last_price")) is None:
            continue
        exch, sym = key.split(":", 1) if ":" in key else ("NSE", key)
        ohlc = q.get("ohlc") or {}
        out[sym if exch == "NSE" else key] = {
            "symbol": sym, "exchange": exch, "price": _f(q["last_price"]),
            "prev_close": _f(ohlc.get("close")), "open": _f(ohlc.get("open")),
            "high": _f(ohlc.get("high")), "low": _f(ohlc.get("low")),
            "upper_circuit": _f(q.get("upper_circuit_limit")),
            "lower_circuit": _f(q.get("lower_circuit_limit")),
            "time": str(q.get("last_trade_time") or q.get("timestamp") or "")}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Save and inspect Kite snapshots (trader skills).")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("save", help="stamp and save a raw Kite answer")
    p.add_argument("kind", choices=sorted(MAX_AGE))
    p.add_argument("--from", dest="src", help="file with the raw JSON (default: stdin)")
    p.add_argument("--dir", default=DIR)
    p = sub.add_parser("show", help="how old is each snapshot?")
    p.add_argument("--dir", default=DIR)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        if a.cmd == "save":
            if a.src:
                with open(a.src, encoding="utf-8-sig") as fh:
                    text = fh.read()
            else:
                text = sys.stdin.read()
            try:
                raw = json.loads(text)
            except ValueError as e:
                raise SnapshotError("that is not JSON: %s" % e)
            print("Saved %s." % save(a.kind, raw, a.dir))
            return 0
        for kind in sorted(MAX_AGE):
            secs = age(kind, a.dir)
            if secs is None:
                print("%-10s none" % kind)
            else:
                print("%-10s %5d s old%s" % (kind, secs, "  (stale)" if secs > MAX_AGE[kind] else ""))
        return 0
    except (SnapshotError, OSError) as e:
        print("kite_snapshot.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_kite_snapshot.py -v`
Expected: all 14 tests pass.

- [ ] **Step 6: Run the full suite and lint**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 .`
Expected: `OK` and `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add trader-alerts/kite_snapshot.py tests/test_kite_snapshot.py tests/fixtures/trader-alerts/kite/quotes-raw.json
git commit -m "Add kite_snapshot: stamped, age-checked Kite snapshots" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `nse.py`, NSE client with cookie, cache and block handling

**Files:**
- Create: `trader-alerts/nse.py`
- Test: `tests/test_nse.py`

**Interfaces:**
- Produces:
  - `HOME`, `UA`, `PAUSE = 1.0`, `BLOCK_CODES = (401, 403, 429, 503)` and `CACHE = "trader/cache/nse"`
  - `class NseError(Exception)` and `class NseBlocked(NseError)`, with `.url`; the message contains "--file"
  - `read_file(path) -> str` and `read_json_file(path) -> obj`
  - `Client(cache=CACHE, opener=None, pause=PAUSE, sleep=time.sleep, today=None)`, with `.get_text(url, cookie=True) -> str`, `.get_json(url) -> obj` and `._cache_path(url) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/test_nse.py`:

```python
import io
import os
import tempfile
import unittest
import urllib.error

from _load import load

nse = load("trader-alerts", "nse")

API = "https://www.nseindia.com/api/holiday-master?type=trading"


class FakeOpener:
    """Answers by URL: a str is the body, an int is an HTTP error code, an Exception is raised."""

    def __init__(self, answers):
        self.answers = answers
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        a = self.answers.get(req.full_url, 404)
        if isinstance(a, Exception):
            raise a
        if isinstance(a, int):
            raise urllib.error.HTTPError(req.full_url, a, "error", {}, None)
        return io.BytesIO(a.encode("utf-8"))


class Client(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sleeps = []

    def tearDown(self):
        self.tmp.cleanup()

    def client(self, answers):
        self.op = FakeOpener(answers)
        return nse.Client(cache=self.tmp.name, opener=self.op, sleep=self.sleeps.append, today="2026-10-26")

    def test_warms_up_then_asks_with_browser_headers(self):
        c = self.client({nse.HOME: 403, API: '{"CM": []}'})
        self.assertEqual(c.get_json(API), {"CM": []})
        self.assertEqual([r.full_url for r in self.op.requests], [nse.HOME, API])
        req = self.op.requests[1]
        self.assertIn("Mozilla", req.get_header("User-agent"))
        self.assertEqual(req.get_header("Referer"), nse.HOME)
        self.assertEqual(self.sleeps, [nse.PAUSE])

    def test_cached_answer_is_not_asked_again(self):
        c = self.client({nse.HOME: "<html>", API: '{"CM": []}'})
        c.get_json(API)
        c.get_json(API)
        self.assertEqual(len(self.op.requests), 2)
        c2 = self.client({})
        self.assertEqual(c2.get_json(API), {"CM": []})
        self.assertEqual(self.op.requests, [])

    def test_blocked_codes_name_the_url_and_the_file_fallback(self):
        for code in (401, 403, 429, 503):
            c = self.client({nse.HOME: "<html>", API: code})
            with self.assertRaises(nse.NseBlocked) as e:
                c.get_json(API)
            self.assertEqual(e.exception.url, API)
            self.assertIn("--file", str(e.exception))
            self.assertIn("HTTP %d" % code, str(e.exception))

    def test_block_page_with_200_is_blocked_and_not_cached(self):
        c = self.client({nse.HOME: "<html>", API: "<html>Access Denied</html>"})
        with self.assertRaises(nse.NseBlocked):
            c.get_json(API)
        self.assertFalse(os.path.exists(c._cache_path(API)))

    def test_other_errors_are_not_blocks(self):
        c = self.client({nse.HOME: "<html>", API: 500})
        with self.assertRaises(nse.NseError) as e:
            c.get_json(API)
        self.assertNotIsInstance(e.exception, nse.NseBlocked)
        c = self.client({nse.HOME: "<html>", API: urllib.error.URLError("no network")})
        with self.assertRaises(nse.NseError) as e:
            c.get_json(API)
        self.assertIn("could not reach www.nseindia.com", str(e.exception))

    def test_no_cookie_for_archives(self):
        url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        c = self.client({url: "SYMBOL\n"})
        self.assertEqual(c.get_text(url, cookie=False), "SYMBOL\n")
        self.assertEqual([r.full_url for r in self.op.requests], [url])


class Files(unittest.TestCase):
    def test_read_json_file(self):
        with tempfile.TemporaryDirectory() as d:
            good = os.path.join(d, "good.json")
            with open(good, "w", encoding="utf-8-sig") as fh:
                fh.write('{"a": 1}')
            self.assertEqual(nse.read_json_file(good), {"a": 1})
            bad = os.path.join(d, "bad.json")
            with open(bad, "w") as fh:
                fh.write("nope")
            with self.assertRaises(nse.NseError) as e:
                nse.read_json_file(bad)
            self.assertIn("is not JSON", str(e.exception))
            with self.assertRaises(nse.NseError) as e:
                nse.read_file(os.path.join(d, "missing.json"))
            self.assertIn("cannot read", str(e.exception))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_nse.py -v`
Expected: an ERROR, because `trader-alerts/nse.py` does not exist.

- [ ] **Step 3: Write `trader-alerts/nse.py`**

```python
#!/usr/bin/env python3
"""NSE website access for the trader skills. Standard library only.

NSE answers scripts only with a session cookie from one of its pages and a
browser User-Agent, and it still blocks often. So every caller also takes
--file: when a fetch raises NseBlocked, open the address it names in a
browser, save what it shows, and run again with --file <saved file>.

Answers are cached per day in trader/cache/nse/<date>/ so a rerun does not
ask NSE again, and requests are at least PAUSE seconds apart.

This file is copied into every skill that reads NSE. Keep the copies
identical: tests/test_repo.py checks.
"""

import datetime
import hashlib
import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.request

HOME = "https://www.nseindia.com/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
PAUSE = 1.0
BLOCK_CODES = (401, 403, 429, 503)
CACHE = os.path.join("trader", "cache", "nse")


class NseError(Exception):
    pass


class NseBlocked(NseError):
    def __init__(self, url, why):
        self.url = url
        NseError.__init__(self, "NSE blocked %s (%s). Open that address in a browser, save the page "
                                "as a file, and run again with --file <saved file>." % (url, why))


def read_file(path):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return fh.read()
    except OSError as e:
        raise NseError("cannot read %s: %s" % (path, e.strerror))


def read_json_file(path):
    try:
        return json.loads(read_file(path))
    except ValueError as e:
        raise NseError("%s is not JSON: %s" % (path, e))


class Client:
    def __init__(self, cache=CACHE, opener=None, pause=PAUSE, sleep=time.sleep, today=None):
        self.cache = cache
        self.pause = pause
        self.sleep = sleep
        self.today = today or datetime.date.today().isoformat()
        self._opener = opener
        self._warm = False
        self._calls = 0

    def _open(self, url, accept):
        if self._opener is None:
            jar = http.cookiejar.CookieJar()
            self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        if self._calls and self.pause:
            self.sleep(self.pause)
        self._calls += 1
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Referer": HOME,
                                                   "Accept-Language": "en-IN,en;q=0.9"})
        try:
            with self._opener.open(req, timeout=20) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in BLOCK_CODES:
                raise NseBlocked(url, "HTTP %d" % e.code)
            raise NseError("%s answered HTTP %d" % (url, e.code))
        except urllib.error.URLError as e:
            raise NseError("could not reach %s: %s" % (url.split("/")[2], e.reason))

    def _cache_path(self, url):
        name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".txt"
        return os.path.join(self.cache, self.today, name)

    def get_text(self, url, cookie=True):
        p = self._cache_path(url)
        if os.path.exists(p):
            return read_file(p)
        if cookie and not self._warm:
            self._warm = True
            try:
                self._open(HOME, "text/html")  # sets the cookie even when it answers 403
            except NseError:
                pass
        text = self._open(url, "application/json,text/csv,*/*")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return text

    def get_json(self, url):
        text = self.get_text(url)
        try:
            return json.loads(text)
        except ValueError:
            os.remove(self._cache_path(url))
            raise NseBlocked(url, "the answer was not JSON, probably a block page")
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_nse.py -v`
Expected: all 7 tests pass.

- [ ] **Step 5: Run the full suite and lint**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 .`
Expected: `OK` and `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add trader-alerts/nse.py tests/test_nse.py
git commit -m "Add nse client: cookie warm-up, daily cache, --file fallback on blocks" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `nse_calendar.py`, IST clock and NSE holidays

**Files:**
- Create: `trader-alerts/nse_calendar.py`
- Create: `tests/fixtures/trader-alerts/nse-holiday-master.json`
- Test: `tests/test_nse_calendar.py`

**Interfaces:**
- Produces:
  - Constants: `IST`, `PRE_OPEN` 09:00, `OPEN` 09:15, `CLOSE` 15:30, `SQUARE_OFF` 15:20, `URL`, `CACHE = "trader/cache/nse/holidays.json"`, `HOLIDAYS` (`{"YYYY-MM-DD": name}`) and `YEARS = (2026,)`
  - `class CalendarError(Exception)`
  - `parse_now(text=None) -> aware IST datetime`
  - `parse_holiday_master(doc) -> {iso: name}`
  - `save_holidays(holidays, path=CACHE) -> [years]`
  - `load_holidays(path=CACHE) -> (holidays, set(years))`
  - `Calendar(holidays=None, years=None)`, with `.known(d)`, `.trading_day(d) -> (bool, reason)` and `.next_open(now) -> aware datetime or None`
  - `.status(now) -> dict` with the keys `now_ist` ("YYYY-MM-DD HH:MM"), `date`, `weekday`, `calendar_known`, `open`, `phase` (`"open"`/`"pre_open"`/`"closed"`) and `reason`. On a trading day it also has `opens`, `closes` and `mis_square_off`, and when the market is not open it has `next_open`.

- [ ] **Step 1: Write the fixture**

`tests/fixtures/trader-alerts/nse-holiday-master.json` holds the CM part of `https://www.nseindia.com/api/holiday-master?type=trading` as read on 2026-10-26:

```json
{"CM": [
  {"tradingDate": "15-Jan-2026", "weekDay": "Thursday", "description": "Municipal Corporation Election - Maharashtra", "morning_session": null, "evening_session": null, "Sr_no": 1},
  {"tradingDate": "26-Jan-2026", "weekDay": "Monday", "description": "Republic Day", "morning_session": null, "evening_session": null, "Sr_no": 2},
  {"tradingDate": "15-Feb-2026", "weekDay": "Sunday", "description": "Mahashivratri", "morning_session": null, "evening_session": null, "Sr_no": 3},
  {"tradingDate": "03-Mar-2026", "weekDay": "Tuesday", "description": "Holi", "morning_session": null, "evening_session": null, "Sr_no": 4},
  {"tradingDate": "21-Mar-2026", "weekDay": "Saturday", "description": "Id-Ul-Fitr (Ramadan Eid)", "morning_session": null, "evening_session": null, "Sr_no": 5},
  {"tradingDate": "26-Mar-2026", "weekDay": "Thursday", "description": "Shri Ram Navami", "morning_session": null, "evening_session": null, "Sr_no": 6},
  {"tradingDate": "31-Mar-2026", "weekDay": "Tuesday", "description": "Shri Mahavir Jayanti", "morning_session": null, "evening_session": null, "Sr_no": 7},
  {"tradingDate": "03-Apr-2026", "weekDay": "Friday", "description": "Good Friday", "morning_session": null, "evening_session": null, "Sr_no": 8},
  {"tradingDate": "14-Apr-2026", "weekDay": "Tuesday", "description": "Dr. Baba Saheb Ambedkar Jayanti", "morning_session": null, "evening_session": null, "Sr_no": 9},
  {"tradingDate": "01-May-2026", "weekDay": "Friday", "description": "Maharashtra Day", "morning_session": null, "evening_session": null, "Sr_no": 10},
  {"tradingDate": "28-May-2026", "weekDay": "Thursday", "description": "Bakri Id", "morning_session": null, "evening_session": null, "Sr_no": 11},
  {"tradingDate": "26-Jun-2026", "weekDay": "Friday", "description": "Muharram", "morning_session": null, "evening_session": null, "Sr_no": 12},
  {"tradingDate": "15-Aug-2026", "weekDay": "Saturday", "description": "Independence Day", "morning_session": null, "evening_session": null, "Sr_no": 13},
  {"tradingDate": "14-Sep-2026", "weekDay": "Monday", "description": "Ganesh Chaturthi", "morning_session": null, "evening_session": null, "Sr_no": 14},
  {"tradingDate": "02-Oct-2026", "weekDay": "Friday", "description": "Mahatma Gandhi Jayanti", "morning_session": null, "evening_session": null, "Sr_no": 15},
  {"tradingDate": "20-Oct-2026", "weekDay": "Tuesday", "description": "Dussehra", "morning_session": null, "evening_session": null, "Sr_no": 16},
  {"tradingDate": "08-Nov-2026", "weekDay": "Sunday", "description": "Diwali Laxmi Pujan*", "morning_session": null, "evening_session": null, "Sr_no": 17},
  {"tradingDate": "10-Nov-2026", "weekDay": "Tuesday", "description": "Diwali-Balipratipada", "morning_session": null, "evening_session": null, "Sr_no": 18},
  {"tradingDate": "24-Nov-2026", "weekDay": "Tuesday", "description": "Prakash Gurpurb Sri Guru Nanak Dev", "morning_session": null, "evening_session": null, "Sr_no": 19},
  {"tradingDate": "25-Dec-2026", "weekDay": "Friday", "description": "Christmas", "morning_session": null, "evening_session": null, "Sr_no": 20}
]}
```

- [ ] **Step 2: Write the failing tests**

`tests/test_nse_calendar.py`:

```python
import datetime
import json
import os
import tempfile
import unittest

from _load import load, FIX

cal = load("trader-alerts", "nse_calendar")

MASTER = os.path.join(FIX, "trader-alerts", "nse-holiday-master.json")


def ist(text):
    return cal.parse_now(text)


def hm(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


class Time(unittest.TestCase):
    def test_parse_now(self):
        t = ist("2026-10-26T09:15")
        self.assertEqual(t.utcoffset(), datetime.timedelta(hours=5, minutes=30))
        self.assertEqual(hm(t), "2026-10-26 09:15")
        self.assertEqual(ist("2026-10-26T03:45:00Z"), t)
        self.assertEqual(hm(ist("2026-10-26T00:00:00-04:00")), "2026-10-26 09:30")
        self.assertIsNotNone(cal.parse_now().tzinfo)
        with self.assertRaises(cal.CalendarError):
            ist("tomorrow")


class Holidays(unittest.TestCase):
    def test_bundled_list_matches_the_nse_master(self):
        with open(MASTER) as fh:
            self.assertEqual(cal.parse_holiday_master(json.load(fh)), cal.HOLIDAYS)
        self.assertEqual(cal.HOLIDAYS["2026-11-08"], "Diwali Laxmi Pujan")

    def test_bad_master(self):
        with self.assertRaises(cal.CalendarError):
            cal.parse_holiday_master({"FO": []})
        with self.assertRaises(cal.CalendarError):
            cal.parse_holiday_master({"CM": [{"tradingDate": "2026-01-26"}]})

    def test_cache_replaces_its_years_and_adds_new_ones(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "holidays.json")
            years = cal.save_holidays({"2026-12-25": "Christmas", "2027-01-26": "Republic Day"}, p)
            self.assertEqual(years, [2026, 2027])
            h, y = cal.load_holidays(p)
            self.assertEqual(y, {2026, 2027})
            self.assertNotIn("2026-10-02", h)
            self.assertEqual(h["2027-01-26"], "Republic Day")

    def test_no_cache_is_the_bundled_list(self):
        with tempfile.TemporaryDirectory() as d:
            h, y = cal.load_holidays(os.path.join(d, "missing.json"))
        self.assertEqual(h, cal.HOLIDAYS)
        self.assertEqual(y, {2026})

    def test_broken_cache(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "holidays.json")
            with open(p, "w") as fh:
                fh.write("[]")
            with self.assertRaises(cal.CalendarError) as e:
                cal.load_holidays(p)
            self.assertIn("holidays refresh", str(e.exception))


class Status(unittest.TestCase):
    def setUp(self):
        self.c = cal.Calendar(dict(cal.HOLIDAYS), cal.YEARS)

    def st(self, text):
        return self.c.status(ist(text))

    def test_a_normal_day(self):
        st = self.st("2026-10-26T10:00")
        self.assertTrue(st["open"])
        self.assertEqual(st["phase"], "open")
        self.assertEqual((st["opens"], st["closes"], st["mis_square_off"]), ("09:15", "15:30", "15:20"))
        self.assertNotIn("next_open", st)
        pre = self.st("2026-10-26T09:05")
        self.assertFalse(pre["open"])
        self.assertEqual(pre["phase"], "pre_open")
        self.assertEqual(pre["next_open"], "2026-10-26 09:15")
        early = self.st("2026-10-26T08:59")
        self.assertEqual(early["reason"], "before the open")
        self.assertEqual(early["next_open"], "2026-10-26 09:15")
        self.assertTrue(self.st("2026-10-26T15:29")["open"])
        after = self.st("2026-10-26T15:30")
        self.assertFalse(after["open"])
        self.assertEqual(after["reason"], "after the close")
        self.assertEqual(after["next_open"], "2026-10-27 09:15")

    def test_holidays_and_weekends(self):
        diwali = self.st("2026-11-10T10:00")
        self.assertFalse(diwali["open"])
        self.assertIn("Diwali-Balipratipada", diwali["reason"])
        self.assertEqual(diwali["next_open"], "2026-11-11 09:15")
        self.assertEqual(self.st("2026-12-25T10:00")["next_open"], "2026-12-28 09:15")
        self.assertEqual(self.st("2026-11-08T18:00")["reason"], "weekend")
        self.assertEqual(self.st("2026-10-24T10:00")["reason"], "weekend")
        self.assertNotIn("opens", self.st("2026-10-24T10:00"))

    def test_unknown_year(self):
        st = self.st("2027-01-04T10:00")
        self.assertFalse(st["calendar_known"])
        self.assertTrue(st["open"])
        self.assertTrue(self.st("2026-06-01T10:00")["calendar_known"])

    def test_next_open_over_a_long_weekend(self):
        self.assertEqual(hm(self.c.next_open(ist("2026-04-02T16:00"))), "2026-04-06 09:15")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_nse_calendar.py -v`
Expected: an ERROR, because `trader-alerts/nse_calendar.py` does not exist.

- [ ] **Step 4: Write `trader-alerts/nse_calendar.py`**

```python
#!/usr/bin/env python3
"""NSE trading calendar in IST for the trader skills. Standard library only.

Pre-open 09:00 to 09:15, normal session 09:15 to 15:30 IST, Monday to
Friday, minus NSE trading holidays. Zerodha squares MIS (intraday)
positions off from about 15:20.

India has no daylight saving time, so a fixed +05:30 offset is exact.

Holidays: HOLIDAYS below is NSE's capital-market list for 2026 as published
by https://www.nseindia.com/api/holiday-master?type=trading (read
2026-10-26). save_holidays() caches a newer list (alerts.py holidays
refresh) and load_holidays() merges it in, replacing the bundled years it
covers. A year in neither is unknown, and status() then says
calendar_known false.

Special sessions (Muhurat trading on Diwali) are not modelled: the clock says
closed on those days.

This file is copied into every skill that needs the market clock. Keep the
copies identical: tests/test_repo.py checks.
"""

import datetime
import json
import os

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
PRE_OPEN = datetime.time(9, 0)
OPEN = datetime.time(9, 15)
CLOSE = datetime.time(15, 30)
SQUARE_OFF = datetime.time(15, 20)
URL = "https://www.nseindia.com/api/holiday-master?type=trading"
CACHE = os.path.join("trader", "cache", "nse", "holidays.json")

HOLIDAYS = {
    "2026-01-15": "Municipal Corporation Election - Maharashtra",
    "2026-01-26": "Republic Day",
    "2026-02-15": "Mahashivratri",
    "2026-03-03": "Holi",
    "2026-03-21": "Id-Ul-Fitr (Ramadan Eid)",
    "2026-03-26": "Shri Ram Navami",
    "2026-03-31": "Shri Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-08-15": "Independence Day",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali Laxmi Pujan",
    "2026-11-10": "Diwali-Balipratipada",
    "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas",
}
YEARS = (2026,)


class CalendarError(Exception):
    pass


def parse_now(text=None):
    """ISO time -> aware IST datetime. No offset means IST. None means now."""
    if not text:
        return datetime.datetime.now(IST).replace(microsecond=0)
    try:
        t = datetime.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        raise CalendarError("--now wants an ISO time like 2026-10-26T09:20 (IST) or ...Z (UTC)")
    return t.replace(tzinfo=IST) if t.tzinfo is None else t.astimezone(IST)


def parse_holiday_master(doc):
    """NSE holiday-master JSON -> {"YYYY-MM-DD": name} for the capital market (CM)."""
    rows = doc.get("CM") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        raise CalendarError("not an NSE holiday master: no CM list")
    out = {}
    for r in rows:
        try:
            d = datetime.datetime.strptime(r["tradingDate"], "%d-%b-%Y").date()
        except (KeyError, TypeError, ValueError):
            raise CalendarError("bad holiday row: %r" % (r,))
        out[d.isoformat()] = str(r.get("description", "")).strip().rstrip("*").strip()
    return out


def save_holidays(holidays, path=CACHE):
    years = sorted({int(d[:4]) for d in holidays})
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"source": URL, "years": years, "holidays": holidays}, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return years


def load_holidays(path=CACHE):
    """(holidays, years known): the bundled list, with any cached years replacing it."""
    holidays, years = dict(HOLIDAYS), set(YEARS)
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            cached = {int(y) for y in doc["years"]}
            holidays = {d: n for d, n in holidays.items() if int(d[:4]) not in cached}
            holidays.update(doc["holidays"])
            years |= cached
        except (ValueError, KeyError, TypeError) as e:
            raise CalendarError("%s is not a holiday cache (%s): run alerts.py holidays refresh" % (path, e))
    return holidays, years


class Calendar:
    def __init__(self, holidays=None, years=None):
        if holidays is None:
            holidays, years = load_holidays()
        self.holidays = holidays
        self.years = set(years if years is not None else YEARS)

    def known(self, d):
        return d.year in self.years

    def trading_day(self, d):
        """(is_trading_day, reason). An unknown year counts every weekday as a trading day."""
        if d.weekday() >= 5:
            return False, "weekend"
        name = self.holidays.get(d.isoformat())
        if name:
            return False, "NSE holiday: " + name
        return True, ""

    def next_open(self, now):
        """The next session open after now (today's if it is before 09:15), aware IST."""
        now = now.astimezone(IST)
        d = now.date()
        if not (self.trading_day(d)[0] and now.time() < OPEN):
            d += datetime.timedelta(days=1)
        for _ in range(15):
            if self.trading_day(d)[0]:
                return datetime.datetime.combine(d, OPEN, tzinfo=IST)
            d += datetime.timedelta(days=1)
        return None

    def status(self, now):
        now = now.astimezone(IST)
        d, t = now.date(), now.time()
        ok, reason = self.trading_day(d)
        st = {"now_ist": now.strftime("%Y-%m-%d %H:%M"), "date": d.isoformat(), "weekday": now.strftime("%A"),
              "calendar_known": self.known(d), "open": False, "phase": "closed", "reason": reason}
        if ok:
            st.update(opens=OPEN.strftime("%H:%M"), closes=CLOSE.strftime("%H:%M"),
                      mis_square_off=SQUARE_OFF.strftime("%H:%M"))
            if OPEN <= t < CLOSE:
                st.update(open=True, phase="open", reason="normal session")
            elif PRE_OPEN <= t < OPEN:
                st.update(phase="pre_open", reason="pre-open session (nothing trades until 09:15)")
            elif t < PRE_OPEN:
                st["reason"] = "before the open"
            else:
                st["reason"] = "after the close"
        if not st["open"]:
            nxt = self.next_open(now)
            if nxt:
                st["next_open"] = nxt.strftime("%Y-%m-%d %H:%M")
        return st
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_nse_calendar.py -v`
Expected: all 10 tests pass.

- [ ] **Step 6: Run the full suite and lint**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 .`
Expected: `OK` and `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add trader-alerts/nse_calendar.py tests/test_nse_calendar.py tests/fixtures/trader-alerts/nse-holiday-master.json
git commit -m "Add nse_calendar: IST session clock and NSE holidays" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `nse_symbols.py`, NSE equity symbol list

The spec (section 2) says a bundled copy of `EQUITY_L.csv`. This plan fetches it into `trader/cache/nse/` instead, with a `--file` fallback, because bundling a 185 KB file into several skill folders bloats the plugin and the copy goes out of date. The user is told about this change at plan review.

**Files:**
- Create: `trader-alerts/nse_symbols.py`
- Create: `tests/fixtures/trader-alerts/EQUITY_L-sample.csv`
- Test: `tests/test_nse_symbols.py`

**Interfaces:**
- Consumes: `nse.read_file`, `nse.Client.get_text(url, cookie=False)`, `nse.NseError` and `nse.NseBlocked` (Task 3)
- Produces:
  - `URL` and `CACHE = "trader/cache/nse/EQUITY_L.csv"`
  - `class SymbolError(Exception)`
  - `normalize(sym) -> "INFY"` and `kite_key(sym) -> "NSE:INFY"`
  - `parse(text) -> {SYM: {"symbol", "name", "series", "isin"}}`
  - `Master(rows)`, with `.rows`, `.lookup(sym) -> row or None` and `.by_isin(isin) -> row or None`
  - `load(path=CACHE) -> Master`
  - `refresh(dest=CACHE, client=None, file=None) -> int`
  - `main(argv) -> int`

- [ ] **Step 1: Write the fixture**

`tests/fixtures/trader-alerts/EQUITY_L-sample.csv`: the real header (note the leading spaces) and seven real rows from NSE's file, read on 2026-10-26:

```
SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE
20MICRONS,20 Microns Limited,EQ,06-OCT-2008,5,1,INE144J01027,5
BAJAJ-AUTO,Bajaj Auto Limited,EQ,26-MAY-2008,10,1,INE917I01010,10
HDFCBANK,HDFC Bank Limited,EQ,08-NOV-1995,1,1,INE040A01034,1
INFY,Infosys Limited,EQ,08-FEB-1995,5,1,INE009A01021,5
M&M,Mahindra & Mahindra Limited,EQ,03-JAN-1996,5,1,INE101A01026,5
RELIANCE,Reliance Industries Limited,EQ,29-NOV-1995,10,1,INE002A01018,10
TCS,Tata Consultancy Services Limited,EQ,25-AUG-2004,1,1,INE467B01029,1
```

- [ ] **Step 2: Write the failing tests**

`tests/test_nse_symbols.py`:

```python
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from _load import load, FIX

sy = load("trader-alerts", "nse_symbols")

SAMPLE = os.path.join(FIX, "trader-alerts", "EQUITY_L-sample.csv")


def sample_text():
    with open(SAMPLE, encoding="utf-8") as fh:
        return fh.read()


class Normalize(unittest.TestCase):
    def test_forms(self):
        for s in ("INFY", "infy", " nse:infy ", "INFY.NS", "NSE:INFY", "infy.ns"):
            self.assertEqual(sy.normalize(s), "INFY", s)
        self.assertEqual(sy.normalize("m&m"), "M&M")
        self.assertEqual(sy.normalize("bajaj-auto"), "BAJAJ-AUTO")
        self.assertEqual(sy.kite_key("m&m.ns"), "NSE:M&M")
        for bad in ("BSE:INFY", "", "  ", None, "NSE:"):
            with self.assertRaises(sy.SymbolError):
                sy.normalize(bad)


class Master(unittest.TestCase):
    def setUp(self):
        self.m = sy.load(SAMPLE)

    def test_lookup_and_isin(self):
        r = self.m.lookup("infy.ns")
        self.assertEqual((r["name"], r["isin"], r["series"]), ("Infosys Limited", "INE009A01021", "EQ"))
        self.assertEqual(self.m.by_isin("ine002a01018")["symbol"], "RELIANCE")
        self.assertIsNone(self.m.lookup("NIFTYBEES"))
        self.assertIsNone(self.m.by_isin("US0378331005"))
        self.assertEqual(len(self.m.rows), 7)

    def test_missing_list(self):
        with self.assertRaises(sy.SymbolError) as e:
            sy.load(os.path.join(tempfile.gettempdir(), "no-such-dir", "EQUITY_L.csv"))
        self.assertIn("refresh", str(e.exception))

    def test_not_a_symbol_list(self):
        for text in ("", "hello\n", "<html>blocked</html>\n"):
            with self.assertRaises(sy.SymbolError):
                sy.parse(text)


class Refresh(unittest.TestCase):
    def test_from_file_and_from_nse(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def get_text(self, url, cookie=True):
                self.calls.append((url, cookie))
                return sample_text()

        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "EQUITY_L.csv")
            self.assertEqual(sy.refresh(dest, file=SAMPLE), 7)
            self.assertEqual(sy.load(dest).lookup("TCS")["isin"], "INE467B01029")
            fc = FakeClient()
            self.assertEqual(sy.refresh(dest, client=fc), 7)
            self.assertEqual(fc.calls, [(sy.URL, False)])

    def test_garbage_keeps_the_old_list(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "EQUITY_L.csv")
            sy.refresh(dest, file=SAMPLE)
            bad = os.path.join(d, "bad.csv")
            with open(bad, "w") as fh:
                fh.write("<html>blocked</html>\n")
            with self.assertRaises(sy.SymbolError):
                sy.refresh(dest, file=bad)
            self.assertEqual(len(sy.load(dest).rows), 7)

    def test_cli_lookup(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = sy.main(["lookup", "infy", "NIFTYBEES", "--list", SAMPLE])
        self.assertEqual(code, 1)
        self.assertIn("Infosys Limited", out.getvalue())
        self.assertRegex(out.getvalue(), r"NIFTYBEES\s+not in NSE's equity list")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_nse_symbols.py -v`
Expected: an ERROR, because `trader-alerts/nse_symbols.py` does not exist.

- [ ] **Step 4: Write `trader-alerts/nse_symbols.py`**

```python
#!/usr/bin/env python3
"""NSE equity symbols for the trader skills. Standard library only.

    python3 nse_symbols.py refresh                     # NSE EQUITY_L.csv -> trader/cache/nse/EQUITY_L.csv
    python3 nse_symbols.py refresh --file EQUITY_L.csv
    python3 nse_symbols.py lookup infy RELIANCE.NS nse:m&m

Source: https://archives.nseindia.com/content/equities/EQUITY_L.csv (every
listed equity with its company name, series and ISIN; no cookie needed).
ETFs are not in it, so lookup() returns None for them and callers treat the
symbol as unverified rather than wrong.

This file is copied into every skill that resolves symbols. Keep the copies
identical: tests/test_repo.py checks.
"""

import argparse
import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import nse

URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
CACHE = os.path.join("trader", "cache", "nse", "EQUITY_L.csv")


class SymbolError(Exception):
    pass


def normalize(sym):
    """'nse:infy', 'INFY.NS', ' infy ' -> 'INFY'. Other exchanges are refused."""
    s = str(sym or "").strip().upper()
    if s.startswith("NSE:"):
        s = s[4:]
    elif ":" in s:
        raise SymbolError("%s: only NSE symbols are supported" % sym)
    if s.endswith(".NS"):
        s = s[:-3]
    if not s:
        raise SymbolError("empty symbol")
    return s


def kite_key(sym):
    return "NSE:" + normalize(sym)


def parse(text):
    """EQUITY_L.csv text -> {SYMBOL: {symbol, name, series, isin}}. Header names carry stray spaces."""
    rows = {}
    for r in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        r = {k.strip().upper(): (v or "").strip() for k, v in r.items() if k is not None}
        sym = r.get("SYMBOL")
        if sym:
            rows[sym] = {"symbol": sym, "name": r.get("NAME OF COMPANY", ""),
                         "series": r.get("SERIES", ""), "isin": r.get("ISIN NUMBER", "")}
    if not rows:
        raise SymbolError("no symbols found: is this NSE's EQUITY_L.csv?")
    return rows


class Master:
    def __init__(self, rows):
        self.rows = rows
        self._isin = {r["isin"]: r for r in rows.values() if r["isin"]}

    def lookup(self, sym):
        return self.rows.get(normalize(sym))

    def by_isin(self, isin):
        return self._isin.get(str(isin or "").strip().upper())


def load(path=CACHE):
    if not os.path.exists(path):
        raise SymbolError("no symbol list at %s: run nse_symbols.py refresh "
                          "(or refresh --file EQUITY_L.csv)" % path)
    return Master(parse(nse.read_file(path)))


def refresh(dest=CACHE, client=None, file=None):
    """Fetch (or read) EQUITY_L.csv, check that it parses, save it to dest. Returns the symbol count."""
    text = nse.read_file(file) if file else (client or nse.Client()).get_text(URL, cookie=False)
    rows = parse(text)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(text)
    return len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description="NSE equity symbols (trader skills).")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("refresh", help="download NSE's equity list")
    p.add_argument("--file", help="an EQUITY_L.csv you saved in a browser")
    p.add_argument("--dest", default=CACHE)
    p = sub.add_parser("lookup", help="check symbols against the list")
    p.add_argument("symbols", nargs="+")
    p.add_argument("--list", default=CACHE)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        if a.cmd == "refresh":
            print("Saved %d NSE symbols to %s." % (refresh(a.dest, file=a.file), a.dest))
            return 0
        m = load(a.list)
        missing = 0
        for s in a.symbols:
            r = m.lookup(s)
            if r:
                print("%-12s %-12s %s  %s" % (s, r["symbol"], r["isin"], r["name"]))
            else:
                missing += 1
                print("%-12s not in NSE's equity list (an ETF, a typo, or delisted)" % s)
        return 1 if missing else 0
    except (SymbolError, nse.NseError) as e:
        print("nse_symbols.py: %s" % e, file=sys.stderr)
        return 2 if isinstance(e, nse.NseBlocked) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_nse_symbols.py -v`
Expected: all 7 tests pass.

- [ ] **Step 6: Run the full suite and lint**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 .`
Expected: `OK` and `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add trader-alerts/nse_symbols.py tests/test_nse_symbols.py tests/fixtures/trader-alerts/EQUITY_L-sample.csv
git commit -m "Add nse_symbols: NSE equity list, normalising and ISIN lookup" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Rewrite `alerts.py` on the NSE clock and Kite quotes

This replaces the NYSE calendar, US daylight-saving code, and Yahoo and Stooq quotes with the Task 2 to 5 helpers. `trader/prices.json` keeps its `{"prices": {SYM: float}}` shape. The skills that have not been converted yet still say `alerts.py quote <TICKER> --write`, and that now reads the Kite snapshot. This is expected mid-conversion.

**Files:**
- Modify (full rewrite): `trader-alerts/alerts.py`
- Modify (full rewrite): `tests/test_alerts.py`
- Create: `tests/fixtures/trader-alerts/kite/quotes.json`
- Delete: `tests/fixtures/trader-alerts/stooq-AAPL.csv`, `stooq-ZZZZ.csv`, `yahoo-AAPL.json`, `yahoo-AXP.json`, `yahoo-BAC.json`, `yahoo-GOOGL.json`, `yahoo-KO.json`, `yahoo-ZZZZ.json`

**Interfaces:**
- Consumes: `kite_snapshot.load`, `kite_snapshot.quotes`, `kite_snapshot.DIR` and `kite_snapshot.SnapshotError` (Task 2); `nse.Client`, `nse.read_json_file`, `nse.NseError` and `nse.NseBlocked` (Task 3); `nse_calendar.parse_now`, `load_holidays`, `save_holidays`, `parse_holiday_master`, `Calendar`, `CACHE`, `URL` and `CalendarError` (Task 4); `nse_symbols.normalize` and `nse_symbols.SymbolError` (Task 5)
- Produces:
  - Constants: `AlertError`, `PRICE_TYPES`, `CLOCK_TYPES = {"opening_bell"}` and `LABEL`
  - `inr(x) -> str`
  - `get_quotes(symbols, kite_dir, now) -> (quotes, errors)`
  - `write_prices(path, quotes, now) -> doc`
  - `validate(rule)`
  - `evaluate(rules, quotes, status, state, now) -> (rings, state)`. Task 7 adds a `positions=None` parameter.
  - `main(argv) -> int`
  - CLI exit codes: `check` returns 0 when something rang, 1 when nothing did, and 2 when price rules had no fresh quotes. NSE blocked returns 2.

- [ ] **Step 1: Write the fixture and delete the US fixtures**

`tests/fixtures/trader-alerts/kite/quotes.json` (a saved snapshot):

```json
{
  "fetched_at": "2026-10-26T15:29:00+05:30",
  "data": {
    "NSE:INFY": {"instrument_token": 408065, "timestamp": "2026-10-26 15:29:58", "last_trade_time": "2026-10-26 15:29:57", "last_price": 1612.5, "last_quantity": 3, "volume": 5123456, "average_price": 1605.2, "net_change": 0, "lower_circuit_limit": 1451.25, "upper_circuit_limit": 1773.75, "ohlc": {"open": 1598.0, "high": 1620.0, "low": 1590.1, "close": 1590.0}},
    "NSE:RELIANCE": {"instrument_token": 738561, "timestamp": "2026-10-26 15:29:59", "last_trade_time": "2026-10-26 15:29:58", "last_price": 1402.3, "last_quantity": 10, "volume": 8123000, "average_price": 1408.75, "net_change": 0, "lower_circuit_limit": 1274.95, "upper_circuit_limit": 1558.25, "ohlc": {"open": 1415.0, "high": 1419.9, "low": 1398.0, "close": 1416.6}},
    "NSE:M&M": {"instrument_token": 519937, "timestamp": "2026-10-26 15:29:59", "last_trade_time": "2026-10-26 15:29:55", "last_price": 3250.0, "last_quantity": 1, "volume": 1450000, "average_price": 3231.4, "net_change": 0, "lower_circuit_limit": 2880.0, "upper_circuit_limit": 3520.0, "ohlc": {"open": 3205.0, "high": 3262.0, "low": 3198.5, "close": 3200.0}}
  }
}
```

```bash
git rm -q tests/fixtures/trader-alerts/stooq-*.csv tests/fixtures/trader-alerts/yahoo-*.json
```

- [ ] **Step 2: Write the new tests**

Replace `tests/test_alerts.py` with:

```python
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

alerts = load("trader-alerts", "alerts")
ks = load("trader-alerts", "kite_snapshot")

ADIR = os.path.join(FIX, "trader-alerts")
KDIR = os.path.join(ADIR, "kite")
MASTER = os.path.join(ADIR, "nse-holiday-master.json")
CAL = alerts.nse_calendar.Calendar(dict(alerts.nse_calendar.HOLIDAYS), alerts.nse_calendar.YEARS)


def ist(text):
    return alerts.nse_calendar.parse_now(text)


def quotes():
    with open(os.path.join(KDIR, "quotes.json")) as fh:
        return ks.quotes(json.load(fh)["data"])


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = alerts.main(argv)
    return code, out.getvalue(), err.getvalue()


class Money(unittest.TestCase):
    def test_indian_grouping(self):
        self.assertEqual(alerts.inr(125000), "Rs 1,25,000")
        self.assertEqual(alerts.inr(1612.5), "Rs 1,612.50")
        self.assertEqual(alerts.inr(1234567.891), "Rs 12,34,567.89")
        self.assertEqual(alerts.inr(999), "Rs 999")
        self.assertEqual(alerts.inr(-950), "-Rs 950")
        self.assertEqual(alerts.inr(0.5), "Rs 0.50")


class Quotes(unittest.TestCase):
    def test_snapshot_quotes_and_missing_symbols(self):
        q, errors = alerts.get_quotes(["INFY", "TCS"], KDIR, ist("2026-10-26T15:30"))
        self.assertEqual(sorted(q), ["INFY"])
        self.assertEqual(errors, ["TCS is not in the Kite quotes snapshot: add NSE:TCS to the quotes call"])

    def test_stale_snapshot_is_refused(self):
        q, errors = alerts.get_quotes(["INFY"], KDIR, ist("2026-10-26T15:31:01"))
        self.assertEqual(q, {})
        self.assertIn("s old", errors[0])


class Rules(unittest.TestCase):
    def setUp(self):
        self.q = quotes()
        self.now = ist("2026-10-26T10:00")
        self.open = CAL.status(self.now)

    def ev(self, rules, state=None, status=None, now=None):
        return alerts.evaluate(rules, self.q, status or self.open, state or {}, now or self.now)

    def test_a_target_rings_once(self):
        rules = [{"id": "infy-1600", "symbol": "INFY", "type": "above", "price": 1600}]
        rings, st = self.ev(rules)
        self.assertEqual([r["message"] for r in rings], ["INFY is Rs 1,612.50: at or above your target Rs 1,600."])
        self.assertTrue(st["rung"]["infy-1600"].startswith("2026-10-26T10:00:00+05:30"))
        self.assertEqual(self.ev(rules, st)[0], [])

    def test_stop_and_rearm(self):
        rules = [{"id": "rel-stop", "symbol": "RELIANCE", "type": "stop", "price": 1410, "rearm": True}]
        rings, st = self.ev(rules)
        self.assertIn("at or below your stop Rs 1,410", rings[0]["message"])
        self.q["RELIANCE"]["price"] = 1420.0
        rings, st = self.ev(rules, st)
        self.assertEqual(rings, [])
        self.assertNotIn("rel-stop", st["rung"])
        self.q["RELIANCE"]["price"] = 1405.0
        self.assertEqual(len(self.ev(rules, st)[0]), 1)

    def test_pct_move_from_previous_close(self):
        self.assertEqual(self.ev([{"id": "r2", "symbol": "RELIANCE", "type": "pct_move", "pct": 2}])[0], [])
        small = [{"id": "r1", "symbol": "RELIANCE", "type": "pct_move", "pct": 1, "direction": "down"}]
        rings, st = self.ev(small)
        self.assertEqual(rings[0]["message"], "RELIANCE moved -1.01% to Rs 1,402.30 (from Rs 1,416.60).")
        self.assertEqual(self.ev(small, st)[0], [])
        up = [{"id": "ru", "symbol": "RELIANCE", "type": "pct_move", "pct": 1, "direction": "up"}]
        self.assertEqual(self.ev(up)[0], [])

    def test_opening_bell_once_per_trading_day(self):
        rules = [{"id": "bell", "type": "opening_bell"}]
        pre = ist("2026-10-26T09:10")
        self.assertEqual(self.ev(rules, status=CAL.status(pre), now=pre)[0], [])
        rings, st = self.ev(rules)
        self.assertEqual(rings[0]["message"], "Opening bell: NSE is open (2026-10-26 10:00 IST).")
        later = ist("2026-10-26T11:00")
        self.assertEqual(self.ev(rules, st, CAL.status(later), later)[0], [])
        nxt = ist("2026-10-27T09:16")
        self.assertEqual(len(self.ev(rules, st, CAL.status(nxt), nxt)[0]), 1)
        diwali = ist("2026-11-10T10:00")
        self.assertEqual(self.ev(rules, status=CAL.status(diwali), now=diwali)[0], [])

    def test_bad_rules(self):
        with self.assertRaises(alerts.AlertError):
            self.ev([{"id": "x", "type": "moon"}])
        with self.assertRaises(alerts.AlertError):
            self.ev([{"id": "x", "type": "above", "symbol": "INFY"}])


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.rules = os.path.join(self.d, "alerts.json")
        self.state = os.path.join(self.d, "state", "alerts.json")
        self.prices = os.path.join(self.d, "prices.json")
        self.hol = os.path.join(self.d, "holidays.json")

    def tearDown(self):
        shutil.rmtree(self.d)

    def check(self, now):
        return run(["check", "--rules", self.rules, "--state", self.state, "--prices-out", self.prices,
                    "--kite-dir", KDIR, "--holidays", self.hol, "--now", now])

    def test_a_day_of_alerts(self):
        for args in (["--opening-bell"], ["--symbol", "infy.ns", "--above", "1600"],
                     ["--symbol", "RELIANCE", "--stop", "1350"]):
            self.assertEqual(run(["add", "--rules", self.rules] + args)[0], 0)
        code, _, err = run(["add", "--rules", self.rules, "--symbol", "INFY", "--above", "1600"])
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)

        code, text, _ = self.check("2026-10-26T15:30")
        self.assertEqual(code, 0)
        self.assertIn("ALERT INFY last traded at Rs 1,612.50: at or above your target Rs 1,600.", text)
        self.assertNotIn("Opening bell", text)
        self.assertIn("not an order", text)
        with open(self.prices) as fh:
            doc = json.load(fh)
        self.assertEqual(doc["prices"], {"INFY": 1612.5, "RELIANCE": 1402.3})
        self.assertEqual(doc["currency"], "INR")

        code, text, _ = self.check("2026-10-27T09:16")
        self.assertEqual(code, 0)
        self.assertIn("ALERT Opening bell: NSE is open (2026-10-27 09:16 IST).", text)
        self.assertIn("error: the quotes snapshot is", text)

        code, text, _ = self.check("2026-10-27T09:20")
        self.assertEqual(code, 2)
        self.assertIn("error: the quotes snapshot is", text)

        code, text, _ = run(["list", "--rules", self.rules, "--state", self.state])
        self.assertIn("rang", text)
        self.assertEqual(run(["reset", "opening-bell", "--state", self.state])[0], 0)
        self.assertEqual(run(["reset", "opening-bell", "--state", self.state])[0], 1)

    def test_quote_write_merges(self):
        code, text, _ = run(["quote", "INFY", "nse:m&m", "--kite-dir", KDIR, "--write", self.prices,
                             "--now", "2026-10-26T15:30"])
        self.assertEqual(code, 0)
        self.assertRegex(text, r"INFY\s+Rs 1,612.50 \(\+1.42% vs prev close Rs 1,590\)")
        run(["quote", "RELIANCE", "--kite-dir", KDIR, "--write", self.prices, "--now", "2026-10-26T15:30"])
        with open(self.prices) as fh:
            doc = json.load(fh)
        self.assertEqual(sorted(doc["prices"]), ["INFY", "M&M", "RELIANCE"])
        self.assertEqual(doc["detail"]["M&M"]["upper_circuit"], 3520.0)

    def test_quote_everything_in_the_snapshot(self):
        code, text, _ = run(["quote", "--kite-dir", KDIR, "--now", "2026-10-26T15:30", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(json.loads(text)["quotes"]), ["INFY", "M&M", "RELIANCE"])

    def test_quote_stale(self):
        code, _, err = run(["quote", "--kite-dir", KDIR, "--now", "2026-10-26T16:00"])
        self.assertEqual(code, 1)
        self.assertIn("s old", err)

    def test_clock(self):
        code, text, _ = run(["clock", "--now", "2026-10-26T10:00", "--holidays", self.hol])
        self.assertEqual(code, 0)
        self.assertIn("NSE OPEN", text)
        self.assertIn("about 15:20", text)
        code, text, _ = run(["clock", "--now", "2026-12-25T10:00", "--holidays", self.hol])
        self.assertEqual(code, 1)
        self.assertIn("NSE holiday: Christmas", text)
        self.assertIn("Next open: 2026-12-28 09:15 IST.", text)
        _, text, _ = run(["clock", "--now", "2027-01-04T10:00", "--holidays", self.hol])
        self.assertIn("holiday list for 2027 is not loaded", text)

    def test_holidays_refresh_from_file(self):
        code, text, _ = run(["holidays", "refresh", "--file", MASTER, "--holidays", self.hol])
        self.assertEqual(code, 0)
        self.assertIn("Saved 20 NSE holidays for 2026", text)
        self.assertTrue(os.path.exists(self.hol))
        code, _, err = run(["holidays", "refresh", "--file", os.path.join(KDIR, "quotes.json"),
                            "--holidays", self.hol])
        self.assertEqual(code, 1)
        self.assertIn("no CM list", err)

    def test_check_without_rules(self):
        code, _, err = run(["check", "--rules", self.rules, "--kite-dir", KDIR])
        self.assertEqual(code, 1)
        self.assertIn("no rules", err)

    def test_bad_symbol(self):
        code, _, err = run(["add", "--rules", self.rules, "--symbol", "BSE:INFY", "--above", "1"])
        self.assertEqual(code, 1)
        self.assertIn("only NSE symbols", err)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_alerts.py -v`
Expected: errors and failures, including `AttributeError: module 'trader_alerts' has no attribute 'nse_calendar'`.

- [ ] **Step 4: Replace `trader-alerts/alerts.py`**

```python
#!/usr/bin/env python3
"""Price alerts and the NSE clock for trader-alerts. Standard library only.

    python3 alerts.py clock                            # is NSE open? next open, MIS square-off
    python3 alerts.py holidays refresh                 # NSE holiday list -> trader/cache/nse/holidays.json
    python3 alerts.py holidays refresh --file h.json   # the same, from a file saved in a browser
    python3 alerts.py quote INFY RELIANCE --write      # trader/kite/quotes.json -> trader/prices.json
    python3 alerts.py add --symbol INFY --above 1700   # rules live in trader/alerts.json
    python3 alerts.py add --symbol RELIANCE --stop 1350
    python3 alerts.py add --symbol TCS --pct 3
    python3 alerts.py add --opening-bell
    python3 alerts.py check                            # rings what hit, once
    python3 alerts.py list
    python3 alerts.py reset infy-above-1700

Rule types:
  above         the price is at or above "price" (a target)
  below / stop  the price is at or below "price" (a stop or a dip to buy)
  pct_move      the price moved "pct" percent or more from the previous close
                (or from "ref" if you give one); "direction": "up" or "down"
  opening_bell  NSE opened today (rings once per trading day)

An above / below alert rings ONCE and then stays quiet until you reset it,
unless the rule has "rearm": true (it re-arms when the price crosses back).
A pct_move alert rings at most once per day.

Prices come only from the Kite connector. Claude calls it for the symbols the
rules watch and saves the answer with kite_snapshot.py save quotes; this
script reads trader/kite/quotes.json and refuses it when it is more than 120
seconds old. Nothing here fetches prices from the web, and nothing here places
an order.

check exits 0 when something rang, 1 when nothing did, and 2 when the price
rules could not be checked (no fresh quotes).
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import kite_snapshot
import nse
import nse_calendar
import nse_symbols


class AlertError(Exception):
    pass


# ---------------------------------------------------------------- money

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


def _n(x):
    x = float(x)
    return str(int(x)) if x == int(x) else "%.2f" % x


# ---------------------------------------------------------------- files

def _write(path, doc):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")


def _read(path, default):
    if not path or not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as e:
        raise AlertError("%s is not valid JSON: %s" % (path, e))


def calendar(a):
    holidays, years = nse_calendar.load_holidays(a.holidays)
    return nse_calendar.Calendar(holidays, years)


# ---------------------------------------------------------------- quotes

def get_quotes(symbols, kite_dir, now):
    """({SYM: quote}, [errors]) from the Kite quotes snapshot. A symbol missing from the
    snapshot is an error naming the Kite instrument to add."""
    try:
        snap = kite_snapshot.quotes(kite_snapshot.load("quotes", kite_dir, now=now))
    except kite_snapshot.SnapshotError as e:
        return {}, [str(e)]
    quotes, errors = {}, []
    for s in symbols:
        if s in snap:
            quotes[s] = snap[s]
        else:
            errors.append("%s is not in the Kite quotes snapshot: add NSE:%s to the quotes call" % (s, s))
    return quotes, errors


def write_prices(path, quotes, now):
    old = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                old = json.load(fh)
        except (ValueError, OSError):
            old = {}
    prices = dict(old.get("prices", {}))
    detail = dict(old.get("detail", {}))
    for s, q in quotes.items():
        prices[s] = q["price"]
        detail[s] = {"prev_close": q.get("prev_close"), "time": q.get("time"), "source": "kite",
                     "upper_circuit": q.get("upper_circuit"), "lower_circuit": q.get("lower_circuit")}
    doc = {"as_of": now.isoformat(), "source": "kite", "currency": "INR",
           "note": "Quotes from the Kite connector. The exchange price is the one that fills.",
           "prices": prices, "detail": detail}
    _write(path, doc)
    return doc


# ---------------------------------------------------------------- rules

PRICE_TYPES = {"above", "below", "stop", "target", "pct_move", "opening_bell"}
CLOCK_TYPES = {"opening_bell"}
LABEL = {"above": "target", "target": "target", "below": "level", "stop": "stop"}


def validate(rule):
    t = rule.get("type")
    if t not in PRICE_TYPES:
        raise AlertError("rule %s: unknown type %r" % (rule.get("id"), t))
    if t not in CLOCK_TYPES and not rule.get("symbol"):
        raise AlertError("rule %s needs a symbol" % rule.get("id"))
    if t in ("above", "below", "stop", "target") and not isinstance(rule.get("price"), (int, float)):
        raise AlertError("rule %s needs a numeric price" % rule.get("id"))
    if t == "pct_move" and not isinstance(rule.get("pct"), (int, float)):
        raise AlertError("rule %s needs a numeric pct" % rule.get("id"))


def evaluate(rules, quotes, status, state, now):
    """Pure function. Returns (rings, new_state). Each ring: {id, symbol, message}."""
    state = json.loads(json.dumps(state or {}))
    rung = state.setdefault("rung", {})
    today = status["date"]
    stamp = now.isoformat()
    rings = []
    for r in rules:
        validate(r)
        rid = r.get("id") or "%s-%s" % (r.get("symbol", "market"), r["type"])
        typ = {"stop": "below", "target": "above"}.get(r["type"], r["type"])
        if typ == "opening_bell":
            if status["open"] and rung.get(rid, "")[:10] != today:
                rings.append({"id": rid, "symbol": "",
                              "message": "Opening bell: NSE is open (%s IST)." % status["now_ist"]})
                rung[rid] = stamp
            continue
        sym = r["symbol"].upper()
        q = quotes.get(sym)
        if not q:
            continue
        p = q["price"]
        if typ in ("above", "below"):
            hit = p >= r["price"] if typ == "above" else p <= r["price"]
            if hit and rid not in rung:
                rings.append({"id": rid, "symbol": sym, "message": "%s %s %s: %s your %s %s%s." % (
                    sym, "is" if status["open"] else "last traded at", inr(p),
                    "at or above" if typ == "above" else "at or below", LABEL[r["type"]], inr(r["price"]),
                    (" (" + r["note"] + ")") if r.get("note") else "")})
                rung[rid] = stamp
            elif not hit and rid in rung and r.get("rearm"):
                del rung[rid]
        elif typ == "pct_move":
            ref = r.get("ref") or q.get("prev_close") or q.get("open")
            if not ref:
                continue
            move = 100.0 * (p / float(ref) - 1)
            want = r.get("direction")
            hit = abs(move) >= r["pct"] and (not want or (want == "up") == (move > 0))
            if hit and rung.get(rid, "")[:10] != today:
                rings.append({"id": rid, "symbol": sym, "message": "%s moved %+.2f%% to %s (from %s)."
                              % (sym, move, inr(p), inr(ref))})
                rung[rid] = stamp
    state["last_check"] = stamp
    return rings, state


# ---------------------------------------------------------------- commands

def _dedupe(items):
    out = []
    for s in items:
        if s and s not in out:
            out.append(s)
    return out


def cmd_clock(a):
    st = calendar(a).status(nse_calendar.parse_now(a.now))
    if a.json:
        print(json.dumps(st, indent=2))
    else:
        print("%s IST (%s): NSE %s, %s." % (st["now_ist"], st["weekday"], "OPEN" if st["open"] else "closed",
                                            st["reason"]))
        if st.get("opens"):
            print("Today's session: %s to %s IST. Zerodha squares MIS positions off from about %s."
                  % (st["opens"], st["closes"], st["mis_square_off"]))
        if st.get("next_open"):
            print("Next open: %s IST." % st["next_open"])
        if not st["calendar_known"]:
            print("NSE's holiday list for %s is not loaded: run alerts.py holidays refresh, "
                  "or check nseindia.com." % st["date"][:4])
    return 0 if st["open"] else 1


def cmd_holidays(a):
    doc = nse.read_json_file(a.file) if a.file else nse.Client().get_json(nse_calendar.URL)
    holidays = nse_calendar.parse_holiday_master(doc)
    years = nse_calendar.save_holidays(holidays, a.holidays)
    print("Saved %d NSE holidays for %s to %s." % (len(holidays), ", ".join(map(str, years)), a.holidays))
    return 0


def cmd_quote(a):
    now = nse_calendar.parse_now(a.now)
    syms = _dedupe([nse_symbols.normalize(s) for s in a.symbols])
    if not syms:
        syms = sorted(kite_snapshot.quotes(kite_snapshot.load("quotes", a.kite_dir, now=now)))
    quotes, errors = get_quotes(syms, a.kite_dir, now)
    if a.write and quotes:
        write_prices(a.write, quotes, now)
    if a.json:
        print(json.dumps({"quotes": quotes, "errors": errors}, indent=2))
    else:
        for s in syms:
            q = quotes.get(s)
            if q:
                chg = ""
                if q.get("prev_close"):
                    chg = " (%+.2f%% vs prev close %s)" % (100.0 * (q["price"] / q["prev_close"] - 1),
                                                           inr(q["prev_close"]))
                print("%-10s %s%s  %s" % (s, inr(q["price"]), chg, q.get("time", "")))
        for e in errors:
            print("error: " + e)
        if a.write and quotes:
            print("Wrote %d price(s) to %s." % (len(quotes), a.write))
    return 0 if quotes else 1


def cmd_check(a):
    doc = _read(a.rules, None)
    if not doc or not doc.get("rules"):
        raise AlertError("no rules in %s: add one with alerts.py add --symbol INFY --above 1700" % a.rules)
    rules = doc["rules"]
    now = nse_calendar.parse_now(a.now)
    status = calendar(a).status(now)
    syms = _dedupe([str(r.get("symbol", "")).upper() for r in rules if r.get("type") not in CLOCK_TYPES])
    quotes, errors = get_quotes(syms, a.kite_dir, now) if syms else ({}, [])
    state = _read(a.state, {})
    rings, state = evaluate(rules, quotes, status, state, now)
    if not a.no_write:
        _write(a.state, state)
        if quotes:
            write_prices(a.prices_out, quotes, now)
    if a.json:
        print(json.dumps({"market": status, "rings": rings, "errors": errors,
                          "quotes": {s: q["price"] for s, q in quotes.items()}}, indent=2))
    else:
        print("NSE %s (%s IST, %s)." % ("OPEN" if status["open"] else "closed", status["now_ist"],
                                        status["reason"]))
        for r in rings:
            print("ALERT " + r["message"])
        if not rings:
            print("Nothing hit. %d rule(s) watched." % len(rules))
        for e in errors:
            print("error: " + e)
        if rings:
            print("An alert is information, not an order. To act on one, size it (trader-budget or "
                  "trader-rebalance), check it (trader-risk) and say yes to it (trader-broker).")
    if rings:
        return 0
    return 2 if syms and not quotes else 1


def cmd_add(a):
    doc = _read(a.rules, {"rules": []})
    doc.setdefault("rules", [])
    if a.opening_bell:
        rule = {"id": a.id or "opening-bell", "type": "opening_bell"}
    else:
        if not a.symbol:
            raise AlertError("--symbol is required (or --opening-bell)")
        sym = nse_symbols.normalize(a.symbol)
        if a.above is not None:
            rule = {"type": "above", "price": a.above}
        elif a.below is not None:
            rule = {"type": "below", "price": a.below}
        elif a.stop is not None:
            rule = {"type": "stop", "price": a.stop}
        elif a.pct is not None:
            rule = {"type": "pct_move", "pct": a.pct}
            if a.direction:
                rule["direction"] = a.direction
        else:
            raise AlertError("give one of --above, --below, --stop or --pct")
        val = rule.get("price", rule.get("pct"))
        rule = dict({"id": a.id or ("%s-%s-%s" % (sym.lower(), rule["type"], _n(val)))}, symbol=sym, **rule)
        if a.rearm:
            rule["rearm"] = True
        if a.note:
            rule["note"] = a.note
    validate(rule)
    if any(r.get("id") == rule["id"] for r in doc["rules"]):
        raise AlertError("a rule with id %s already exists" % rule["id"])
    doc["rules"].append(rule)
    _write(a.rules, doc)
    print("Added %s: %s" % (rule["id"], json.dumps(rule)))
    return 0


def cmd_list(a):
    doc = _read(a.rules, {"rules": []})
    state = _read(a.state, {})
    if not doc.get("rules"):
        print("No rules yet.")
        return 1
    for r in doc["rules"]:
        rid = r.get("id")
        rung = state.get("rung", {}).get(rid)
        print("%-24s %s%s" % (rid, json.dumps({k: v for k, v in r.items() if k != "id"}),
                              ("  (rang %s)" % rung) if rung else ""))
    return 0


def cmd_reset(a):
    state = _read(a.state, {})
    if a.id not in state.get("rung", {}):
        print("%s has not rung (nothing to reset)." % a.id)
        return 1
    del state["rung"][a.id]
    _write(a.state, state)
    print("Re-armed %s." % a.id)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Price alerts and the NSE clock (trader-alerts).")
    sub = ap.add_subparsers(dest="cmd")

    def clock_args(p):
        p.add_argument("--now", help="pretend it is this time (ISO; no offset = IST)")
        p.add_argument("--holidays", default=nse_calendar.CACHE, help="the cached NSE holiday list")
        p.add_argument("--json", action="store_true")

    def kite_args(p):
        p.add_argument("--kite-dir", default=kite_snapshot.DIR, help="where the Kite snapshots are")

    p = sub.add_parser("clock", help="is NSE open?")
    clock_args(p)
    p = sub.add_parser("holidays", help="refresh NSE's holiday list")
    p.add_argument("action", choices=["refresh"])
    p.add_argument("--file", help="the holiday-master JSON saved from a browser")
    p.add_argument("--holidays", default=nse_calendar.CACHE)
    p = sub.add_parser("quote", help="show quotes from the Kite snapshot")
    clock_args(p)
    kite_args(p)
    p.add_argument("symbols", nargs="*")
    p.add_argument("--write", nargs="?", const="trader/prices.json", metavar="PATH",
                   help="save to prices.json (default trader/prices.json)")
    p = sub.add_parser("check", help="check every rule, ring what hit")
    clock_args(p)
    kite_args(p)
    p.add_argument("--rules", default="trader/alerts.json")
    p.add_argument("--state", default="trader/state/alerts.json")
    p.add_argument("--prices-out", default="trader/prices.json")
    p.add_argument("--no-write", action="store_true")
    p = sub.add_parser("add", help="add a rule")
    p.add_argument("--rules", default="trader/alerts.json")
    p.add_argument("--symbol")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--above", type=float)
    g.add_argument("--below", type=float)
    g.add_argument("--stop", type=float)
    g.add_argument("--pct", type=float)
    g.add_argument("--opening-bell", action="store_true")
    p.add_argument("--direction", choices=["up", "down"])
    p.add_argument("--rearm", action="store_true")
    p.add_argument("--note")
    p.add_argument("--id")
    p = sub.add_parser("list", help="list the rules")
    p.add_argument("--rules", default="trader/alerts.json")
    p.add_argument("--state", default="trader/state/alerts.json")
    p = sub.add_parser("reset", help="re-arm a rule that rang")
    p.add_argument("id")
    p.add_argument("--state", default="trader/state/alerts.json")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"clock": cmd_clock, "holidays": cmd_holidays, "quote": cmd_quote, "check": cmd_check,
                "add": cmd_add, "list": cmd_list, "reset": cmd_reset}[a.cmd](a)
    except nse.NseBlocked as e:
        print("alerts.py: %s" % e, file=sys.stderr)
        return 2
    except (AlertError, nse.NseError, nse_calendar.CalendarError, kite_snapshot.SnapshotError,
            nse_symbols.SymbolError) as e:
        print("alerts.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_alerts.py -v`
Expected: all 16 tests pass.

- [ ] **Step 6: Run the full suite and lint**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 .`
Expected: `OK` and `All checks passed!`. If another skill's test read the deleted Yahoo fixtures, fix that test to stop using them and say so in the commit message. As of this plan, only `test_alerts.py` reads `tests/fixtures/trader-alerts/`.

- [ ] **Step 7: Commit**

```bash
git add -A trader-alerts/alerts.py tests/test_alerts.py tests/fixtures/trader-alerts
git commit -m "Convert trader-alerts to the NSE clock and Kite quotes" -m "Removes the NYSE calendar, US daylight saving and Yahoo/Stooq quotes." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: MIS square-off warning and `alerts.py need`

**Files:**
- Modify: `trader-alerts/alerts.py`
- Create: `tests/fixtures/trader-alerts/kite/positions.json`
- Test: `tests/test_alerts.py` (add classes)

**Interfaces:**
- Consumes: `kite_snapshot.load("positions", ...)`, `nse_calendar.SQUARE_OFF` and Task 6's `evaluate`
- Produces:
  - `MIS_WARNING_AT = "15:05"`
  - `mis_positions(positions) -> [(SYM, qty)]`
  - `evaluate(rules, quotes, status, state, now, positions=None)`
  - The rule type `mis_warning` with an optional `"at": "HH:MM"`
  - CLI: `add --mis-warning [--at HH:MM]` and `need [--rules PATH] [--json]`, which prints `{"quotes": ["NSE:SYM", ...], "positions": bool}`

- [ ] **Step 1: Write the fixture**

`tests/fixtures/trader-alerts/kite/positions.json`:

```json
{
  "fetched_at": "2026-10-26T15:00:00+05:30",
  "data": {
    "net": [
      {"tradingsymbol": "INFY", "exchange": "NSE", "product": "MIS", "quantity": 5, "average_price": 1600.0, "last_price": 1612.5, "pnl": 62.5, "m2m": 62.5},
      {"tradingsymbol": "TCS", "exchange": "NSE", "product": "MIS", "quantity": 0, "average_price": 3040.0, "last_price": 3050.5, "pnl": 21.0, "m2m": 21.0},
      {"tradingsymbol": "RELIANCE", "exchange": "NSE", "product": "CNC", "quantity": 10, "average_price": 1380.0, "last_price": 1402.3, "pnl": 223.0, "m2m": 0.0}
    ],
    "day": [
      {"tradingsymbol": "INFY", "exchange": "NSE", "product": "MIS", "quantity": 5, "average_price": 1600.0, "last_price": 1612.5, "pnl": 62.5, "m2m": 62.5}
    ]
  }
}
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_alerts.py`, before `if __name__ == "__main__":`:

```python
class MisWarning(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(KDIR, "positions.json")) as fh:
            self.pos = json.load(fh)["data"]
        self.rules = [{"id": "mis", "type": "mis_warning", "at": "15:05"}]

    def ev(self, when, state=None, pos=None):
        now = ist(when)
        return alerts.evaluate(self.rules, {}, CAL.status(now), state or {}, now,
                               self.pos if pos is None else pos)

    def test_rings_once_after_the_time_with_open_mis(self):
        self.assertEqual(self.ev("2026-10-26T15:04")[0], [])
        rings, st = self.ev("2026-10-26T15:05")
        self.assertEqual(rings[0]["message"],
                         "MIS positions still open at 15:05 IST: INFY +5. Zerodha squares MIS off from about "
                         "15:20 IST; close them yourself first if you want to choose the price.")
        self.assertEqual(self.ev("2026-10-26T15:10", st)[0], [])

    def test_quiet_without_open_mis_or_outside_the_session(self):
        flat = {"net": [{"tradingsymbol": "INFY", "exchange": "NSE", "product": "MIS", "quantity": 0}]}
        self.assertEqual(self.ev("2026-10-26T15:06", pos=flat)[0], [])
        self.assertEqual(self.ev("2026-10-26T15:31")[0], [])
        self.assertEqual(self.ev("2026-11-10T15:06")[0], [])

    def test_short_mis_shows_a_minus(self):
        short = {"net": [{"tradingsymbol": "TCS", "exchange": "NSE", "product": "MIS", "quantity": -3}]}
        self.assertIn("TCS -3", self.ev("2026-10-26T15:06", pos=short)[0][0]["message"])

    def test_bad_time(self):
        now = ist("2026-10-26T15:06")
        with self.assertRaises(alerts.AlertError):
            alerts.evaluate([{"id": "m", "type": "mis_warning", "at": "3pm"}], {}, CAL.status(now), {}, now,
                            self.pos)

    def test_check_reads_the_positions_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            rules = os.path.join(d, "alerts.json")
            run(["add", "--rules", rules, "--mis-warning"])
            code, text, _ = run(["check", "--rules", rules, "--state", os.path.join(d, "state.json"),
                                 "--prices-out", os.path.join(d, "prices.json"), "--kite-dir", KDIR,
                                 "--holidays", os.path.join(d, "h.json"), "--now", "2026-10-26T15:06"])
            self.assertEqual(code, 0)
            self.assertIn("ALERT MIS positions still open at 15:06 IST: INFY +5.", text)
            code, text, _ = run(["check", "--rules", rules, "--state", os.path.join(d, "state2.json"),
                                 "--no-write", "--kite-dir", KDIR, "--holidays", os.path.join(d, "h.json"),
                                 "--now", "2026-10-26T15:12"])
            self.assertEqual(code, 2)
            self.assertIn("positions snapshot is", text)


class Need(unittest.TestCase):
    def test_lists_what_to_ask_kite_for(self):
        with tempfile.TemporaryDirectory() as d:
            rules = os.path.join(d, "alerts.json")
            run(["add", "--rules", rules, "--symbol", "infy", "--above", "1700"])
            run(["add", "--rules", rules, "--symbol", "m&m", "--pct", "2"])
            run(["add", "--rules", rules, "--opening-bell"])
            run(["add", "--rules", rules, "--mis-warning", "--at", "15:00"])
            code, text, _ = run(["need", "--rules", rules, "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(text), {"quotes": ["NSE:INFY", "NSE:M&M"], "positions": True})
            self.assertEqual(run(["need", "--rules", os.path.join(d, "none.json")])[0], 1)
```

The second `check` in `test_check_reads_the_positions_snapshot` runs at 15:12. The positions snapshot was saved at 15:00, so it is 720 s old, over the 600 s limit. The MIS rule is due, so the check cannot be completed and returns 2.

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_alerts.py -v`
Expected: the `MisWarning` tests fail with `TypeError: evaluate() takes 5 positional arguments but 6 were given`, and `Need` fails with exit code 2 from argparse ("invalid choice: 'need'").

- [ ] **Step 4: Implement**

In `trader-alerts/alerts.py`:

1. Add `import datetime` to the imports, between `import argparse` and `import json`.

2. Replace the rule-type constants:

```python
PRICE_TYPES = {"above", "below", "stop", "target", "pct_move", "opening_bell", "mis_warning"}
CLOCK_TYPES = {"opening_bell", "mis_warning"}
LABEL = {"above": "target", "target": "target", "below": "level", "stop": "stop"}
MIS_WARNING_AT = "15:05"


def _hhmm(text, rid):
    try:
        return datetime.datetime.strptime(str(text), "%H:%M").time()
    except ValueError:
        raise AlertError("rule %s: \"at\" wants a time like 15:05, not %r" % (rid, text))


def mis_positions(positions):
    """[(symbol, quantity)] for the open MIS positions in a Kite positions answer."""
    rows = (positions or {}).get("net") or []
    out = []
    for p in rows:
        qty = int(p.get("quantity") or 0)
        if p.get("product") == "MIS" and qty:
            out.append((str(p.get("tradingsymbol", "")).upper(), qty))
    return out


def mis_due(rules, status, now):
    """The mis_warning rules whose time has come in today's session."""
    return [r for r in rules if r.get("type") == "mis_warning" and status["phase"] == "open"
            and now.time() >= _hhmm(r.get("at", MIS_WARNING_AT), r.get("id"))]
```

3. In `validate`, add as the last line:

```python
    if t == "mis_warning":
        _hhmm(rule.get("at", MIS_WARNING_AT), rule.get("id"))
```

4. Change the `evaluate` signature and docstring to:

```python
def evaluate(rules, quotes, status, state, now, positions=None):
    """Pure function. Returns (rings, new_state). Each ring: {id, symbol, message}.
    positions is the Kite positions answer, needed only by mis_warning rules."""
```

and add this block right after the `opening_bell` block (before `sym = r["symbol"].upper()`):

```python
        if typ == "mis_warning":
            if r in mis_due([r], status, now) and rung.get(rid, "")[:10] != today:
                held = mis_positions(positions)
                if held:
                    rings.append({"id": rid, "symbol": "", "message": (
                        "MIS positions still open at %s IST: %s. Zerodha squares MIS off from about %s IST; "
                        "close them yourself first if you want to choose the price."
                        % (status["now_ist"][11:], ", ".join("%s %+d" % h for h in held),
                           nse_calendar.SQUARE_OFF.strftime("%H:%M")))})
                    rung[rid] = stamp
            continue
```

5. In `cmd_check`, replace the lines from `state = _read(a.state, {})` through `rings, state = evaluate(...)`:

```python
    positions = None
    due = mis_due(rules, status, now)
    if due:
        try:
            positions = kite_snapshot.load("positions", a.kite_dir, now=now)
        except kite_snapshot.SnapshotError as e:
            errors.append(str(e))
    state = _read(a.state, {})
    rings, state = evaluate(rules, quotes, status, state, now, positions)
```

and replace the final `return 2 if syms and not quotes else 1` with:

```python
    return 2 if (syms and not quotes) or (due and positions is None) else 1
```

6. Add the `need` command after `cmd_check`:

```python
def cmd_need(a):
    rules = _read(a.rules, {"rules": []}).get("rules", [])
    keys = _dedupe(["NSE:" + str(r["symbol"]).upper() for r in rules
                    if r.get("type") not in CLOCK_TYPES and r.get("symbol")])
    pos = any(r.get("type") == "mis_warning" for r in rules)
    if a.json:
        print(json.dumps({"quotes": keys, "positions": pos}))
    else:
        print("quotes: " + (" ".join(keys) if keys else "(none)"))
        print("positions: " + ("yes, for the MIS warning" if pos else "no"))
    return 0 if (keys or pos) else 1
```

7. In `cmd_add`, replace the first branch:

```python
    if a.opening_bell:
        rule = {"id": a.id or "opening-bell", "type": "opening_bell"}
    elif a.mis_warning:
        rule = {"id": a.id or "mis-warning", "type": "mis_warning", "at": a.at or MIS_WARNING_AT}
    else:
```

8. In `main`:
   - In the `add` parser, add `g.add_argument("--mis-warning", action="store_true")` after `--opening-bell`, and add `p.add_argument("--at", help="HH:MM IST for --mis-warning (default 15:05)")`.
   - Add the `need` parser before `list`:

```python
    p = sub.add_parser("need", help="which Kite quotes and snapshots a check needs")
    p.add_argument("--rules", default="trader/alerts.json")
    p.add_argument("--json", action="store_true")
```

   - Add `"need": cmd_need` to the dispatch dict.

9. In the module docstring, add these usage lines after `add --opening-bell`:

```
    python3 alerts.py add --mis-warning                # open MIS positions near the 15:20 square-off
    python3 alerts.py need                             # the Kite quotes (and positions) a check needs
```

and this rule type after `opening_bell`:

```
  mis_warning   an MIS (intraday) position is still open at or after "at"
                (default 15:05 IST); Zerodha squares MIS off from about 15:20.
                Reads trader/kite/positions.json. Rings once per day.
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_alerts.py -v`
Expected: all 22 tests pass.

- [ ] **Step 6: Run the full suite and lint**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 .`
Expected: `OK` and `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add trader-alerts/alerts.py tests/test_alerts.py tests/fixtures/trader-alerts/kite/positions.json
git commit -m "Add MIS square-off warning and alerts.py need" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: trader-alerts docs, example rules, shared-helper check

**Files:**
- Modify (full rewrite): `trader-alerts/SKILL.md`
- Modify (full rewrite): `trader-alerts/alerts.example.json`
- Modify: `tests/test_repo.py` (add a test)
- Modify: `README.md` (alerts table row, and the `alerts.py clock` example line)
- Modify: `CLAUDE.md` (the "Scope and fork notes" first bullet)

- [ ] **Step 1: Write the failing repo test**

In `tests/test_repo.py`, add after `ORDER_PATH = [...]`:

```python
# helper modules copied into several skills; every copy must be the same bytes
SHARED = ["kite_snapshot.py", "nse.py", "nse_calendar.py", "nse_symbols.py"]
```

and add to `class Repo`:

```python
    def test_shared_helpers_are_identical(self):
        for name in SHARED:
            copies = [os.path.join(ROOT, s, name) for s in SKILLS if os.path.isfile(os.path.join(ROOT, s, name))]
            self.assertTrue(copies, "%s exists in no skill" % name)
            texts = set()
            for p in copies:
                with open(p, "rb") as fh:
                    texts.add(fh.read())
            self.assertEqual(len(texts), 1, "copies of %s differ: %s" % (name, copies))

    def test_alerts_example_rules_are_nse(self):
        with open(os.path.join(ROOT, "trader-alerts", "alerts.example.json")) as fh:
            rules = json.load(fh)["rules"]
        syms = {r["symbol"] for r in rules if "symbol" in r}
        self.assertEqual(syms, {"INFY", "RELIANCE", "TCS", "HDFCBANK"})
        self.assertIn("mis_warning", {r["type"] for r in rules})
```

- [ ] **Step 2: Run the tests and confirm the example test fails**

Run: `python3 -m unittest discover -s tests -p test_repo.py -v`
Expected: `test_shared_helpers_are_identical` passes (one copy of each) and `test_alerts_example_rules_are_nse` FAILS (the symbols are AAPL, BAC and so on).

- [ ] **Step 3: Rewrite `trader-alerts/alerts.example.json`**

```json
{
  "rules": [
    {"id": "opening-bell", "type": "opening_bell"},
    {"id": "infy-above-1700", "symbol": "INFY", "type": "above", "price": 1700},
    {"id": "reliance-stop-1350", "symbol": "RELIANCE", "type": "stop", "price": 1350, "note": "my stop"},
    {"id": "tcs-move-3", "symbol": "TCS", "type": "pct_move", "pct": 3},
    {"id": "hdfcbank-dip-1500", "symbol": "HDFCBANK", "type": "below", "price": 1500, "rearm": true},
    {"id": "mis-warning", "type": "mis_warning", "at": "15:05"}
  ]
}
```

- [ ] **Step 4: Rewrite `trader-alerts/SKILL.md`**

````markdown
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
````

- [ ] **Step 5: Update the README and CLAUDE.md**

In `README.md`, replace the row:

```
| `/trader-alerts` | Price Alerts | Rings when a price target, a stop or the opening bell hits, with the real NYSE calendar. |
```

with:

```
| `/trader-alerts` | Price Alerts | Rings when a price target, a stop, the opening bell or the MIS square-off hits, with the real NSE calendar and Kite quotes. |
```

and the line:

```
python3 trader-alerts/alerts.py clock                                  # NYSE open or closed
```

with:

```
python3 trader-alerts/alerts.py clock                                  # NSE open or closed
```

In `CLAUDE.md`, replace the first bullet under "## Scope and fork notes" with:

```
- The pack is being converted to India: see `docs/superpowers/specs/2026-10-26-indian-market-design.md` and the plans in `docs/superpowers/plans/`. trader-alerts is converted (NSE clock, Kite quotes, `kite_snapshot.py`, `nse.py`, `nse_calendar.py`, `nse_symbols.py`). The other skills are still US until their phase lands. Shared helpers are copied into each skill that needs them and must stay byte-identical (`test_shared_helpers_are_identical`).
```

- [ ] **Step 6: Run the full suite, lint and the em-dash check**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 . && ! grep -rl "$(printf '\342\200\224')" trader-alerts tests docs CLAUDE.md README.md`
Expected: `OK`, `All checks passed!`, and no file names printed.

- [ ] **Step 7: Smoke-test the real CLI outside the repo**

```bash
cd "$(mktemp -d)" && R=/home/ubuntu/stock-market/trader-skill
python3 "$R/trader-alerts/alerts.py" clock; echo "exit $?"
python3 "$R/trader-alerts/alerts.py" holidays refresh; echo "exit $?"
python3 "$R/trader-alerts/nse_symbols.py" refresh && python3 "$R/trader-alerts/nse_symbols.py" lookup infy m&m
```

Expected:
- `clock` prints today's NSE status, with exit 0 when open and 1 when closed.
- `holidays refresh` prints "Saved N NSE holidays" (exit 0), or an NseBlocked message naming the URL and `--file` (exit 2). Both are acceptable.
- `lookup` prints Infosys Limited and Mahindra & Mahindra Limited.

Report the actual output in the task summary.

- [ ] **Step 7b (only if Task 1 logged in): end-to-end with live Kite quotes**

In the same temp dir:
1. Run `alerts.py add --symbol INFY --above 1`.
2. Call the Kite quotes tool for `NSE:INFY`, save its answer to `raw.json`, and run `kite_snapshot.py save quotes --from raw.json --dir trader/kite`.
3. Run `alerts.py check`.

Expected: `ALERT INFY ...` and exit 0. This proves the real connector answer flows through. Do not commit anything from the temp dir.

- [ ] **Step 8: Commit**

```bash
git add trader-alerts/SKILL.md trader-alerts/alerts.example.json tests/test_repo.py README.md CLAUDE.md
git commit -m "Document Indian trader-alerts; check shared helper copies stay identical" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
