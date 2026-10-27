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

Every run asks NSE again (no daily cache), so a schedule sees new filings.

State: trader/state/insider.json remembers what you have seen, so each
filing alerts once. trader/insider.json holds the latest rows for the
other skills. Exit code 0 when something new is shown and nothing failed, 1
when nothing is new and everything was checked, 2 when anything could not be
checked (an error, or NSE blocked a request; the message names the URL and
--file).

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
import urllib.parse

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
                doc = client.get_json(PIT_URL % urllib.parse.quote(sym, safe=""), cache=False)
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
                text = client.get_text(url, cookie=False, cache=False)
            rows += parse_deals(text, kind)
        except nse.NseBlocked as e:
            blocked.append("%s (for %s deals use --%s-file, not --file)" % (e, kind, kind))
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
        if not symbols and not (a.cmd == "deals" and a.every_symbol):
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
            _write(a.out, {"as_of": now.isoformat(), "cmd": a.cmd, "complete": not (errors or blocked),
                           "errors": errors, "blocked": blocked,
                           "rows": [dict(x, when=x["when"].isoformat()) for x in rows]})
    except (InsiderError, nse.NseError, nse_calendar.CalendarError, nse_symbols.SymbolError, watchlist.WatchError) as e:
        print("insider.py: %s" % e, file=sys.stderr)
        return 2
    except Exception as e:  # never let a scheduled run exit 1 ("nothing new") on a crash
        print("insider.py: unexpected %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"rows": [dict(x, when=x["when"].isoformat()) for x in shown], "errors": errors,
                          "blocked": blocked}, indent=2))
    else:
        print(render(shown, errors, blocked))
    if blocked or errors:
        return 2
    return 0 if shown else 1


if __name__ == "__main__":
    sys.exit(main())
