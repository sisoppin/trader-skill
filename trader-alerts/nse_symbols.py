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
    if file:
        text = nse.read_file(file)
        rows = parse(text)
    else:
        client = client or nse.Client()
        text = client.get_text(URL, cookie=False)
        try:
            rows = parse(text)
        except SymbolError:
            client.forget(URL)
            raise nse.NseBlocked(URL, "the answer was not NSE's equity list, probably a block page")
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
