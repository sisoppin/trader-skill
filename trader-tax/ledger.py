#!/usr/bin/env python3
"""FIFO lots and realised gains for trader-tax (Indian listed equity). Standard library only.

Not tax advice: arithmetic on your trades.

  intraday     on any day, the shares of a stock you both bought and sold
               that day are an intraday round trip: speculative business
               income, matched first-in first-out within the day
  lots         the rest of a day's buys open lots (date, quantity, price)
  sales        the rest of a day's sells close the OLDEST lots first (FIFO,
               as demat accounts require)
  term         a lot sold MORE than 12 months after it was bought is long
               term (LTCG); otherwise short term (STCG). Bought 2025-01-10:
               sold 2026-01-10 is short term, 2026-01-11 long term.
  2018 rule    for shares bought before 2018-02-01, the cost of a long-term
               sale is the higher of the actual cost and the lower of the
               31 Jan 2018 price and the sale price (grandfathering)
"""

import datetime

GRANDFATHER_BEFORE = datetime.date(2018, 2, 1)
EPS = 1e-9


def anniversary(d):
    """The same date a year later (29 Feb becomes 28 Feb)."""
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def term(acquired, sold):
    return "LTCG" if sold > anniversary(acquired) else "STCG"


def _gain(kind, symbol, sold, acquired, qty, buy, sell, grandfathered=False):
    cost, proceeds = qty * buy, qty * sell
    return {"symbol": symbol, "kind": kind, "sold": sold, "acquired": acquired, "qty": qty,
            "buy_price": round(buy, 4), "sell_price": round(sell, 4), "cost": round(cost, 2),
            "proceeds": round(proceeds, 2), "gain": round(proceeds - cost, 2), "grandfathered": grandfathered}


def close(lot, qty, price, sold, fmv=None):
    """The gain from selling qty shares of one lot at price on date sold, with the 2018 rule."""
    kind = term(lot["date"], sold)
    buy, gf = lot["price"], False
    if lot["date"] < GRANDFATHER_BEFORE and kind == "LTCG" and lot["symbol"] in (fmv or {}):
        buy = max(lot["price"], min(fmv[lot["symbol"]], price))
        gf = buy != lot["price"]
    return _gain(kind, lot["symbol"], sold, lot["date"], qty, buy, price, gf)


def build(trades, fmv=None):
    """Trades (from tradebook.merge) -> {"lots": {SYM: [lot]}, "realised": [gain], "speculative": [gain],
    "problems": [text]}. A lot is {"symbol", "date", "qty", "price", "id"}."""
    fmv = fmv or {}
    lots, realised, speculative, problems = {}, [], [], []
    days = {}
    order = []
    for t in trades:
        key = (t["date"], t["symbol"])
        if key not in days:
            days[key] = {"BUY": [], "SELL": []}
            order.append(key)
        days[key][t["side"]].append([t["qty"], t["price"], t["id"]])
    order.sort(key=lambda k: k[0])
    warned_fmv = set()
    for d, sym in order:
        buys, sells = days[(d, sym)]["BUY"], days[(d, sym)]["SELL"]
        intraday = min(sum(b[0] for b in buys), sum(s[0] for s in sells))
        if intraday:
            left, cost, proceeds = intraday, 0.0, 0.0
            bi = si = 0
            while left:
                take = min(left, buys[bi][0], sells[si][0])
                cost += take * buys[bi][1]
                proceeds += take * sells[si][1]
                buys[bi][0] -= take
                sells[si][0] -= take
                left -= take
                if not buys[bi][0]:
                    bi += 1
                if not sells[si][0]:
                    si += 1
            speculative.append(_gain("SPECULATIVE", sym, d, d, intraday, cost / intraday, proceeds / intraday))
        for qty, price, tid in buys:
            if qty:
                lots.setdefault(sym, []).append({"symbol": sym, "date": d, "qty": qty, "price": price, "id": tid})
        for qty, price, tid in sells:
            open_lots = lots.get(sym, [])
            while qty and open_lots:
                lot = open_lots[0]
                take = min(qty, lot["qty"])
                g = close(lot, take, price, d, fmv)
                if g["kind"] == "LTCG" and lot["date"] < GRANDFATHER_BEFORE and sym not in fmv and sym not in warned_fmv:
                    warned_fmv.add(sym)
                    problems.append("no 31 Jan 2018 price for %s in fmv_2018.csv: its pre-2018 lots use the "
                                    "actual cost, which may overstate the gain" % sym)
                realised.append(g)
                lot["qty"] -= take
                qty -= take
                if not lot["qty"]:
                    open_lots.pop(0)
            if qty:
                problems.append("sold %d more %s on %s than the trades show you held: add the earlier tradebook or "
                                "the opening lots (lots.csv); that part is left out" % (qty, sym, d.isoformat()))
    lots = {s: ls for s, ls in lots.items() if ls}
    return {"lots": lots, "realised": realised, "speculative": speculative, "problems": problems}


def what_if(lots, qty, price, sold, fmv=None):
    """The gains selling qty shares from these lots (FIFO) at price on date sold would realise, without
    changing them. Returns (gains, shortfall)."""
    out, left = [], qty
    for lot in lots:
        if not left:
            break
        take = min(left, lot["qty"])
        out.append(close(lot, take, price, sold, fmv))
        left -= take
    return out, left
