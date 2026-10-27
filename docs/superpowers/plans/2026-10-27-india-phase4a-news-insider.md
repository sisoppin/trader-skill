# India Phase 4a (News and Insider) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert trader-news to NSE corporate announcements and replace trader-pelosi (US Congress trades) with trader-insider (SEBI insider-trade disclosures plus NSE bulk and block deals).

**Architecture:** Both skills read NSE through the shared `nse.py` client (cookie warm-up, daily cache, `NseBlocked` with a `--file` fallback). They take their watch list from a new shared `watchlist.py` (Kite holdings names plus trader/targets.json) and alert once per item through a state file. Bulk and block deals come from NSE's archive CSVs, which need no cookie.

**Tech Stack:** Python 3.8+, standard library only, `unittest` with offline fixtures captured live from NSE on 2026-10-27 (one synthetic PIT file is labelled as such).

**Spec:** `docs/superpowers/specs/2026-10-26-indian-market-design.md` (sections 2, 3.2 and 9, phase 4). Phase 4b (trader-analyst, trader-copycat) follows in its own plan. The user chose `--investor` over symbols they list, plus `--fund` from an AMC CSV.

**Branch:** work on `feat/india-phase4a`, branched from `feat/india-phase3`.

**Provenance:** every code block below was drafted and run in a scratch worktree first. The suite passed with 316 tests on Python 3.12 and 3.8, and ruff was clean. The expected values come from those runs and from live NSE answers.

## Global Constraints

- Python 3.8 or newer, standard library only. No em dashes (U+2014) in any .md, .py, .json, .csv, .txt or .xml file.
- Shared helpers are copied unchanged from their source copy, and `tests/test_repo.py` checks that every copy is identical and present where it is imported:
  - `kite_snapshot.py`, `nse.py`, `nse_calendar.py`, `nse_symbols.py` and `rupees.py` come from `trader-alerts/`.
  - `watchlist.py` comes from `trader-news/`, and is new in this plan.
- NSE access only through `nse.Client`, and every fetcher accepts `--file` (or `--offline DIR`). A blocked request exits 2 and prints the URL with the `--file` hint.
- Tests are fully offline. `--now` works only with `TRADER_TEST_CLOCK=1` (`tests/_load.py` sets it).
- Never run a tool from the repo root. Lint with `--no-cache`.
- Commit messages end with a Co-Authored-By trailer.
- Full check: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`

## Review Focus

1. **A block page from NSE** (HTML, or a JSON dict instead of a list): this is an error or block line, never silently "nothing new". Covered by `test_not_a_list_is_an_error`, `test_not_a_pit_answer`, `test_bad_csv` and `test_a_blocked_symbol_exits_2_with_the_file_hint`.
2. **"Off Market" transfers**: they must not be tagged `[market]`, because the word contains "market". Covered by `test_real_infy_rows`.
3. **block.csv "NO RECORDS"**: means no deals, not an error. Covered by `test_real_bulk_and_empty_block`.
4. **Seen ids grow without limit**: ids older than 90 days are dropped. Covered by `test_seen_ids_older_than_90_days_are_forgotten`.
5. **Holdings snapshot of any age**: used only for symbol names, so it never blocks the watch list. Covered by `test_holdings_and_targets`.

---

### Task 1: trader-news on NSE announcements, with the shared watch list

**Files:**
- Copy (unchanged): `trader-alerts/{kite_snapshot,nse,nse_calendar,nse_symbols}.py` into `trader-news/`
- Create: `trader-news/watchlist.py` (the new shared helper), `tests/fixtures/trader-news/announcements-INFY.json`
- Replace: `trader-news/news.py`, `tests/test_news.py`, `trader-news/SKILL.md`
- Delete: `tests/fixtures/trader-news/{company_tickers.json,sec-8-K-0000021344.xml,sec-8-K-0000320193.xml,yahoo-AAPL.xml,yahoo-KO.xml}`
- Modify: `tests/test_repo.py` (`SHARED`)

**Interfaces:**
- Produces:
  - `watchlist.watch_list(kite_dir, targets) -> [SYM]` and `watchlist.WatchError`
  - `news.category(desc, text="")`
  - `news.parse(data, symbol) -> [item]`, where an item is `{symbol, when (aware IST), category, title, text, link, id}`
  - `news.collect(symbols, client=None, offline=None, file=None) -> (items, errors, blocked)`
  - `news.select(items, state, now, days, show_all)`
  - CLI exit codes: 0 when something new is shown, 1 when nothing is new, 2 when NSE blocked a request.

- [ ] **Step 1: Write the fixture and the failing tests**

```bash
git rm -q tests/fixtures/trader-news/company_tickers.json tests/fixtures/trader-news/sec-8-K-0000021344.xml tests/fixtures/trader-news/sec-8-K-0000320193.xml tests/fixtures/trader-news/yahoo-AAPL.xml tests/fixtures/trader-news/yahoo-KO.xml
```

`tests/fixtures/trader-news/announcements-INFY.json`:

```json
[
 {
  "an_dt": "24-Oct-2026 19:43:00",
  "attFileSize": "12.44 MB",
  "attchmntFile": "https://nsearchives.nseindia.com/corporate/Infosys_24102026194244_Financials_newspaper_ad_SE_filing.pdf",
  "attchmntText": "Infosys Limited has informed the Exchange about Copy of Newspaper Publication",
  "bflag": null,
  "csvName": null,
  "desc": "Copy of Newspaper Publication",
  "difference": "00:00:01",
  "dt": "24102026194300",
  "exchdisstime": "24-Oct-2026 19:43:01",
  "fileSize": "12.44 MB",
  "hasXbrl": true,
  "old_new": null,
  "orgid": null,
  "seq_id": "106827749",
  "smIndustry": "Computers - Software",
  "sm_isin": "INE009A01021",
  "sm_name": "Infosys Limited",
  "sort_date": "2026-10-24 19:43:00",
  "symbol": "INFY"
 },
 {
  "an_dt": "23-Oct-2026 16:08:26",
  "attFileSize": "25.48 MB",
  "attchmntFile": "https://nsearchives.nseindia.com/corporate/Infosys_23102026160704_BM_Outcome_Oct232026_1.pdf",
  "attchmntText": "Infosys Limited has submitted to the Exchange, Financial Results for the quarter and half year ended September 30, 2026 and declaration of interim dividend",
  "bflag": null,
  "csvName": null,
  "desc": "Outcome of Board Meeting",
  "difference": "00:00:01",
  "dt": "23102026160826",
  "exchdisstime": "23-Oct-2026 16:08:27",
  "fileSize": "25.48 MB",
  "hasXbrl": true,
  "old_new": null,
  "orgid": null,
  "seq_id": "106826465",
  "smIndustry": "Computers - Software",
  "sm_isin": "INE009A01021",
  "sm_name": "Infosys Limited",
  "sort_date": "2026-10-23 16:08:26",
  "symbol": "INFY"
 },
 {
  "an_dt": "20-Feb-2026 21:29:54",
  "attFileSize": "218.94 KB",
  "attchmntFile": "https://nsearchives.nseindia.com/corporate/INFY_20022026212916_Investor_events_20022026.pdf",
  "attchmntText": "Infosys Limited has informed the Exchange about Schedule of meet",
  "bflag": null,
  "csvName": null,
  "desc": "Analysts/Institutional Investor Meet/Con. Call Updates",
  "difference": "00:00:01",
  "dt": "20022026212954",
  "exchdisstime": "20-Feb-2026 21:29:55",
  "fileSize": "218.94 KB",
  "hasXbrl": true,
  "old_new": null,
  "orgid": null,
  "seq_id": "106541437",
  "smIndustry": "Computers - Software",
  "sm_isin": "INE009A01021",
  "sm_name": "Infosys Limited",
  "sort_date": "2026-02-20 21:29:54",
  "symbol": "INFY"
 },
 {
  "an_dt": "08-Jul-2025 12:03:11",
  "attFileSize": "222.65 KB",
  "attchmntFile": "https://nsearchives.nseindia.com/corporate/Infosys_05062025092103_Clarification_letter.pdf",
  "attchmntText": "The Exchange had sought clarification from Infosys Limited for the quarter ended 31-Mar-2025 with respect to Regulation 33 of the SEBI (Listing Obligations and Disclosure Requirements) Regulations, 2015. On basis of above the Company was required to clarify the following:   -1. Financial results submitted is not as per format prescribed by SEBI -2. Limited Review Report/ Independent Auditor's Report is not in the format prescribed by SEBI The response of the Company is enclosed.",
  "bflag": null,
  "csvName": null,
  "desc": "Reply to Clarification- Financial results",
  "difference": "00:00:01",
  "dt": "08072025120311",
  "exchdisstime": "08-Jul-2025 12:03:12",
  "fileSize": "222.65 KB",
  "hasXbrl": false,
  "old_new": null,
  "orgid": null,
  "seq_id": "106292789",
  "smIndustry": "Computers - Software",
  "sm_isin": "INE009A01021",
  "sm_name": "Infosys Limited",
  "sort_date": "2025-07-08 12:03:11",
  "symbol": "INFY"
 },
 {
  "an_dt": "17-Oct-2024 15:40:29",
  "attFileSize": null,
  "attchmntFile": "https://nsearchives.nseindia.com/corporate/INFY_17102024154029_BMOutcomeOctober172024.pdf",
  "attchmntText": "Infosys Limited has informed the Exchange that Board of Directors at its meeting held on October 17, 2024, declared Interim Dividend of 21 per equity share.",
  "bflag": null,
  "csvName": null,
  "desc": "Dividend",
  "difference": "00:00:01",
  "dt": "17102024154029",
  "exchdisstime": "17-Oct-2024 15:40:30",
  "fileSize": "-",
  "hasXbrl": false,
  "old_new": null,
  "orgid": null,
  "seq_id": "106025713",
  "smIndustry": "Computers - Software",
  "sm_isin": "INE009A01021",
  "sm_name": "Infosys Limited",
  "sort_date": "2024-10-17 15:40:29",
  "symbol": "INFY"
 },
 {
  "an_dt": "23-Jul-2024 18:36:48",
  "attFileSize": null,
  "attchmntFile": "https://nsearchives.nseindia.com/corporate/INFY_23072024183648_ExchangeletterJuly232024.pdf",
  "attchmntText": "Infosys Limited has informed the Exchange about Acquisition",
  "bflag": null,
  "csvName": null,
  "desc": "Acquisition",
  "difference": "00:00:01",
  "dt": "23072024183648",
  "exchdisstime": "23-Jul-2024 18:36:49",
  "fileSize": "-",
  "hasXbrl": false,
  "old_new": null,
  "orgid": null,
  "seq_id": "105923264",
  "smIndustry": "Computers - Software",
  "sm_isin": "INE009A01021",
  "sm_name": "Infosys Limited",
  "sort_date": "2024-07-23 18:36:48",
  "symbol": "INFY"
 }
]
```

Replace `tests/test_news.py` with:

```python
import datetime
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

