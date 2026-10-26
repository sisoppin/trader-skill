#!/usr/bin/env python3
"""Pre-trade risk check for trader-risk. Standard library only, no network.

Every order in this pack is a LIVE order with real money: Kite has no paper
account. This check is the gate between a proposal and the broker. It reads
the proposed orders (trader/orders.json), your rules (trader/config.json)
and the Kite snapshots Claude saved just before (trader/kite/: quotes,
holdings, positions, margins, orders), and gives each order PASS or BLOCK
with the reasons. Orders are checked in file order as if each PASS had
filled, so buys that are fine one by one but break the cash buffer together
are caught. Sale proceeds are not counted as cash on the same day, and a sell gets no credit for a buy
earlier in the same batch: shorts and new positions are judged on the snapshots alone.

    python3 check.py                       # the trader/ files, writes trader/state/risk.json
    python3 check.py --orders trader/orders.json --json
    python3 check.py --no-write            # check without recording the verdicts

What blocks an order:

  format       not a bare NSE tradingsymbol; transaction_type not BUY or
               SELL; quantity not a whole number above 0; validity not DAY;
               variety not regular or amo; a LIMIT order without a price;
               SL and SL-M (stop-loss) orders, which this pack does not use
  asset        anything not on NSE; F&O contracts (always)
  product      anything but CNC (delivery) and MIS (intraday); MIS while
               "allow_mis" is false
  blocked      a symbol on your "blocked" list
  hours        outside 09:15 to 15:30 IST on an NSE trading day, unless
               "allow_amo" is true and the order is variety amo; any day
               in a year whose NSE holiday list is not loaded
  price        no fresh Kite quote; a quote without circuit limits (use the full
               quotes call); an order without est_charges (trader-budget writes it); MARKET while "allow_market_orders" is
               false; a LIMIT price more than "max_limit_deviation_pct"
               from the last price; a price outside today's circuit band
  size         under "min_order_value" or over "max_order_value" (rupees)
  cash         a CNC buy plus its charges needs more than your available
               cash, or dips into your "cash_buffer_pct" buffer
  position     the stock would be over "max_position_pct" of the account
  short        a CNC sell of more than you hold less what open sell orders
               in Kite's order book already cover; an MIS sell that would
               leave you short, unless "allow_short" is true
  intraday     a new MIS position after "mis_cutoff" (15:00 IST); MIS
               exposure over "max_mis_exposure_pct" of your equity margin;
               any new MIS position once the day's loss reaches
               "daily_loss_limit"
  duplicate    the same symbol, side and product twice in this batch, or
               already open (not filled) in Kite's order book
  daily limit  more than "max_orders_per_day" orders today (Kite's order
               book plus the ones passed earlier in this batch)
  data         a Kite snapshot a rule needs is missing or stale: that is a
               BLOCK, never a skipped rule

A limit of 0 means off for "max_order_value", "max_orders_per_day" and
"daily_loss_limit", and the check says so in a warning. The allow_* switches
must be true or false without quotes, "blocked" must be a list, and a limit
that is not a finite number is an error. A Kite snapshot of an unexpected
shape is a data BLOCK. CNC rules read today's delivery trades from the
positions snapshot as well as holdings, so they need both.

Exit code 0 when every order passes, 1 when any order is blocked or the
check could not run. The verdicts go to trader/state/risk.json with a
fingerprint of each order, so trader-broker only shows an order as ready
if THIS exact order passed.
"""

import argparse
import datetime
import hashlib
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import kite_snapshot
import nse_calendar
from rupees import inr

DEFAULTS = {
    "cash_buffer_pct": 10, "max_position_pct": 25, "max_order_value": 10000, "min_order_value": 100,
    "max_orders_per_day": 5, "allow_market_orders": False, "max_limit_deviation_pct": 2,
    "allow_mis": False, "mis_cutoff": "15:00", "max_mis_exposure_pct": 50, "daily_loss_limit": 2000,
    "allow_short": False, "allow_amo": False, "blocked": [],
}
SWITCHES = ("allow_mis", "allow_short", "allow_market_orders", "allow_amo")
ZERO_MEANS_OFF = {"max_order_value": "no per-order cap", "max_orders_per_day": "no daily order limit",
                  "daily_loss_limit": "no daily loss limit"}
