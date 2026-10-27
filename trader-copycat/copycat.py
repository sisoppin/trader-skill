#!/usr/bin/env python3
"""Copy an Indian investor or a mutual fund for trader-copycat, and write trader/targets.json.

    python3 copycat.py investor "Rekha Jhunjhunwala" --symbols TITAN CRISIL NCC
    python3 copycat.py investor "Rekha Jhunjhunwala" --symbols TITAN CRISIL NCC --write
    python3 copycat.py investor "Rekha Jhunjhunwala" --symbols TITAN NCC --offline DIR
    python3 copycat.py fund "Parag Parikh Flexi Cap" --file portfolio.csv
    python3 copycat.py fund "Parag Parikh Flexi Cap" --file oct.csv --previous sep.csv --top 10 --write

investor: an individual's holdings are public only where they own more than 1% of a company, in that
company's quarterly shareholding pattern on NSE. There is no list of everything one person owns, so you
name the stocks (--symbols) and the tool reads each one's two newest patterns (shp.py). The result is a
partial portfolio: stakes under 1% never show. Weights come from the value of each holding (shares x price
from trader/prices.json, which /trader-alerts writes from Kite quotes).

fund: a mutual fund's full portfolio, from the monthly sheet its AMC publishes, saved as CSV (amc.py).
Weights come from % to NAV. ISINs are matched to NSE symbols with the NSE symbol list
(nse_symbols.py refresh); unmatched stocks are listed and left out.

Both scale the chosen holdings (--top N, default 10; 0 for all) to 100 and show what changed since the
quarter (or month) before: new, added, trimmed, same, and gone or sold. --write saves trader/targets.json
for /trader-budget and /trader-rebalance.

Exit code 0 when everything was read, 2 when any stock could not be read, a price is missing, or NSE
blocked a request (the message names the URL and how to rerun with --offline). --write refuses to save
weights built from a partial read.

This is someone else's portfolio, disclosed after the fact. Copying it is your own decision: not financial
advice.
"""

import argparse
import json
import math
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import amc
import nse
import nse_calendar
import nse_symbols
import shp
from rupees import inr


class CopyError(Exception):
    pass


def load_prices(path):
    if not path or not os.path.exists(path):
        return {}, None
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except ValueError as e:
        raise CopyError("%s is not valid JSON: %s" % (path, e))
    prices = doc.get("prices") if isinstance(doc, dict) else None
    if not isinstance(prices, dict):
        raise CopyError("%s has no prices object (write it with trader-alerts: alerts.py quote ... --write)" % path)
    out = {}
    for k, v in prices.items():
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x) and x > 0:
            out[str(k).upper()] = x
    return out, doc.get("as_of")


def scale(rows, key, top):
    """Keep the top N rows by key (0 = all) and add weight = share of their total, scaled to 100."""
    held = sorted([r for r in rows if r.get(key)], key=lambda r: r[key], reverse=True)
    if top:
        held = held[:top]
    total = sum(r[key] for r in held)
    for r in held:
        r["weight"] = round(r[key] / total * 100, 2) if total else 0.0
    return held


def investor(name, symbols, client=None, offline=None):
    """-> (rows, absent, errors, blocked). A row: {symbol, company, quarter, shares, pct, before, change, names}."""
    rows, absent, errors, blocked = [], [], [], []
    for sym in symbols:
        try:
            if offline:
                master = nse.read_json_file(os.path.join(offline, "shp-%s.json" % sym))
            else:
                master = client.get_json(shp.MASTER_URL % urllib.parse.quote(sym, safe=""))
            quarters = shp.parse_master(master, sym)[:2]
            if not quarters:
                raise shp.ShpError("NSE lists no shareholding patterns")
            docs = []
            for q in quarters:
                if offline:
                    text = nse.read_file(os.path.join(offline, q["xbrl"].rsplit("/", 1)[-1]))
                else:
                    text = client.get_text(q["xbrl"], cookie=False)
                try:
                    docs.append(shp.parse(text))
                except shp.ShpError as e:
                    if client is not None:
                        client.forget(q["xbrl"])
                    raise shp.ShpError("%s: %s" % (q["xbrl"], e))
            now = shp.holding(docs[0], name)
            before = shp.holding(docs[1], name) if len(docs) > 1 else None
            if not now and not before:
                absent.append(sym)
                continue
            rows.append({"symbol": sym, "company": docs[0]["company"], "quarter": docs[0]["quarter"].isoformat(),
                         "shares": now["shares"] if now else 0, "pct": now["pct"] if now else 0.0,
                         "before": before["shares"] if before else 0,
                         "change": shp.change(now, before) if len(docs) > 1 else "new",
                         "names": (now or before)["names"]})
        except nse.NseBlocked as e:
            blocked.append("%s (save shp-%s.json and the two newest XBRL files it links to in one folder, then "
                           "rerun with --offline <folder>)" % (e, sym))
        except (shp.ShpError, nse.NseError) as e:
            errors.append("%s: %s" % (sym, e))
    return rows, absent, errors, blocked