news = load("trader-news", "news")

NDIR = os.path.join(FIX, "trader-news")
NOW = "2026-10-26T10:00"


def fixture():
    with open(os.path.join(NDIR, "announcements-INFY.json")) as fh:
        return json.load(fh)


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = news.main(argv)
    return code, out.getvalue(), err.getvalue()


class Parse(unittest.TestCase):
    def test_real_announcements(self):
        items = news.parse(fixture(), "INFY")
        self.assertEqual(len(items), 6)
        self.assertEqual([i["category"] for i in items],
                         ["other", "results", "analyst meet", "results", "dividend", "deal"])
        first = items[0]
        self.assertEqual((first["symbol"], first["title"], first["id"]), ("INFY", "Copy of Newspaper Publication",
                                                                         "106827749"))
        self.assertEqual(first["when"].strftime("%Y-%m-%d %H:%M %z"), "2026-10-24 19:43 +0530")
        self.assertTrue(first["link"].startswith("https://nsearchives.nseindia.com/"))

    def test_categories(self):
        self.assertEqual(news.category("Outcome of Board Meeting", "Financial Results for the quarter"), "results")
        self.assertEqual(news.category("Board Meeting Intimation", "to consider buyback"), "dividend")
        self.assertEqual(news.category("Board Meeting Intimation", "to consider fund raising"), "board meeting")
        self.assertEqual(news.category("Disclosure of creation of pledge", ""), "pledge")
        self.assertEqual(news.category("Copy of Newspaper Publication", ""), "other")

    def test_not_a_list_is_an_error(self):
        with self.assertRaises(news.NewsError):
            news.parse({"error": "blocked"}, "INFY")


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "news.json")

    def tearDown(self):
        self.tmp.cleanup()

    def news(self, *extra):
        return run(["--symbols", "infy.ns", "--offline", NDIR, "--state", self.state, "--now", NOW] + list(extra))

    def test_new_items_show_once(self):
        code, text, _ = self.news("--days", "7")
        self.assertEqual(code, 0)
        self.assertIn("2026-10-24 19:43  INFY       [other] Copy of Newspaper Publication", text)
        self.assertIn("[results] Outcome of Board Meeting", text)
        self.assertNotIn("Dividend", text)
        self.assertIn("Not financial advice", text)
        code, text, _ = self.news("--days", "7")
        self.assertEqual(code, 1)
        self.assertIn("Nothing new.", text)
        code, text, _ = self.news("--days", "7", "--all")
        self.assertEqual(code, 0)
        self.assertIn("Copy of Newspaper Publication", text)

    def test_window_and_json(self):
        code, text, _ = self.news("--days", "1200", "--json", "--dry-run")
        items = json.loads(text)["items"]
        self.assertEqual(len(items), 6)
        self.assertEqual(items[0]["when"], "2026-10-24T19:43:00+05:30")
        self.assertFalse(os.path.exists(self.state))

    def test_one_file_for_one_symbol(self):
        path = os.path.join(NDIR, "announcements-INFY.json")
        code, text, _ = run(["--symbols", "INFY", "--file", path, "--state", self.state, "--now", NOW])
        self.assertEqual(code, 0)
        code, _, err = run(["--symbols", "INFY", "TCS", "--file", path, "--state", self.state, "--now", NOW])
        self.assertEqual(code, 1)
        self.assertIn("exactly one", err)

    def test_missing_offline_file_is_an_error_line(self):
        code, text, _ = run(["--symbols", "INFY", "TCS", "--offline", NDIR, "--state", self.state, "--now", NOW])
        self.assertEqual(code, 0)
        self.assertIn("error: TCS: no saved announcements", text)

    def test_seen_ids_older_than_90_days_are_forgotten(self):
        with open(self.state, "w") as fh:
            json.dump({"seen": {"old": "2026-01-01T10:00:00+05:30", "new": "2026-10-20T10:00:00+05:30"}}, fh)
        self.news("--dry-run")
        self.news()
        with open(self.state) as fh:
            seen = json.load(fh)["seen"]
        self.assertNotIn("old", seen)
        self.assertIn("new", seen)
        self.assertIn("106827749", seen)


class Blocked(unittest.TestCase):
    def test_a_blocked_symbol_exits_2_with_the_file_hint(self):
        class Client:
            def get_json(self, url):
                raise news.nse.NseBlocked(url, "HTTP 403")
        items, errors, blocked = news.collect(["INFY"], Client())
        self.assertEqual((items, errors), ([], []))
        self.assertIn("--file", blocked[0])
        self.assertIn("symbol=INFY", blocked[0])


class Watch(unittest.TestCase):
    def test_holdings_and_targets(self):
        with tempfile.TemporaryDirectory() as d:
            kd = os.path.join(d, "kite")
            news.kite_snapshot.save("holdings", [{"tradingsymbol": "INFY"}, {"tradingsymbol": "TCS"}], kd,
                                    now=datetime.datetime(2026, 1, 1, tzinfo=news.nse_calendar.IST))
            targets = os.path.join(d, "targets.json")
            with open(targets, "w") as fh:
                json.dump({"weights": [{"symbol": "TCS", "weight": 1}, {"symbol": "HDFCBANK", "weight": 1}]}, fh)
            self.assertEqual(news.watchlist.watch_list(kd, targets), ["INFY", "TCS", "HDFCBANK"])
            code, _, err = run(["--kite-dir", os.path.join(d, "none"), "--targets", os.path.join(d, "none.json"),
                                "--now", NOW])
            self.assertEqual(code, 1)
            self.assertIn("which stocks?", err)


