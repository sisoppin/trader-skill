"""NSE shareholding patterns for trader-copycat: who holds more than 1% of a company.

Every quarter each listed company files its shareholding pattern with NSE as XBRL. The pattern names every
public shareholder with more than 1% of the company (and every promoter), with their share count. NSE lists
the filings per stock at

    https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=<SYMBOL>

and each row links to the XBRL file (https://nsearchives.nseindia.com/corporate/xbrl/SHP_..._WEB.xml).

In the XBRL a shareholder's name sits on a context named D_<Category>_ContextN and the shares and the
percentage on the matching <Category>_ContextN. One person can appear more than once (two accounts, or two
categories): the holding is the sum. The PAC_ contexts repeat holdings already counted (persons acting in
concert) and are skipped. Standard library only.
"""

import datetime
import re
import xml.etree.ElementTree as ET

MASTER_URL = "https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=%s"


class ShpError(Exception):
    pass


def parse_master(doc, symbol):
    """NSE's shareholding list -> [{quarter (date), xbrl}], newest quarter first."""
    if not isinstance(doc, list):
        raise ShpError("the shareholding list for %s is not NSE's answer (not a list)" % symbol)
    out = {}
    for r in doc:
        if not isinstance(r, dict):
            continue
        try:
            q = datetime.datetime.strptime(str(r.get("date")).strip(), "%d-%b-%Y").date()
        except ValueError:
            continue
        link = str(r.get("xbrl") or "")
        if link.lower().endswith(".xml") and q not in out:
            out[q] = link
    return [{"quarter": q, "xbrl": out[q]} for q in sorted(out, reverse=True)]


def _category(ctx):
    c = re.sub(r"_?Context\d+$", "", ctx)
    return c[len("DetailsOfSharesHeldBy"):] if c.startswith("DetailsOfSharesHeldBy") else c


def parse(text):
    """One shareholding XBRL -> {symbol, company, isin, quarter, total_shares, holders: [{category, name, shares, pct}]}.

    pct is a percentage of the company (4.24 for 4.24%)."""
    try:
        root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except ET.ParseError as e:
        raise ShpError("not an XBRL file (%s), probably a block page" % e)
    local = lambda el: el.tag.rsplit("}", 1)[-1]
    head, names, facts = {}, {}, {}
    for el in root:
        n, c, v = local(el), el.get("contextRef") or "", (el.text or "").strip()
        if n in ("Symbol", "NameOfTheCompany", "DateOfReport", "ISIN") and n not in head and not c.startswith("D_"):
            head[n] = v
        elif n == "NameOfTheShareholder" and c.startswith("D_") and not c.startswith("D_PAC"):
            names.setdefault(c[2:], " ".join(v.split()))
        elif n in ("NumberOfShares", "ShareholdingAsAPercentageOfTotalNumberOfShares"):
            facts.setdefault(c, {})[n] = v
    try:
        quarter = datetime.datetime.strptime(head.get("DateOfReport", ""), "%Y-%m-%d").date()
    except ValueError:
        raise ShpError("the shareholding XBRL has no DateOfReport")
    holders = []
    for ctx, name in names.items():
        f = facts.get(ctx, {})
        try:
            shares = int(float(f["NumberOfShares"]))
        except (KeyError, ValueError):
            shares = None
        try:
            pct = round(float(f["ShareholdingAsAPercentageOfTotalNumberOfShares"]) * 100, 2)
        except (KeyError, ValueError):
            pct = None
        holders.append({"category": _category(ctx), "name": name, "shares": shares, "pct": pct})
    total = facts.get("ShareholdingPattern_ContextI", {}).get("NumberOfShares")
    return {"symbol": head.get("Symbol", "").upper(), "company": head.get("NameOfTheCompany", ""),
            "isin": head.get("ISIN", ""), "quarter": quarter,
            "total_shares": int(float(total)) if total else None, "holders": holders}


def words(name):
    return set(re.findall(r"[a-z0-9]+", str(name).lower()))


def matches(query, name):
    """Every word of the query is a word of the name: 'rekha jhunjhunwala' matches 'REKHA JHUNJHUNWALA'."""
    q = words(query)
    return bool(q) and q <= words(name)


def holding(doc, query):
    """The query's total holding in one pattern -> {shares, pct, names, categories}, or None if not named."""
    hits = [h for h in doc["holders"] if matches(query, h["name"])]
    if not hits:
        return None
    if any(h["shares"] is None or h["pct"] is None for h in hits):
        raise ShpError("%s is named in the pattern but has no share count" % query)
    return {"shares": sum(h["shares"] for h in hits), "pct": round(sum(h["pct"] for h in hits), 2),
            "names": sorted({h["name"] for h in hits}), "categories": sorted({h["category"] for h in hits})}


def change(now, before):
    """Quarter-on-quarter: new, added, trimmed, same, or gone (sold, or now under 1% and no longer named)."""
    if now and not before:
        return "new"
    if before and not now:
        return "gone"
    if now["shares"] > before["shares"]:
        return "added"
    if now["shares"] < before["shares"]:
        return "trimmed"
    return "same"
