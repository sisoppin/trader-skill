#!/usr/bin/env python3
"""Quarterly results for trader-analyst, from the financials companies file with NSE.

    python3 results.py                                  # your Kite holdings and trader/targets.json
    python3 results.py --symbols INFY TCS HDFCBANK
    python3 results.py --symbols INFY --standalone      # the parent company alone, not the group
    python3 results.py --symbols INFY --write           # also save trader/metrics.json for the screener
    python3 results.py --symbols INFY --offline DIR     # NSE blocked you: files saved from a browser

Source: NSE's integrated filing (financials) list for each stock,
  https://www.nseindia.com/api/integrated-filing-results?index=equities&symbol=<SYMBOL>&type=Integrated%20Filing-%20Financials
and the XBRL file each row links to (https://nsearchives.nseindia.com/corporate/xbrl/...). Each XBRL file holds
one quarter, so the tool reads the newest five: this quarter, the one before (QoQ), the same quarter a year
earlier (YoY), and four in a row for the trailing twelve months (TTM). Filings from before April 2025 used
NSE's older results page and are not read.

Numbers are in rupees as filed. Revenue is revenue from operations (interest earned for a bank). Net profit
is the profit attributable to the owners of the company when the filing gives it. Operating margin is
(profit before tax + finance costs - other income) / revenue; it is left empty for banks, whose format has no
such line. A company that files only standalone results is read standalone, and the row says so.

Exit code 0 when every stock was read, 2 when any stock could not be read or NSE blocked a request (the
message names the URL to open and how to rerun with --offline).

These are the company's reported numbers, not a forecast. Not financial advice.
"""

import argparse
import datetime
import json
import os
import sys
import urllib.parse
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import kite_snapshot
import nse
import nse_calendar
import nse_symbols
import watchlist
from rupees import inr

LIST_URL = ("https://www.nseindia.com/api/integrated-filing-results?index=equities&symbol=%s"
            "&type=Integrated%%20Filing-%%20Financials")
QUARTERS = 5
FIELDS = ("RevenueFromOperations", "InterestEarned", "OtherIncome", "FinanceCosts", "ProfitBeforeTax",
          "ProfitOrLossAttributableToOwnersOfParent", "ProfitLossForPeriod", "ProfitLossForThePeriod",
          "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
          "BasicEarningsPerShareAfterExtraordinaryItems")


class ResultsError(Exception):
    pass


def _date(text, fmt):
    try:
        return datetime.datetime.strptime(str(text).strip(), fmt).date()
    except ValueError:
        return None


def parse_list(doc, symbol):
    """NSE's integrated-filing list ({"data": [...]}) -> filings {quarter, basis, xbrl, filed, name}."""
    rows = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        raise ResultsError("the results list for %s is not NSE's answer (no data list)" % symbol)
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        q = _date(r.get("qe_Date"), "%d-%b-%Y")
        filed = _date(str(r.get("broadcast_Date") or "")[:11], "%d-%b-%Y")
        link = str(r.get("xbrl") or "")
        basis = str(r.get("consolidated") or "").strip().lower()
        if not q or basis not in ("consolidated", "standalone") or not link.lower().endswith(".xml"):
            continue
        out.append({"quarter": q, "basis": basis, "xbrl": link, "filed": filed or q,
                    "broadcast": str(r.get("broadcast_Date") or ""), "name": str(r.get("cmName") or "").strip()})
    return out


def pick(filings, standalone=False):
    """The newest QUARTERS quarters on one basis, newest first; a revised filing replaces the original.

    Consolidated by default; a company with no consolidated filings is read standalone."""
    basis = "standalone" if standalone else "consolidated"
    if not any(f["basis"] == basis for f in filings):
        basis = "consolidated" if standalone else "standalone"
    best = {}
    for f in filings:
        if f["basis"] != basis:
            continue
        old = best.get(f["quarter"])
        if old is None or (f["filed"], f["broadcast"]) > (old["filed"], old["broadcast"]):
            best[f["quarter"]] = f
    return [best[q] for q in sorted(best, reverse=True)[:QUARTERS]]


