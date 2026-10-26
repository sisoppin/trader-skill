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
        if not r["trade_id"]:
            raise TradeError("%s: no trade_id (Console tradebooks always carry one; re-download the file)" % where)
        trades.append({"date": _date(r["trade_date"], where), "symbol": _symbol(r["symbol"], where), "side": side,
                       "qty": _qty(r["quantity"], where), "price": _price(r["price"], where),
                       "id": r["trade_id"], "source": os.path.basename(path)})
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
                    "id": "lots:%s:%d" % (os.path.basename(path), i), "source": os.path.basename(path)})
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


def _describe(t):
    return "%s %d @ %.2f" % (t["side"], t["qty"], t["price"])


def merge(*lists):
    """All trades in date order (stable). A trade seen again with the same id, date and symbol is a
    duplicate and dropped (the first one wins) when side, qty and price agree; if they differ, raise.
    A Kite trade that matches a Console (or lots) trade in everything but the trade id also raises: the
    two sources would count the same fill twice."""
    kept, out, matched = {}, [], set()
    for trades in lists:
        for t in trades:
            key = (t["id"], t["date"], t["symbol"])
            prev = kept.get(key)
            if prev is None:
                kept[key] = t
                out.append(t)
                continue
            if prev["side"] == t["side"] and prev["qty"] == t["qty"] and abs(prev["price"] - t["price"]) <= 0.01:
                matched.add(key)
                continue
            raise TradeError("trade %s on %s (%s) appears twice with different details: %s in %s and %s in %s"
                             % (t["id"], t["date"], t["symbol"], _describe(prev), prev["source"],
                                _describe(t), t["source"]))
    loose = [t for t in out if (t["id"], t["date"], t["symbol"]) not in matched]
    for k in (t for t in loose if t["source"] == "kite"):
        for t in loose:
            if t["source"] != "kite" and t["id"] != k["id"] and (t["date"], t["symbol"], t["side"], t["qty"]) \
                    == (k["date"], k["symbol"], k["side"], k["qty"]) and abs(t["price"] - k["price"]) <= 0.01:
                raise TradeError("Kite trade %s matches Console trade %s except for the trade id: check that Kite "
                                 "and Console use the same trade ids before trusting the tax figures"
                                 % (k["id"], t["id"]))
    return sorted(out, key=lambda t: t["date"])
