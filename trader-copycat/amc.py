"""Mutual fund portfolios for trader-copycat, from the monthly sheet the fund house (AMC) publishes.

Every AMC publishes each scheme's full portfolio every month on its website, usually as an Excel sheet. The
user opens it, picks the scheme's sheet and saves it as CSV. Sheets differ between AMCs, so the parser finds
the header row by its column names (ISIN, the instrument or company name, quantity, market value, % to NAV
or % to net assets, matched case-insensitively) and keeps only equity shares of Indian companies: an ISIN
starting with INE whose security code (characters 8 and 9) is 01. Bonds, debentures and commercial paper
from the same companies (INE... with another code), cash, TREPS, derivatives and foreign stocks are
skipped, and so is any row without a % to NAV. Standard library only.
"""

import csv
import io
import re

NAME = ("name of the instrument", "name of instrument", "instrument", "company name", "name of the issuer",
        "issuer", "security", "name")
PCT = ("% to nav", "% of nav", "% to net assets", "% of net assets", "% to aum", "% of aum", "% to net asset",
       "% of net asset", "percentage to nav", "% nav")
QTY = ("quantity", "no. of shares", "shares", "qty")
VALUE = ("market value", "market/fair value", "fair value", "value")


class AmcError(Exception):
    pass


def _norm(cell):
    return " ".join(str(cell or "").lower().replace("\n", " ").split())


def _col(header, names):
    for want in names:
        for i, h in enumerate(header):
            if h == want or h.startswith(want + " ") or h.startswith(want + "("):
                return i
    return None


def _num(text):
    t = str(text or "").replace(",", "").replace("%", "").strip()
    if t.startswith("(") and t.endswith(")"):
        t = "-" + t[1:-1]
    try:
        return float(t)
    except ValueError:
        return None


def is_equity(isin):
    isin = str(isin or "").strip().upper()
    return bool(re.match(r"^INE[A-Z0-9]{4}01[A-Z0-9]{3}$", isin))


def parse(text):
    """CSV text -> [{isin, name, quantity, value, pct}] for the equity rows, pct as a percentage of NAV."""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    header_at, cols = None, None
    for i, r in enumerate(rows):
        h = [_norm(c) for c in r]
        isin, pct = _col(h, ("isin", "isin code", "isin no.")), _col(h, PCT)
        if isin is not None and pct is not None:
            header_at = i
            cols = {"isin": isin, "pct": pct, "name": _col(h, NAME), "qty": _col(h, QTY), "value": _col(h, VALUE)}
            break
    if header_at is None:
        raise AmcError("no header row with an ISIN column and a % to NAV column (is this the AMC's portfolio sheet "
                       "saved as CSV?)")
    cell = lambda r, k: r[cols[k]] if cols[k] is not None and cols[k] < len(r) else ""
    out = []
    for r in rows[header_at + 1:]:
        isin = cell(r, "isin").strip().upper()
        pct = _num(cell(r, "pct"))
        if not is_equity(isin) or pct is None:
            continue
        out.append({"isin": isin, "name": " ".join(cell(r, "name").split()), "quantity": _num(cell(r, "qty")),
                    "value": _num(cell(r, "value")), "pct": pct})
    if not out:
        raise AmcError("the sheet has a header row but no equity rows (INE...01... ISINs with a % to NAV)")
    if max(x["pct"] for x in out) <= 1 and sum(x["pct"] for x in out) <= 1.01:
        for x in out:  # the sheet gives fractions (0.0523), not percentages (5.23)
            x["pct"] = round(x["pct"] * 100, 4)
    merged = {}
    for x in out:  # one stock can appear twice (two lots, or a pending listing); add them up
        m = merged.get(x["isin"])
        if m is None:
            merged[x["isin"]] = dict(x)
        else:
            m["pct"] += x["pct"]
            for k in ("quantity", "value"):
                m[k] = None if m[k] is None or x[k] is None else m[k] + x[k]
    return list(merged.values())


def change(now, before):
    """Month-on-month by quantity (or % to NAV when a sheet has no quantity): new, added, trimmed, same, sold."""
    if now and not before:
        return "new"
    if before and not now:
        return "sold"
    k = "quantity" if now["quantity"] is not None and before["quantity"] is not None else "pct"
    if now[k] > before[k]:
        return "added"
    if now[k] < before[k]:
        return "trimmed"
    return "same"