if __name__ == "__main__":
    unittest.main()
```

- In `tests/test_repo.py`, replace:

```
SHARED = ["kite_snapshot.py", "nse.py", "nse_calendar.py", "nse_symbols.py", "rupees.py", "charges.py"]
```

  with:

```
SHARED = ["kite_snapshot.py", "nse.py", "nse_calendar.py", "nse_symbols.py", "rupees.py", "charges.py",
          "watchlist.py"]
```


- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_news.py -v`
Expected: errors, because the old US news.py has no `parse` and no `category`.

- [ ] **Step 3: Implement**

```bash
cp trader-alerts/kite_snapshot.py trader-alerts/nse.py trader-alerts/nse_calendar.py trader-alerts/nse_symbols.py trader-news/
```

`trader-news/watchlist.py`:

```python
#!/usr/bin/env python3
"""Which stocks to watch, for the trader skills. Standard library only.

The symbols come from the Kite holdings snapshot (any age: it is only a
list of names) and from trader/targets.json, in that order, each once.

This file is copied into every skill that watches a list of stocks. Keep
the copies identical: tests/test_repo.py checks.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import kite_snapshot


class WatchError(Exception):
    pass


def watch_list(kite_dir, targets):
    syms = []
    try:
        for r in kite_snapshot.load("holdings", kite_dir, max_age=10 ** 9) or []:
            syms.append(str(r.get("tradingsymbol", "")).upper())
    except kite_snapshot.SnapshotError:
        pass
    if targets and os.path.exists(targets):
        try:
            with open(targets, encoding="utf-8") as fh:
                doc = json.load(fh)
        except ValueError as e:
            raise WatchError("%s is not valid JSON: %s" % (targets, e))
        for w in doc.get("weights", []) if isinstance(doc, dict) else []:
            syms.append(str(w.get("symbol") or w.get("ticker") or "").upper())
    out = []
    for s in syms:
        if s and s not in out:
            out.append(s)
    return out
```

Replace `trader-news/news.py` with:

```python
#!/usr/bin/env python3
"""News monitor for trader-news: NSE corporate announcements. Standard library only.

Watches the announcements NSE publishes for the stocks you hold (or plan to
copy) and prints only what is new since the last check, newest first, each
with a category so results, dividends, board meetings and deals stand out.

    python3 news.py                                  # symbols from Kite holdings and trader/targets.json
    python3 news.py --symbols INFY TCS
    python3 news.py --symbols INFY --all --days 30   # everything in 30 days, seen or not
    python3 news.py --symbols INFY --file ann.json   # NSE blocked you: the page saved from a browser

Source, one request per symbol (NSE needs its cookie, see nse.py):
    https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=<SYMBOL>
If NSE blocks the request, the tool prints that address: open it in a
browser, save what it shows, and run again with --file (one symbol) or
--offline DIR holding announcements-<SYMBOL>.json files.

State: trader/state/news.json remembers what you have seen (90 days), so an
item shows once. Exit code 0 when something new is shown, 1 when nothing
is new, 2 when NSE blocked a request.

An announcement is the company's own filing: open the attachment before
acting, and treat nothing here as advice.
"""

import argparse
import datetime
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
import watchlist

URL = "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=%s"
KEEP_DAYS = 90
CATEGORIES = (
    ("results", ("financial result", "quarterly result", "audited", "unaudited", "results")),
    ("dividend", ("dividend", "bonus", "split", "buyback", "buy back", "record date")),
    ("board meeting", ("board meeting",)),
    ("deal", ("acquisition", "amalgamation", "merger", "scheme of arrangement", "demerger", "takeover")),
    ("pledge", ("pledge", "encumbrance")),
    ("insider", ("insider", "sast", "regulation 29", "reg. 29", "regulation 7")),
    ("rating", ("credit rating", "rating")),
    ("management", ("appointment", "resignation", "cessation", "director", "chief executive", "ceo", "cfo")),
    ("analyst meet", ("analyst", "investor meet", "con. call", "earnings call")),
)


class NewsError(Exception):
    pass


def category(desc, text=""):
    """The first matching category over the title and the attachment text (results before dividend etc.)."""
    low = ("%s %s" % (desc or "", text or "")).lower()
    for name, words in CATEGORIES:
        if any(w in low for w in words):
            return name
    return "other"


def parse(data, symbol):
    """NSE announcements JSON (a list) -> items {symbol, when, category, title, text, link, id}."""
    if not isinstance(data, list):
        raise NewsError("the announcements for %s are not a list (NSE answer changed, or a block page)" % symbol)
    items = []
    for r in data:
        if not isinstance(r, dict) or not r.get("seq_id"):
            continue
        try:
            when = datetime.datetime.strptime(str(r.get("sort_date"))[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        items.append({"symbol": str(r.get("symbol") or symbol).upper(), "when": when.replace(tzinfo=nse_calendar.IST),
                      "category": category(r.get("desc"), r.get("attchmntText")),
                      "title": str(r.get("desc") or "").strip(),
                      "text": " ".join(str(r.get("attchmntText") or "").split()),
                      "link": r.get("attchmntFile") or "", "id": str(r["seq_id"])})
    return items


def load_state(path):
    if not path or not os.path.exists(path):
        return {"seen": {}}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except ValueError as e:
        raise NewsError("%s is not valid JSON: %s" % (path, e))
    return doc if isinstance(doc.get("seen"), dict) else {"seen": {}}


def save_state(path, state, now):
    cut = now - datetime.timedelta(days=KEEP_DAYS)
    state["seen"] = {k: v for k, v in state["seen"].items()
                     if nse_calendar.parse_iso(v) >= cut}
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")


def collect(symbols, client=None, offline=None, file=None):
    """(items, errors, blocked) for the symbols. A blocked request names the URL and stops counting as data."""
    items, errors, blocked = [], [], []
    for sym in symbols:
        try:
            if file:
                data = nse.read_json_file(file)
            elif offline:
                path = os.path.join(offline, "announcements-%s.json" % sym)
                if not os.path.exists(path):
                    raise NewsError("no saved announcements for %s at %s" % (sym, path))
                data = nse.read_json_file(path)
            else:
                data = client.get_json(URL % sym)
            items += parse(data, sym)
        except nse.NseBlocked as e:
            blocked.append(str(e))
        except (NewsError, nse.NseError) as e:
            errors.append("%s: %s" % (sym, e))
    return items, errors, blocked


def select(items, state, now, days=7, show_all=False):
    """Items inside the window, newest first; only unseen ones unless show_all."""
    start = now - datetime.timedelta(days=days)
    out = [i for i in items if i["when"] >= start and (show_all or i["id"] not in state["seen"])]
    return sorted(out, key=lambda i: (i["when"], i["id"]), reverse=True)


def render(items, errors, blocked):
    lines = []
    for i in items:
        lines.append("%s  %-10s [%s] %s" % (i["when"].strftime("%Y-%m-%d %H:%M"), i["symbol"], i["category"], i["title"]))
        if i["text"]:
            lines.append("    " + i["text"][:200])
        if i["link"]:
            lines.append("    " + i["link"])
    if not items:
        lines.append("Nothing new.")
    for e in errors:
        lines.append("error: " + e)
    for b in blocked:
        lines.append("blocked: " + b)
    lines.append("An announcement is the company's own filing: read it before acting. Not financial advice.")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="NSE corporate announcements for your stocks (trader-news).")
    ap.add_argument("--symbols", nargs="*", help="default: Kite holdings and trader/targets.json")
    ap.add_argument("--kite-dir", default=kite_snapshot.DIR)
    ap.add_argument("--targets", default="trader/targets.json")
    ap.add_argument("--state", default="trader/state/news.json")
    ap.add_argument("--days", type=float, default=7, help="ignore announcements older than this")
    ap.add_argument("--all", action="store_true", help="show seen items too")
    ap.add_argument("--file", help="NSE's announcements JSON saved from a browser (one symbol)")
    ap.add_argument("--offline", metavar="DIR", help="read announcements-<SYMBOL>.json files from DIR")
    ap.add_argument("--now", help="pretend it is this time (ISO, IST; tests only, needs TRADER_TEST_CLOCK=1)")
    ap.add_argument("--dry-run", action="store_true", help="do not update the state file")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        now = nse_calendar.parse_now(a.now)
        if a.days <= 0:
            raise NewsError("--days must be above 0")
        if a.symbols:
            symbols = []
            for s in a.symbols:
                n = nse_symbols.normalize(s)
                if n not in symbols:
                    symbols.append(n)
        else:
            symbols = watchlist.watch_list(a.kite_dir, a.targets)
        if not symbols:
            raise NewsError("which stocks? pass --symbols INFY TCS, or save Kite holdings / write trader/targets.json")
        if a.file and len(symbols) != 1:
            raise NewsError("--file holds one symbol's announcements: pass exactly one --symbols")
        client = None if (a.file or a.offline) else nse.Client()
        items, errors, blocked = collect(symbols, client, a.offline, a.file)
        state = load_state(a.state)
        shown = select(items, state, now, a.days, a.all)
        if not a.dry_run:
            for i in items:
                state["seen"].setdefault(i["id"], now.isoformat())
            save_state(a.state, state, now)
    except (NewsError, nse.NseError, nse_calendar.CalendarError, nse_symbols.SymbolError, watchlist.WatchError) as e:
        print("news.py: %s" % e, file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps({"items": [dict(i, when=i["when"].isoformat()) for i in shown], "errors": errors,
                          "blocked": blocked}, indent=2))
    else:
        print(render(shown, errors, blocked))
    if blocked:
        return 2
    return 0 if shown else 1


if __name__ == "__main__":
    sys.exit(main())
```

