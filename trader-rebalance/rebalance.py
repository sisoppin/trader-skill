#!/usr/bin/env python3
"""Rebalancer for trader-rebalance. Standard library only, no network.

Compares what you hold, from the Kite snapshots (holdings, today's delivery
positions, margins for cash, quotes for prices), with your target weights
(trader/targets.json, capped by your rules) and proposes the LIVE orders that
bring every stock outside the band back to its target. It never places
anything: trader-risk checks each order and trader-broker asks for your yes.

    python3 rebalance.py                      # report only
    python3 rebalance.py --band 5 --write     # write trader/orders.json (proposals)
    python3 rebalance.py --sell-untracked     # also sell holdings that are not in the targets
    python3 rebalance.py --json

The rules:
  value         account = available cash + every holding at its Kite price
  targets       weights renormalised to 100 over the stock sleeve, which is the
                account minus your cash buffer; no stock over max_position_pct
                of the account (the excess is shared out, like trader-budget)
  drift         current % of the account minus target %, in percentage points
  band          only stocks drifting MORE than the band trade (default 5
                points, or "rebalance_band_pct" in the config); a trade takes
                the stock all the way back to its target
  whole shares  NSE has no fractional shares; every order is a LIMIT order at
                the Kite last price, with Zerodha's charges estimated
  sells first   sells are listed before buys
  cash          buys spend only cash above your buffer, charges included; sale
                proceeds are NOT counted the same day (trader-risk does the
                same), so run it again after the sales settle
  min / max     orders under min_order_value are skipped; an order over
                max_order_value is cut to the max (run it again later)
  order count   at most max_orders_per_day orders (sells first); trader-risk
                also counts what Kite's order book already shows today
  open orders   a stock with an open order in Kite's order book (any status
                but COMPLETE, REJECTED or CANCELLED) gets no new order, buy or
                sell, until that order fills or is cancelled
  untracked     holdings not in the targets are left alone and listed, unless
                --sell-untracked

Exit code 0 when there are orders to propose, 1 when nothing is outside the band.
"""

import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import charges
import kite_snapshot
import nse_symbols
from rupees import inr

DEFAULTS = {"cash_buffer_pct": 10, "max_position_pct": 25, "max_order_value": 10000, "min_order_value": 100,
            "max_orders_per_day": 5, "blocked": [], "rebalance_band_pct": 5}
EPS = 1e-9
FINISHED = ("COMPLETE", "REJECTED", "CANCELLED")


class RebalanceError(Exception):
    pass


