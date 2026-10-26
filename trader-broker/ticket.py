#!/usr/bin/env python3
"""Order tickets and the decision log for trader-broker. Standard library only.

This tool never talks to a broker and never places anything. Every order in
this pack is a LIVE order with real money on your Zerodha account: Kite has
no paper account. The tool does three things around the one moment that
matters, your yes:

  show      renders each proposed order as a plain-English ticket plus the
            exact arguments Claude will send to the Kite connector's
            place_order tool. An order is READY only if trader-risk passed
            THIS exact order (matched by fingerprint) in the last 10 minutes
            and nobody has decided on it yet.
  approve   records your explicit yes for ONE order, with your reply word for
            word. It refuses "yes to all", "sure", "ok", a yes that names a
            different stock, quantity or price, and any order that is not READY.
  decline   records a no.
  result    records what happened after the Kite connector's approval card:
            placed (with Kite's order id), denied, or failed.
  log       prints today's decisions.

    python3 ticket.py show                    # every order, READY or not
    python3 ticket.py show --index 1 --json   # one ticket as JSON
    python3 ticket.py approve --index 1 --reply "yes"
    python3 ticket.py result --index 1 --status placed --broker-id 261026000123456
    python3 ticket.py log

Everything is written to trader/state/broker.json (append only). Fills and
holdings come from Kite itself (holdings and trades), not from this log.
"""

import argparse
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import nse_calendar
from rupees import inr

KITE_FIELDS = ("exchange", "tradingsymbol", "transaction_type", "quantity", "product", "order_type",
               "price", "trigger_price", "validity", "variety")
TOOL = "place_order"  # the Kite connector's order tool
PRODUCT_WORDS = {"CNC": "delivery (CNC)", "MIS": "intraday (MIS)"}
RISK_MAX_AGE = 600  # seconds: an older risk check has stale prices behind it
YES_WORDS = ("yes", "y")
BATCH_WORDS = {"all", "every", "everything", "rest", "remaining", "them", "both", "batch", "each"}
# Everything a plain yes may say beyond the one order. Anything else is refused.
FILLER = {"please", "place", "it", "this", "that", "order", "the", "go", "ahead", "confirm", "confirmed",
          "share", "shares", "of", "at", "rs", "for", "now"}
SIDE_WORDS = {"buy", "sell"}
PRODUCT_TERMS = {"delivery": "CNC", "cnc": "CNC", "intraday": "MIS", "mis": "MIS"}
TYPE_TERMS = {"limit": "LIMIT", "market": "MARKET"}
OK_SYMBOLS = {",", ".", "!", "₹"}  # comma, full stop, exclamation mark, rupee sign


class TicketError(Exception):
    pass


# ---------------------------------------------------------------- files

