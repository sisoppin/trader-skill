#!/usr/bin/env python3
"""Copy a shared helper from one skill to every other skill that has it.

The shared helpers (test_repo.SHARED) are copied into each skill so every
skill folder works on its own, and test_shared_helpers_are_identical fails
when the copies drift. Edit one copy, then:

    python3 tests/sync_helpers.py nse_calendar.py --from trader-risk
    python3 tests/sync_helpers.py --check        # list helpers whose copies differ

Not a test (unittest only discovers test*.py). Standard library only.
"""

import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_repo import ROOT, SHARED, SKILLS  # noqa: E402


def copies(name):
    return [s for s in SKILLS if os.path.isfile(os.path.join(ROOT, s, name))]


def read(skill, name):
    with open(os.path.join(ROOT, skill, name), "rb") as fh:
        return fh.read()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sync a shared helper across the skill folders.")
    ap.add_argument("name", nargs="?", help="the helper file, like nse_calendar.py")
    ap.add_argument("--from", dest="src", help="the skill folder holding the edited copy")
    ap.add_argument("--check", action="store_true", help="only list helpers whose copies differ")
    a = ap.parse_args(argv)
    if a.check:
        drift = [n for n in SHARED if len({read(s, n) for s in copies(n)}) > 1]
        for n in drift:
            print("%s differs across: %s" % (n, ", ".join(copies(n))))
        print("all shared helpers match" if not drift else "%d helper(s) differ" % len(drift))
        return 1 if drift else 0
    if a.name not in SHARED or not a.src:
        ap.error("give a shared helper (%s) and --from <skill>" % ", ".join(sorted(SHARED)))
    if a.src not in copies(a.name):
        ap.error("%s has no %s" % (a.src, a.name))
    src = os.path.join(ROOT, a.src, a.name)
    for s in copies(a.name):
        if s != a.src:
            shutil.copyfile(src, os.path.join(ROOT, s, a.name))
            print("copied %s -> %s" % (src, s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