def read_json(path, what, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise RebalanceError("no %s at %s" % (what, path))
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise RebalanceError("%s is not valid JSON: %s" % (path, e))


def _symbol(text):
    try:
        return nse_symbols.normalize(text)
    except nse_symbols.SymbolError as e:
        raise RebalanceError(str(e))


def _num(v, what):
    try:
        x = float(v)
    except (TypeError, ValueError):
        x = None
    if x is None or x != x or x in (float("inf"), float("-inf")) or x < 0:
        raise RebalanceError("config %s must be a number of at least 0, got %r" % (what, v))
    return x


def parse_targets(doc, blocked=()):
    rows = doc.get("weights", doc) if isinstance(doc, dict) else doc
    if isinstance(rows, dict):
        rows = [{"symbol": k, "weight": v} for k, v in rows.items()]
    blocked = {_symbol(b) for b in blocked or []}
    out = {}
    for r in rows or []:
        t = _symbol(r.get("symbol") or r.get("ticker"))
        w = _num(r.get("weight", 0) or 0, "weight for %s" % t)
        if w > 0 and t not in blocked:
            out[t] = out.get(t, 0.0) + w
    tot = sum(out.values())
    if not tot:
        raise RebalanceError("no target weights (run trader-copycat, or write trader/targets.json)")
    return {t: 100.0 * w / tot for t, w in out.items()}


def capped_targets(weights, sleeve, cap):
    """Rupee target per symbol, proportional to weight, none above the cap."""
    alloc, active, money_left = {}, dict(weights), sleeve
    while active:
        wsum = sum(active.values())
        trial = {t: money_left * w / wsum for t, w in active.items()}
        over = [t for t, v in trial.items() if v > cap + EPS]
        if not over:
            alloc.update(trial)
            break
        for t in over:
            alloc[t] = cap
            money_left -= cap
            del active[t]
        if money_left <= EPS:
            for t in active:
                alloc[t] = 0.0
            break
    return alloc


def account(snap):
    """(cash, {SYM: shares}) from the Kite holdings, positions (today's CNC) and margins snapshots."""
    m = snap["margins"]
    av = ((m or {}).get("equity") or {}).get("available") or {}
    cash = av.get("live_balance", av.get("cash"))
    try:
        cash = float(cash)
    except (TypeError, ValueError):
        raise RebalanceError("the margins snapshot has no equity cash (Kite answer changed?)")
    held = {}
    for r in snap["holdings"] or []:
        s = str(r.get("tradingsymbol", "")).upper()
        held[s] = held.get(s, 0) + int(float(r.get("quantity") or 0) + float(r.get("t1_quantity") or 0))
    for r in (snap["positions"] or {}).get("net") or []:
        if r.get("product") == "CNC":
            s = str(r.get("tradingsymbol", "")).upper()
            held[s] = held.get(s, 0) + int(float(r.get("quantity") or 0))
    return cash, {s: n for s, n in held.items() if n}


def _order(sym, side, qty, price, cfg, why):
    value = qty * price
    est = charges.estimate("CNC", side, value, cfg.get("charges"))
    return {"exchange": "NSE", "tradingsymbol": sym, "transaction_type": side, "quantity": str(int(qty)),
            "product": "CNC", "order_type": "LIMIT", "price": "%.2f" % price, "validity": "DAY",
            "variety": "regular", "est_value": "%.2f" % value, "est_charges": "%.2f" % est["total"], "why": why}


def plan(cash, held, prices, weights, cfg, band=None, sell_untracked=False, open_orders=None):
    """Pure function: the drift table and the proposed Kite orders."""
    c = dict(DEFAULTS)
    c.update(cfg or {})
    band = _num(c["rebalance_band_pct"] if band is None else band, "rebalance_band_pct")
    buf_pct, cap_pct = _num(c["cash_buffer_pct"], "cash_buffer_pct"), _num(c["max_position_pct"], "max_position_pct")
    min_o, max_o = _num(c["min_order_value"], "min_order_value"), _num(c["max_order_value"], "max_order_value")
    max_n = int(_num(c["max_orders_per_day"], "max_orders_per_day"))
    if buf_pct >= 100:
        raise RebalanceError("config cash_buffer_pct must be below 100, got %r" % (c["cash_buffer_pct"],))
    if cap_pct <= 0 or cap_pct > 100:
        raise RebalanceError("config max_position_pct must be above 0 and at most 100, got %r"
                             % (c["max_position_pct"],))
    busy = {str(o.get("tradingsymbol", "")).upper() for o in open_orders or []
            if str(o.get("status", "")).upper() not in FINISHED}
    need = sorted(set(held) | set(weights), key=lambda t: (-weights.get(t, 0.0), t))
    missing = [t for t in need if not prices.get(t)]
    if missing:
        raise RebalanceError("no Kite quote for %s: add %s to the quotes call, then kite_snapshot.py save quotes"
                             % (", ".join(missing), " ".join("NSE:" + m for m in missing)))
    value = {t: held.get(t, 0) * prices[t] for t in need}
    total = cash + sum(value.values())
    if total <= 0:
        raise RebalanceError("the account is empty: nothing to rebalance (trader-budget sizes a first buy)")
    buf = total * buf_pct / 100.0
    cap = total * cap_pct / 100.0
    target = capped_targets(weights, total - buf, cap)

    rows, sells, buys, notes = [], [], [], []
    for t in need:
        tracked = t in weights
        tgt = target.get(t, 0.0)
        cur_pct, tgt_pct = 100.0 * value[t] / total, 100.0 * tgt / total
        drift = cur_pct - tgt_pct
        row = {"symbol": t, "shares": held.get(t, 0), "price": prices[t], "value": round(value[t], 2),
               "current_pct": round(cur_pct, 2), "target_pct": round(tgt_pct, 2),
               "drift": round(drift, 2) if abs(drift) >= 0.005 else 0.0, "target_value": round(tgt, 2),
               "tracked": tracked, "action": "hold"}
        rows.append(row)
        if t in busy:
            row["action"] = "open order in Kite, skipped"
            notes.append("%s has an open order in Kite's order book: wait for it to fill or cancel it, then run "
                         "again" % t)
            continue
        if not tracked:
            if sell_untracked and held.get(t, 0) > 0:
                sells.append((t, held[t], "not in your targets; selling the whole position (--sell-untracked)"))
                row["action"] = "sell all"
            else:
                row["action"] = "untracked, left alone"
            continue
        if abs(drift) <= band + EPS:
            continue
        why = "drifted %+.1f points from its %.1f%% target (band %s)" % (drift, tgt_pct, _n(band))
        delta = tgt - value[t]
        if delta < 0:
            sells.append((t, min(int(-delta // prices[t]), held.get(t, 0)), why))
            row["action"] = "sell"
        else:
            buys.append((t, delta, why))
            row["action"] = "buy"

    orders = []
    for t, qty, why in sells:
        p = prices[t]
        if max_o and qty * p > max_o + EPS:
            qty = int(max_o // p)
            notes.append("%s sell cut to your %s max order; run again later" % (t, inr(max_o)))
        if qty < 1 or qty * p < min_o - EPS:
            notes.append("%s sell of %s is under one share or your %s minimum order: skipped"
                         % (t, inr(qty * p), inr(min_o)))
            continue
        orders.append(_order(t, "SELL", qty, p, c, why))

    spendable = max(cash - buf, 0.0)
    want = sum(d for _, d, _ in buys)
    scale = 1.0
    if want > spendable + EPS:
        scale = spendable / want if want else 0.0
        notes.append("buys scaled to %.0f%%: only %s is free above your %s cash buffer (sale proceeds count "
                     "after they settle)" % (100 * scale, inr(spendable), inr(buf)))
    for t, delta, why in buys:
        p = prices[t]
        rupees = delta * scale
        if max_o and rupees > max_o + EPS:
            rupees = max_o
            notes.append("%s buy cut to your %s max order; run again later" % (t, inr(max_o)))
        qty = int(rupees // p)
        while qty and qty * p + charges.estimate("CNC", "BUY", qty * p, c.get("charges"))["total"] > rupees + EPS:
            qty -= 1
        if qty < 1 or qty * p < min_o - EPS:
            notes.append("%s buy of %s does not reach one whole share or your %s minimum: skipped"
                         % (t, inr(rupees), inr(min_o)))
            continue
        orders.append(_order(t, "BUY", qty, p, c, why))

    if max_n and len(orders) > max_n:
        notes.append("%d orders proposed; kept the first %d (sells first) for your %d-a-day limit, run again "
                     "tomorrow for the rest" % (len(orders), max_n, max_n))
        orders = orders[:max_n]
    spent = sum(float(o["est_value"]) + float(o["est_charges"]) for o in orders if o["transaction_type"] == "BUY")
    return {"account_value": round(total, 2), "cash": round(cash, 2), "cash_buffer": round(buf, 2),
            "cap": round(cap, 2), "band": band, "rows": rows, "orders": orders, "notes": notes,
            "cash_after_buys": round(cash - spent, 2)}


def _n(x):
    x = float(x)
    return str(int(x)) if x == int(x) else "%.2f" % x


def report(res):
    lines = ["Account %s (cash %s, buffer %s, cap %s per stock), band %s points"
             % (inr(res["account_value"]), inr(res["cash"]), inr(res["cash_buffer"]), inr(res["cap"]),
                _n(res["band"])), ""]
    lines.append("%-12s %7s %12s %14s %8s %9s %8s  %s" % ("symbol", "shares", "price", "value", "now %",
                                                         "target %", "drift", "action"))
    for r in res["rows"]:
        lines.append("%-12s %7d %12s %14s %7.2f%% %8.2f%% %+8.2f  %s"
                     % (r["symbol"], r["shares"], inr(r["price"]), inr(r["value"]), r["current_pct"],
                        r["target_pct"], r["drift"], r["action"]))
    lines.append("")
    if res["orders"]:
        lines.append("Proposed LIVE orders, sells first (Kite place_order arguments; nothing has been placed):")
        for o in res["orders"]:
            lines.append("  %s %s %s, CNC, LIMIT %s, est. %s + %s charges" % (
                o["transaction_type"], o["quantity"], o["tradingsymbol"], inr(o["price"]), inr(o["est_value"]),
                inr(o["est_charges"])))
        lines.append("Cash after the buys, if they fill: about %s (sale proceeds not counted)."
                     % inr(res["cash_after_buys"]))
    else:
        lines.append("Nothing is outside the band. No trades.")
    for n in res["notes"]:
        lines.append("Note: " + n)
    lines.append("")
    lines.append("Selling can realise a taxable gain: check trader-tax (lots.py sell) first. Then trader-risk "
                 "checks every order and trader-broker asks you yes or no for each one.")
    lines.append("Education and tooling, not financial advice.")
    return "\n".join(lines)


def load_snapshots(kite_dir, now=None):
    snap = {}
    for kind in ("holdings", "positions", "margins", "orders", "quotes"):
        try:
            v = kite_snapshot.load(kind, kite_dir, now=now)
        except kite_snapshot.SnapshotError as e:
            raise RebalanceError(str(e))
        snap[kind] = kite_snapshot.quotes(v) if kind == "quotes" else v
    if not isinstance(snap["holdings"], list) or not isinstance(snap["positions"], dict) \
            or not isinstance(snap["orders"], list):
        raise RebalanceError("the holdings, positions or orders snapshot is not in Kite's shape "
                             "(Kite answer changed?)")
    return snap


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bring the portfolio back to its target weights (trader-rebalance).")
    ap.add_argument("--targets", default="trader/targets.json")
    ap.add_argument("--config", default="trader/config.json")
    ap.add_argument("--kite-dir", default=kite_snapshot.DIR, help="where the Kite snapshots are")
    ap.add_argument("--now", help="pretend it is this time (ISO, IST; tests only, needs TRADER_TEST_CLOCK=1)")
    ap.add_argument("--band", type=float, help="drift band in percentage points (default 5)")
    ap.add_argument("--sell-untracked", action="store_true", help="sell holdings that are not in the targets")
    ap.add_argument("--write", nargs="?", const="trader/orders.json", metavar="PATH",
                    help="write the proposals (default trader/orders.json)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        now = None
        if a.now:
            if os.environ.get("TRADER_TEST_CLOCK") != "1":
                raise RebalanceError("--now is for tests only (set TRADER_TEST_CLOCK=1 to simulate)")
            t = datetime.datetime.fromisoformat(a.now.replace("Z", "+00:00"))
            now = t.replace(tzinfo=kite_snapshot.IST) if t.tzinfo is None else t.astimezone(kite_snapshot.IST)
        cfg = read_json(a.config, "config", required=False) or {}
        snap = load_snapshots(a.kite_dir, now)
        cash, held = account(snap)
        prices = {s: q["price"] for s, q in snap["quotes"].items()}
        weights = parse_targets(read_json(a.targets, "targets"), cfg.get("blocked"))
        res = plan(cash, held, prices, weights, cfg, a.band, a.sell_untracked, snap["orders"])
        removed = False
        if a.write and not res["orders"] and os.path.exists(a.write):
            os.remove(a.write)
            removed = True
        if a.write and res["orders"]:
            d = os.path.dirname(a.write)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(a.write, "w", encoding="utf-8") as fh:
                json.dump({"created_by": "trader-rebalance",
                           "created_at": (now or datetime.datetime.now(kite_snapshot.IST)).replace(microsecond=0)
                           .isoformat(), "status": "proposed", "live": True,
                           "note": ("Proposals only, sells first. Every order is a LIVE order with real money. "
                                    "Nothing is placed until trader-risk passes each order and you say yes to it."),
                           "orders": res["orders"]}, fh, indent=2)
                fh.write("\n")
    except (RebalanceError, ValueError, charges.ChargesError) as e:
        print("rebalance.py: %s" % e, file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print(report(res))
        if a.write and res["orders"]:
            print("Wrote %d proposed order(s) to %s." % (len(res["orders"]), a.write))
        if removed:
            print("Removed the old %s: nothing to propose." % a.write)
    return 0 if res["orders"] else 1


if __name__ == "__main__":
    sys.exit(main())