NUMBERS = ("cash_buffer_pct", "max_position_pct", "max_order_value", "min_order_value", "max_orders_per_day",
           "max_limit_deviation_pct", "max_mis_exposure_pct", "daily_loss_limit")
LEGACY = ("paper", "max_order_usd", "min_order_usd", "allow_options", "allow_margin", "fractional", "broker")
KITE_FIELDS = ("exchange", "tradingsymbol", "transaction_type", "quantity", "product", "order_type",
               "price", "trigger_price", "validity", "variety")
FNO = re.compile(r"\d.*(FUT|CE|PE)$")
NOT_PLACED = {"REJECTED", "CANCELLED"}
NOT_OPEN = {"COMPLETE", "REJECTED", "CANCELLED"}
PAISA = 0.005
SNAPSHOTS = ("quotes", "holdings", "positions", "margins", "orders")


class RiskError(Exception):
    pass


def read_json(path, what, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise RiskError("no %s at %s" % (what, path))
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise RiskError("%s is not valid JSON: %s" % (path, e))


def fingerprint(order):
    """Same function in trader-broker/ticket.py: the exact order that was checked."""
    core = {k: order[k] for k in KITE_FIELDS if k in order and order[k] is not None}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _f(x):
    """A finite number, or None."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _qty(x):
    """A whole number of shares above 0, or None."""
    v = _f(x)
    if v is None or v <= 0 or v != int(v):
        return None
    return int(v)


def _pct(x):
    x = float(x)
    return str(int(x)) if x == int(x) else ("%.2f" % x)


def config(cfg):
    """Your rules merged over the cautious defaults, numbers parsed. Returns (rules, warnings)."""
    c = dict(DEFAULTS)
    c.update(cfg or {})
    for k in SWITCHES:
        if not isinstance(c[k], bool):
            raise RiskError("config %s must be true or false without quotes, got %r" % (k, c[k]))
    if not isinstance(c["blocked"], list):
        raise RiskError("config blocked must be a list of symbols, like [\"INFY\"]")
    names = []
    for b in c["blocked"]:
        n = str(b).strip().upper()
        if n.startswith("NSE:"):
            n = n[4:]
        if n.endswith(".NS"):
            n = n[:-3]
        if not n or ":" in n:
            raise RiskError("config blocked entries must be NSE symbols like INFY, got %r" % (b,))
        names.append(n)
    c["blocked"] = names
    for k in NUMBERS:
        v = _f(c[k])
        if v is None or v < 0:
            raise RiskError("config %s must be a number of at least 0, got %r" % (k, c[k]))
        c[k] = v
    if c["max_orders_per_day"] != int(c["max_orders_per_day"]):
        raise RiskError("config max_orders_per_day must be a whole number, got %r" % (c["max_orders_per_day"],))
    try:
        c["mis_cutoff"] = datetime.datetime.strptime(str(c["mis_cutoff"]), "%H:%M").time()
    except ValueError:
        raise RiskError("config mis_cutoff wants a time like 15:00, got %r" % c["mis_cutoff"])
    warnings = []
    for k, text in ZERO_MEANS_OFF.items():
        if c[k] == 0:
            warnings.append("%s is 0: %s" % (k, text))
    old = [k for k in LEGACY if k in (cfg or {})]
    if old:
        warnings.append("ignored US-era config keys: %s. Kite has no paper account and every order is live; "
                        "the limits are max_order_value and min_order_value in rupees" % ", ".join(old))
    return c, warnings


def _need(data, kind):
    """(snapshot, None) or (None, the BLOCK reason) for a snapshot a rule needs."""
    v = data.get(kind)
    if v is None or isinstance(v, str):
        return None, "data: %s" % (v or "no %s snapshot" % kind)
    return v, None


def account(data):
    """What the Kite snapshots say about the account. Missing pieces stay None."""
    acct = {"cash": None, "equity": None, "held": None, "held_value": None, "mis_net": None,
            "mis_exposure": None, "day_pnl": None, "placed": None, "open": None}
    quotes = data.get("quotes") if isinstance(data.get("quotes"), dict) else {}
    m = data.get("margins")
    if isinstance(m, dict):
        eq = m.get("equity") or {}
        av = eq.get("available") or {}
        acct["cash"] = _f(av.get("live_balance", av.get("cash")))
        acct["equity"] = _f(eq.get("net"))
    h = data.get("holdings")
    if isinstance(h, list):
        held, value = {}, {}
        for row in h:
            sym = str(row.get("tradingsymbol", "")).upper()
            n = (_f(row.get("quantity")) or 0) + (_f(row.get("t1_quantity")) or 0)
            px = (quotes.get(sym) or {}).get("price") or _f(row.get("last_price")) or 0
            held[sym] = held.get(sym, 0) + n
            value[sym] = value.get(sym, 0) + n * px
        acct["held"], acct["held_value"] = held, value
    p = data.get("positions")
    if isinstance(p, dict):
        net, exposure = {}, 0.0
        for row in p.get("net") or []:
            sym = str(row.get("tradingsymbol", "")).upper()
            n = _f(row.get("quantity")) or 0
            if row.get("product") == "CNC":
                # delivery trades made today are listed under positions, not holdings
                if acct["held"] is not None:
                    px = (quotes.get(sym) or {}).get("price") or _f(row.get("last_price")) or 0
                    acct["held"][sym] = acct["held"].get(sym, 0) + n
                    acct["held_value"][sym] = acct["held_value"].get(sym, 0.0) + n * px
                continue
            if row.get("product") != "MIS":
                continue
            net[sym] = net.get(sym, 0) + n
            exposure += abs(n) * (_f(row.get("last_price")) or 0)
        acct["mis_net"], acct["mis_exposure"] = net, exposure
        acct["day_pnl"] = sum(_f(row.get("pnl")) or 0 for row in p.get("day") or [])
    o = data.get("orders")
    if isinstance(o, list):
        acct["placed"] = sum(1 for row in o if str(row.get("status", "")).upper() not in NOT_PLACED)
        acct["open"] = []
        for row in o:
            is_open, n = _pending(row)
            if is_open:
                acct["open"].append((str(row.get("tradingsymbol", "")).upper(),
                                     str(row.get("transaction_type", "")).upper(),
                                     str(row.get("product", "")).upper(), n or 0))
    return acct


def _numeric(x):
    return _f(x) is not None


def _pending(row):
    """(is_open, pending shares) for a Kite order row. Shares is None when the open order has no usable
    quantity. pending_quantity if numeric, else quantity minus filled_quantity, never below 0."""
    if str(row.get("status", "")).upper() in NOT_OPEN:
        return False, 0
    for k in ("quantity", "filled_quantity", "pending_quantity"):
        if row.get(k) is not None and not _numeric(row.get(k)):
            return True, None
    if _numeric(row.get("pending_quantity")):
        return True, max(_f(row.get("pending_quantity")), 0)
    if not _numeric(row.get("quantity")):
        return True, None
    return True, max(_f(row.get("quantity")) - (_f(row.get("filled_quantity")) or 0), 0)


def validated(data):
    """A copy of data where every snapshot of an unexpected shape is replaced by an error text."""
    d = dict(data)

    def bad(kind, why):
        d[kind] = "the %s snapshot %s (Kite answer changed?)" % (kind, why)

    m = d.get("margins")
    if m is not None and not isinstance(m, str):
        eq = m.get("equity") if isinstance(m, dict) else None
        av = eq.get("available") if isinstance(eq, dict) else None
        av = av if isinstance(av, dict) else {}
        if not (_numeric(av.get("live_balance", av.get("cash"))) and _numeric((eq or {}).get("net"))):
            bad("margins", "has no equity cash or net")
    h = d.get("holdings")
    if h is not None and not isinstance(h, str):
        if not (isinstance(h, list) and all(isinstance(r, dict) for r in h)):
            bad("holdings", "is not a list of holdings")
    p = d.get("positions")
    if p is not None and not isinstance(p, str):
        ok = isinstance(p, dict)
        for k in ("net", "day"):
            v = p.get(k) if ok else None
            ok = ok and (isinstance(v, list) and all(isinstance(r, dict) for r in v))
        if not ok:
            bad("positions", "is not a dict of net and day lists")
    o = d.get("orders")
    if o is not None and not isinstance(o, str):
        if not (isinstance(o, list) and all(isinstance(r, dict) for r in o)):
            bad("orders", "is not a list of orders")
        elif any(_pending(r)[1] is None for r in o):
            bad("orders", "has an order without a usable quantity")
    return d


def check(orders, cfg, data, now, cal):
    """Pure function. data maps each snapshot kind to its Kite answer (quotes already normalised by
    kite_snapshot.quotes) or to the error text that explains why it is missing. now is an aware
    datetime; cal is an nse_calendar.Calendar. Returns {"results": [...], "pass": n, "block": n, ...}."""
    c, top_warn = config(cfg)
    top_warn.insert(0, "LIVE: every order here is a real-money order on your Zerodha account")
    now = now.astimezone(nse_calendar.IST)
    st = cal.status(now)
    data = validated(data)
    acct = account(data)
    quotes, quote_err = _need(data, "quotes")
    blocked = set(c["blocked"])
    # sells never get credit for earlier orders of this batch: shorts and "opening" are judged on the snapshot
    snap_mis = dict(acct["mis_net"]) if acct["mis_net"] is not None else None
    snap_held = dict(acct["held"]) if acct["held"] is not None else None
    sold_cnc = {}
    seen, results = set(), []

    for i, o in enumerate(orders, 1):
        reasons, warns = [], []

        def need(kind):
            v, err = _need(data, kind)
            if err and err not in reasons:
                reasons.append(err)
            return v is not None

        sym = str(o.get("tradingsymbol") or "").strip()
        exch = str(o.get("exchange") or "").strip().upper()
        side = str(o.get("transaction_type") or "").strip().upper()
        product = str(o.get("product") or "").strip().upper()
        typ = str(o.get("order_type") or "").strip().upper()
        variety = str(o.get("variety") or "regular").strip().lower()
        qty = _qty(o.get("quantity"))
        price = _f(o.get("price"))

        # format and asset
        if not sym:
            reasons.append("format: no tradingsymbol")
        elif sym != sym.upper() or ":" in sym or sym.endswith(".NS") or " " in sym:
            reasons.append("format: tradingsymbol must be the bare NSE symbol in capitals, like INFY, not %r" % sym)
        if exch != "NSE":
            reasons.append("asset: only NSE orders are supported, not %r" % o.get("exchange"))
        if sym and FNO.search(sym.upper()):
            reasons.append("asset: %s looks like an F&O contract; F&O is not supported" % sym)
        if side not in ("BUY", "SELL"):
            reasons.append("format: transaction_type must be BUY or SELL, got %r" % o.get("transaction_type"))
        if qty is None:
            reasons.append("format: quantity must be a whole number of shares above 0, got %r" % o.get("quantity"))
        for k in ("quantity", "price"):
            if o.get(k) is not None and not isinstance(o.get(k), str):
                warns.append("send %s as a string (\"%s\"), the way the orders file writes it" % (k, o.get(k)))
        if typ in ("SL", "SL-M"):
            reasons.append("format: %s (stop-loss) orders are not supported by this pack" % typ)
        elif typ not in ("LIMIT", "MARKET"):
            reasons.append("format: order_type must be LIMIT or MARKET, got %r" % o.get("order_type"))
        ec = o.get("est_charges")
        est_charges = _f(ec) if not isinstance(ec, bool) else None
        if est_charges is None or est_charges < 0:
            reasons.append("format: est_charges must be a rupee amount of at least 0 (trader-budget writes it)")
            est_charges = 0.0
        if typ == "LIMIT" and not (price and price > 0):
            reasons.append("format: a LIMIT order needs a price above 0")
        if str(o.get("validity") or "DAY").strip().upper() != "DAY":
            reasons.append("format: validity must be DAY, got %r" % o.get("validity"))
        if variety not in ("regular", "amo"):
            reasons.append("format: variety must be regular (or amo), got %r" % o.get("variety"))
        if product not in ("CNC", "MIS"):
            reasons.append("product: %r is not supported: CNC (delivery) or MIS (intraday) only, no NRML or F&O"
                           % o.get("product"))
        if product == "MIS" and not c["allow_mis"]:
            reasons.append("product: MIS (intraday) is off (\"allow_mis\": false)")
        if sym.upper() in blocked:
            reasons.append("blocked: %s is on your blocked list" % sym)

        # market hours
        if not st["calendar_known"]:
            reasons.append("hours: NSE's holiday list for %s is not loaded (alerts.py holidays refresh), so the "
                           "market may be closed today" % st["date"][:4])
        elif st["open"]:
            if variety == "amo":
                reasons.append("hours: an amo (after-market) order while NSE is open; use variety regular")
        elif not (c["allow_amo"] and variety == "amo"):
            reasons.append("hours: NSE is closed (%s, %s IST); orders go in 09:15 to 15:30 IST on trading days"
                           % (st["reason"], st["now_ist"]))

        # price
        q = None
        if quote_err:
            reasons.append(quote_err)
        elif sym:
            q = quotes.get(sym.upper())
            if not q:
                reasons.append("data: no fresh Kite quote for NSE:%s; add it to the quotes call" % sym)
        if typ == "MARKET" and not c["allow_market_orders"]:
            reasons.append("price: MARKET orders are off (\"allow_market_orders\": false); use a LIMIT price")
        ref = price if typ == "LIMIT" else (q["price"] if q else None)
        if q and typ == "LIMIT" and price:
            dev = abs(price - q["price"]) / q["price"] * 100.0
            if dev > c["max_limit_deviation_pct"] + 1e-9:
                reasons.append("price: limit %s is %.2f%% from the last price %s, over your %s%% limit"
                               % (inr(price), dev, inr(q["price"]), _pct(c["max_limit_deviation_pct"])))
        if q and ref:
            lo, hi = q.get("lower_circuit"), q.get("upper_circuit")
            if lo is None or hi is None:
                reasons.append("data: the Kite quote for NSE:%s has no circuit limits; use the full quotes call" % sym)
            elif ref < lo - PAISA or ref > hi + PAISA:
                reasons.append("price: %s is outside today's circuit band %s to %s" % (inr(ref), inr(lo), inr(hi)))
        value = qty * ref if (qty and ref) else None

        # size
        if value is not None:
            if value < c["min_order_value"] - PAISA:
                reasons.append("size: %s is under your %s minimum order" % (inr(value), inr(c["min_order_value"])))
            if c["max_order_value"] and value > c["max_order_value"] + PAISA:
                reasons.append("size: %s is over your %s max order" % (inr(value), inr(c["max_order_value"])))

        # the account, simulated in order
        opening = None
        if product == "CNC" and side == "BUY" and value is not None:
            if need("margins") and need("holdings") and need("positions"):
                cash = acct["cash"]
                total = cash + sum(acct["held_value"].values())
                after = cash - value - est_charges
                buffer_rs = total * c["cash_buffer_pct"] / 100.0
                if after < -PAISA:
                    reasons.append("cash: needs %s with charges but only %s is available"
                                   % (inr(value + est_charges), inr(cash)))
                elif after < buffer_rs - PAISA:
                    reasons.append("cash: leaves %s, under your %s%% buffer of %s"
                                   % (inr(max(after, 0)), _pct(c["cash_buffer_pct"]), inr(buffer_rs)))
                pos_after = acct["held_value"].get(sym, 0.0) + value
                limit = total * c["max_position_pct"] / 100.0
                if total > 0 and pos_after > limit + PAISA:
                    reasons.append("position: %s would be %s, %.1f%% of the %s account, over your %s%% cap"
                                   % (sym, inr(pos_after), 100.0 * pos_after / total, inr(total),
                                      _pct(c["max_position_pct"])))
        if product == "CNC" and side == "SELL" and qty:
            if need("holdings") and need("positions"):
                have = snap_held.get(sym, 0) - sold_cnc.get(sym, 0)
                pend = sum(n for (s_, t_, p_, n) in (acct["open"] or []) if (s_, t_, p_) == (sym, "SELL", "CNC"))
                if qty > have - pend + 1e-9:
                    if pend:
                        reasons.append("short: selling %d %s but you hold %d and %d are already in open sell orders"
                                       % (qty, sym, int(have), int(pend)))
                    else:
                        reasons.append("short: selling %d %s but you hold %d; a delivery sale needs the shares"
                                       % (qty, sym, int(have)))
        if product == "MIS" and side in ("BUY", "SELL") and qty:
            if need("positions") and need("margins"):
                net = snap_mis.get(sym, 0)
                after_net = net + (qty if side == "BUY" else -qty)
                opening = abs(after_net) > abs(net) or after_net * net < 0
                if side == "SELL" and after_net < 0 and not c["allow_short"]:
                    reasons.append("short: this MIS sell would leave you short %d %s; short selling is off "
                                   "(\"allow_short\": false)" % (-after_net, sym))
                if opening:
                    if now.time() >= c["mis_cutoff"]:
                        reasons.append("intraday: no new MIS positions after %s IST; Zerodha squares MIS off "
                                       "from about 15:20" % c["mis_cutoff"].strftime("%H:%M"))
                    if value is not None and acct["equity"] is not None:
                        after = acct["mis_exposure"] + value
                        limit = acct["equity"] * c["max_mis_exposure_pct"] / 100.0
                        if after > limit + PAISA:
                            reasons.append("intraday: MIS exposure would be %s, over %s%% of your %s equity margin"
                                           % (inr(after), _pct(c["max_mis_exposure_pct"]), inr(acct["equity"])))
                    if c["daily_loss_limit"] and acct["day_pnl"] <= -c["daily_loss_limit"]:
                        reasons.append("intraday: today's loss %s has reached your %s daily loss limit; no new MIS "
                                       "positions today" % (inr(-acct["day_pnl"]), inr(c["daily_loss_limit"])))

        # duplicates and the daily limit
        key = (sym, side, product)
        if key in seen:
            reasons.append("duplicate: a second %s %s %s in this batch" % (side, sym, product))
        seen.add(key)
        if acct["open"] and any((s_, t_, p_) == key for (s_, t_, p_, n) in acct["open"]):
            reasons.append("duplicate: an open %s %s %s order is already in Kite's order book; wait for it to "
                           "fill or cancel it" % (side, sym, product))
        if need("orders"):
            passed = sum(1 for r in results if r["verdict"] == "PASS")
            cap_n = int(c["max_orders_per_day"])
            if cap_n and acct["placed"] + passed >= cap_n:
                reasons.append("daily limit: %d orders in Kite's order book today plus %d passed earlier in this "
                               "batch, your limit is %d a day" % (acct["placed"], passed, cap_n))

        verdict = "BLOCK" if reasons else "PASS"
        if verdict == "PASS" and value is not None:
            if product == "CNC" and side == "BUY":
                acct["cash"] -= value + est_charges
                acct["held_value"][sym] = acct["held_value"].get(sym, 0.0) + value
                acct["held"][sym] = acct["held"].get(sym, 0) + qty
            elif product == "CNC":
                acct["held"][sym] = acct["held"].get(sym, 0) - qty
                sold_cnc[sym] = sold_cnc.get(sym, 0) + qty
                acct["held_value"][sym] = max(acct["held_value"].get(sym, 0.0) - value, 0.0)
            else:
                acct["mis_net"][sym] = acct["mis_net"].get(sym, 0) + (qty if side == "BUY" else -qty)
                acct["mis_exposure"] = max(acct["mis_exposure"] + (value if opening else -value), 0.0)
        results.append({
            "index": i, "symbol": sym, "side": side, "product": product, "quantity": qty,
            "amount": ("%d x %s = %s" % (qty, inr(ref), inr(value))) if value is not None else str(o.get("quantity")),
            "value": round(value, 2) if value is not None else None,
            "fingerprint": fingerprint(o), "verdict": verdict, "reasons": reasons, "warnings": warns,
        })

    return {
        "checked_at": now.replace(microsecond=0).isoformat(), "date": st["date"], "live": True,
        "market": {k: st.get(k) for k in ("open", "reason", "now_ist", "calendar_known")},
        "results": results,
        "pass": sum(1 for r in results if r["verdict"] == "PASS"),
        "block": sum(1 for r in results if r["verdict"] == "BLOCK"),
        "warnings": top_warn,
        "cash_after": round(acct["cash"], 2) if acct["cash"] is not None else None,
    }


def report(res):
    lines = []
    for w in res["warnings"]:
        lines.append("WARNING: " + w)
    lines.append("")
    for r in res["results"]:
        lines.append("%-5s #%d %s %s %s %s" % (r["verdict"], r["index"], r["side"], r["symbol"], r["product"],
                                               r["amount"]))
        for x in r["reasons"]:
            lines.append("        - " + x)
        for x in r["warnings"]:
            lines.append("        ~ " + x)
    lines.append("")
    cash = (" Cash after the passed orders: %s." % inr(res["cash_after"])) if res["cash_after"] is not None else ""
    lines.append("%d passed, %d blocked.%s LIVE account, real money." % (res["pass"], res["block"], cash))
    if res["block"]:
        lines.append("Blocked orders do not go to the broker. Fix the order or your rules, then check again.")
    else:
        lines.append("Every order passed. trader-broker still asks you yes or no for each one.")
    lines.append("Education and tooling, not financial advice.")
    return "\n".join(lines)


def load_data(kite_dir, now):
    """Each Kite snapshot, or the error text saying why it cannot be used."""
    data = {}
    for kind in SNAPSHOTS:
        try:
            v = kite_snapshot.load(kind, kite_dir, now=now)
        except kite_snapshot.SnapshotError as e:
            data[kind] = str(e)
            continue
        data[kind] = kite_snapshot.quotes(v) if kind == "quotes" else v
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check proposed LIVE orders against your limits (trader-risk).")
    ap.add_argument("--orders", default="trader/orders.json")
    ap.add_argument("--config", default="trader/config.json")
    ap.add_argument("--kite-dir", default=kite_snapshot.DIR, help="where the Kite snapshots are")
    ap.add_argument("--holidays", default=nse_calendar.CACHE, help="the cached NSE holiday list")
    ap.add_argument("--now", help="pretend it is this time (ISO; no offset = IST)")
    ap.add_argument("--out", default="trader/state/risk.json", help="where the verdicts are recorded")
    ap.add_argument("--no-write", action="store_true", help="do not record the verdicts")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        if os.path.exists(a.out):
            os.remove(a.out)  # a crash or error must never leave an earlier PASS on disk
        doc = read_json(a.orders, "orders file (run trader-budget first)")
        orders = doc.get("orders", doc) if isinstance(doc, dict) else doc
        if not isinstance(orders, list) or not orders:
            raise RiskError("no orders in %s" % a.orders)
        cfg = read_json(a.config, "config", required=False) or {}
        now = nse_calendar.parse_now(a.now)
        cal = nse_calendar.Calendar(*nse_calendar.load_holidays(a.holidays))
        res = check(orders, cfg, load_data(a.kite_dir, now), now, cal)
        if not a.no_write:
            d = os.path.dirname(a.out)
            if d:
                os.makedirs(d, exist_ok=True)
            rec = dict(res)
            rec["orders_file"] = a.orders
            with open(a.out, "w", encoding="utf-8") as fh:
                json.dump(rec, fh, indent=2)
                fh.write("\n")
    except (RiskError, nse_calendar.CalendarError) as e:
        print("check.py: %s" % e, file=sys.stderr)
        return 1
    print(json.dumps(res, indent=2) if a.json else report(res))
    return 1 if res["block"] else 0


if __name__ == "__main__":
    sys.exit(main())