def fund(path, previous, master):
    """-> (rows, unmapped). A row: {symbol, name, isin, pct, quantity, before, change}; sold rows have pct 0.

    unmapped: [{isin, name, pct}] for equity rows whose ISIN is not on the NSE symbol list."""
    now = {r["isin"]: r for r in amc.parse(nse.read_file(path))}
    before = {r["isin"]: r for r in amc.parse(nse.read_file(previous))} if previous else {}
    rows, unmapped = [], []
    for isin in list(now) + [i for i in before if i not in now]:
        n, b = now.get(isin), before.get(isin)
        hit = master.by_isin(isin)
        if hit is None:
            if n:
                unmapped.append({"isin": isin, "name": n["name"], "pct": n["pct"]})
            continue
        rows.append({"symbol": hit["symbol"], "name": (n or b)["name"] or hit["name"], "isin": isin,
                     "pct": n["pct"] if n else 0.0, "quantity": n["quantity"] if n else 0,
                     "before": (b["quantity"] if b and b["quantity"] is not None else (b["pct"] if b else 0)),
                     "change": amc.change(n, b) if previous else "-"})
    return rows, unmapped


def write_targets(path, doc):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Copy an investor or a mutual fund into trader/targets.json.")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("investor", help="an individual's >1%% stakes from NSE shareholding patterns")
    p.add_argument("name", help='the name as filed, e.g. "Rekha Jhunjhunwala"')
    p.add_argument("--symbols", nargs="+", required=True, help="the stocks to look in")
    p.add_argument("--offline", metavar="DIR", help="read shp-<SYMBOL>.json and the XBRL files from DIR")
    p.add_argument("--prices", default="trader/prices.json")
    f = sub.add_parser("fund", help="a mutual fund's monthly portfolio sheet saved as CSV")
    f.add_argument("name", help='the scheme, e.g. "Parag Parikh Flexi Cap"')
    f.add_argument("--file", required=True, help="this month's portfolio sheet as CSV")
    f.add_argument("--previous", help="last month's sheet as CSV, to show what changed")
    f.add_argument("--symbols-file", default=nse_symbols.CACHE, help="NSE EQUITY_L.csv (nse_symbols.py refresh)")
    for x in (p, f):
        x.add_argument("--top", type=int, default=10, help="copy the N biggest holdings (0 = all, default 10)")
        x.add_argument("--write", nargs="?", const="trader/targets.json", metavar="PATH",
                       help="save the weights (default trader/targets.json)")
        x.add_argument("--now", help="pretend it is this time (ISO, IST; tests only, needs TRADER_TEST_CLOCK=1)")
        x.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 2
    errors, blocked, lines, refused = [], [], [], False
    written, not_written = None, None
    try:
        now = nse_calendar.parse_now(a.now)
        if a.top < 0:
            raise CopyError("--top must be 0 (all) or more")
        if a.cmd == "investor":
            symbols = []
            for s in a.symbols:
                n = nse_symbols.normalize(s)
                if n not in symbols:
                    symbols.append(n)
            rows, absent, errors, blocked = investor(a.name, symbols, None if a.offline else nse.Client(), a.offline)
            prices, prices_at = load_prices(a.prices)
            missing = [r["symbol"] for r in rows if r["shares"] and r["symbol"] not in prices]
            for r in rows:
                r["value"] = round(r["shares"] * prices[r["symbol"]], 2) if r["symbol"] in prices else None
            chosen = scale(rows, "value", a.top) if not missing else []
            quarters = sorted({r["quarter"] for r in rows if r["shares"]})
            lines.append("%s in NSE shareholding patterns (stakes above 1%% only), quarter ended %s" % (
                a.name, ", ".join(quarters) or "-"))
            for r in sorted(rows, key=lambda r: (-(r["value"] or 0), -r["shares"], r["symbol"])):
                w = next((c["weight"] for c in chosen if c is r), None)
                lines.append("  %-10s %12s shares  %5.2f%% of the company  %-8s %s%s" % (
                    r["symbol"], inr(r["shares"])[3:], r["pct"], r["change"],
                    inr(r["value"]) if r["value"] is not None else "no price",
                    ("  weight %.2f" % w) if w is not None else ""))
            for s in absent:
                lines.append("  %-10s not named (holds under 1%%, or none)" % s)
            if absent and not rows and not errors and not blocked:
                lines.append("nobody named %r in any of these patterns: names match word by word, so check the name "
                             "as the company filed it (the SKILL.md example shows how)" % a.name)
            if missing:
                lines.append("no price for %s: save Kite quotes and run trader-alerts' alerts.py quote %s --write, "
                             "then rerun" % (", ".join(missing), " ".join(missing)))
            doc = {"kind": "investor", "source": "%s in NSE shareholding patterns, quarter ended %s (%s)" % (
                       a.name, ", ".join(quarters), ", ".join(r["symbol"] for r in chosen)),
                   "as_of": quarters[-1] if quarters else None, "written": now.isoformat(),
                   "method": "holding value (shares x price from %s as of %s), top %s scaled to 100; only stakes "
                             "above 1%% are disclosed, so this is a partial portfolio" % (a.prices, prices_at,
                                                                                           a.top or "all"),
                   "weights": [{"symbol": r["symbol"], "name": r["company"], "weight": r["weight"],
                                "shares": r["shares"], "pct_of_company": r["pct"], "value": r["value"],
                                "change": r["change"]} for r in chosen]}
        else:
            master = nse_symbols.load(a.symbols_file)
            rows, unmapped = fund(a.file, a.previous, master)
            chosen = scale(rows, "pct", a.top)
            lines.append("%s: %d stocks in the sheet, copying the top %d by %% to NAV" % (
                a.name, len([r for r in rows if r["pct"]]) + len(unmapped), len(chosen)))
            ranked = sorted([(r["pct"], r["symbol"], None) for r in rows if r["pct"] > 0]
                            + [(u["pct"], u["isin"], u) for u in unmapped], key=lambda x: (-x[0], x[1]))
            crowded = [x[2] for x in (ranked[:a.top] if a.top else ranked) if x[2]]
            for r in sorted(rows, key=lambda r: (-r["pct"], r["symbol"])):
                w = next((c["weight"] for c in chosen if c is r), None)
                lines.append("  %-10s %6.2f%% of NAV  %-8s%s" % (r["symbol"], r["pct"], r["change"],
                                                               ("  weight %.2f" % w) if w is not None else ""))
            if crowded:
                lines.append("  would be copied but not on the NSE symbol list: %s" % ", ".join(
                    u["name"] or u["isin"] for u in crowded))
            for u in unmapped:
                lines.append("  %-10s %6.2f%% of NAV  not on the NSE symbol list, left out: %s %s" % (
                    "?", u["pct"], u["isin"], u["name"]))
            doc = {"kind": "fund", "source": "%s portfolio sheet %s" % (a.name, os.path.basename(a.file)),
                   "as_of": now.date().isoformat(), "written": now.isoformat(),
                   "method": "%% to NAV, top %s scaled to 100" % (a.top or "all"),
                   "weights": [{"symbol": r["symbol"], "name": r["name"], "weight": r["weight"], "isin": r["isin"],
                                "pct_of_nav": r["pct"], "change": r["change"]} for r in chosen]}
        if a.write:
            why = None
            if errors or blocked:
                why = "%d stock(s) could not be read, so the weights would be wrong" % (len(errors) + len(blocked))
            elif a.cmd == "investor" and missing:
                why = "no price for %s" % ", ".join(missing)
            elif a.cmd == "fund" and crowded:
                why = ("%s would be in the copied holdings but is not on the NSE symbol list (run nse_symbols.py "
                       "refresh, or pick a smaller --top)" % ", ".join(u["name"] or u["isin"] for u in crowded))
            elif not doc["weights"]:
                raise CopyError("nothing to copy: no holding to weight")
            if why:
                refused = True
                not_written = why
                lines.append("not written: %s" % why)
            else:
                write_targets(a.write, doc)
                written = a.write
                lines.append("wrote %s (%d weights)" % (a.write, len(doc["weights"])))
    except (CopyError, amc.AmcError, shp.ShpError, nse.NseError, nse_calendar.CalendarError,
            nse_symbols.SymbolError) as e:
        print("copycat.py: %s" % e, file=sys.stderr)
        return 2
    except Exception as e:  # never let a crash look like success
        print("copycat.py: unexpected %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 2
    for e in errors:
        lines.append("error: " + e)
    for b in blocked:
        lines.append("blocked: " + b)
    lines.append("Someone else's portfolio, disclosed after the fact. Not financial advice.")
    if a.json:
        print(json.dumps(dict(doc, rows=rows, errors=errors, blocked=blocked, written=written,
                                    not_written=not_written), indent=2, default=str))
    else:
        print("\n".join(lines))
    return 2 if (errors or blocked or refused or (a.cmd == "investor" and missing)) else 0


if __name__ == "__main__":
    sys.exit(main())
