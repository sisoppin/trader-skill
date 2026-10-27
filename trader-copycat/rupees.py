#!/usr/bin/env python3
"""Rupee amounts in Indian grouping for the trader skills. Standard library only.

    inr(125000)      -> "Rs 1,25,000"
    inr(1612.5)      -> "Rs 1,612.50"
    inr(-950)        -> "-Rs 950"

This file is copied into every skill that shows money. Keep the copies
identical: tests/test_repo.py checks.
"""


def inr(x):
    """1234567.891 -> 'Rs 12,34,567.89' (Indian grouping). Whole rupees drop the paise."""
    x = float(x)
    whole, paise = ("%.2f" % abs(x)).split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    text = ",".join(groups + [tail])
    if paise != "00":
        text += "." + paise
    return ("-Rs " if x < 0 else "Rs ") + text
