#!/usr/bin/env python3
"""Indian capital gains on your NSE trades, for trader-tax. Standard library only, no network.

Not tax advice: arithmetic on your trades. A tax professional decides what
applies to you.

    python3 lots.py report                       # open lots, unrealised gain by term
    python3 lots.py gains                        # realised gains, set-off, carry-forward, estimate per FY
    python3 lots.py gains --fy 2026-27
    python3 lots.py sell INFY 4                  # what selling 4 INFY now would realise (FIFO)
    python3 lots.py harvest --min-loss 1000      # losses to book, and LTCG headroom
    python3 lots.py harvest --write              # loss-harvest sells -> trader/orders.json (needs fresh holdings
                                                 # and orders; --include-gains adds long-term gain sells;
                                                 # removes the old file if there is nothing to propose or it fails)

Inputs (see tradebook.py):
  trader/tradebook*.csv   Zerodha Console equity tradebooks (all your history)
  trader/lots.csv         opening lots bought before the tradebook starts
  trader/fmv_2018.csv     31 Jan 2018 prices for shares bought before 2018-02-01
  trader/kite/trades.json today's Kite trades (kite_snapshot.py save trades); used only if saved today
  trader/kite/holdings.json   Kite holdings, to check the lots add up
  trader/kite/positions.json  today's delivery (CNC) trades, added to the holdings for that check
  trader/kite/orders.json     Kite's order book: harvest skips a stock with an open order
  trader/kite/quotes.json     Kite quotes, for unrealised gains

A sale "today" (sell, harvest) is worked out by adding it to your trades, so
shares you bought today are matched intraday first. Harvest measures each
proposal with the full set-off for this financial year: a loss is proposed
only if it saves tax this year or carries forward, and a long-term gain only
if it adds no tax and uses up no carried or current loss. Stocks on your
blocked list (config "blocked") or with an open order are never proposed.

The rules are in ledger.py (lots, terms, the 2018 rule) and india_tax.py
(financial years, set-off, exemption, carry-forward). India has no wash-sale
rule: a loss stays a loss if you buy back, but the new shares start a new
12-month clock.
"""

import argparse
import datetime
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import charges
import india_tax
import kite_snapshot
import ledger
import nse_calendar
import tradebook
from rupees import inr

NOT_ADVICE = ("Not tax advice: arithmetic on your trades. Check the rates each year and ask a tax professional "
              "what applies to you. Education and tooling, not financial advice.")
KIND_WORDS = {"STCG": "short term", "LTCG": "long term", "SPECULATIVE": "intraday (speculative)"}
FINISHED = ("COMPLETE", "REJECTED", "CANCELLED")
NO_POSITIONS = "today's delivery trades are not checked (no positions snapshot)"


class TaxError(Exception):
    pass


def _now(a):
    try:
        return nse_calendar.parse_now(a.now)
    except nse_calendar.CalendarError as e:
        raise TaxError(str(e))


def _today(a):
    return _now(a).date()


