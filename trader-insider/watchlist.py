#!/usr/bin/env python3
"""Which stocks to watch, for the trader skills. Standard library only.

The symbols come from the Kite holdings snapshot (any age: it is only a
list of names) and from trader/targets.json, in that order, each once.

This file is copied into every skill that watches a list of stocks. Keep
the copies identical: tests/test_repo.py checks.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import kite_snapshot


class WatchError(Exception):
    pass


def watch_list(kite_dir, targets):
    syms = []
    try:
        for r in kite_snapshot.load("holdings", kite_dir, max_age=10 ** 9) or []:
            syms.append(str(r.get("tradingsymbol", "")).upper())
    except kite_snapshot.SnapshotError as e:
        held = kite_snapshot.path("holdings", kite_dir)
        if os.path.exists(held):
            raise WatchError("%s: %s" % (held, e))
    if targets and os.path.exists(targets):
        try:
            with open(targets, encoding="utf-8") as fh:
                doc = json.load(fh)
        except ValueError as e:
            raise WatchError("%s is not valid JSON: %s" % (targets, e))
        for w in (doc.get("weights") or []) if isinstance(doc, dict) else []:
            if not isinstance(w, dict):
                continue
            syms.append(str(w.get("symbol") or w.get("ticker") or "").upper())
    out = []
    for s in syms:
        if s and s not in out:
            out.append(s)
    return out