Replace `trader-news/SKILL.md` with:

````markdown
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
````

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_news.py -v`
Expected: all 10 tests pass. Then run `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`.

```bash
git add -A trader-news tests/test_news.py tests/test_repo.py tests/fixtures/trader-news
git commit -m "Convert trader-news to NSE announcements; add shared watchlist helper" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 2: trader-pelosi becomes trader-insider

**Files:**
- Rename: `git mv trader-pelosi trader-insider`, then remove `trader-insider/ptr.py`, `tests/test_pelosi.py` and `tests/fixtures/trader-pelosi/`
- Copy (unchanged): `trader-alerts/{kite_snapshot,nse,nse_calendar,nse_symbols,rupees}.py` and `trader-news/watchlist.py` into `trader-insider/`
- Create: `trader-insider/insider.py`, `tests/test_insider.py`, `tests/fixtures/trader-insider/{pit-INFY.json,pit-ABC.json,bulk.csv,block.csv}`
- Replace: `trader-insider/SKILL.md`
- Modify: `tests/test_repo.py` (`SKILLS`, `ORDER_PATH`, the LIVE-docs list)

**Interfaces:**
- Consumes: `watchlist.watch_list` (Task 1), `nse.Client`, `read_file`, `read_json_file`, `NseBlocked`, and `rupees.inr`
- Produces:
  - `insider.parse_pit(doc, symbol) -> [row]`, where a row is `{id, kind: "insider", symbol, when, name, category, mode, side, shares, value, after_pct, security, market, insider}`
  - `insider.parse_deals(text, kind) -> [row]`, where a row is `{id, kind: bulk|block, symbol, when, name, side, shares, price}`
  - `insider.fetch_pit`, `insider.fetch_deals`
  - CLI commands `check` (default), `pit` and `deals`. Exit codes 0, 1, 2 as in news. The command writes `trader/insider.json`.

- [ ] **Step 1: Rename and write the fixtures**

```bash
git mv trader-pelosi trader-insider
git rm -q -f trader-insider/ptr.py
git rm -q tests/test_pelosi.py
git rm -q -r tests/fixtures/trader-pelosi
```

`pit-INFY.json`, `bulk.csv` and `block.csv` are real NSE answers (2026-10-27). `pit-ABC.json` is synthetic, labelled as such, and covers the promoter and director cases.

`tests/fixtures/trader-insider/pit-INFY.json`:

```json
{
 "acqNameList": [
  "Infosys Employee benefits Trust",
  "Atul Chaturvedi",
  "Binod Choudhary",
  "Joseph J. Alenchery",
  "Venkateshwaran Ananthakrishnan",
  "Raghavendra K A",
  "Inderpreet Sawhney",
  "Infosys Employee Benefits Trust",
  "Abhijit Sarkar",
  "Anand Santhanam",
  "Amitabh Pushparaj Mudaliar",
  "Ambeshwar Nath",
  "Ajay S Bhandari"
 ],
 "data": [
  {
   "acqMode": "Off Market",
   "acqName": "Infosys Employee benefits Trust",
   "acqfromDt": "27-Mar-2026",
   "acqtoDt": "27-Mar-2026",
   "afterAcqSharesNo": "8668508",
   "afterAcqSharesPer": "0.21",
   "anex": "7(2)",
   "befAcqSharesNo": "8668483",
   "befAcqSharesPer": "0.21",
   "buyQuantity": "0",
   "buyValue": "0",
   "company": "Infosys Limited",
   "date": "06-Apr-2026 16:07",
   "derivativeType": "-",
   "did": "570208",
   "exchange": "NA",
   "intimDt": "02-Apr-2026",
   "personCategory": "Other",
   "pid": "1197666",
   "remarks": "-",
   "secAcq": "25",
   "secType": "ADR/GDR/FCCB",
   "secVal": "31743",
   "securitiesTypePost": "ADR/GDR/FCCB",
   "sellValue": "0",
   "sellquantity": "0",
   "symbol": "INFY",
   "tdpDerivativeContractType": "-",
   "tdpTransactionType": "-",
   "tkdAcqm": null,
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/IT_1197666_1646241_06042026040732_WEB.xml",
   "xbrlFileSize": "11.57 KB"
  },
  {
   "acqMode": "ESOP",
   "acqName": "Atul Chaturvedi",
   "acqfromDt": "02-Apr-2026",
   "acqtoDt": "02-Apr-2026",
   "afterAcqSharesNo": "2061",
   "afterAcqSharesPer": "0",
   "anex": "7(2)",
   "befAcqSharesNo": "Nil",
   "befAcqSharesPer": "0",
   "buyQuantity": "0",
   "buyValue": "0",
   "company": "Infosys Limited",
   "date": "06-Apr-2026 16:07",
   "derivativeType": "-",
   "did": "570210",
   "exchange": "NA",
   "intimDt": "02-Apr-2026",
   "personCategory": "Other",
   "pid": "1197666",
   "remarks": "-",
   "secAcq": "2061",
   "secType": "ADR/GDR/FCCB",
   "secVal": "2632737",
   "securitiesTypePost": "ADR/GDR/FCCB",
   "sellValue": "0",
   "sellquantity": "0",
   "symbol": "INFY",
   "tdpDerivativeContractType": "-",
   "tdpTransactionType": "-",
   "tkdAcqm": null,
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/IT_1197666_1646241_06042026040732_WEB.xml",
   "xbrlFileSize": "11.57 KB"
  },
  {
   "acqMode": "Off Market",
   "acqName": "Infosys Employee benefits Trust",
   "acqfromDt": "30-Mar-2026",
   "acqtoDt": "30-Mar-2026",
   "afterAcqSharesNo": "8650911",
   "afterAcqSharesPer": "0.21",
   "anex": "7(2)",
   "befAcqSharesNo": "8668508",
   "befAcqSharesPer": "0.21",
   "buyQuantity": "0",
   "buyValue": "0",
   "company": "Infosys Limited",
   "date": "06-Apr-2026 16:07",
   "derivativeType": "-",
   "did": "570209",
   "exchange": "NA",
   "intimDt": "02-Apr-2026",
   "personCategory": "Other",
   "pid": "1197666",
   "remarks": "-",
   "secAcq": "17597",
   "secType": "ADR/GDR/FCCB",
   "secVal": "22006808",
   "securitiesTypePost": "ADR/GDR/FCCB",
   "sellValue": "0",
   "sellquantity": "0",
   "symbol": "INFY",
   "tdpDerivativeContractType": "-",
   "tdpTransactionType": "-",
   "tkdAcqm": null,
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/IT_1197666_1646241_06042026040732_WEB.xml",
   "xbrlFileSize": "11.57 KB"
  },
  {
   "acqMode": "ESOP",
   "acqName": "Binod Choudhary",
   "acqfromDt": "18-Mar-2026",
   "acqtoDt": "18-Mar-2026",
   "afterAcqSharesNo": "31959",
   "afterAcqSharesPer": "0",
   "anex": "7(2)",
   "befAcqSharesNo": "28781",
   "befAcqSharesPer": "0",
   "buyQuantity": "0",
   "buyValue": "0",
   "company": "Infosys Limited",
   "date": "23-Mar-2026 20:16",
   "derivativeType": "-",
   "did": "568115",
   "exchange": "NA",
   "intimDt": "23-Mar-2026",
   "personCategory": "-",
   "pid": "1196521",
   "remarks": "-",
   "secAcq": "3178",
   "secType": "ADR/GDR/FCCB",
   "secVal": "4274944",
   "securitiesTypePost": "ADR/GDR/FCCB",
   "sellValue": "0",
   "sellquantity": "0",
   "symbol": "INFY",
   "tdpDerivativeContractType": "-",
   "tdpTransactionType": "Buy",
   "tkdAcqm": null,
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/IT_1196521_1638999_23032026081630_WEB.xml",
   "xbrlFileSize": "14.86 KB"
  },
  {
   "acqMode": "ESOP",
   "acqName": "Joseph J. Alenchery",
   "acqfromDt": "18-Mar-2026",
   "acqtoDt": "18-Mar-2026",
   "afterAcqSharesNo": "11178",
   "afterAcqSharesPer": "0",
   "anex": "7(2)",
   "befAcqSharesNo": "10252",
   "befAcqSharesPer": "0",
   "buyQuantity": "0",
   "buyValue": "0",
   "company": "Infosys Limited",
   "date": "23-Mar-2026 20:16",
   "derivativeType": "-",
   "did": "568118",
   "exchange": "NA",
   "intimDt": "23-Mar-2026",
   "personCategory": "-",
   "pid": "1196521",
   "remarks": "-",
   "secAcq": "926",
   "secType": "ADR/GDR/FCCB",
   "secVal": "1245625",
   "securitiesTypePost": "ADR/GDR/FCCB",
   "sellValue": "0",
   "sellquantity": "0",
   "symbol": "INFY",
   "tdpDerivativeContractType": "-",
   "tdpTransactionType": "Buy",
   "tkdAcqm": null,
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/IT_1196521_1638999_23032026081630_WEB.xml",
   "xbrlFileSize": "14.86 KB"
  }
 ]
}
```