def _config(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as e:
        raise TaxError("%s is not valid JSON: %s" % (path, e))


def load_inputs(a):
    """{"book": ledger.build result, "notes": [...], "cfg": {...}} from the files and snapshots."""
    notes = []
    files = a.tradebook or sorted(glob.glob(os.path.join("trader", "tradebook*.csv")))
    lists, skipped = [], 0
    if a.lots and os.path.exists(a.lots):
        lists.append(tradebook.read_lots(a.lots))
    for f in files:
        trades, n = tradebook.read_tradebook(f)
        lists.append(trades)
        skipped += n
    if skipped:
        notes.append("%d non-equity or non-NSE tradebook rows skipped (F&O, BSE, ...)" % skipped)
    now = _now(a)
    try:
        data = kite_snapshot.load("trades", a.kite_dir, now=now, max_age=float("inf"))
        saved = (now - datetime.timedelta(seconds=kite_snapshot.age("trades", a.kite_dir, now))).date()
        if saved == now.date():
            lists.append(tradebook.kite_trades(data))
        else:
            notes.append("today's Kite trades are not included (the snapshot is from %s)" % saved)
    except kite_snapshot.SnapshotError as e:
        notes.append("today's Kite trades are not included (%s)" % e)
    if not lists:
        raise TaxError("no trades: download your Zerodha Console tradebook to trader/tradebook-<year>.csv "
                       "(or pass --tradebook), and put older holdings in trader/lots.csv")
    fmv = tradebook.read_fmv(a.fmv) if a.fmv and os.path.exists(a.fmv) else {}
    trades = tradebook.merge(*lists)
    book = ledger.build(trades, fmv)
    book["fmv"] = fmv
    book["trades"] = trades
    return {"book": book, "notes": notes + book["problems"], "cfg": _config(a.config)}


def quote_prices(kite_dir, now=None):
    try:
        snap = kite_snapshot.quotes(kite_snapshot.load("quotes", kite_dir, now=now))
    except kite_snapshot.SnapshotError as e:
        raise TaxError(str(e))
    return {s: q["price"] for s, q in snap.items()}


def holdings_check(lots, kite_dir, now=None):
    """(warnings, {symbol: (trades_qty, kite_qty)}, error): where the lots do not match Kite's holdings
    (quantity + T1, plus today's CNC net positions when a fresh positions snapshot exists). error is set
    when the holdings snapshot is missing or stale."""
    try:
        hold = kite_snapshot.load("holdings", kite_dir, now=now)
    except kite_snapshot.SnapshotError as e:
        return ["could not check the lots against Kite holdings (%s)" % e], {}, str(e)
    kite = {}
    for r in hold if isinstance(hold, list) else []:
        sym = str(r.get("tradingsymbol", "")).upper()
        kite[sym] = kite.get(sym, 0) + int(float(r.get("quantity") or 0) + float(r.get("t1_quantity") or 0))
    try:
        pos = kite_snapshot.load("positions", kite_dir, now=now)
    except kite_snapshot.SnapshotError:
        pos = None
    for r in ((pos or {}).get("net") or []) if isinstance(pos, dict) else []:
        if r.get("product") == "CNC":
            sym = str(r.get("tradingsymbol", "")).upper()
            kite[sym] = kite.get(sym, 0) + int(float(r.get("quantity") or 0))
    mine = {s: sum(l["qty"] for l in ls) for s, ls in lots.items()}
    out, bad = [], {}
    for s in sorted(set(kite) | set(mine)):
        if kite.get(s, 0) != mine.get(s, 0):
            bad[s] = (mine.get(s, 0), kite.get(s, 0))
            out.append("%s: the trades give %d shares but Kite holds %d; the tradebook or lots.csv is incomplete"
                       % (s, mine.get(s, 0), kite.get(s, 0)))
    if pos is None:
        out.append(NO_POSITIONS)
    return out, bad, None


def reconcile(lots, kite_dir, now=None):
    """Warnings where the lots do not match Kite's holdings (quantity + T1)."""
    return holdings_check(lots, kite_dir, now)[0]


def unrealised(lots, prices, today, fmv=None):
    """One row per lot: what selling it today at the Kite price would realise."""
    rows = []
    for sym in sorted(lots):
        for lot in lots[sym]:
            if sym not in prices:
                rows.append({"symbol": sym, "lot": lot, "price": None, "gain": None, "kind": None})
                continue
            g = ledger.close(lot, lot["qty"], prices[sym], today, fmv)
            rows.append({"symbol": sym, "lot": lot, "price": prices[sym], "gain": g["gain"], "kind": g["kind"],
                         "grandfathered": g["grandfathered"],
                         "long_term_from": ledger.anniversary(lot["date"]) + datetime.timedelta(days=1)})
    return rows


def cmd_report(a):
    inp = load_inputs(a)
    lots = inp["book"]["lots"]
    today = _today(a)
    rows = unrealised(lots, quote_prices(a.kite_dir, _now(a)), today, inp["book"]["fmv"])
    notes = inp["notes"] + reconcile(lots, a.kite_dir, _now(a))
    if a.json:
        print(json.dumps({"lots": rows, "notes": notes}, indent=2, default=str))
        return 0
    print("%-12s %-10s %6s %12s %12s %14s  %s" % ("symbol", "bought", "qty", "cost", "price", "unrealised", "term"))
    for r in rows:
        lot = r["lot"]
        if r["price"] is None:
            print("%-12s %-10s %6d %12s %12s %14s  no Kite quote" % (r["symbol"], lot["date"], lot["qty"],
                                                                     inr(lot["price"]), "", ""))
            continue
        when = "" if r["kind"] == "LTCG" else ", long term from %s" % r["long_term_from"]
        if r.get("grandfathered"):
            when += ", 31 Jan 2018 price used as cost"
        print("%-12s %-10s %6d %12s %12s %14s  %s%s" % (r["symbol"], lot["date"], lot["qty"], inr(lot["price"]),
                                                       inr(r["price"]), inr(r["gain"]), KIND_WORDS[r["kind"]], when))
    for n in notes:
        print("Note: " + n)
    print(NOT_ADVICE)
    return 0


def cmd_gains(a):
    inp = load_inputs(a)
    book = inp["book"]
    years = india_tax.summarise(book["realised"], book["speculative"], inp["cfg"].get("tax_rules"))
    if a.fy:
        years = [y for y in years if y["fy"] == a.fy]
        if not years:
            raise TaxError("no realised gains or losses in FY %s" % a.fy)
    if a.json:
        print(json.dumps({"years": years, "notes": inp["notes"]}, indent=2, default=str))
        return 0
    for y in years:
        print("FY %s" % y["fy"])
        print("  short term: gains %s, losses %s, net after set-off %s" % (inr(y["stcg"]), inr(y["stcl"]),
                                                                          inr(y["st_net"])))
        print("  long term:  gains %s, losses %s, net after set-off %s (exemption used %s, left %s)"
              % (inr(y["ltcg"]), inr(y["ltcl"]), inr(y["lt_net"]), inr(y["exemption_used"]), inr(y["exemption_left"])))
        print("  intraday (speculative, slab rate): %s, net %s" % (inr(y["speculative"]), inr(y["speculative_net"])))
        if y["estimate"]:
            e = y["estimate"]
            print("  estimated tax: short term %s + long term %s = %s (plus cess and surcharge if any)"
                  % (inr(e["stcg"]), inr(e["ltcg"]), inr(e["total"])))
        for c in y["carry_forward"]:
            print("  carried forward: %s loss %s from %s, usable until FY %s"
                  % ({"ST": "short-term", "LT": "long-term", "SPEC": "speculative"}[c["kind"]], inr(c["amount"]),
                     c["fy"], c["last_fy"]))
        for n in y["notes"]:
            print("  - " + n)
    for n in inp["notes"]:
        print("Note: " + n)
    print("Carried-forward losses count only if that year's return was filed on time.")
    print(NOT_ADVICE)
    return 0


def cmd_sell(a):
    inp = load_inputs(a)
    sym = tradebook._symbol(a.symbol, "symbol")
    lots = inp["book"]["lots"].get(sym, [])
    if not lots:
        raise TaxError("the trades show no %s held" % sym)
    price = a.price if a.price is not None else quote_prices(a.kite_dir, _now(a)).get(sym)
    if not price:
        raise TaxError("no Kite quote for NSE:%s: add it to the quotes call, or pass --price" % sym)
    gains, short = ledger.sale_effect(inp["book"]["trades"], sym, a.qty, price, _today(a), inp["book"]["fmv"])
    if short:
        raise TaxError("you hold only %d %s by the trades" % (a.qty - short, sym))
    if a.json:
        print(json.dumps({"gains": gains}, indent=2, default=str))
        return 0
    for g in gains:
        print("%d %s bought %s at %s: %s %s%s" % (g["qty"], sym, g["acquired"], inr(g["buy_price"]),
                                                  KIND_WORDS[g["kind"]], inr(g["gain"]),
                                                  " (31 Jan 2018 price used)" if g["grandfathered"] else ""))
    print("Total: %s. Shares are sold oldest first (FIFO)." % inr(sum(g["gain"] for g in gains)))
    for n in inp["notes"]:
        print("Note: " + n)
    print(NOT_ADVICE)
    return 0


def fy_row(book, extra_gains, fy, tax_rules=None):
    """This financial year's india_tax.summarise row after adding extra_gains (realised or speculative) to
    the book. A zero placeholder gain makes sure the year has a row, so losses carried into a year with no
    sales yet still count."""
    start = datetime.date(int(fy[:4]), 4, 1)
    realised = list(book["realised"]) + [g for g in extra_gains if g["kind"] != "SPECULATIVE"]
    spec = list(book["speculative"]) + [g for g in extra_gains if g["kind"] == "SPECULATIVE"]
    realised.append({"kind": "STCG", "sold": start, "gain": 0.0})
    for y in india_tax.summarise(realised, spec, tax_rules):
        if y["fy"] == fy:
            return y
    return None


def effect(book, extra_gains, fy, tax_rules=None):
    """(estimate_total, carry_total) for financial year fy after adding extra_gains: the estimated tax that
    year (0 when there is no estimate) and the losses still carried forward at its end."""
    y = fy_row(book, extra_gains, fy, tax_rules)
    if not y:
        return 0.0, 0.0
    return (y["estimate"] or {}).get("total", 0.0), round(sum(c["amount"] for c in y["carry_forward"]), 2)


def _max_value(cfg):
    try:
        return float(cfg.get("max_order_value", 10000) or 0)
    except (TypeError, ValueError):
        raise TaxError("config max_order_value must be a number of rupees")


def _cut(sym, qty, price, max_value, notes):
    """qty cut to max_order_value (trader-risk blocks bigger orders), or None when not even one share fits."""
    if qty < 1:
        return None
    if max_value and qty * price > max_value:
        qty = int(max_value // price)
        if qty < 1:
            notes.append("%s: one share costs more than your max order; not proposed" % sym)
            return None
    return qty


def _sell(sym, qty, price, cfg, why):
    value = qty * price
    est = charges.estimate("CNC", "SELL", value, cfg.get("charges"))
    return {"exchange": "NSE", "tradingsymbol": sym, "transaction_type": "SELL", "quantity": str(qty),
            "product": "CNC", "order_type": "LIMIT", "price": "%.2f" % price, "validity": "DAY",
            "variety": "regular", "est_value": "%.2f" % value, "est_charges": "%.2f" % est["total"], "why": why}


def _total(gains):
    return round(sum(g["gain"] for g in gains), 2)


def harvest(book, prices, today, min_loss, cfg, notes, skip=(), tax_rules=None):
    """{"losses", "gains", "loss_orders", "gain_orders", "loss_candidates"} for this financial year, each
    sale worked out by adding it to the trades (ledger.sale_effect: intraday first, then the oldest lots)
    and measured with the full set-off (india_tax.summarise).

    Losses: selling a whole position that books at least min_loss, cut to max_order_value. Proposed only if
    it saves tax this year or adds to the loss carried forward. Gains: long-term lots, oldest first, sized
    to the exemption left, cut to max_order_value, then one share less at a time until the sale adds no tax
    and uses up no carried or current loss. A symbol is never in both, and symbols in skip are left out."""
    fy = india_tax.fy_of(today)
    max_value = _max_value(cfg)
    trades, fmv = book["trades"], book["fmv"]
    losses, loss_orders, extra, taken = [], [], [], set()
    cands = []
    for sym in sorted(book["lots"]):
        if sym in skip:
            continue
        if sym not in prices:
            notes.append("%s: no Kite quote, skipped" % sym)
            continue
        price = prices[sym]
        full = sum(l["qty"] for l in book["lots"][sym])
        res = ledger.sale_effect(trades, sym, full, price, today, fmv)[0]
        net = _total(res)
        if not (net < 0 and -net >= min_loss):
            continue
        taken.add(sym)
        qty = _cut(sym, full, price, max_value, notes)
        if qty is None:
            continue
        if qty < full:
            res = ledger.sale_effect(trades, sym, qty, price, today, fmv)[0]
            net = _total(res)
            if net > -min_loss:
                notes.append("%s: selling only %d of %d (to stay under your max order) would book %s because the "
                             "oldest shares go first; not proposed"
                             % (sym, qty, full, "a gain of %s" % inr(net) if net > 0
                                else "a loss of only %s" % inr(-net)))
                continue
        cands.append((sym, qty, full, price, res, net))
    # Largest loss first (then symbol), so the biggest saving gets the first claim; each is then measured on
    # top of the losses already proposed, as the gain loop below does.
    cands.sort(key=lambda c: (c[5], c[0]))
    for sym, qty, full, price, res, net in cands:
        base_tax, base_carry = effect(book, extra, fy, tax_rules)
        new_tax, new_carry = effect(book, extra + res, fy, tax_rules)
        saved, carried = round(base_tax - new_tax, 2), round(new_carry - base_carry, 2)
        if saved <= 0.005 and carried <= 0.005:
            notes.append("%s: booking this loss saves no tax this year (it would only offset gains already inside "
                         "the exemption) and nothing would carry forward; not proposed" % sym)
            continue
        if qty < full:
            notes.append("%s: selling %d of %d now keeps the order under your %s max order; sell the rest later"
                         % (sym, qty, full, inr(max_value)))
        parts = (["saves about %s this year" % inr(saved)] if saved > 0.005 else []) \
            + (["%s carries forward" % inr(carried)] if carried > 0.005 else [])
        losses.append({"symbol": sym, "qty": qty, "price": price, "loss": round(-net, 2),
                       "by_term": {k: round(sum(g["gain"] for g in res if g["kind"] == k), 2)
                                   for k in ("STCG", "LTCG", "SPECULATIVE")},
                       "saves": saved, "carries": carried})
        loss_orders.append(_sell(sym, qty, price, cfg, "book a %s loss (%s)" % (inr(-net), ", ".join(parts))))
        extra += res

    gains, gain_orders = [], []
    for sym in sorted(book["lots"]):
        if sym not in prices or sym in skip or sym in taken:
            continue
        price = prices[sym]
        base_tax, base_carry = effect(book, extra, fy, tax_rules)
        y = fy_row(book, extra, fy, tax_rules)
        left = max(0.0, y["exemption_left"] if y else india_tax.rules(tax_rules)["ltcg_exemption"])
        n, booked = 0, 0.0
        for lot in book["lots"][sym]:
            g = ledger.close(lot, lot["qty"], price, today, fmv)
            if g["kind"] != "LTCG" or g["gain"] <= 0:
                break
            per = g["gain"] / lot["qty"]
            fit = min(lot["qty"], int((left - booked) // per)) if per > 0 else 0
            if fit > 0:
                n += fit
                booked += fit * per
            if fit < lot["qty"]:
                break
        if n < 1:
            continue
        cut = _cut(sym, n, price, max_value, notes)
        if cut is None:
            continue
        qty, used, res = cut, None, []
        while qty > 0:
            res = ledger.sale_effect(trades, sym, qty, price, today, fmv)[0]
            new_tax, new_carry = effect(book, extra + res, fy, tax_rules)
            if used is None:
                used = round(base_carry - new_carry, 2)
            if all(g["kind"] == "LTCG" for g in res) and _total(res) > 0.005 \
                    and abs(new_tax - base_tax) <= 0.005 and abs(new_carry - base_carry) <= 0.005:
                break
            qty -= 1
        if qty < 1:
            if used and used > 0.005:
                notes.append("%s: a long-term gain now would use up %s of loss that is worth more later; not "
                             "proposed" % (sym, inr(used)))
            continue
        if cut < n:
            notes.append("%s: selling %d of %d now keeps the order under your %s max order; sell the rest later"
                         % (sym, cut, n, inr(max_value)))
        gain = _total(res)
        gains.append({"symbol": sym, "qty": qty, "price": price, "gain": gain})
        gain_orders.append(_sell(sym, qty, price, cfg, "book %s of long-term gain: no tax this year and no carried "
                                                       "loss used up" % inr(gain)))
        extra += res
    return {"losses": losses, "gains": gains, "loss_orders": loss_orders, "gain_orders": gain_orders,
            "loss_candidates": sorted(taken)}


def remove_old(path):
    """Remove an old orders file; returns how to name it ("the old PATH (proposals from WHO)")."""
    who = None
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        who = doc.get("created_by") if isinstance(doc, dict) else None
    except (OSError, ValueError):
        who = None
    os.remove(path)
    if who and isinstance(who, str):
        return "the old %s (proposals from %s)" % (path, who)
    return "the old %s" % path


def cmd_harvest(a):
    if a.min_loss < 0:
        raise TaxError("--min-loss must be 0 or more")
    inp = load_inputs(a)
    book = inp["book"]
    now = _now(a)
    today = now.date()
    warnings, bad, hold_err = holdings_check(book["lots"], a.kite_dir, now)
    if a.write and hold_err:
        raise TaxError("harvest --write needs a fresh Kite holdings snapshot to check the lots "
                       "(refresh it with kite_snapshot.py save holdings)")
    try:
        ords = kite_snapshot.load("orders", a.kite_dir, now=now)
        if not isinstance(ords, list):
            raise kite_snapshot.SnapshotError("the orders snapshot is not a list (Kite answer changed?)")
        ord_err = None
    except kite_snapshot.SnapshotError as e:
        ords, ord_err = [], str(e)
    if a.write and ord_err:
        raise TaxError("harvest --write needs a fresh Kite orders snapshot to check for open orders "
                       "(refresh it with kite_snapshot.py save orders)")
    notes = inp["notes"] + (["could not check the lots against Kite holdings (%s)" % hold_err] if hold_err else [])
    notes += [w for w in warnings if w == NO_POSITIONS]
    if ord_err:
        notes.append("could not check Kite's open orders (%s)" % ord_err)
    for s_, (mine, theirs) in sorted(bad.items()):
        if s_ in book["lots"]:
            notes.append("%s skipped: the trades give %d shares but Kite holds %d, so the oldest-first tax figures "
                         "would be wrong" % (s_, mine, theirs))
    busy = {str(o.get("tradingsymbol", "")).upper() for o in ords
            if isinstance(o, dict) and str(o.get("status", "")).upper() not in FINISHED}
    blocked = {tradebook._symbol(b, "config blocked") for b in inp["cfg"].get("blocked") or []}
    for s_ in sorted(book["lots"]):
        if s_ in busy:
            notes.append("%s has an open order in Kite: skipped" % s_)
        if s_ in blocked:
            notes.append("%s is on your blocked list: skipped" % s_)
    tax_rules = inp["cfg"].get("tax_rules")
    india_tax.rules(tax_rules)
    h = harvest(book, quote_prices(a.kite_dir, now), today, a.min_loss, inp["cfg"], notes,
                set(bad) | busy | blocked, tax_rules)
    losses, gains = h["losses"], h["gains"]
    orders = h["loss_orders"] + (h["gain_orders"] if a.include_gains else [])
    removed = None
    if a.write and not orders and os.path.exists(a.write):
        removed = remove_old(a.write)
    if a.write and orders:
        d = os.path.dirname(a.write)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(a.write, "w", encoding="utf-8") as fh:
            json.dump({"created_by": "trader-tax", "created_at": datetime.datetime.now(kite_snapshot.IST)
                       .replace(microsecond=0).isoformat(), "status": "proposed", "live": True,
                       "note": "Proposals only. Every order is a LIVE order with real money. Nothing is placed until "
                               "trader-risk passes each order and you say yes to it in the chat.",
                       "orders": orders}, fh, indent=2)
            fh.write("\n")
    if a.json:
        print(json.dumps({"losses": losses, "gains": gains, "orders": orders, "notes": notes}, indent=2))
        return 0 if orders else 1
    print("FY %s, today %s." % (india_tax.fy_of(today), today))
    if losses:
        print("Losses worth booking (oldest shares first; each saves tax this year or carries forward):")
        for c in losses:
            spec = c["by_term"]["SPECULATIVE"]
            print("  SELL %d %s at %s: loss %s (short term %s, long term %s%s)" % (
                c["qty"], c["symbol"], inr(c["price"]), inr(c["loss"]), inr(c["by_term"]["STCG"]),
                inr(c["by_term"]["LTCG"]), ", intraday %s" % inr(spec) if spec else ""))
    elif h["loss_candidates"]:
        print("No loss of %s or more is worth booking this year (see the notes)." % inr(a.min_loss))
    else:
        print("No position would book a loss of %s or more." % inr(a.min_loss))
    if gains:
        print("Long-term gains that add no tax this year and use up no carried loss:")
        for c in gains:
            print("  SELL %d %s at %s: long-term gain %s" % (c["qty"], c["symbol"], inr(c["price"]), inr(c["gain"])))
    if orders:
        print("Proposed LIVE orders:")
        for o in orders:
            print("  SELL %s %s at %s (CNC LIMIT, about %s): %s" % (o["quantity"], o["tradingsymbol"],
                                                                 inr(float(o["price"])), inr(float(o["est_value"])),
                                                                 o["why"]))
    if removed:
        print("Removed %s: nothing to propose." % removed)
    if a.write and orders:
        print("Wrote %d proposed LIVE order(s) to %s. trader-risk checks them next." % (len(orders), a.write))
    print("India has no wash-sale rule, but shares you buy back start a new 12-month clock.")
    for n in notes:
        print("Note: " + n)
    print(NOT_ADVICE)
    return 0 if (losses or gains) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Indian capital gains on your NSE trades (trader-tax). Not tax advice.")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--tradebook", action="append", help="a Zerodha Console tradebook CSV (repeat for more)")
        p.add_argument("--lots", default="trader/lots.csv")
        p.add_argument("--fmv", default="trader/fmv_2018.csv")
        p.add_argument("--kite-dir", default=kite_snapshot.DIR)
        p.add_argument("--config", default="trader/config.json")
        p.add_argument("--now", help="pretend it is this time (ISO, IST; tests only, needs TRADER_TEST_CLOCK=1)")
        p.add_argument("--json", action="store_true")

    common(sub.add_parser("report", help="open lots and unrealised gains"))
    p = sub.add_parser("gains", help="realised gains per financial year")
    common(p)
    p.add_argument("--fy", help="one financial year, like 2026-27")
    p = sub.add_parser("sell", help="what selling now would realise")
    common(p)
    p.add_argument("symbol")
    p.add_argument("qty", type=int)
    p.add_argument("--price", type=float)
    p = sub.add_parser("harvest", help="losses to book and long-term gain headroom")
    common(p)
    p.add_argument("--min-loss", type=float, default=1000.0)
    p.add_argument("--include-gains", action="store_true", help="also write the long-term gain sells")
    p.add_argument("--write", nargs="?", const="trader/orders.json", metavar="PATH")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"report": cmd_report, "gains": cmd_gains, "sell": cmd_sell, "harvest": cmd_harvest}[a.cmd](a)
    except (TaxError, tradebook.TradeError, india_tax.TaxRuleError, charges.ChargesError) as e:
        print("lots.py: %s" % e, file=sys.stderr)
        if getattr(a, "write", None) and os.path.exists(a.write):
            print("Removed %s so no out-of-date proposals are left." % remove_old(a.write), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
