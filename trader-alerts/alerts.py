#!/usr/bin/env python3
"""Price alerts and the NSE clock for trader-alerts. Standard library only.

    python3 alerts.py clock                            # is NSE open? next open, MIS square-off
    python3 alerts.py holidays refresh                 # NSE holiday list -> trader/cache/nse/holidays.json
    python3 alerts.py holidays refresh --file h.json   # the same, from a file saved in a browser
    python3 alerts.py quote INFY RELIANCE --write      # trader/kite/quotes.json -> trader/prices.json
    python3 alerts.py add --symbol INFY --above 1700   # rules live in trader/alerts.json
    python3 alerts.py add --symbol RELIANCE --stop 1350
    python3 alerts.py add --symbol TCS --pct 3
    python3 alerts.py add --opening-bell
    python3 alerts.py add --mis-warning                # open MIS positions near the 15:20 square-off
    python3 alerts.py need                             # the Kite quotes (and positions) a check needs
    python3 alerts.py check                            # rings what hit, once
    python3 alerts.py list
    python3 alerts.py reset infy-above-1700

Rule types:
  above         the price is at or above "price" (a target)
  below / stop  the price is at or below "price" (a stop or a dip to buy)
  pct_move      the price moved "pct" percent or more from the previous close
                (or from "ref" if you give one); "direction": "up" or "down"
  opening_bell  NSE opened today (rings once per trading day)
  mis_warning   an MIS (intraday) position is still open at or after "at"
                (default 15:05 IST); Zerodha squares MIS off from about 15:20.
                Reads trader/kite/positions.json. Rings once per day.

An above / below alert rings ONCE and then stays quiet until you reset it,
unless the rule has "rearm": true (it re-arms when the price crosses back).
A pct_move alert rings at most once per day.

Prices come only from the Kite connector. Claude calls it for the symbols the
rules watch and saves the answer with kite_snapshot.py save quotes; this
script reads trader/kite/quotes.json and refuses it when it is more than 120
seconds old. Nothing here fetches prices from the web, and nothing here places
an order.

check exits 0 when something rang, 1 when nothing rang and every rule was
checked, and 2 when anything could not be checked (missing or stale Kite
data, a symbol missing from the snapshot, a bad rules file). A scheduled run
must treat 2 as "look at this", never as "all quiet".
"""

import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import kite_snapshot
import nse
import nse_calendar
import nse_symbols
from rupees import inr


class AlertError(Exception):
    pass


def _n(x):
    x = float(x)
    return str(int(x)) if x == int(x) else "%.2f" % x


# ---------------------------------------------------------------- files

def _write(path, doc):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")


def _read(path, default):
    if not path or not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as e:
        raise AlertError("%s is not valid JSON: %s" % (path, e))


def calendar(a):
    holidays, years = nse_calendar.load_holidays(a.holidays)
    return nse_calendar.Calendar(holidays, years)


# ---------------------------------------------------------------- quotes

STALE_QUOTE = 300  # seconds: in market hours, Kite's own quote time may lag the snapshot by this much