`tests/fixtures/trader-insider/pit-ABC.json`:

```json
{"_note": "synthetic rows for tests, in the shape of NSE's PIT answer", "acqNameList": [], "data": [
 {"pid": "9001", "did": "1", "symbol": "ABC", "company": "ABC Limited", "acqName": "Promoter Holdings LLP", "personCategory": "Promoter Group", "acqMode": "Market Purchase", "tdpTransactionType": "-", "buyQuantity": "50000", "sellquantity": "0", "secAcq": "50000", "secVal": "7500000", "afterAcqSharesPer": "52.40", "secType": "Equity Shares", "date": "20-Oct-2026 18:05"},
 {"pid": "9002", "did": "1", "symbol": "ABC", "company": "ABC Limited", "acqName": "A Director", "personCategory": "Director", "acqMode": "Market Sale", "tdpTransactionType": "-", "buyQuantity": "0", "sellquantity": "1200", "secAcq": "1200", "secVal": "180000", "afterAcqSharesPer": "0.01", "secType": "Equity Shares", "date": "21-Oct-2026 10:00"},
 {"pid": "9003", "did": "1", "symbol": "ABC", "company": "ABC Limited", "acqName": "An Employee", "personCategory": "Employees/Designated Persons", "acqMode": "ESOP", "tdpTransactionType": "-", "buyQuantity": "0", "sellquantity": "0", "secAcq": "300", "secVal": "-", "afterAcqSharesPer": "-", "secType": "Equity Shares", "date": "05-Aug-2026 12:00"}
]}
```

`tests/fixtures/trader-insider/bulk.csv`:

```
Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price,Remarks
26-OCT-2026,APOLLO,Apollo Micro Systems Ltd,QE SECURITIES LLP,BUY,2465951,410.93,-
26-OCT-2026,APOLLO,Apollo Micro Systems Ltd,JUMP TRADING FINANCIAL INDIA PRIVATE LIMITED,BUY,2641960,411.53,-
26-OCT-2026,BELDING,Belding India Limited,SETU SECURITIES PVT LTD,BUY,385019,872.10,-
26-OCT-2026,BELDING,Belding India Limited,IRAGE BROKING SERVICES LLP,BUY,401,861.60,-
26-OCT-2026,BMISL,Bench Mark Infotech Ser L,ANIRUDH MOHTA,BUY,73200,188.40,-
26-OCT-2026,BMLL,Bio Medica Laboratories L,OSWAL ENERGIES LIMITED,BUY,144000,146.00,-
```

`tests/fixtures/trader-insider/block.csv`:

```
Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price
NO RECORDS,,,,,,
```


- [ ] **Step 2: Write the failing tests**

`tests/test_insider.py`:

