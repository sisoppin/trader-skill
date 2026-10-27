import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

rebalance = load("trader-rebalance", "rebalance")
check = load("trader-risk", "check")

RDIR = os.path.join(FIX, "trader-rebalance")
KDIR = os.path.join(RDIR, "kite")
TARGETS = os.path.join(RDIR, "targets.json")
CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
NOW = "2026-10-26T10:01"


def cfg(**over):
    with open(CFG_PATH) as fh:
        c = json.load(fh)
    c.update(over)
    return c


def setup(**over):
    snap = rebalance.load_snapshots(KDIR, check.nse_calendar.parse_now(NOW))
    cash, held = rebalance.account(snap)
    prices = {s: q["price"] for s, q in snap["quotes"].items()}
    with open(TARGETS) as fh:
        weights = rebalance.parse_targets(json.load(fh), over.get("blocked"))
    return cash, held, prices, weights, cfg(**over)


def orders(res):
    return [(o["transaction_type"], o["tradingsymbol"], o["quantity"]) for o in res["orders"]]


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = rebalance.main(argv)
    return code, out.getvalue(), err.getvalue()


class Example(unittest.TestCase):
    def test_sells_first_then_buys_within_free_cash(self):
        res = rebalance.plan(*setup())
        self.assertEqual(res["account_value"], 71335.7)
        self.assertEqual([(r["symbol"], r["action"]) for r in res["rows"]],
                         [("HDFCBANK", "buy"), ("INFY", "sell"), ("RELIANCE", "buy"), ("TCS", "buy"),
                          ("ITC", "untracked, left alone")])
        self.assertEqual(orders(res), [("SELL", "INFY", "4"), ("BUY", "HDFCBANK", "2"), ("BUY", "RELIANCE", "4"),
                                       ("BUY", "TCS", "1")])
        self.assertEqual(res["cash_after_buys"], 8026.1)
        self.assertGreater(res["cash_after_buys"], res["cash_buffer"])
        self.assertIn("buys scaled to 55%", res["notes"][0])
        o = res["orders"][0]
        self.assertEqual((o["product"], o["order_type"], o["price"], o["est_value"], o["est_charges"]),
                         ("CNC", "LIMIT", "1612.50", "6450.00", "22.03"))

    def test_the_orders_pass_the_risk_check(self):
        res = rebalance.plan(*setup())
        now = check.nse_calendar.parse_now(NOW)
        cal = check.nse_calendar.Calendar(dict(check.nse_calendar.HOLIDAYS), check.nse_calendar.YEARS)
        risk = check.check(res["orders"], cfg(), check.load_data(KDIR, now), now, cal)
        self.assertEqual([r["verdict"] for r in risk["results"]], ["PASS"] * 4, risk["results"])


class Rules(unittest.TestCase):
    def test_sell_untracked_and_blocked(self):
        res = rebalance.plan(*setup(), sell_untracked=True)
        self.assertEqual(orders(res)[1], ("SELL", "ITC", "10"))
        res = rebalance.plan(*setup(blocked=["infy.ns"]))
        self.assertEqual([r["action"] for r in res["rows"] if r["symbol"] == "INFY"], ["untracked, left alone"])

    def test_band(self):
        self.assertEqual(rebalance.plan(*setup(), band=15)["orders"], [])
        res = rebalance.plan(*setup(), band=10)
        self.assertEqual(orders(res), [("BUY", "RELIANCE", "7")])
        self.assertIn("RELIANCE buy cut to your Rs 10,000 max order", " ".join(res["notes"]))

    def test_max_order_and_order_count(self):
        res = rebalance.plan(*setup(max_order_value="3000"))
        self.assertEqual(orders(res)[0], ("SELL", "INFY", "1"))
        self.assertIn("INFY sell cut to your Rs 3,000 max order", " ".join(res["notes"]))
        res = rebalance.plan(*setup(max_orders_per_day=2))
        self.assertEqual(len(res["orders"]), 2)
        self.assertIn("kept the first 2 (sells first)", res["notes"][-1])

    def test_todays_delivery_trades_count_as_held(self):
        snap = {"holdings": [{"tradingsymbol": "INFY", "quantity": 14, "t1_quantity": 0}],
                "positions": {"net": [{"tradingsymbol": "INFY", "product": "CNC", "quantity": -4},
                                      {"tradingsymbol": "TCS", "product": "MIS", "quantity": 5}], "day": []},
                "margins": {"equity": {"available": {"live_balance": 100.0}}}}
        self.assertEqual(rebalance.account(snap), (100.0, {"INFY": 10}))
        with self.assertRaises(rebalance.RebalanceError):
            rebalance.account(dict(snap, margins={"commodity": {}}))

    def test_missing_quote_and_bad_config(self):
        cash, held, prices, weights, c = setup()
        del prices["TCS"]
        with self.assertRaises(rebalance.RebalanceError) as e:
            rebalance.plan(cash, held, prices, weights, c)
        self.assertIn("NSE:TCS", str(e.exception))
        with self.assertRaises(rebalance.RebalanceError):
            rebalance.plan(*setup(cash_buffer_pct="nan"))


