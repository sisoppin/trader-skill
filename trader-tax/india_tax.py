#!/usr/bin/env python3
"""Indian capital-gains arithmetic for trader-tax, per financial year. Standard library only.

Not tax advice. The rates below are the defaults in RULES and can be
changed with a "tax_rules" block in trader/config.json. Check them every
year (the Income-tax Act 2025 applies from 1 April 2026):

  financial year   1 April to 31 March, named like 2026-27
  STCG             listed equity held 12 months or less: 20%
  LTCG             held more than 12 months: 12.5% on the part above the
                   yearly exemption of Rs 1,25,000
  speculative      intraday round trips: business income at your slab
                   rate, kept separate (no estimate here)
  set-off          short-term loss against short-term gain, then against
                   long-term gain; long-term loss only against long-term
                   gain; speculative loss only against speculative income
  carry forward    what is still a loss carries forward 8 years (4 for
                   speculative), used oldest first, but only if that year's
                   return was filed on time
  estimate         from financial year "estimate_from_fy" on; earlier years
                   had other rates, so they show gains without an estimate
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from rupees import inr

RULES = {"stcg_pct": 20.0, "ltcg_pct": 12.5, "ltcg_exemption": 125000.0, "carry_years": 8,
         "speculative_carry_years": 4, "estimate_from_fy": "2025-26"}


class TaxRuleError(Exception):
    pass


def fy_of(d):
    """date -> '2026-27' (the financial year that starts on 1 April)."""
    start = d.year if d.month >= 4 else d.year - 1
    return "%d-%02d" % (start, (start + 1) % 100)


def _fy_start(fy):
    return int(fy[:4])


def rules(overrides=None):
    r = dict(RULES)
    for k, v in (overrides or {}).items():
        if k not in RULES:
            raise TaxRuleError("unknown tax rule %r (known: %s)" % (k, ", ".join(sorted(RULES))))
        if k == "estimate_from_fy":
            if not (isinstance(v, str) and len(v) == 7 and v[4] == "-" and v[:4].isdigit()):
                raise TaxRuleError("estimate_from_fy wants a year like 2025-26, got %r" % (v,))
            r[k] = v
            continue
        try:
            num = float(v)
        except (TypeError, ValueError):
            raise TaxRuleError("tax rule %s must be a number, got %r" % (k, v))
        if not math.isfinite(num) or num < 0:
            raise TaxRuleError("tax rule %s must be a number of at least 0, got %r" % (k, v))
        r[k] = int(num) if k.endswith("carry_years") else num
    return r


def _sum(gains, kind, sign):
    return sum(g["gain"] for g in gains if g["kind"] == kind and (g["gain"] > 0) == (sign > 0) and g["gain"])


def summarise(realised, speculative, overrides=None):
    """Per financial year, oldest first: gains by kind, set-off, carry-forward and the tax estimate."""
    r = rules(overrides)
    by_fy = {}
    for g in list(realised) + list(speculative):
        by_fy.setdefault(fy_of(g["sold"]), []).append(g)
    if not by_fy:
        return []
    first, last = min(by_fy), max(by_fy)
    carry = []  # [{"fy", "kind": ST|LT|SPEC, "amount", "last_fy"}]
    years = []
    for start in range(_fy_start(first), _fy_start(last) + 1):
        fy = "%d-%02d" % (start, (start + 1) % 100)
        gs = by_fy.get(fy, [])
        stcg, stcl = _sum(gs, "STCG", 1), -_sum(gs, "STCG", -1)
        ltcg, ltcl = _sum(gs, "LTCG", 1), -_sum(gs, "LTCG", -1)
        sp = sum(g["gain"] for g in gs if g["kind"] == "SPECULATIVE")
        st, lt = stcg - stcl, ltcg - ltcl
        notes = []
        if st < 0 and lt > 0:
            use = min(-st, lt)
            lt -= use
            st += use
            notes.append("short-term loss %s set off against long-term gain" % inr(use))
        carry = [c for c in carry if _fy_start(c["last_fy"]) >= start]
        used_carry = 0.0
        for c in sorted(carry, key=lambda c: c["fy"]):
            targets = {"ST": ("st", "lt"), "LT": ("lt",), "SPEC": ("sp",)}[c["kind"]]
            for tname in targets:
                avail = {"st": st, "lt": lt, "sp": sp}[tname]
                if avail <= 0 or c["amount"] <= 0:
                    continue
                use = min(avail, c["amount"])
                c["amount"] -= use
                used_carry += use
                if tname == "st":
                    st -= use
                elif tname == "lt":
                    lt -= use
                else:
                    sp -= use
                notes.append("%s loss carried from %s: %s used against %s" % (
                    {"ST": "short-term", "LT": "long-term", "SPEC": "speculative"}[c["kind"]], c["fy"], inr(use),
                    {"st": "short-term gain", "lt": "long-term gain", "sp": "speculative income"}[tname]))
        carry = [c for c in carry if c["amount"] > 0.005]
        for kind, value, years_n in (("ST", st, r["carry_years"]), ("LT", lt, r["carry_years"]),
                                     ("SPEC", sp, r["speculative_carry_years"])):
            if value < -0.005:
                carry.append({"fy": fy, "kind": kind, "amount": -value,
                              "last_fy": "%d-%02d" % (start + years_n, (start + years_n + 1) % 100)})
        st_taxable = max(st, 0.0)
        lt_pos = max(lt, 0.0)
        exemption_used = min(lt_pos, r["ltcg_exemption"])
        lt_taxable = lt_pos - exemption_used
        estimate = None
        if start >= _fy_start(r["estimate_from_fy"]):
            st_tax = st_taxable * r["stcg_pct"] / 100.0
            lt_tax = lt_taxable * r["ltcg_pct"] / 100.0
            estimate = {"stcg": round(st_tax, 2), "ltcg": round(lt_tax, 2), "total": round(st_tax + lt_tax, 2)}
        elif gs:
            notes.append("no tax estimate for %s: the rates before FY %s were different" % (fy, r["estimate_from_fy"]))
        if not gs and not used_carry:
            continue
        years.append({
            "fy": fy, "stcg": round(stcg, 2), "stcl": round(stcl, 2), "ltcg": round(ltcg, 2), "ltcl": round(ltcl, 2),
            "speculative": round(sum(g["gain"] for g in gs if g["kind"] == "SPECULATIVE"), 2),
            "st_net": round(st, 2), "lt_net": round(lt, 2), "speculative_net": round(sp, 2),
            "st_taxable": round(st_taxable, 2), "lt_taxable": round(lt_taxable, 2),
            "exemption_used": round(exemption_used, 2),
            "exemption_left": round(r["ltcg_exemption"] - exemption_used, 2),
            "carry_forward": [dict(c, amount=round(c["amount"], 2)) for c in carry],
            "estimate": estimate, "notes": notes,
        })
    return years