def _quote_age(q, now):
    """Seconds between Kite's quote timestamp (IST, no offset) and now, or None if unknown."""
    try:
        t = datetime.datetime.strptime(q.get("quote_time") or "", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return (now - t.replace(tzinfo=nse_calendar.IST)).total_seconds()


def get_quotes(symbols, kite_dir, now, session_open=False):
    """({SYM: quote}, [errors]) from the Kite quotes snapshot. A symbol missing from the
    snapshot, without a usable price, or (in market hours) with an old Kite quote time is an
    error naming the Kite instrument, never a silent skip."""
    try:
        raw = kite_snapshot.load("quotes", kite_dir, now=now)
    except kite_snapshot.SnapshotError as e:
        return {}, [str(e)]
    snap = kite_snapshot.quotes(raw)
    quotes, errors = {}, []
    for s in symbols:
        q = snap.get(s)
        if q is None:
            if isinstance(raw, dict) and ("NSE:" + s) in raw:
                errors.append("Kite gave no usable price for NSE:%s" % s)
            else:
                errors.append("%s is not in the Kite quotes snapshot: add NSE:%s to the quotes call" % (s, s))
            continue
        age = _quote_age(q, now)
        if session_open and age is not None and age > STALE_QUOTE:
            errors.append("Kite's quote for NSE:%s is from %s, more than %d s old in market hours: "
                          "refresh the quotes" % (s, q["quote_time"], STALE_QUOTE))
            continue
        quotes[s] = q
    return quotes, errors


def write_prices(path, quotes, now):
    old = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                old = json.load(fh)
        except (ValueError, OSError):
            old = {}
    prices = dict(old.get("prices", {}))
    detail = dict(old.get("detail", {}))
    for s, q in quotes.items():
        prices[s] = q["price"]
        detail[s] = {"as_of": now.isoformat(), "prev_close": q.get("prev_close"), "time": q.get("time"),
                     "source": "kite",
                     "upper_circuit": q.get("upper_circuit"), "lower_circuit": q.get("lower_circuit")}
    doc = {"as_of": now.isoformat(), "source": "kite", "currency": "INR",
           "note": "Quotes from the Kite connector. as_of is when this file was last written; each symbol's "
                   "own detail.as_of is when its price was saved. The exchange price is the one that fills.",
           "prices": prices, "detail": detail}
    _write(path, doc)
    return doc


# ---------------------------------------------------------------- rules

PRICE_TYPES = {"above", "below", "stop", "target", "pct_move", "opening_bell", "mis_warning"}
CLOCK_TYPES = {"opening_bell", "mis_warning"}
LABEL = {"above": "target", "target": "target", "below": "level", "stop": "stop"}
MIS_WARNING_AT = "15:05"


def _hhmm(text, rid):
    try:
        return datetime.datetime.strptime(str(text), "%H:%M").time()
    except ValueError:
        raise AlertError("rule %s: \"at\" wants a time like 15:05, not %r" % (rid, text))


def mis_positions(positions):
    """[(symbol, quantity)] for the open MIS positions in a Kite positions answer."""
    rows = (positions or {}).get("net") or []
    out = []
    for p in rows:
        qty = int(p.get("quantity") or 0)
        if p.get("product") == "MIS" and qty:
            out.append((str(p.get("tradingsymbol", "")).upper(), qty))
    return out


def mis_due(rules, status, now):
    """The mis_warning rules whose time has come in today's session."""
    return [r for r in rules if r.get("type") == "mis_warning" and status["phase"] == "open"
            and now.time() >= _hhmm(r.get("at", MIS_WARNING_AT), r.get("id"))]


def rule_symbol(rule):
    """The rule's symbol, normalised the same way as add does ("nse:infy" -> "INFY")."""
    try:
        return nse_symbols.normalize(rule.get("symbol"))
    except nse_symbols.SymbolError as e:
        raise AlertError("rule %s: %s" % (rule.get("id"), e))


def validate(rule):
    t = rule.get("type")
    if t not in PRICE_TYPES:
        raise AlertError("rule %s: unknown type %r" % (rule.get("id"), t))
    if t not in CLOCK_TYPES and not rule.get("symbol"):
        raise AlertError("rule %s needs a symbol" % rule.get("id"))
    if t in ("above", "below", "stop", "target") and not isinstance(rule.get("price"), (int, float)):
        raise AlertError("rule %s needs a numeric price" % rule.get("id"))
    if t == "pct_move" and not isinstance(rule.get("pct"), (int, float)):
        raise AlertError("rule %s needs a numeric pct" % rule.get("id"))
    if t == "mis_warning":
        _hhmm(rule.get("at", MIS_WARNING_AT), rule.get("id"))


def evaluate(rules, quotes, status, state, now, positions=None):
    """Pure function. Returns (rings, new_state). Each ring: {id, symbol, message}.
    positions is the Kite positions answer, needed only by mis_warning rules."""
    state = json.loads(json.dumps(state or {}))
    rung = state.setdefault("rung", {})
    today = status["date"]
    stamp = now.isoformat()
    rings = []
    for r in rules:
        validate(r)
        rid = r.get("id") or "%s-%s" % (r.get("symbol", "market"), r["type"])
        typ = {"stop": "below", "target": "above"}.get(r["type"], r["type"])
        if typ == "opening_bell":
            if status["open"] and rung.get(rid, "")[:10] != today:
                msg = "Opening bell: NSE is open (%s IST)." % status["now_ist"]
                if not status.get("calendar_known", True):
                    msg += (" It may be an NSE holiday: the holiday list for %s is not loaded."
                            % status["date"][:4])
                rings.append({"id": rid, "symbol": "", "message": msg})
                rung[rid] = stamp
            continue
        if typ == "mis_warning":
            if r in mis_due([r], status, now) and rung.get(rid, "")[:10] != today:
                held = mis_positions(positions)
                if held:
                    rings.append({"id": rid, "symbol": "", "message": (
                        "MIS positions still open at %s IST: %s. Zerodha squares MIS off from about %s IST; "
                        "close them yourself first if you want to choose the price."
                        % (status["now_ist"][11:], ", ".join("%s %+d" % h for h in held),
                           nse_calendar.SQUARE_OFF.strftime("%H:%M")))})
                    rung[rid] = stamp
            continue
        sym = rule_symbol(r)
        q = quotes.get(sym)
        if not q:
            continue
        p = q["price"]
        if typ in ("above", "below"):
            hit = p >= r["price"] if typ == "above" else p <= r["price"]
            if hit and rid not in rung:
                rings.append({"id": rid, "symbol": sym, "message": "%s %s %s: %s your %s %s%s." % (
                    sym, "is" if status["open"] else "last traded at", inr(p),
                    "at or above" if typ == "above" else "at or below", LABEL[r["type"]], inr(r["price"]),
                    (" (" + r["note"] + ")") if r.get("note") else "")})
                rung[rid] = stamp
            elif not hit and rid in rung and r.get("rearm"):
                del rung[rid]
        elif typ == "pct_move":
            ref = r.get("ref") or q.get("prev_close") or q.get("open")
            if not ref:
                continue
            move = 100.0 * (p / float(ref) - 1)
            want = r.get("direction")
            hit = abs(move) >= r["pct"] and (not want or (want == "up") == (move > 0))
            if hit and rung.get(rid, "")[:10] != today:
                rings.append({"id": rid, "symbol": sym, "message": "%s moved %+.2f%% to %s (from %s)."
                              % (sym, move, inr(p), inr(ref))})
                rung[rid] = stamp
    state["last_check"] = stamp
    return rings, state


# ---------------------------------------------------------------- commands

def _dedupe(items):
    out = []
    for s in items:
        if s and s not in out:
            out.append(s)
    return out


def cmd_clock(a):
    st = calendar(a).status(nse_calendar.parse_now(a.now))
    if a.json:
        print(json.dumps(st, indent=2))
    else:
        print("%s IST (%s): NSE %s, %s." % (st["now_ist"], st["weekday"], "OPEN" if st["open"] else "closed",
                                            st["reason"]))
        if st.get("opens"):
            print("Today's session: %s to %s IST. Zerodha squares MIS positions off from about %s."
                  % (st["opens"], st["closes"], st["mis_square_off"]))
        if st.get("next_open"):
            print("Next open: %s IST." % st["next_open"])
        if not st["calendar_known"]:
            print("NSE's holiday list for %s is not loaded: run alerts.py holidays refresh, "
                  "or check nseindia.com." % st["date"][:4])
    return 0 if st["open"] else 1


def cmd_holidays(a):
    doc = nse.read_json_file(a.file) if a.file else nse.Client().get_json(nse_calendar.URL)
    holidays = nse_calendar.parse_holiday_master(doc)
    years = nse_calendar.save_holidays(holidays, a.holidays)
    print("Saved %d NSE holidays for %s to %s." % (len(holidays), ", ".join(map(str, years)), a.holidays))
    return 0


def cmd_quote(a):
    now = nse_calendar.parse_now(a.now)
    syms = _dedupe([nse_symbols.normalize(s) for s in a.symbols])
    if not syms:
        syms = sorted(kite_snapshot.quotes(kite_snapshot.load("quotes", a.kite_dir, now=now)))
    quotes, errors = get_quotes(syms, a.kite_dir, now, calendar(a).status(now)["open"])
    if a.write and quotes:
        write_prices(a.write, quotes, now)
    if a.json:
        print(json.dumps({"quotes": quotes, "errors": errors}, indent=2))
    else:
        for s in syms:
            q = quotes.get(s)
            if q:
                chg = ""
                if q.get("prev_close"):
                    chg = " (%+.2f%% vs prev close %s)" % (100.0 * (q["price"] / q["prev_close"] - 1),
                                                           inr(q["prev_close"]))
                print("%-10s %s%s  %s" % (s, inr(q["price"]), chg, q.get("time", "")))
        for e in errors:
            print("error: " + e)
        if a.write and quotes:
            print("Wrote %d price(s) to %s." % (len(quotes), a.write))
    return 0 if quotes else 1


def cmd_check(a):
    doc = _read(a.rules, None)
    if not doc or not doc.get("rules"):
        raise AlertError("no rules in %s: add one with alerts.py add --symbol INFY --above 1700" % a.rules)
    rules = doc["rules"]
    now = nse_calendar.parse_now(a.now)
    status = calendar(a).status(now)
    for r in rules:
        validate(r)
    syms = _dedupe([rule_symbol(r) for r in rules if r.get("type") not in CLOCK_TYPES])
    quotes, errors = get_quotes(syms, a.kite_dir, now, status["open"]) if syms else ({}, [])
    positions = None
    due = mis_due(rules, status, now)
    if due:
        try:
            positions = kite_snapshot.load("positions", a.kite_dir, now=now)
        except kite_snapshot.SnapshotError as e:
            errors.append(str(e))
    state = _read(a.state, {})
    rings, state = evaluate(rules, quotes, status, state, now, positions)
    if not a.no_write:
        _write(a.state, state)
        if quotes:
            write_prices(a.prices_out, quotes, now)
    if a.json:
        print(json.dumps({"market": status, "rings": rings, "errors": errors,
                          "quotes": {s: q["price"] for s, q in quotes.items()}}, indent=2))
    else:
        print("NSE %s (%s IST, %s)." % ("OPEN" if status["open"] else "closed", status["now_ist"],
                                        status["reason"]))
        if not status["calendar_known"]:
            print("NSE's holiday list for %s is not loaded, so today may be a holiday: run alerts.py "
                  "holidays refresh." % status["date"][:4])
        for r in rings:
            print("ALERT " + r["message"])
        if not rings:
            print("Nothing hit. %d rule(s) watched." % len(rules))
        for e in errors:
            print("error: " + e)
        if rings:
            print("An alert is information, not an order. To act on one, size it (trader-budget or "
                  "trader-rebalance), check it (trader-risk) and say yes to it (trader-broker).")
    if rings:
        return 0
    return 2 if errors else 1


def cmd_need(a):
    rules = _read(a.rules, {"rules": []}).get("rules", [])
    keys = _dedupe(["NSE:" + rule_symbol(r) for r in rules if r.get("type") not in CLOCK_TYPES])
    pos = any(r.get("type") == "mis_warning" for r in rules)
    if a.json:
        print(json.dumps({"quotes": keys, "positions": pos}))
    else:
        print("quotes: " + (" ".join(keys) if keys else "(none)"))
        print("positions: " + ("yes, for the MIS warning" if pos else "no"))
    return 0 if (keys or pos) else 1


def cmd_add(a):
    doc = _read(a.rules, {"rules": []})
    doc.setdefault("rules", [])
    if a.opening_bell:
        rule = {"id": a.id or "opening-bell", "type": "opening_bell"}
    elif a.mis_warning:
        rule = {"id": a.id or "mis-warning", "type": "mis_warning", "at": a.at or MIS_WARNING_AT}
    else:
        if not a.symbol:
            raise AlertError("--symbol is required (or --opening-bell)")
        sym = nse_symbols.normalize(a.symbol)
        if a.above is not None:
            rule = {"type": "above", "price": a.above}
        elif a.below is not None:
            rule = {"type": "below", "price": a.below}
        elif a.stop is not None:
            rule = {"type": "stop", "price": a.stop}
        elif a.pct is not None:
            rule = {"type": "pct_move", "pct": a.pct}
            if a.direction:
                rule["direction"] = a.direction
        else:
            raise AlertError("give one of --above, --below, --stop or --pct")
        val = rule.get("price", rule.get("pct"))
        rule = dict({"id": a.id or ("%s-%s-%s" % (sym.lower(), rule["type"], _n(val)))}, symbol=sym, **rule)
        if a.rearm:
            rule["rearm"] = True
        if a.note:
            rule["note"] = a.note
    validate(rule)
    if any(r.get("id") == rule["id"] for r in doc["rules"]):
        raise AlertError("a rule with id %s already exists" % rule["id"])
    doc["rules"].append(rule)
    _write(a.rules, doc)
    print("Added %s: %s" % (rule["id"], json.dumps(rule)))
    return 0


def cmd_list(a):
    doc = _read(a.rules, {"rules": []})
    state = _read(a.state, {})
    if not doc.get("rules"):
        print("No rules yet.")
        return 1
    for r in doc["rules"]:
        rid = r.get("id")
        rung = state.get("rung", {}).get(rid)
        print("%-24s %s%s" % (rid, json.dumps({k: v for k, v in r.items() if k != "id"}),
                              ("  (rang %s)" % rung) if rung else ""))
    return 0


def cmd_reset(a):
    state = _read(a.state, {})
    if a.id not in state.get("rung", {}):
        print("%s has not rung (nothing to reset)." % a.id)
        return 1
    del state["rung"][a.id]
    _write(a.state, state)
    print("Re-armed %s." % a.id)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Price alerts and the NSE clock (trader-alerts).")
    sub = ap.add_subparsers(dest="cmd")

    def clock_args(p):
        p.add_argument("--now", help="pretend it is this time (ISO; no offset = IST)")
        p.add_argument("--holidays", default=nse_calendar.CACHE, help="the cached NSE holiday list")
        p.add_argument("--json", action="store_true")

    def kite_args(p):
        p.add_argument("--kite-dir", default=kite_snapshot.DIR, help="where the Kite snapshots are")

    p = sub.add_parser("clock", help="is NSE open?")
    clock_args(p)
    p = sub.add_parser("holidays", help="refresh NSE's holiday list")
    p.add_argument("action", choices=["refresh"])
    p.add_argument("--file", help="the holiday-master JSON saved from a browser")
    p.add_argument("--holidays", default=nse_calendar.CACHE)
    p = sub.add_parser("quote", help="show quotes from the Kite snapshot")
    clock_args(p)
    kite_args(p)
    p.add_argument("symbols", nargs="*")
    p.add_argument("--write", nargs="?", const="trader/prices.json", metavar="PATH",
                   help="save to prices.json (default trader/prices.json)")
    p = sub.add_parser("check", help="check every rule, ring what hit")
    clock_args(p)
    kite_args(p)
    p.add_argument("--rules", default="trader/alerts.json")
    p.add_argument("--state", default="trader/state/alerts.json")
    p.add_argument("--prices-out", default="trader/prices.json")
    p.add_argument("--no-write", action="store_true")
    p = sub.add_parser("add", help="add a rule")
    p.add_argument("--rules", default="trader/alerts.json")
    p.add_argument("--symbol")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--above", type=float)
    g.add_argument("--below", type=float)
    g.add_argument("--stop", type=float)
    g.add_argument("--pct", type=float)
    g.add_argument("--opening-bell", action="store_true")
    g.add_argument("--mis-warning", action="store_true")
    p.add_argument("--direction", choices=["up", "down"])
    p.add_argument("--rearm", action="store_true")
    p.add_argument("--note")
    p.add_argument("--id")
    p.add_argument("--at", help="HH:MM IST for --mis-warning (default 15:05)")
    p = sub.add_parser("need", help="which Kite quotes and snapshots a check needs")
    p.add_argument("--rules", default="trader/alerts.json")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("list", help="list the rules")
    p.add_argument("--rules", default="trader/alerts.json")
    p.add_argument("--state", default="trader/state/alerts.json")
    p = sub.add_parser("reset", help="re-arm a rule that rang")
    p.add_argument("id")
    p.add_argument("--state", default="trader/state/alerts.json")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"clock": cmd_clock, "holidays": cmd_holidays, "quote": cmd_quote, "check": cmd_check,
                "need": cmd_need, "add": cmd_add, "list": cmd_list, "reset": cmd_reset}[a.cmd](a)
    except nse.NseBlocked as e:
        print("alerts.py: %s" % e, file=sys.stderr)
        return 2
    except (AlertError, nse.NseError, nse_calendar.CalendarError, kite_snapshot.SnapshotError,
            nse_symbols.SymbolError) as e:
        print("alerts.py: %s" % e, file=sys.stderr)
        return 2 if a.cmd == "check" else 1


if __name__ == "__main__":
    sys.exit(main())