class FixRound1(unittest.TestCase):
    def test_open_orders_skip_the_symbol(self):
        res = rebalance.plan(*setup(), open_orders=[{"tradingsymbol": "INFY", "status": "OPEN"}])
        self.assertNotIn("INFY", [o["tradingsymbol"] for o in res["orders"]])
        self.assertTrue(res["orders"])
        self.assertEqual([r["action"] for r in res["rows"] if r["symbol"] == "INFY"], ["open order in Kite, skipped"])
        self.assertIn("INFY has an open order in Kite's order book: wait for it to fill or cancel it, then run "
                      "again", res["notes"])
        res = rebalance.plan(*setup(), open_orders=[{"tradingsymbol": "RELIANCE", "status": "trigger pending"}])
        self.assertNotIn("RELIANCE", [o["tradingsymbol"] for o in res["orders"]])
        self.assertIn(("SELL", "INFY"), [(o["transaction_type"], o["tradingsymbol"]) for o in res["orders"]])

    def test_finished_orders_change_nothing(self):
        base = rebalance.plan(*setup())
        done = [{"tradingsymbol": "INFY", "status": s} for s in ("COMPLETE", "rejected", "Cancelled")]
        self.assertEqual(rebalance.plan(*setup(), open_orders=done), base)

    def test_orders_snapshot_must_be_a_list(self):
        with tempfile.TemporaryDirectory() as d:
            for f in os.listdir(KDIR):
                shutil.copy(os.path.join(KDIR, f), d)
            with open(os.path.join(d, "orders.json"), "w") as fh:
                json.dump({"fetched_at": "2026-10-26T10:00:00+05:30", "data": {"x": 1}}, fh)
            with self.assertRaises(rebalance.RebalanceError):
                rebalance.load_snapshots(d, check.nse_calendar.parse_now(NOW))
        self.assertEqual(rebalance.load_snapshots(KDIR, check.nse_calendar.parse_now(NOW))["orders"], [])

    def test_write_with_nothing_to_propose_removes_the_old_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            with open(out, "w") as fh:
                fh.write("{}")
            code, text, _ = run(["--targets", TARGETS, "--config", CFG_PATH, "--kite-dir", KDIR, "--now", NOW,
                                 "--band", "15", "--write", out])
            self.assertEqual(code, 1)
            self.assertFalse(os.path.exists(out))
            self.assertIn("Removed the old %s: nothing to propose." % out, text)

    def test_percentage_bounds(self):
        for k, v in (("cash_buffer_pct", "100"), ("cash_buffer_pct", "150"), ("max_position_pct", "0"),
                     ("max_position_pct", "101")):
            with self.assertRaises(rebalance.RebalanceError, msg=(k, v)):
                rebalance.plan(*setup(**{k: v}))


class Cli(unittest.TestCase):
    def base(self):
        return ["--targets", TARGETS, "--config", CFG_PATH, "--kite-dir", KDIR]

    def test_write_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            code, text, _ = run(self.base() + ["--now", NOW, "--write", out])
            self.assertEqual(code, 0)
            self.assertIn("Proposed LIVE orders", text)
            self.assertIn("not financial advice", text)
            with open(out) as fh:
                doc = json.load(fh)
            self.assertEqual((doc["created_by"], doc["live"], len(doc["orders"])), ("trader-rebalance", True, 4))
            code, text, _ = run(self.base() + ["--now", NOW, "--band", "15"])
            self.assertEqual(code, 1)
            self.assertIn("Nothing is outside the band", text)

    def test_stale_snapshots_and_the_test_clock(self):
        code, _, err = run(self.base() + ["--now", "2026-10-26T10:05"])
        self.assertEqual(code, 1)
        self.assertIn("quotes snapshot is", err)
        saved = os.environ.pop("TRADER_TEST_CLOCK")
        try:
            code, _, err = run(self.base() + ["--now", NOW])
        finally:
            os.environ["TRADER_TEST_CLOCK"] = saved
        self.assertEqual(code, 1)
        self.assertIn("for tests only", err)



class FinalFix(unittest.TestCase):
    def base(self):
        return ["--targets", TARGETS, "--config", CFG_PATH, "--kite-dir", KDIR]

    def test_blocked_holdings_are_never_sold(self):
        res = rebalance.plan(*setup(blocked=["itc.ns"]), sell_untracked=True)
        self.assertNotIn("ITC", [o["tradingsymbol"] for o in res["orders"]])
        self.assertEqual([r["action"] for r in res["rows"] if r["symbol"] == "ITC"], ["blocked, left alone"])
        self.assertIn("ITC is on your blocked list: not sold", res["notes"])
        res = rebalance.plan(*setup(blocked=["INFY"]), sell_untracked=True)
        self.assertNotIn("INFY", [o["tradingsymbol"] for o in res["orders"]])
        self.assertIn(("SELL", "ITC", "10"), orders(res))

    def test_an_error_under_write_removes_the_old_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            with open(out, "w") as fh:
                json.dump({"created_by": "trader-tax", "orders": []}, fh)
            code, _, err = run(self.base() + ["--now", "2026-10-26T10:05", "--write", out])
            self.assertEqual(code, 1)
            self.assertIn("quotes snapshot is", err)
            self.assertFalse(os.path.exists(out))
            self.assertIn("Removed the old %s (proposals from trader-tax)" % out, err)

    def test_removing_the_old_file_names_who_wrote_it(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            with open(out, "w") as fh:
                json.dump({"created_by": "trader-tax", "orders": []}, fh)
            code, text, _ = run(self.base() + ["--now", NOW, "--band", "15", "--write", out])
            self.assertEqual(code, 1)
            self.assertFalse(os.path.exists(out))
            self.assertIn("Removed the old %s (proposals from trader-tax): nothing to propose." % out, text)


if __name__ == "__main__":
    unittest.main()
