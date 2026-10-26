import datetime
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

size = load("trader-budget", "size")

BDIR = os.path.join(ROOT, "trader-budget")
KDIR = os.path.join(FIX, "trader-budget", "kite")
NOW = "2026-10-26T10:01"


def cfg(**over):
    c = size.load_config(os.path.join(BDIR, "config.example.json"))
    c.update(over)
    return c


def targets():
    with open(os.path.join(BDIR, "targets.example.json")) as fh:
        return size.parse_weights(json.load(fh))


def prices():
    return size.quote_prices(KDIR, datetime.datetime(2026, 10, 26, 10, 1, tzinfo=size.IST))


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = size.main(argv)
    return code, out.getvalue(), err.getvalue()


class Example(unittest.TestCase):
    def test_the_example_budget_is_capped_by_the_max_order(self):
        r = size.size(targets(), cfg(), None, prices())
        self.assertEqual((r["budget"], r["cash_buffer"], r["investable"], r["cap"]), (50000, 5000, 45000, 10000))
        self.assertEqual(r["cap_by"], "your Rs 10,000 max order")
        self.assertEqual([(p["symbol"], p["shares"], p["rupees"]) for p in r["positions"]],
                         [("INFY", 6, 9675.0), ("RELIANCE", 7, 9816.1), ("TCS", 3, 9151.5), ("HDFCBANK", 6, 9900.0)])
        self.assertEqual((r["invested"], r["idle"]), (38542.6, 6457.4))

    def test_orders_are_kite_place_order_shaped(self):
        r = size.size(targets(), cfg(), None, prices())
        o = size.orders_from(r, cfg())
        self.assertEqual(o[0], {
            "exchange": "NSE", "tradingsymbol": "INFY", "transaction_type": "BUY", "quantity": "6",
            "product": "CNC", "order_type": "LIMIT", "price": "1612.50", "validity": "DAY",
            "variety": "regular", "est_value": "9675.00", "est_charges": "11.49",
            "why": "25.00% of the stock sleeve; capped at Rs 10,000, your Rs 10,000 max order"})
        self.assertTrue(all(isinstance(x["quantity"], str) and isinstance(x["price"], str) for x in o))
        self.assertEqual({x["product"] for x in size.orders_from(r, cfg(), "mis")}, {"MIS"})


class Rules(unittest.TestCase):
    def test_bigger_budget_uses_the_position_cap_and_drops_blocked(self):
        r = size.size(targets(), cfg(max_order_value="0", blocked=["tcs.ns"]), 100000, prices())
        self.assertEqual((r["cap"], r["cap_by"]), (25000, "25% of the Rs 1,00,000 budget"))
        self.assertEqual(r["dropped"], [{"ticker": "TCS", "reason": "on your blocked list"}])
        self.assertEqual([(p["symbol"], p["shares"]) for p in r["positions"]],
                         [("INFY", 15), ("RELIANCE", 17), ("HDFCBANK", 15)])
        self.assertEqual((r["invested"], r["idle"]), (72776.6, 17223.4))

    def test_a_share_dearer_than_its_slice_is_dropped(self):
        r = size.size(size.parse_weights({"TCS": 50, "INFY": 50}),
                      cfg(max_order_value="2000", max_position_pct="50"), 5000, prices())
        self.assertEqual(r["dropped"], [{"ticker": "TCS",
                                         "reason": "one share costs Rs 3,050.50, more than its slice of Rs 2,000"}])
        self.assertEqual([(p["symbol"], p["shares"]) for p in r["positions"]], [("INFY", 1)])

    def test_nothing_affordable_is_an_error(self):
        with self.assertRaises(size.SizeError):
            size.size(targets(), cfg(), 2000, prices())

    def test_missing_quote_names_the_kite_instrument(self):
        with self.assertRaises(size.SizeError) as e:
            size.size(size.parse_weights({"INFY": 50, "M&M": 50}), cfg(), None, prices())
        self.assertIn("NSE:M&M", str(e.exception))

    def test_symbol_spellings_and_bad_input(self):
        self.assertEqual([r["ticker"] for r in size.parse_weights({"infy.ns": 1, "nse:tcs": 1})], ["INFY", "TCS"])
        with self.assertRaises(size.SizeError):
            size.parse_weights({"BSE:INFY": 1})
        with self.assertRaises(size.SizeError):
            size.parse_weights({"INFY": "lots"})
        with self.assertRaises(size.SizeError):
            size.size(targets(), cfg(budget=None), None, prices())


class Cli(unittest.TestCase):
    def test_write_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            code, text, _ = run(["--targets", os.path.join(BDIR, "targets.example.json"),
                                 "--config", os.path.join(BDIR, "config.example.json"),
                                 "--kite-dir", KDIR, "--now", NOW, "--write", out])
            self.assertEqual(code, 0)
            self.assertIn("BUY 6 INFY, CNC, LIMIT Rs 1,612.50, est. Rs 9,675 + Rs 11.49 charges", text)
            self.assertIn("LIVE", text)
            self.assertIn("not financial advice", text)
            with open(out) as fh:
                doc = json.load(fh)
            self.assertIs(doc["live"], True)
            self.assertEqual(doc["created_by"], "trader-budget")
            self.assertEqual(len(doc["orders"]), 4)

    def test_stale_quotes_stop_the_sizing(self):
        code, _, err = run(["--weights", "INFY=100", "--config", os.path.join(BDIR, "config.example.json"),
                            "--kite-dir", KDIR, "--now", "2026-10-26T10:03"])
        self.assertEqual(code, 1)
        self.assertIn("s old", err)

    def test_missing_targets(self):
        code, _, err = run(["--targets", os.path.join(FIX, "nope.json"), "--kite-dir", KDIR, "--now", NOW])
        self.assertEqual(code, 1)
        self.assertIn("no targets file", err)


if __name__ == "__main__":
    unittest.main()