def read_json(path, what, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise TicketError("no %s at %s" % (what, path))
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise TicketError("%s is not valid JSON: %s" % (path, e))


def write_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def rec_day(rec):
    """The trading day a decision belongs to: its "date", else the day of "at"."""
    return str(rec.get("date") or str(rec.get("at", ""))[:10])


# ---------------------------------------------------------------- the order

def fingerprint(order):
    """Same function as trader-risk/check.py: identifies the exact order."""
    core = {k: order[k] for k in KITE_FIELDS if k in order and order[k] is not None}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def tool_input(order):
    """The exact arguments for the Kite connector's place_order tool: Kite's parameter names, as written."""
    return {k: order[k] for k in KITE_FIELDS if k in order and order[k] is not None}


def plain(order):
    """BUY 6 shares of INFY, limit Rs 1,612.50, delivery (CNC), good for today"""
    side = str(order.get("transaction_type", "")).upper()
    q = str(order.get("quantity"))
    what = "%s share%s of %s" % (q, "" if q == "1" else "s", order.get("tradingsymbol", "?"))
    if str(order.get("order_type", "")).upper() == "LIMIT":
        how = "limit %s" % inr(order.get("price"))
    else:
        how = "at market"
    product = PRODUCT_WORDS.get(str(order.get("product", "")).upper(), str(order.get("product")))
    text = "%s %s, %s, %s, good for today" % (side, what, how, product)
    if str(order.get("variety", "regular")).lower() == "amo":
        text += ", after-market order"
    return text


def estimate(order):
    """'estimated Rs 9,675 + Rs 11.49 charges = Rs 9,686.49 out' (a sale: proceeds less charges)."""
    try:
        value, cost = float(order["est_value"]), float(order.get("est_charges") or 0)
    except (KeyError, TypeError, ValueError):
        return ""
    if str(order.get("transaction_type", "")).upper() == "SELL":
        return "estimated %s - %s charges = %s in" % (inr(value), inr(cost), inr(value - cost))
    return "estimated %s + %s charges = %s out" % (inr(value), inr(cost), inr(value + cost))


def amount_numbers(order):
    nums = []
    for k in ("quantity", "price", "est_value"):
        try:
            nums.append(float(order[k]))
        except (KeyError, TypeError, ValueError):
            pass
    return nums


def parse_yes(reply, order, batch_symbols=()):
    """Is this reply an explicit yes for THIS one order? Returns (ok, why).

    An allowlist, not a blocklist. A reply counts only if it starts with "yes"
    or "y" and every other piece of it is one of:
      - a number that equals the order's quantity, price or est_value (every
        number must match, so "yes 6 shares at 1700" is refused);
      - this order's own symbol (any case), a filler word (FILLER), the side
        (buy or sell, matching the order), the product (delivery or intraday,
        matching the order) or the type (limit or market, matching the order);
      - a comma, full stop, exclamation mark or rupee sign.
    A batch word (all, both, rest...) or another stock in the batch is refused
    with its own message. Any other word (sell on a buy, WIPRO, never, nope,
    tomorrow, except, too, lakh...) is refused, so a yes that contradicts the
    order or adds a condition cannot pass.
    """
    raw = (reply or "").strip()
    if not raw:
        return False, "the reply is empty"
    if "?" in raw:
        return False, "the reply is a question, not a yes"
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9&\-]*|\d[\d,]*(?:\.\d+)?|\S", raw)
    if not tokens or tokens[0].lower() not in YES_WORDS:
        return False, "only a reply that starts with \"yes\" counts (not ok, sure, go, do it)"
    lowered = [t.lower() for t in tokens]
    if BATCH_WORDS & set(lowered):
        return False, "a yes covers one order at a time, not a batch"
    sym = str(order.get("tradingsymbol", "")).upper()
    others = {str(s).upper() for s in batch_symbols} - {sym}
    side = str(order.get("transaction_type", "")).lower()
    product = str(order.get("product", "")).upper()
    order_type = str(order.get("order_type", "")).upper()
    wants = amount_numbers(order)
    for tok, low in zip(tokens[1:], lowered[1:]):
        if tok[0].isdigit():
            n = float(tok.replace(",", ""))
            if not any(abs(n - w) < 0.005 for w in wants):
                return False, "the reply says %s, but this order is %s" % (tok, plain(order))
        elif tok[0].isalpha():
            up = tok.upper()
            if up == sym:
                continue
            if up in others:
                return False, "the reply names %s, but this order is for %s" % (up, sym)
            if low in FILLER:
                continue
            if low in SIDE_WORDS and low == side:
                continue
            if low in PRODUCT_TERMS and PRODUCT_TERMS[low] == product:
                continue
            if low in TYPE_TERMS and TYPE_TERMS[low] == order_type:
                continue
            return False, "the reply has words beyond a plain yes for this order (%r); ask again" % tok
        elif tok not in OK_SYMBOLS:
            return False, "the reply has words beyond a plain yes for this order (%r); ask again" % tok
    return True, "explicit yes for %s" % plain(order)


# ---------------------------------------------------------------- state

def load_state(path):
    return read_json(path, "broker state", required=False) or {"orders": []}


def latest(state, fp, today):
    """The latest decision recorded today for this fingerprint, or None."""
    found = None
    for rec in state.get("orders", []):
        if rec.get("fingerprint") == fp and rec_day(rec) == today:
            found = rec
    return found


