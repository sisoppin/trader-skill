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


# ---------------------------------------------------------------- the maths

def normalise(rows, blocked=(), top=None):
    """Drop blocked and non-positive weights, keep the top N, renormalise to 100."""
    blocked = {str(b).upper() for b in (blocked or [])}
    dropped, keep, seen = [], [], set()
    for r in rows:
        if r["ticker"] in seen:
            raise SizeError("%s is listed twice in the weights" % r["ticker"])
        seen.add(r["ticker"])
        if r["ticker"] in blocked:
            dropped.append({"ticker": r["ticker"], "reason": "on your blocked list"})
        elif r["weight"] <= 0:
            dropped.append({"ticker": r["ticker"], "reason": "weight is zero or negative"})
        else:
            keep.append(dict(r))
    keep.sort(key=lambda r: -r["weight"])
    if top:
        for r in keep[top:]:
            dropped.append({"ticker": r["ticker"], "reason": "outside the top %d" % top})
        keep = keep[:top]
    total = sum(r["weight"] for r in keep)
    for r in keep:
        r["source_weight"] = r["weight"]
        r["weight"] = 100.0 * r["weight"] / total if total else 0.0
    return keep, dropped


def allocate(rows, investable, cap):
    """Exact (unrounded) dollars per ticker with the cap enforced.

    Proportional to weight; any stock over the cap is pinned at the cap and
    the rest of the money is shared over the others, repeated until no stock
    is over. Returns ({ticker: dollars}, set of capped tickers)."""
    alloc, capped = {}, set()
    active = [r for r in rows]
    money = investable
    while active:
        wsum = sum(r["weight"] for r in active)
        trial = {r["ticker"]: money * r["weight"] / wsum for r in active}
        over = [r for r in active if trial[r["ticker"]] > cap + EPS]
        if not over:
            alloc.update(trial)
            break
        for r in over:
            alloc[r["ticker"]] = cap
            capped.add(r["ticker"])
            money -= cap
        active = [r for r in active if r["ticker"] not in capped]
        if money <= EPS:
            for r in active:
                alloc[r["ticker"]] = 0.0
            break
    return alloc, capped


def round_to_unit(exact, capped, order, cap, unit):
    """Round to whole dollars (unit 1) or cents (unit 0.01) and keep the total.

    The total placed is the exact total rounded DOWN to the unit, so it never
    spends money you do not have. Each slice is rounded to the nearest unit,
    then the difference (usually one unit) goes to the biggest stock that is
    not capped, then the next, never pushing anyone over the cap."""
    def units(x):
        return int(math.floor(x / unit + EPS))

    cap_u = units(cap)
    total_u = units(sum(exact.values()))
    out = {}
    for t, v in exact.items():
        out[t] = cap_u if t in capped else int(math.floor(v / unit + 0.5 + EPS))
    diff = total_u - sum(out.values())
    takers = [t for t in order if t not in capped]
    guard = 0
    while diff != 0 and takers and guard < 100000:
        moved = False
        for t in takers:
            if diff == 0:
                break
            if diff > 0 and out[t] + 1 <= cap_u:
                out[t] += 1
                diff -= 1
                moved = True
            elif diff < 0 and out[t] > 0:
                out[t] -= 1
                diff += 1
                moved = True
        if not moved:
            break
        guard += 1
    return {t: round(u * unit, 2) for t, u in out.items()}


def whole_shares(dollars, prices, order, cap, money):
    """Whole shares: floor each slice, then buy one more share at a time for the
    stock furthest below its slice while cash lasts and the cap holds."""
    shares = {}
    for t in order:
        shares[t] = int(math.floor(dollars[t] / prices[t] + EPS)) if dollars[t] > 0 else 0
    spent = sum(shares[t] * prices[t] for t in order)
    left = money - spent
    while True:
        best, gap = None, None
        for t in order:
            p = prices[t]
            if p > left + EPS or (shares[t] + 1) * p > cap + EPS:
                continue
            g = dollars[t] - shares[t] * p
            if best is None or g > gap + EPS:
                best, gap = t, g
        if best is None:
            break
        shares[best] += 1
        left -= prices[best]
    return shares


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
