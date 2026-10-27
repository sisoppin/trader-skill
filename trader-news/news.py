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