```python
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

ins = load("trader-insider", "insider")

IDIR = os.path.join(FIX, "trader-insider")
NOW = "2026-10-26T18:00"


def read(name):
    with open(os.path.join(IDIR, name)) as fh:
        return fh.read()


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = ins.main(argv)
    return code, out.getvalue(), err.getvalue()


class Pit(unittest.TestCase):
    def test_real_infy_rows(self):
        rows = ins.parse_pit(json.loads(read("pit-INFY.json")), "INFY")
        self.assertEqual(len(rows), 5)
        self.assertEqual(len({r["id"] for r in rows}), 5)
        first = rows[0]
        self.assertEqual((first["name"], first["mode"], first["side"], first["shares"], first["value"]),
                         ("Infosys Employee benefits Trust", "Off Market", "-", 25, 31743.0))
        self.assertEqual(first["when"].strftime("%Y-%m-%d %H:%M"), "2026-04-06 16:07")
        self.assertFalse(any(r["market"] for r in rows))
        self.assertFalse(any(r["insider"] for r in rows))
        self.assertEqual([r["side"] for r in rows[3:]], ["BUY", "BUY"])

    def test_promoter_market_buy_and_director_sale(self):
        rows = ins.parse_pit(json.loads(read("pit-ABC.json")), "ABC")
        self.assertEqual([(r["side"], r["market"], r["insider"]) for r in rows],
                         [("BUY", True, True), ("SELL", True, True), ("-", False, True)])
        self.assertIsNone(rows[2]["value"])

    def test_not_a_pit_answer(self):
        with self.assertRaises(ins.InsiderError):
            ins.parse_pit([{"x": 1}], "INFY")


class Deals(unittest.TestCase):
    def test_real_bulk_and_empty_block(self):
        bulk = ins.parse_deals(read("bulk.csv"), "bulk")
        self.assertEqual(len(bulk), 6)
        self.assertEqual((bulk[0]["symbol"], bulk[0]["name"], bulk[0]["side"], bulk[0]["shares"], bulk[0]["price"]),
                         ("APOLLO", "QE SECURITIES LLP", "BUY", 2465951, 410.93))
        self.assertEqual(ins.parse_deals(read("block.csv"), "block"), [])
        self.assertEqual(len({r["id"] for r in bulk}), 6)

    def test_bad_csv(self):
        with self.assertRaises(ins.InsiderError):
            ins.parse_deals("<html>blocked</html>\n", "bulk")
        with self.assertRaises(ins.InsiderError):
            ins.parse_deals("Date,Symbol,Client Name\nyesterday,ABC,X\n", "bulk")


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "state.json")
        self.out = os.path.join(self.tmp.name, "insider.json")

    def tearDown(self):
        self.tmp.cleanup()

    def ins(self, *args):
        return run(list(args) + ["--offline", IDIR, "--state", self.state, "--out", self.out, "--now", NOW])

    def test_check_alerts_once_and_writes_the_rows(self):
        code, text, _ = self.ins("--symbols", "ABC", "APOLLO", "--days", "30")
        self.assertEqual(code, 0)
        self.assertIn("2026-10-21 10:00  ABC        insider SELL A Director 1200 shares (Equity Shares), Market Sale, "
                      "Director [market] [insider]", text)
        self.assertIn("APOLLO     bulk deal BUY 2465951 shares at Rs 410.93 by QE SECURITIES LLP", text)
        self.assertNotIn("An Employee", text)
        self.assertIn("error: APOLLO: cannot read", text)
        self.assertIn("Not financial advice", text)
        with open(self.out) as fh:
            self.assertEqual(len(json.load(fh)["rows"]), 4)
        code, text, _ = self.ins("--symbols", "ABC", "APOLLO", "--days", "30")
        self.assertEqual(code, 1)
        self.assertIn("Nothing new.", text)

    def test_deals_for_every_symbol(self):
        code, text, _ = self.ins("deals", "--symbols", "INFY", "--json", "--dry-run")
        self.assertEqual(json.loads(text)["rows"], [])
        code, text, _ = self.ins("deals", "--every-symbol", "--json", "--dry-run")
        self.assertEqual(len(json.loads(text)["rows"]), 6)
        self.assertFalse(os.path.exists(self.state))

    def test_file_only_for_one_symbol_pit(self):
        path = os.path.join(IDIR, "pit-INFY.json")
        code, text, _ = run(["pit", "--symbols", "INFY", "--file", path, "--days", "365", "--state", self.state,
                             "--out", self.out, "--now", NOW])
        self.assertEqual(code, 0)
        self.assertIn("Atul Chaturvedi", text)
        code, _, err = run(["deals", "--symbols", "INFY", "--file", path, "--now", NOW])
        self.assertEqual(code, 1)
        self.assertIn("--file holds one symbol", err)


class Blocked(unittest.TestCase):
    def test_blocked_requests_are_reported(self):
        class Client:
            def get_json(self, url):
                raise ins.nse.NseBlocked(url, "HTTP 403")

            def get_text(self, url, cookie=True):
                raise ins.nse.NseBlocked(url, "HTTP 503")
        _, _, blocked = ins.fetch_pit(["INFY"], Client())
        self.assertIn("symbol=INFY", blocked[0])
        _, _, blocked = ins.fetch_deals(Client())
        self.assertEqual(len(blocked), 2)
        self.assertIn("--file", blocked[0])


if __name__ == "__main__":
    unittest.main()
```

- In `tests/test_repo.py`, replace:

```
SKILLS = ["trader-copycat", "trader-news", "trader-budget", "trader-pelosi", "trader-analyst",
```

  with:

```
SKILLS = ["trader-copycat", "trader-news", "trader-budget", "trader-insider", "trader-analyst",
```

- In `tests/test_repo.py`, replace:

```
ORDER_PATH = ["trader-copycat", "trader-budget", "trader-pelosi", "trader-risk", "trader-broker",
```

  with:

```
ORDER_PATH = ["trader-copycat", "trader-budget", "trader-insider", "trader-risk", "trader-broker",
```

- In `tests/test_repo.py`, replace:

```
        for s in ("trader-budget", "trader-risk", "trader-broker", "trader-rebalance", "trader-tax"):
```

  with:

```
        for s in ("trader-budget", "trader-risk", "trader-broker", "trader-rebalance", "trader-tax", "trader-insider"):
```


- [ ] **Step 3: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_insider.py -v`
Expected: an ERROR, because `trader-insider/insider.py` does not exist. `test_repo` fails until the SKILL.md is renamed.

- [ ] **Step 4: Implement**

```bash
cp trader-alerts/kite_snapshot.py trader-alerts/nse.py trader-alerts/nse_calendar.py trader-alerts/nse_symbols.py trader-alerts/rupees.py trader-insider/
cp trader-news/watchlist.py trader-insider/
```

`trader-insider/insider.py`:

```python
#!/usr/bin/env python3
"""Smart-money tracker for trader-insider: SEBI insider trades and NSE bulk and block deals.

    python3 insider.py                          # both, for your Kite holdings and trader/targets.json
    python3 insider.py pit --symbols INFY       # insider trades (SEBI PIT disclosures) for INFY
    python3 insider.py pit --symbols INFY --file pit.json   # NSE blocked you: the page saved in a browser
    python3 insider.py deals                    # today's bulk and block deals in your stocks
    python3 insider.py deals --every-symbol     # every bulk and block deal today

Sources:
  insider trades  https://www.nseindia.com/api/corporates-pit?index=equities&symbol=<SYMBOL>
                  (one request per symbol; NSE needs its cookie, see nse.py)
  bulk deals      https://archives.nseindia.com/content/equities/bulk.csv   (today, no cookie)
  block deals     https://archives.nseindia.com/content/equities/block.csv  (today, no cookie)

An insider trade is a disclosure by a promoter, director, key person or
their relatives under SEBI's insider-trading rules. A [market] tag marks a
market purchase or sale, the kind that says the most; ESOP allotments and
off-market transfers are shown but untagged. Bulk deals are trades of 0.5%
or more of a company's shares on one day; block deals are big trades done in
the block window.

State: trader/state/insider.json remembers what you have seen, so each
filing alerts once. trader/insider.json holds the latest rows for the
other skills. Exit code 0 when something new is shown, 1 when nothing is
new, 2 when NSE blocked a request (the message names the URL and --file).

These are other people's trades, reported after the fact. Copying them is
your own decision: not financial advice.
"""

import argparse
import csv
import datetime
import hashlib
import io
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
import watchlist
from rupees import inr

PIT_URL = "https://www.nseindia.com/api/corporates-pit?index=equities&symbol=%s"
BULK_URL = "https://archives.nseindia.com/content/equities/bulk.csv"
BLOCK_URL = "https://archives.nseindia.com/content/equities/block.csv"
INSIDERS = ("promoter", "director", "kmp", "key managerial", "immediate relative", "designated person")
KEEP_DAYS = 90


class InsiderError(Exception):
    pass