def parse_xbrl(text):
    """One quarter's XBRL -> {period_end, FIELD: float}, from the quarter's own context (no dimensions)."""
    try:
        root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except ET.ParseError as e:
        raise ResultsError("not an XBRL file (%s), probably a block page" % e)
    local = lambda el: el.tag.rsplit("}", 1)[-1]
    end = None
    for el in root:
        if local(el) == "DateOfEndOfReportingPeriod" and el.text:
            end = _date(el.text, "%Y-%m-%d")
            break
    if end is None:
        raise ResultsError("the XBRL file has no DateOfEndOfReportingPeriod")
    best, best_len = None, None
    for el in root:
        if local(el) != "context" or el.find(".//{*}segment") is not None or el.find(".//{*}scenario") is not None:
            continue
        s, e = el.find(".//{*}startDate"), el.find(".//{*}endDate")
        if s is None or e is None or _date(e.text, "%Y-%m-%d") != end:
            continue
        n = (end - (_date(s.text, "%Y-%m-%d") or end)).days
        if best_len is None or n < best_len:
            best, best_len = el.get("id"), n
    if best is None:
        raise ResultsError("the XBRL file has no context for the quarter ending %s" % end)
    out = {"period_end": end}
    for el in root:
        if el.get("contextRef") == best and local(el) in FIELDS:
            try:
                out[local(el)] = float(el.text)
            except (TypeError, ValueError):
                pass
    return out


