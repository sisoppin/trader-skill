import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

lots = load("trader-tax", "lots")
check = load("trader-risk", "check")

TDIR = os.path.join(FIX, "trader-tax")
KDIR = os.path.join(TDIR, "kite")
CFG = os.path.join(ROOT, "trader-budget", "config.example.json")
NOW = "2026-10-26T10:01"


def args(kite_dir=KDIR, now=NOW):
    return ["--tradebook", os.path.join(TDIR, "tradebook-sample.csv"), "--lots", os.path.join(TDIR, "lots.csv"),
            "--fmv", os.path.join(TDIR, "fmv_2018.csv"), "--kite-dir", kite_dir, "--config", CFG, "--now", now]


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = lots.main(argv)
    return code, out.getvalue(), err.getvalue()


class Gains(unittest.TestCase):
    def test_every_year(self):
        code, text, _ = run(["gains"] + args())
        self.assertEqual(code, 0)
        for line in ("FY 2024-25", "FY 2025-26", "FY 2026-27",
                     "estimated tax: short term Rs 70 + long term Rs 0 = Rs 70",
                     "carried forward: speculative loss Rs 80 from 2024-25, usable until FY 2028-29",
                     "1 non-equity or non-NSE tradebook rows skipped",
                     "Not tax advice"):
            self.assertIn(line, text)

    def test_the_same_tradebook_twice_counts_once(self):
        once = run(["gains", "--json"] + args())[1]
        twice = run(["gains", "--json", "--tradebook", os.path.join(TDIR, "tradebook-sample.csv")] + args())[1]
        self.assertEqual(json.loads(once)["years"], json.loads(twice)["years"])

    def test_one_year_and_a_year_with_nothing(self):
        code, text, _ = run(["gains", "--fy", "2026-27", "--json"] + args())
        self.assertEqual(code, 0)
        self.assertEqual([y["fy"] for y in json.loads(text)["years"]], ["2026-27"])
        code, _, err = run(["gains", "--fy", "2019-20"] + args())
        self.assertEqual(code, 1)
        self.assertIn("no realised gains or losses in FY 2019-20", err)


class Report(unittest.TestCase):
    def test_open_lots(self):
        code, text, _ = run(["report"] + args())
        self.assertEqual(code, 0)
        self.assertIn("31 Jan 2018 price used as cost", text)
        self.assertRegex(text, r"TCS\s+2026-08-03\s+3\s+Rs 3,300\s+Rs 3,050.50\s+-Rs 748.50  short term, "
                               r"long term from 2027-08-04")
        self.assertNotIn("incomplete", text)

    def test_lots_that_do_not_match_kite_are_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            kd = os.path.join(d, "kite")
            shutil.copytree(KDIR, kd)
            with open(os.path.join(kd, "holdings.json")) as fh:
                doc = json.load(fh)
            doc["data"][0]["quantity"] = 9
            with open(os.path.join(kd, "holdings.json"), "w") as fh:
                json.dump(doc, fh)
            _, text, _ = run(["report"] + args(kd))
            self.assertIn("INFY: the trades give 8 shares but Kite holds 9", text)

    def test_stale_quotes(self):
        code, _, err = run(["report"] + args(now="2026-10-26T10:05"))
        self.assertEqual(code, 1)
        self.assertIn("quotes snapshot is", err)


class Sell(unittest.TestCase):
    def test_what_a_sale_would_realise(self):
        code, text, _ = run(["sell", "infy.ns", "3"] + args())
        self.assertEqual(code, 0)
        self.assertIn("3 INFY bought 2017-06-15 at Rs 1,150: long term Rs 1,387.50 (31 Jan 2018 price used)", text)
        code, _, err = run(["sell", "INFY", "20"] + args())
        self.assertEqual(code, 1)
        self.assertIn("you hold only 8 INFY", err)
        code, _, err = run(["sell", "WIPRO", "1"] + args())
        self.assertIn("no WIPRO held", err)

    def test_sell_shows_a_missing_2018_price(self):
        code, text, _ = run(["sell", "INFY", "3"] + args()[:4] + ["--fmv", os.path.join(TDIR, "none.csv")] + args()[6:])
        self.assertEqual(code, 0)
        self.assertIn("no 31 Jan 2018 price for INFY", text)


class Harvest(unittest.TestCase):
    def test_losses_and_long_term_headroom(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            code, text, _ = run(["harvest", "--min-loss", "500", "--write", out] + args())
            self.assertEqual(code, 0)
            self.assertIn("SELL 3 TCS at Rs 3,050.50: loss Rs 748.50", text)
            self.assertIn("SELL 8 INFY at Rs 1,612.50: long-term gain Rs 3,700", text)
            self.assertIn("no wash-sale rule", text)
            with open(out) as fh:
                doc = json.load(fh)
            self.assertIs(doc["live"], True)
            self.assertEqual([o["tradingsymbol"] for o in doc["orders"]], ["TCS"])
            code, text, _ = run(["harvest", "--min-loss", "500", "--include-gains", "--write", out] + args())
            with open(out) as fh:
                orders = json.load(fh)["orders"]
            self.assertEqual([(o["tradingsymbol"], o["quantity"]) for o in orders],
                             [("TCS", "3"), ("HDFCBANK", "4"), ("INFY", "6"), ("RELIANCE", "2")])
            self.assertIn("INFY: selling 6 of 8 now keeps the order under your Rs 10,000 max order", text)
            self.assertEqual(orders[2]["why"], "book Rs 2,775 of long-term gain inside the yearly exemption")

    def test_nothing_to_harvest(self):
        code, text, _ = run(["harvest", "--min-loss", "5000"] + args())
        self.assertIn("No position would book a loss of Rs 5,000 or more", text)

    def test_a_harvest_sell_passes_the_risk_check(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            run(["harvest", "--min-loss", "500", "--write", out] + args())
            with open(out) as fh:
                orders = json.load(fh)["orders"]
        now = check.nse_calendar.parse_now(NOW)
        data = check.load_data(KDIR, now)
        data.update(positions={"net": [], "day": []}, orders=[],
                    margins={"equity": {"net": 50000.0, "available": {"live_balance": 50000.0}}})
        cal = check.nse_calendar.Calendar(dict(check.nse_calendar.HOLIDAYS), check.nse_calendar.YEARS)
        with open(CFG) as fh:
            res = check.check(orders, json.load(fh), data, now, cal)
        self.assertEqual([r["verdict"] for r in res["results"]], ["PASS"], res["results"])


class Inputs(unittest.TestCase):
    def test_no_trades_explains_where_to_get_them(self):
        with tempfile.TemporaryDirectory() as d:
            here = os.getcwd()
            os.chdir(d)
            try:
                code, _, err = run(["gains", "--kite-dir", os.path.join(d, "kite"), "--now", NOW])
            finally:
                os.chdir(here)
        self.assertEqual(code, 1)
        self.assertIn("Zerodha Console tradebook", err)

    def test_missing_kite_trades_is_a_note(self):
        with tempfile.TemporaryDirectory() as d:
            _, text, _ = run(["gains"] + args(os.path.join(d, "kite")))
        self.assertIn("today's Kite trades are not included", text)
        self.assertNotIn("FY 2026-27\n  short term: gains Rs 0, losses Rs 0, net after set-off Rs 0\n  long term:  "
                         "gains Rs 1,000", text)


if __name__ == "__main__":
    unittest.main()