def _int(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _num(v):
    try:
        x = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def side_of(r):
    t = str(r.get("tdpTransactionType") or "").strip().lower()
    if t in ("buy", "sell"):
        return t.upper()
    if (_int(r.get("buyQuantity")) or 0) > 0:
        return "BUY"
    if (_int(r.get("sellquantity")) or 0) > 0:
        return "SELL"
    mode = str(r.get("acqMode") or "").lower()
    if "sale" in mode or "sell" in mode:
        return "SELL"
    if "purchase" in mode or "buy" in mode:
        return "BUY"
    return "-"


def parse_pit(doc, symbol):
    """NSE PIT JSON ({"data": [...]}) -> rows {id, kind: "insider", symbol, when, name, category, mode, side,
    shares, value, after_pct, security, market, insider}."""
    rows = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        raise InsiderError("the insider trades for %s are not NSE's PIT answer (no data list)" % symbol)
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            when = datetime.datetime.strptime(str(r.get("date"))[:17], "%d-%b-%Y %H:%M")
        except ValueError:
            continue
        cat = str(r.get("personCategory") or "-").strip()
        mode = str(r.get("acqMode") or "-").strip()
        out.append({"id": "pit:%s:%s" % (r.get("pid"), r.get("did")), "kind": "insider",
                    "symbol": str(r.get("symbol") or symbol).upper(), "when": when.replace(tzinfo=nse_calendar.IST),
                    "name": str(r.get("acqName") or "").strip(), "category": cat, "mode": mode, "side": side_of(r),
                    "shares": _int(r.get("secAcq")), "value": _num(r.get("secVal")),
                    "after_pct": _num(r.get("afterAcqSharesPer")), "security": str(r.get("secType") or "").strip(),
                    "market": mode.lower().startswith("market "),
                    "insider": any(w in cat.lower() for w in INSIDERS)})
    return out


def parse_deals(text, kind):
    """NSE bulk.csv / block.csv text -> rows {id, kind, symbol, when, name, side, shares, price}. 'NO RECORDS' is none."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    fields = [(f or "").strip().lower() for f in (reader.fieldnames or [])]
    if "symbol" not in fields or "client name" not in fields:
        raise InsiderError("this is not NSE's %s deals CSV (no Symbol / Client Name columns)" % kind)
    out = []
    for r in reader:
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items() if k is not None}
        if not r.get("symbol") or r.get("date", "").upper().startswith("NO RECORDS"):
            continue
        try:
            when = datetime.datetime.strptime(r["date"], "%d-%b-%Y")
        except ValueError:
            raise InsiderError("%s deals: %r is not a date like 26-OCT-2026" % (kind, r.get("date")))
        key = "|".join((kind, r["date"], r["symbol"], r.get("client name", ""), r.get("buy/sell", ""),
                        r.get("quantity traded", ""), r.get("trade price / wght. avg. price", "")))
        out.append({"id": "deal:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16], "kind": kind,
                    "symbol": r["symbol"].upper(), "when": when.replace(tzinfo=nse_calendar.IST),
                    "name": r.get("client name", ""), "side": r.get("buy/sell", "").upper(),
                    "shares": _int(r.get("quantity traded")), "price": _num(r.get("trade price / wght. avg. price"))})
    return out


def load_state(path):
    if not path or not os.path.exists(path):
        return {"seen": {}}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except ValueError as e:
        raise InsiderError("%s is not valid JSON: %s" % (path, e))
    return doc if isinstance(doc.get("seen"), dict) else {"seen": {}}


def save_state(path, state, now):
    cut = now - datetime.timedelta(days=KEEP_DAYS)
    state["seen"] = {k: v for k, v in state["seen"].items() if nse_calendar.parse_iso(v) >= cut}
    _write(path, state)


def _write(path, doc):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")


def fetch_pit(symbols, client=None, file=None, offline=None):
    rows, errors, blocked = [], [], []
    for sym in symbols:
        try:
            if file:
                doc = nse.read_json_file(file)
            elif offline:
                doc = nse.read_json_file(os.path.join(offline, "pit-%s.json" % sym))
            else:
                doc = client.get_json(PIT_URL % sym)
            rows += parse_pit(doc, sym)
        except nse.NseBlocked as e:
            blocked.append(str(e))
        except (InsiderError, nse.NseError) as e:
            errors.append("%s: %s" % (sym, e))
    return rows, errors, blocked


def fetch_deals(client=None, bulk_file=None, block_file=None, offline=None):
    rows, errors, blocked = [], [], []
    for kind, url, file, name in (("bulk", BULK_URL, bulk_file, "bulk.csv"), ("block", BLOCK_URL, block_file, "block.csv")):
        try:
            if file:
                text = nse.read_file(file)
            elif offline:
                text = nse.read_file(os.path.join(offline, name))
            else:
                text = client.get_text(url, cookie=False)
            rows += parse_deals(text, kind)
        except nse.NseBlocked as e:
            blocked.append(str(e))
        except (InsiderError, nse.NseError) as e:
            errors.append("%s deals: %s" % (kind, e))
    return rows, errors, blocked


def render(rows, errors, blocked):
    lines = []
    for r in rows:
        when = r["when"].strftime("%Y-%m-%d %H:%M" if r["kind"] == "insider" else "%Y-%m-%d")
        if r["kind"] == "insider":
            tags = (" [market]" if r["market"] else "") + (" [insider]" if r["insider"] else "")
            lines.append("%s  %-10s insider %s %s %s shares (%s), %s, %s%s" % (
                when, r["symbol"], r["side"], r["name"], r["shares"] if r["shares"] is not None else "?",
                r["security"] or "-", r["mode"], r["category"], tags))
            if r["value"] is not None:
                lines.append("    value %s%s" % (inr(r["value"]), (", holds %.2f%% after" % r["after_pct"])
                                                 if r["after_pct"] is not None else ""))
        else:
            lines.append("%s  %-10s %s deal %s %s shares at %s by %s" % (
                when, r["symbol"], r["kind"], r["side"], r["shares"], inr(r["price"]) if r["price"] else "?", r["name"]))
    if not rows:
        lines.append("Nothing new.")
    for e in errors:
        lines.append("error: " + e)
    for b in blocked:
        lines.append("blocked: " + b)
    lines.append("These are other people's trades, reported after the fact. Not financial advice.")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Insider trades and bulk/block deals in your stocks (trader-insider).")
    ap.add_argument("cmd", nargs="?", default="check", choices=["check", "pit", "deals"])
    ap.add_argument("--symbols", nargs="*", help="default: Kite holdings and trader/targets.json")
    ap.add_argument("--every-symbol", action="store_true", help="deals: show every symbol, not just yours")
    ap.add_argument("--days", type=float, default=30, help="insider trades disclosed in the last N days")
    ap.add_argument("--file", help="pit: NSE's PIT JSON saved from a browser (one symbol)")
    ap.add_argument("--bulk-file", help="deals: bulk.csv saved from a browser")
    ap.add_argument("--block-file", help="deals: block.csv saved from a browser")
    ap.add_argument("--offline", metavar="DIR", help="read pit-<SYMBOL>.json, bulk.csv and block.csv from DIR")
    ap.add_argument("--kite-dir", default=kite_snapshot.DIR)
    ap.add_argument("--targets", default="trader/targets.json")
    ap.add_argument("--state", default="trader/state/insider.json")
    ap.add_argument("--out", default="trader/insider.json")
    ap.add_argument("--all", action="store_true", help="show seen rows too")
    ap.add_argument("--now", help="pretend it is this time (ISO, IST; tests only, needs TRADER_TEST_CLOCK=1)")
    ap.add_argument("--dry-run", action="store_true", help="write no state and no trader/insider.json")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        now = nse_calendar.parse_now(a.now)
        if a.days <= 0:
            raise InsiderError("--days must be above 0")
        symbols = []
        for s in (a.symbols or watchlist.watch_list(a.kite_dir, a.targets)):
            n = nse_symbols.normalize(s)
            if n not in symbols:
                symbols.append(n)
        if a.cmd in ("check", "pit") and not symbols:
            raise InsiderError("which stocks? pass --symbols INFY TCS, or save Kite holdings / write trader/targets.json")
        if a.file and (a.cmd != "pit" or len(symbols) != 1):
            raise InsiderError("--file holds one symbol's insider trades: use it with pit and exactly one --symbols")
        client = None if (a.offline or (a.file and a.cmd == "pit")) else nse.Client()
        rows, errors, blocked = [], [], []
        if a.cmd in ("check", "pit"):
            r, e, b = fetch_pit(symbols, client, a.file, a.offline)
            start = now - datetime.timedelta(days=a.days)
            rows += [x for x in r if x["when"] >= start]
            errors += e
            blocked += b
        if a.cmd in ("check", "deals"):
            r, e, b = fetch_deals(client, a.bulk_file, a.block_file, a.offline)
            rows += [x for x in r if a.every_symbol or x["symbol"] in symbols]
            errors += e
            blocked += b
        state = load_state(a.state)
        shown = [x for x in rows if a.all or x["id"] not in state["seen"]]
        shown.sort(key=lambda x: (x["when"], x["id"]), reverse=True)
        if not a.dry_run:
            for x in rows:
                state["seen"].setdefault(x["id"], now.isoformat())
            save_state(a.state, state, now)
            _write(a.out, {"as_of": now.isoformat(), "rows": [dict(x, when=x["when"].isoformat()) for x in rows]})
    except (InsiderError, nse.NseError, nse_calendar.CalendarError, nse_symbols.SymbolError, watchlist.WatchError) as e:
        print("insider.py: %s" % e, file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps({"rows": [dict(x, when=x["when"].isoformat()) for x in shown], "errors": errors,
                          "blocked": blocked}, indent=2))
    else:
        print(render(shown, errors, blocked))
    if blocked:
        return 2
    return 0 if shown else 1


if __name__ == "__main__":
    sys.exit(main())
```

Replace `trader-insider/SKILL.md` with:

````markdown
---
name: trader-insider
description: >-
  Smart Money Tracker for NSE stocks. Reads SEBI insider-trading (PIT)
  disclosures for your stocks (promoters, promoter group, directors, key
  managerial people and their relatives) and NSE's daily bulk and block
  deals, tags market purchases and sales by insiders, and alerts once per
  new filing. Writes trader/insider.json for the other skills. Use when the
  user says "are promoters buying", "insider trades in INFY", "who bought
  TCS today", "bulk deals", "block deals", "smart money", or on a schedule
  after the close.
argument-hint: "[symbols]"
---

# trader-insider

The Smart Money Tracker shows what the people closest to a company, and
the biggest traders of the day, are doing in your stocks. These trades are
disclosed after the fact: they are information, not a signal to copy.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/insider.py"                         # both, Kite holdings + targets
python3 "${CLAUDE_SKILL_DIR}/insider.py" pit --symbols INFY --days 90
python3 "${CLAUDE_SKILL_DIR}/insider.py" pit --symbols INFY --file pit.json
python3 "${CLAUDE_SKILL_DIR}/insider.py" deals                   # today's bulk and block deals in your stocks
python3 "${CLAUDE_SKILL_DIR}/insider.py" deals --every-symbol
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/kite/holdings.json`, `trader/targets.json` | the stocks to watch |
| `trader/state/insider.json` | what you have seen (90 days), so each filing alerts once |
| `trader/insider.json` | the latest rows, for the other skills |

## Where the data comes from

- Insider trades: `https://www.nseindia.com/api/corporates-pit?index=equities&symbol=<SYMBOL>`,
  one request per stock. NSE often blocks scripts: the tool prints the
  address and exits 2. Ask the user to open it in a browser, save it, and
  run `pit --symbols <SYMBOL> --file <saved file>`.
- Bulk deals: `https://archives.nseindia.com/content/equities/bulk.csv` and
  block deals: `.../block.csv`, today only, no cookie needed. `--bulk-file`
  and `--block-file` take saved copies.

## How to read it

- `[market]` marks a market purchase or sale, the kind that tells you the
  most. ESOP allotments and off-market transfers are shown but untagged.
- `[insider]` marks a promoter, promoter group, director, key managerial
  person, designated person or a relative.
- A bulk deal is 0.5% or more of the company's shares in one day by one
  client. A block deal is a large trade in the block window.

## Steps

1. Run `insider.py` (exit 0 new, 1 nothing new, 2 NSE blocked a request).
2. Report each new row in one line: who, buy or sell, how many shares, the
   value and what they hold after. Lead with `[market] [insider]` rows.
3. Never suggest copying a trade as if it were advice. If the user wants to
   act, the normal path runs: `/trader-budget`, `/trader-risk`, then
   `/trader-broker` with an explicit yes for each LIVE order.

## Example

For ABC (test data), a promoter-group market purchase of 50,000 shares on
20 Oct 2026 shows as `BUY ... Market Purchase, Promoter Group [market]
[insider]`, and a director's market sale of 1,200 shares the next day as a
SELL with the same tags. On 26 Oct 2026, APOLLO had two bulk-deal buys of
about 25 lakh shares each.

## What it never does

It never places an order, never calls a trade "smart" or "a signal", and
never hides that disclosures arrive days after the trade.

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

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_insider.py -v`
Expected: all 9 tests pass. Then run `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .` (test_repo included).

```bash
git add -A trader-insider trader-pelosi tests/test_insider.py tests/test_pelosi.py tests/test_repo.py tests/fixtures/trader-insider tests/fixtures/trader-pelosi
git commit -m "Replace trader-pelosi with trader-insider: SEBI insider trades and NSE bulk/block deals" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 3: README and CLAUDE.md for news and insider

**Files:**
- Modify: `README.md`, `CLAUDE.md`

Phase 5 rewrites the README story text, including the "Pelosi" paragraphs. This task changes only the table rows, the command lines, the layout lines and the skill mentions, so that `/trader-insider` appears as the repo test requires.

- [ ] **Step 1: Apply the replacements**

Each old text must match exactly once.

- In `README.md`, replace:

```
| `/trader-news` | News Monitor | Watches headlines and SEC filings (8-Ks) for every stock you hold and flags what touches them. |
```

  with:

```
| `/trader-news` | News Monitor | Watches NSE corporate announcements (results, dividends, board meetings, deals, pledges) for every stock you hold and shows each new one once. |
```

- In `README.md`, replace:

```
| `/trader-pelosi` | Pelosi Tracker | Reads Congress's stock-trade disclosures (House PTRs) as soon as they post, turns each PDF into clean rows and alerts you once per new filing. |
```

  with:

```
| `/trader-insider` | Smart Money Tracker | Reads SEBI insider-trade disclosures (promoters, directors, key people) and NSE bulk and block deals in your stocks, and alerts you once per new filing. |
```

- In `README.md`, replace:

```
news / pelosi / alerts                          (watch, on a schedule)
```

  with:

```
news / insider / alerts                         (watch, on a schedule)
```

- In `README.md`, replace:

```
   **`/trader-pelosi`** alerts you when a new disclosure posts, and
```

  with:

```
   **`/trader-insider`** alerts you when an insider trade or bulk deal posts, and
```

- In `README.md`, replace:

```
python3 trader-news/news.py --tickers AAPL AXP GOOGL KO BAC --hours 24 # headlines + 8-Ks
```

  with:

```
python3 trader-news/news.py --symbols INFY TCS --days 7                  # NSE announcements
```

- In `README.md`, replace:

```
python3 trader-pelosi/ptr.py index --member pelosi                     # her PTRs this year
```

  with:

```
python3 trader-insider/insider.py --symbols INFY                       # insider trades + bulk/block deals
```

- In `README.md`, replace:

```
python3 trader-pelosi/ptr.py --help                                    # new, fetch, parse
```

  with:

(nothing: delete the line)

- In `README.md`, replace:

```
trader-news/       SKILL.md, news.py
```

  with:

```
trader-news/       SKILL.md, news.py, watchlist.py
```

- In `README.md`, replace:

```
trader-pelosi/     SKILL.md, ptr.py
```

  with:

```
trader-insider/    SKILL.md, insider.py
```

- In `CLAUDE.md`, replace:

```
and the portfolio skills trader-rebalance and trader-tax (Kite holdings, Zerodha Console tradebook, Indian capital gains).
```

  with:

```
the portfolio skills trader-rebalance and trader-tax (Kite holdings, Zerodha Console tradebook, Indian capital gains), and trader-news and trader-insider (NSE announcements, SEBI insider trades, bulk and block deals; trader-pelosi was renamed trader-insider).
```

- In `CLAUDE.md`, replace:

```
`rupees.py`, and `charges.py` whose source copy is in trader-budget) are copied
```

  with:

```
`rupees.py`, `charges.py` whose source copy is in trader-budget, and `watchlist.py` whose source copy is in trader-news) are copied
```


- [ ] **Step 2: Verify and commit**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache . && ! grep -rl "$(printf '\342\200\224')" trader-* tests docs CLAUDE.md README.md`
Expected: `OK` (316 tests), `All checks passed!`, and no file names printed.

Smoke test, outside the repo:

```bash
R=/home/ubuntu/stock-market/trader-skill; T=$(mktemp -d) && cd "$T" && export TRADER_TEST_CLOCK=1
python3 "$R/trader-news/news.py" --symbols INFY --offline "$R/tests/fixtures/trader-news" --now 2026-10-26T10:00 --days 7
python3 "$R/trader-insider/insider.py" --symbols ABC APOLLO --offline "$R/tests/fixtures/trader-insider" --now 2026-10-26T18:00
```

Expected:
- news shows the two INFY items from the last week.
- insider shows the ABC director and promoter rows tagged `[market] [insider]`, and the two APOLLO bulk deals.

```bash
git add README.md CLAUDE.md
git commit -m "Document Indian news and insider skills in README and CLAUDE.md" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

