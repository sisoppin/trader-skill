#!/usr/bin/env python3
"""Zerodha equity charges estimate for trader-budget. Standard library only.

An estimate only: the contract note is the real number. Rates for NSE
equity from https://zerodha.com/charges (read 2026-10-26):

                     delivery (CNC)              intraday (MIS)
  brokerage          zero                        0.03% or Rs 20 per executed order, lower
  STT                0.1% on buy and sell        0.025% on the sell side
  NSE transaction    0.00307%                    0.00307%
  SEBI               Rs 10 per crore             Rs 10 per crore
  stamp duty         0.015% on the buy side      0.003% on the buy side
  DP charge          Rs 13 per stock sold        none
                     (Rs 3.50 CDSL + Rs 9.50 Zerodha, once per stock per day
                     however many shares or orders; Rs 15.34 with GST)
  GST                18% on brokerage + SEBI + transaction + DP charges

The DP charge is counted in full on every CNC sell order, so two sells of
the same stock on one day are estimated a little high, never low.

Override any rate with a "charges" block in trader/config.json, using the
keys of RATES. Rates change: check the page every financial year.
"""

RATES = {
    "brokerage_mis_pct": 0.03, "brokerage_mis_cap": 20.0,
    "stt_cnc_pct": 0.1, "stt_mis_sell_pct": 0.025,
    "nse_txn_pct": 0.00307, "sebi_per_crore": 10.0,
    "stamp_cnc_buy_pct": 0.015, "stamp_mis_buy_pct": 0.003,
    "dp_cnc_sell": 13.0,
    "gst_pct": 18.0,
}
CRORE = 1e7


class ChargesError(Exception):
    pass


def rates(overrides=None):
    r = dict(RATES)
    for k, v in (overrides or {}).items():
        if k not in RATES:
            raise ChargesError("unknown charge %r in the config (known: %s)" % (k, ", ".join(sorted(RATES))))
        try:
            r[k] = float(v)
        except (TypeError, ValueError):
            raise ChargesError("charge %s must be a number, got %r" % (k, v))
    return r


def estimate(product, side, value, overrides=None):
    """Rupee charges for one executed order: {brokerage, stt, transaction, sebi, stamp, dp, gst, total}."""
    r = rates(overrides)
    product, side, value = str(product).upper(), str(side).upper(), float(value)
    if product not in ("CNC", "MIS"):
        raise ChargesError("charges are known for CNC and MIS only, not %s" % product)
    if side not in ("BUY", "SELL"):
        raise ChargesError("side must be BUY or SELL, not %s" % side)

    def pct(p):
        return value * p / 100.0

    if product == "CNC":
        brokerage = 0.0
        stt = pct(r["stt_cnc_pct"])
        stamp = pct(r["stamp_cnc_buy_pct"]) if side == "BUY" else 0.0
        dp = r["dp_cnc_sell"] if side == "SELL" and value > 0 else 0.0
    else:
        dp = 0.0
        brokerage = min(pct(r["brokerage_mis_pct"]), r["brokerage_mis_cap"])
        stt = pct(r["stt_mis_sell_pct"]) if side == "SELL" else 0.0
        stamp = pct(r["stamp_mis_buy_pct"]) if side == "BUY" else 0.0
    txn = pct(r["nse_txn_pct"])
    sebi = value * r["sebi_per_crore"] / CRORE
    gst = (brokerage + sebi + txn + dp) * r["gst_pct"] / 100.0
    parts = {"brokerage": brokerage, "stt": stt, "transaction": txn, "sebi": sebi, "stamp": stamp, "dp": dp,
             "gst": gst}
    out = {k: round(v, 2) for k, v in parts.items()}
    out["total"] = round(sum(parts.values()), 2)
    return out