def figures(f):
    """Facts -> {period_end, revenue, net_profit, eps, operating_profit, bank}."""
    bank = "RevenueFromOperations" not in f and "InterestEarned" in f
    rev = f.get("InterestEarned") if bank else f.get("RevenueFromOperations")
    profit = f.get("ProfitOrLossAttributableToOwnersOfParent",
                   f.get("ProfitLossForPeriod", f.get("ProfitLossForThePeriod")))
    eps = f.get("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                f.get("BasicEarningsPerShareAfterExtraordinaryItems"))
    op = None
    if not bank and None not in (f.get("ProfitBeforeTax"), f.get("FinanceCosts"), f.get("OtherIncome")):
        op = f["ProfitBeforeTax"] + f["FinanceCosts"] - f["OtherIncome"]
    return {"period_end": f["period_end"], "revenue": rev, "net_profit": profit, "eps": eps,
            "operating_profit": op, "bank": bank}


def _months_back(d, n):
    """The quarter end n months before d (30 Sep - 3 = 30 Jun, 31 Mar - 3 = 31 Dec)."""
    y, m = d.year, d.month - n
    while m <= 0:
        y, m = y - 1, m + 12
    nxt = datetime.date(y + (m == 12), m % 12 + 1, 1)
    return nxt - datetime.timedelta(days=1)


def growth(new, old):
    if new is None or old in (None, 0):
        return None
    return round((new - old) / abs(old) * 100, 1)


def pct(a, b):
    return None if a is None or not b else round(a / b * 100, 1)


def fy_label(d):
    """30 Sep 2026 -> 'Q2 FY27' (the Indian financial year ends in March)."""
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(d.month)
    fy = d.year + 1 if d.month > 3 else d.year
    return ("Q%d FY%02d" % (q, fy % 100)) if q else d.isoformat()


def metrics(symbol, name, basis, quarters, filed):
    """Per-quarter figures (newest first) -> one metrics row for trader/metrics.json."""
    by_end = {q["period_end"]: q for q in quarters}
    q0 = quarters[0]
    end = q0["period_end"]
    prev, year = by_end.get(_months_back(end, 3)), by_end.get(_months_back(end, 12))
    run = [by_end.get(_months_back(end, 3 * i)) for i in range(4)]
    ttm = lambda k: (round(sum(q[k] for q in run), 2) if all(q and q[k] is not None for q in run) else None)
    row = {"symbol": symbol, "name": name, "basis": basis, "period_end": end.isoformat(), "quarter": fy_label(end),
           "filed": filed.isoformat(), "bank": q0["bank"],
           "revenue": q0["revenue"], "net_profit": q0["net_profit"], "eps": q0["eps"],
           "operating_margin": pct(q0["operating_profit"], q0["revenue"]),
           "net_margin": pct(q0["net_profit"], q0["revenue"]),
           "revenue_growth_yoy": growth(q0["revenue"], year and year["revenue"]),
           "revenue_growth_qoq": growth(q0["revenue"], prev and prev["revenue"]),
           "net_profit_growth_yoy": growth(q0["net_profit"], year and year["net_profit"]),
           "net_profit_growth_qoq": growth(q0["net_profit"], prev and prev["net_profit"]),
           "eps_growth_yoy": growth(q0["eps"], year and year["eps"]),
           "revenue_ttm": ttm("revenue"), "net_profit_ttm": ttm("net_profit"), "eps_ttm": ttm("eps"),
           "source": "NSE integrated filing (financials)"}
    return row


def fetch(symbol, client=None, offline=None, standalone=False):
    """One stock -> its metrics row. Raises ResultsError or nse errors."""
    if offline:
        doc = nse.read_json_file(os.path.join(offline, "results-%s.json" % symbol))
    else:
        doc = client.get_json(LIST_URL % urllib.parse.quote(symbol, safe=""))
    picked = pick(parse_list(doc, symbol), standalone)
    if not picked:
        raise ResultsError("NSE lists no integrated-filing results (from April 2025 on)")
    quarters = []
    for f in picked:
        if offline:
            text = nse.read_file(os.path.join(offline, f["xbrl"].rsplit("/", 1)[-1]))
        else:
            text = client.get_text(f["xbrl"], cookie=False)
        try:
            quarters.append(figures(parse_xbrl(text)))
        except ResultsError as e:
            if client is not None:
                client.forget(f["xbrl"])
            raise ResultsError("%s: %s" % (f["xbrl"], e))
    quarters.sort(key=lambda q: q["period_end"], reverse=True)
    return metrics(symbol, picked[0]["name"], picked[0]["basis"], quarters, picked[0]["filed"])


def _cr(x):
    return "-" if x is None else inr(round(x / 1e7)) + " cr"


def _g(x):
    return "n/a" if x is None else "%+.1f%%" % x


def render(rows, errors, blocked):
    lines = []
    for r in rows:
        lines.append("%s  %s (%s, %s%s)" % (r["symbol"], r["quarter"], r["period_end"], r["basis"],
                                            ", bank" if r["bank"] else ""))
        lines.append("    revenue     %s  (%s YoY, %s QoQ)" % (_cr(r["revenue"]), _g(r["revenue_growth_yoy"]),
                                                              _g(r["revenue_growth_qoq"])))
        lines.append("    net profit  %s  (%s YoY, %s QoQ)" % (_cr(r["net_profit"]), _g(r["net_profit_growth_yoy"]),
                                                              _g(r["net_profit_growth_qoq"])))
        lines.append("    EPS         %s  (%s YoY)   TTM EPS %s" % (
            "-" if r["eps"] is None else "Rs %.2f" % r["eps"], _g(r["eps_growth_yoy"]),
            "n/a" if r["eps_ttm"] is None else "Rs %.2f" % r["eps_ttm"]))
        lines.append("    margins     operating %s, net %s" % (
            "n/a" if r["operating_margin"] is None else "%.1f%%" % r["operating_margin"],
            "n/a" if r["net_margin"] is None else "%.1f%%" % r["net_margin"]))
    for e in errors:
        lines.append("error: " + e)
    for b in blocked:
        lines.append("blocked: " + b)
    lines.append("Reported numbers from NSE filings, not a forecast. Not financial advice.")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Quarterly results from NSE filings (trader-analyst).")
    ap.add_argument("--symbols", nargs="*", help="default: Kite holdings and trader/targets.json")
    ap.add_argument("--standalone", action="store_true", help="read standalone results instead of consolidated")
    ap.add_argument("--offline", metavar="DIR", help="read results-<SYMBOL>.json and the XBRL files from DIR")
    ap.add_argument("--kite-dir", default=kite_snapshot.DIR)
    ap.add_argument("--targets", default="trader/targets.json")
    ap.add_argument("--write", nargs="?", const="trader/metrics.json", metavar="PATH",
                    help="save the rows for the screener (default trader/metrics.json)")
    ap.add_argument("--now", help="pretend it is this time (ISO, IST; tests only, needs TRADER_TEST_CLOCK=1)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rows, errors, blocked = [], [], []
    try:
        now = nse_calendar.parse_now(a.now)
        symbols = []
        for s in (a.symbols or watchlist.watch_list(a.kite_dir, a.targets)):
            n = nse_symbols.normalize(s)
            if n not in symbols:
                symbols.append(n)
        if not symbols:
            raise ResultsError("which stocks? pass --symbols INFY TCS, or save Kite holdings / write trader/targets.json")
        client = None if a.offline else nse.Client()
        for sym in symbols:
            try:
                rows.append(fetch(sym, client, a.offline, a.standalone))
            except nse.NseBlocked as e:
                blocked.append("%s (save results-%s.json and each XBRL file it links to in one folder, then rerun "
                               "with --offline <folder>)" % (e, sym))
            except (ResultsError, nse.NseError) as e:
                errors.append("%s: %s" % (sym, e))
        if a.write:
            d = os.path.dirname(a.write)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(a.write, "w", encoding="utf-8") as fh:
                json.dump({"as_of": now.isoformat(), "complete": not (errors or blocked), "errors": errors,
                           "blocked": blocked, "companies": rows}, fh, indent=2)
                fh.write("\n")
    except (ResultsError, nse.NseError, nse_calendar.CalendarError, nse_symbols.SymbolError,
            watchlist.WatchError) as e:
        print("results.py: %s" % e, file=sys.stderr)
        return 2
    except Exception as e:  # never let a scheduled run look like success on a crash
        print("results.py: unexpected %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"companies": rows, "errors": errors, "blocked": blocked}, indent=2))
    else:
        print(render(rows, errors, blocked))
    return 2 if (errors or blocked) else 0


if __name__ == "__main__":
    sys.exit(main())