def risk_verdict(risk, fp, now):
    if not risk:
        return None, "trader-risk has not checked these orders (run check.py)"
    try:
        checked = nse_calendar.parse_now(risk.get("checked_at"))
    except nse_calendar.CalendarError:
        checked = None
    if not risk.get("checked_at") or checked is None:
        return None, "the risk check has no time on it; run check.py again"
    age = (now - checked).total_seconds()
    if age > RISK_MAX_AGE or age < -60:
        return None, "the risk check is from %s, %d minutes ago; prices move, run check.py again" % (
            risk["checked_at"], age // 60)
    for r in risk.get("results", []):
        if r.get("fingerprint") == fp:
            return r, None
    return None, "this exact order was not in the last risk check (it changed or is new); run check.py again"


def status_of(order, risk, state, now):
    """(ready, label, risk_result)"""
    fp = fingerprint(order)
    rv, why = risk_verdict(risk, fp, now)
    if rv is None:
        return False, "NOT READY: " + why, None
    if rv.get("verdict") != "PASS":
        return False, "BLOCKED by trader-risk: " + "; ".join(rv.get("reasons", [])), rv
    rec = latest(state, fp, now.date().isoformat())
    if rec:
        st = rec.get("status")
        if st == "approved":
            return False, "APPROVED by you at %s, waiting for the %s call" % (rec.get("at"), TOOL), rv
        return False, "DONE: %s at %s" % (st, rec.get("at")), rv
    return True, "READY: trader-risk PASS, waiting for your yes", rv


# ---------------------------------------------------------------- rendering

def render(order, idx, total, risk, state, now):
    ready, label, rv = status_of(order, risk, state, now)
    lines = ["ORDER %d of %d: LIVE ORDER, real money, Zerodha Kite" % (idx, total), "  " + plain(order)]
    est = estimate(order)
    if est:
        lines.append("  " + est)
    if order.get("why"):
        lines.append("  why: " + order["why"])
    lines.append("  " + label)
    for w in (rv or {}).get("warnings", []):
        lines.append("  note: " + w)
    lines.append("  Claude will call the Kite connector's %s tool with exactly:" % TOOL)
    for line in json.dumps(tool_input(order), indent=2).splitlines():
        lines.append("    " + line)
    if ready:
        lines.append("  Reply \"yes\" to place this one order, or \"no\" to skip it.")
        lines.append("  The Kite connector's own approval card then asks again: approve places it, deny stops it.")
    return "\n".join(lines), ready


def ticket_json(order, idx, risk, state, now):
    ready, label, rv = status_of(order, risk, state, now)
    return {"index": idx, "ready": ready, "status": label, "plain": plain(order), "estimate": estimate(order),
            "fingerprint": fingerprint(order), "live": True, "broker": "kite", "tool": TOOL,
            "tool_input": tool_input(order), "why": order.get("why", "")}


# ---------------------------------------------------------------- commands

def _load(a):
    doc = read_json(a.orders, "orders file (run trader-budget first)")
    orders = doc.get("orders", doc) if isinstance(doc, dict) else doc
    if not isinstance(orders, list) or not orders:
        raise TicketError("no orders in %s" % a.orders)
    risk = read_json(a.risk, "risk check", required=False)
    state = load_state(a.state)
    try:
        now = nse_calendar.parse_now(a.now)
    except nse_calendar.CalendarError as e:
        raise TicketError(str(e))
    return orders, risk, state, now


def _pick(orders, index):
    if index is None:
        raise TicketError("say which order: --index N")
    if not 1 <= index <= len(orders):
        raise TicketError("there is no order %d (there are %d)" % (index, len(orders)))
    return orders[index - 1]


def _record(order, index, now, status, **extra):
    rec = {"at": now.replace(microsecond=0).isoformat(), "date": now.date().isoformat(), "index": index,
           "fingerprint": fingerprint(order), "symbol": str(order.get("tradingsymbol", "")).upper(),
           "side": str(order.get("transaction_type", "")).upper(), "plain": plain(order), "status": status}
    rec.update(extra)
    return rec


def cmd_show(a):
    orders, risk, state, now = _load(a)
    picks = [(a.index, _pick(orders, a.index))] if a.index else list(enumerate(orders, 1))
    if a.json:
        out = [ticket_json(o, i, risk, state, now) for i, o in picks]
        print(json.dumps(out[0] if a.index else out, indent=2))
        return 0 if any(t["ready"] for t in out) else 1
    blocks, any_ready = [], False
    for i, o in picks:
        text, ready = render(o, i, len(orders), risk, state, now)
        blocks.append(text)
        any_ready = any_ready or ready
    print("\n\n".join(blocks))
    print("\nOne order at a time: a yes covers one ticket, never the batch. Education and tooling, "
          "not financial advice.")
    return 0 if any_ready else 1


def cmd_approve(a):
    orders, risk, state, now = _load(a)
    order = _pick(orders, a.index)
    ready, label, rv = status_of(order, risk, state, now)
    if not ready:
        raise TicketError("order %d is not ready: %s" % (a.index, label))
    ok, why = parse_yes(a.reply, order, [o.get("tradingsymbol", "") for o in orders])
    if not ok:
        print("Not recorded: %s. Ask the user again with the ticket for order %d." % (why, a.index))
        return 1
    state.setdefault("orders", []).append(_record(order, a.index, now, "approved", reply=a.reply, live=True,
                                                  broker="kite"))
    write_json(a.state, state)
    print("Recorded your yes for order %d: %s." % (a.index, plain(order)))
    print("Now call the Kite connector's %s tool with exactly:" % TOOL)
    print(json.dumps(tool_input(order), indent=2))
    print("The connector's approval card asks again. Then: ticket.py result --index %d --status "
          "placed|denied|failed --broker-id <Kite order id>" % a.index)
    return 0


def cmd_decline(a):
    orders, risk, state, now = _load(a)
    order = _pick(orders, a.index)
    state.setdefault("orders", []).append(_record(order, a.index, now, "declined", reply=a.reply or "no"))
    write_json(a.state, state)
    print("Recorded: you said no to order %d (%s). Nothing was sent." % (a.index, plain(order)))
    return 0


def cmd_result(a):
    orders, risk, state, now = _load(a)
    order = _pick(orders, a.index)
    rec = latest(state, fingerprint(order), now.date().isoformat())
    if not rec or rec.get("status") != "approved":
        raise TicketError("order %d has no yes recorded today; a result can only follow an approval" % a.index)
    extra = {}
    if a.broker_id:
        extra["broker_order_id"] = a.broker_id
    if a.note:
        extra["note"] = a.note
    state["orders"].append(_record(order, a.index, now, a.status, **extra))
    write_json(a.state, state)
    print("Recorded order %d as %s." % (a.index, a.status))
    if a.status == "placed":
        print("Kite's holdings and trades are the record of the fill: refresh those snapshots before the next check.")
    return 0


def cmd_log(a):
    state = load_state(a.state)
    try:
        today = nse_calendar.parse_now(a.now).date().isoformat()
    except nse_calendar.CalendarError as e:
        raise TicketError(str(e))
    rows = [r for r in state.get("orders", []) if a.all or rec_day(r) == today]
    if not rows:
        print("No decisions recorded%s." % ("" if a.all else " today"))
        return 1
    for r in rows:
        extra = (" id " + r["broker_order_id"]) if r.get("broker_order_id") else ""
        reply = (' reply "%s"' % r["reply"]) if r.get("reply") and r["status"] in ("approved", "declined") else ""
        print("%s  #%s %-9s %s%s%s" % (r.get("at"), r.get("index"), r.get("status"), r.get("plain"), reply, extra))
    placed = sum(1 for r in rows if r.get("status") == "placed")
    print("%d placed%s." % (placed, "" if a.all else " today"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="LIVE order tickets and your yes (trader-broker). Never places orders.")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--orders", default="trader/orders.json")
        p.add_argument("--risk", default="trader/state/risk.json")
        p.add_argument("--state", default="trader/state/broker.json")
        p.add_argument("--now", help="pretend it is this time (ISO; no offset = IST)")

    p = sub.add_parser("show", help="render the tickets")
    common(p)
    p.add_argument("--index", type=int)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("approve", help="record the user's explicit yes for one order")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--reply", required=True, help="the user's reply, word for word")
    p = sub.add_parser("decline", help="record a no")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--reply")
    p = sub.add_parser("result", help="record what happened after the Kite approval card")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--status", required=True, choices=["placed", "denied", "failed"])
    p.add_argument("--broker-id", help="Kite's order id")
    p.add_argument("--note")
    p = sub.add_parser("log", help="today's decisions")
    p.add_argument("--state", default="trader/state/broker.json")
    p.add_argument("--now")
    p.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"show": cmd_show, "approve": cmd_approve, "decline": cmd_decline, "result": cmd_result,
                "log": cmd_log}[a.cmd](a)
    except TicketError as e:
        print("ticket.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
