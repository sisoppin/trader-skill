#!/usr/bin/env python3
"""Kite snapshots for the trader skills. Standard library only.

The scripts cannot call the Kite connector, so Claude does: it calls the
connector, then saves the raw answer here. This script stamps the time it was
saved, and every reader refuses a snapshot that is too old.

    python3 kite_snapshot.py save quotes --from raw.json    # or pipe the JSON on stdin
    python3 kite_snapshot.py save positions --from raw.json
    python3 kite_snapshot.py show                           # age of every snapshot

Each file is trader/kite/<kind>.json:
    {"fetched_at": "2026-10-26T15:29:00+05:30", "data": <the Kite answer>}

How old a snapshot may be before a reader refuses it: quotes 120 s;
holdings, positions, margins and trades 600 s.

This file is copied into every skill that reads Kite data. Keep the copies
identical: tests/test_repo.py checks.
"""

import argparse
import datetime
import json
import os
import sys

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
DIR = os.path.join("trader", "kite")
MAX_AGE = {"quotes": 120, "holdings": 600, "positions": 600, "margins": 600, "trades": 600}
SKEW = 60  # seconds a snapshot may look "from the future" before the clock is suspect


class SnapshotError(Exception):
    pass


def now_ist():
    return datetime.datetime.now(IST).replace(microsecond=0)


def _kind(kind):
    if kind not in MAX_AGE:
        raise SnapshotError("unknown snapshot kind %r (one of %s)" % (kind, ", ".join(sorted(MAX_AGE))))
    return kind


def unwrap(raw):
    """The Kite answer without the REST envelope {"status": ..., "data": ...}."""
    if isinstance(raw, dict) and "status" in raw:
        if raw.get("status") != "success" or "data" not in raw:
            raise SnapshotError("Kite answered %s: %s" % (raw.get("status"), raw.get("message", "no message")))
        return raw["data"]
    return raw


def path(kind, d=DIR):
    return os.path.join(d, _kind(kind) + ".json")


def save(kind, raw, d=DIR, now=None):
    p = path(kind, d)
    doc = {"fetched_at": (now or now_ist()).isoformat(), "data": unwrap(raw)}
    os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    return p


def _read(kind, d):
    p = path(kind, d)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
    except ValueError as e:
        raise SnapshotError("%s is not valid JSON: %s" % (p, e))
    if not isinstance(doc, dict) or "fetched_at" not in doc or "data" not in doc:
        raise SnapshotError("%s is not a snapshot: save it with kite_snapshot.py save %s" % (p, kind))
    return doc


def _fetched(doc, kind):
    try:
        t = datetime.datetime.fromisoformat(doc["fetched_at"])
    except (TypeError, ValueError):
        raise SnapshotError("the %s snapshot has a bad fetched_at: %r" % (kind, doc.get("fetched_at")))
    if t.tzinfo is None:
        raise SnapshotError("the %s snapshot's fetched_at has no UTC offset" % kind)
    return t


def age(kind, d=DIR, now=None):
    """Seconds since the snapshot was saved, or None if there is none."""
    doc = _read(kind, d)
    if doc is None:
        return None
    return ((now or now_ist()) - _fetched(doc, kind)).total_seconds()


def load(kind, d=DIR, now=None, max_age=None):
    """The Kite answer saved for kind. Refuses a missing, stale or future snapshot."""
    doc = _read(kind, d)
    if doc is None:
        raise SnapshotError("no %s snapshot in %s: call the Kite connector for %s, then "
                            "kite_snapshot.py save %s" % (kind, d, kind, kind))
    secs = ((now or now_ist()) - _fetched(doc, kind)).total_seconds()
    limit = MAX_AGE[kind] if max_age is None else max_age
    if secs < -SKEW:
        raise SnapshotError("the %s snapshot is from the future (%s): check this computer's clock"
                            % (kind, doc["fetched_at"]))
    if secs > limit:
        raise SnapshotError("the %s snapshot is %d s old (limit %d s): refresh it with the Kite connector "
                            "and kite_snapshot.py save %s" % (kind, secs, limit, kind))
    return doc["data"]


def _f(x):
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def quotes(data):
    """Kite quotes {"NSE:INFY": {...}} -> {"INFY": {symbol, exchange, price, prev_close, open, high,
    low, upper_circuit, lower_circuit, time}}. NSE symbols are keyed bare, others as EXCH:SYM."""
    out = {}
    for key, q in (data or {}).items():
        if not isinstance(q, dict) or _f(q.get("last_price")) is None:
            continue
        exch, sym = key.split(":", 1) if ":" in key else ("NSE", key)
        ohlc = q.get("ohlc") or {}
        out[sym if exch == "NSE" else key] = {
            "symbol": sym, "exchange": exch, "price": _f(q["last_price"]),
            "prev_close": _f(ohlc.get("close")), "open": _f(ohlc.get("open")),
            "high": _f(ohlc.get("high")), "low": _f(ohlc.get("low")),
            "upper_circuit": _f(q.get("upper_circuit_limit")),
            "lower_circuit": _f(q.get("lower_circuit_limit")),
            "time": str(q.get("last_trade_time") or q.get("timestamp") or "")}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Save and inspect Kite snapshots (trader skills).")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("save", help="stamp and save a raw Kite answer")
    p.add_argument("kind", choices=sorted(MAX_AGE))
    p.add_argument("--from", dest="src", help="file with the raw JSON (default: stdin)")
    p.add_argument("--dir", default=DIR)
    p = sub.add_parser("show", help="how old is each snapshot?")
    p.add_argument("--dir", default=DIR)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        if a.cmd == "save":
            if a.src:
                with open(a.src, encoding="utf-8-sig") as fh:
                    text = fh.read()
            else:
                text = sys.stdin.read()
            try:
                raw = json.loads(text)
            except ValueError as e:
                raise SnapshotError("that is not JSON: %s" % e)
            print("Saved %s." % save(a.kind, raw, a.dir))
            return 0
        for kind in sorted(MAX_AGE):
            secs = age(kind, a.dir)
            if secs is None:
                print("%-10s none" % kind)
            else:
                print("%-10s %5d s old%s" % (kind, secs, "  (stale)" if secs > MAX_AGE[kind] else ""))
        return 0
    except (SnapshotError, OSError) as e:
        print("kite_snapshot.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
