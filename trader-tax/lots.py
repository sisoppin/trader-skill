#!/usr/bin/env python3
"""Indian capital gains on your NSE trades, for trader-tax. Standard library only, no network.

Not tax advice: arithmetic on your trades. A tax professional decides what
applies to you.

    python3 lots.py report                       # open lots, unrealised gain by term
    python3 lots.py gains                        # realised gains, set-off, carry-forward, estimate per FY
    python3 lots.py gains --fy 2026-27
    python3 lots.py sell INFY 4                  # what selling 4 INFY now would realise (FIFO)
    python3 lots.py harvest --min-loss 1000      # losses to book, and LTCG headroom
    python3 lots.py harvest --write              # loss-harvest sells -> trader/orders.json (needs fresh holdings;
                                                 # --include-gains adds long-term gain sells; removes the file if none)

Inputs (see tradebook.py):
  trader/tradebook*.csv   Zerodha Console equity tradebooks (all your history)
  trader/lots.csv         opening lots bought before the tradebook starts
  trader/fmv_2018.csv     31 Jan 2018 prices for shares bought before 2018-02-01
  trader/kite/trades.json today's Kite trades (kite_snapshot.py save trades)
  trader/kite/holdings.json   Kite holdings, to check the lots add up
  trader/kite/quotes.json     Kite quotes, for unrealised gains

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
    try:
        lists.append(tradebook.kite_trades(kite_snapshot.load("trades", a.kite_dir, now=_now(a), max_age=86400)))
    except kite_snapshot.SnapshotError as e:
        notes.append("today's Kite trades are not included (%s)" % e)
    if not lists:
        raise TaxError("no trades: download your Zerodha Console tradebook to trader/tradebook-<year>.csv "
                       "(or pass --tradebook), and put older holdings in trader/lots.csv")
    fmv = tradebook.read_fmv(a.fmv) if a.fmv and os.path.exists(a.fmv) else {}
    book = ledger.build(tradebook.merge(*lists), fmv)
    book["fmv"] = fmv
    return {"book": book, "notes": notes + book["problems"], "cfg": _config(a.config)}


def quote_prices(kite_dir, now=None):
    try:
        snap = kite_snapshot.quotes(kite_snapshot.load("quotes", kite_dir, now=now))
    except kite_snapshot.SnapshotError as e:
        raise TaxError(str(e))
    return {s: q["price"] for s, q in snap.items()}


def holdings_check(lots, kite_dir, now=None):
    """(warnings, {symbol: (trades_qty, kite_qty)}, error): where the lots do not match Kite's holdings
    (quantity + T1). error is set when the holdings snapshot is missing or stale."""
    try:
        hold = kite_snapshot.load("holdings", kite_dir, now=now)
    except kite_snapshot.SnapshotError as e:
        return ["could not check the lots against Kite holdings (%s)" % e], {}, str(e)
    kite = {}
    for r in hold if isinstance(hold, list) else []:
        sym = str(r.get("tradingsymbol", "")).upper()
        kite[sym] = kite.get(sym, 0) + int(float(r.get("quantity") or 0) + float(r.get("t1_quantity") or 0))
    mine = {s: sum(l["qty"] for l in ls) for s, ls in lots.items()}
    out, bad = [], {}
    for s in sorted(set(kite) | set(mine)):
        if kite.get(s, 0) != mine.get(s, 0):
            bad[s] = (mine.get(s, 0), kite.get(s, 0))
            out.append("%s: the trades give %d shares but Kite holds %d; the tradebook or lots.csv is incomplete"
                       % (s, mine.get(s, 0), kite.get(s, 0)))
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
    gains, short = ledger.what_if(lots, a.qty, price, _today(a), inp["book"]["fmv"])
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


def harvest(lots, prices, today, years, min_loss, fmv=None, exemption=125000.0, skip=()):
    """(losses, gains): selling a whole position that books at least min_loss of loss, and long-term gains
    that still fit this FY's unused exemption. A symbol is never in both, and symbols in skip are left out."""
    fy = india_tax.fy_of(today)
    this = [y for y in years if y["fy"] == fy]
    left = this[0]["exemption_left"] if this else exemption
    losses, gains = [], []
    for sym in sorted(lots):
        if sym not in prices or sym in skip:
            continue
        qty = sum(l["qty"] for l in lots[sym])
        res, _ = ledger.what_if(lots[sym], qty, prices[sym], today, fmv)
        net = sum(g["gain"] for g in res)
        if net < 0 and -net >= min_loss:
            by_term = {k: round(sum(g["gain"] for g in res if g["kind"] == k), 2) for k in ("STCG", "LTCG")}
            losses.append({"symbol": sym, "qty": qty, "price": prices[sym], "loss": round(-net, 2),
                           "by_term": by_term})
            left -= max(0.0, by_term["LTCG"])
    left = max(0.0, left)
    taken = set(c["symbol"] for c in losses)
    for sym in sorted(lots):
        if left <= 0:
            break
        if sym not in prices or sym in skip or sym in taken:
            continue
        n, booked = 0, 0.0
        for lot in lots[sym]:
            g = ledger.close(lot, lot["qty"], prices[sym], today, fmv)
            if g["kind"] != "LTCG" or g["gain"] <= 0:
                break
            per = g["gain"] / lot["qty"]
            fit = min(lot["qty"], int((left - booked) // per)) if per > 0 else 0
            if fit > 0:
                n += fit
                booked += fit * per
            if fit < lot["qty"]:
                break
        if n > 0:
            gains.append({"symbol": sym, "qty": n, "price": prices[sym], "gain": round(booked, 2)})
            left -= booked
    return losses, gains


def sell_orders(cands, lots, today, fmv, cfg, kind, min_loss, notes):
    """Kite SELL orders for the candidates, each cut to max_order_value (trader-risk blocks bigger orders).
    The stated effect is worked out from the shares actually sold (oldest first), not pro rata."""
    try:
        max_value = float(cfg.get("max_order_value", 10000) or 0)
    except (TypeError, ValueError):
        raise TaxError("config max_order_value must be a number of rupees")
    out = []
    for c in cands:
        sym, qty = c["symbol"], c["qty"]
        if qty < 1:
            continue
        if max_value and qty * c["price"] > max_value:
            qty = int(max_value // c["price"])
            if qty < 1:
                notes.append("%s: one share costs more than your max order; not proposed" % sym)
                continue
        res, _ = ledger.what_if(lots[sym], qty, c["price"], today, fmv)
        net = round(sum(g["gain"] for g in res), 2)
        if qty < c["qty"]:
            if kind == "loss" and net > -min_loss:
                notes.append("%s: selling only %d of %d (to stay under your max order) would book %s because the "
                             "oldest shares go first; not proposed"
                             % (sym, qty, c["qty"], "a gain of %s" % inr(net) if net > 0
                                else "a loss of only %s" % inr(-net)))
                continue
            notes.append("%s: selling %d of %d now keeps the order under your %s max order; sell the rest later"
                         % (sym, qty, c["qty"], inr(max_value)))
        if kind == "loss":
            why = "book a %s loss (trader-tax harvest)" % inr(-net)
        else:
            why = "book %s of long-term gain inside the yearly exemption" % inr(net)
        value = qty * c["price"]
        est = charges.estimate("CNC", "SELL", value, cfg.get("charges"))
        out.append({"exchange": "NSE", "tradingsymbol": sym, "transaction_type": "SELL",
                    "quantity": str(qty), "product": "CNC", "order_type": "LIMIT", "price": "%.2f" % c["price"],
                    "validity": "DAY", "variety": "regular", "est_value": "%.2f" % value,
                    "est_charges": "%.2f" % est["total"], "why": why})
    return out


def cmd_harvest(a):
    if a.min_loss < 0:
        raise TaxError("--min-loss must be 0 or more")
    inp = load_inputs(a)
    book = inp["book"]
    today = _today(a)
    _, bad, hold_err = holdings_check(book["lots"], a.kite_dir, _now(a))
    if a.write and hold_err:
        if os.path.exists(a.write):
            os.remove(a.write)
        raise TaxError("harvest --write needs a fresh Kite holdings snapshot to check the lots "
                       "(refresh it with kite_snapshot.py save holdings)")
    notes = inp["notes"] + (["could not check the lots against Kite holdings (%s)" % hold_err] if hold_err else [])
    for s_, (mine, theirs) in sorted(bad.items()):
        if s_ in book["lots"]:
            notes.append("%s skipped: the trades give %d shares but Kite holds %d, so the oldest-first tax figures "
                         "would be wrong" % (s_, mine, theirs))
    tax_rules = india_tax.rules(inp["cfg"].get("tax_rules"))
    years = india_tax.summarise(book["realised"], book["speculative"], inp["cfg"].get("tax_rules"))
    losses, gains = harvest(book["lots"], quote_prices(a.kite_dir, _now(a)), today, years, a.min_loss, book["fmv"],
                            tax_rules["ltcg_exemption"], skip=set(bad))
    orders = sell_orders(losses, book["lots"], today, book["fmv"], inp["cfg"], "loss", a.min_loss, notes)
    if a.include_gains:
        orders += sell_orders(gains, book["lots"], today, book["fmv"], inp["cfg"], "gain", a.min_loss, notes)
    removed = False
    if a.write and not orders and os.path.exists(a.write):
        os.remove(a.write)
        removed = True
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
        print("Losses you could book (selling the whole position, oldest shares first):")
        for c in losses:
            print("  SELL %d %s at %s: loss %s (short term %s, long term %s)" % (
                c["qty"], c["symbol"], inr(c["price"]), inr(c["loss"]), inr(c["by_term"]["STCG"]),
                inr(c["by_term"]["LTCG"])))
    else:
        print("No position would book a loss of %s or more." % inr(a.min_loss))
    if gains:
        print("Long-term gains that still fit this year's exemption (tax free up to the limit):")
        for c in gains:
            print("  SELL %d %s at %s: long-term gain %s" % (c["qty"], c["symbol"], inr(c["price"]), inr(c["gain"])))
    if orders:
        print("Proposed LIVE orders:")
        for o in orders:
            print("  SELL %s %s at %s (CNC LIMIT, about %s): %s" % (o["quantity"], o["tradingsymbol"],
                                                                 inr(float(o["price"])), inr(float(o["est_value"])),
                                                                 o["why"]))
    if removed:
        print("Removed the old %s: nothing to propose." % a.write)
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
        return 1


if __name__ == "__main__":
    sys.exit(main())
