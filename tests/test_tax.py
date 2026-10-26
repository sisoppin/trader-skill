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


HEAD = ("symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,trade_id,order_id,"
        "order_execution_time\n")


def abc_inputs(d, buys, price, held=None, holdings=True):
    """Temp tradebook + kite dir for one symbol ABC: buys is [(date, qty, price)]. Returns the common args."""
    tb = os.path.join(d, "tb.csv")
    with open(tb, "w") as fh:
        fh.write(HEAD)
        for i, (day, qty, cost) in enumerate(buys):
            fh.write("ABC,INE000A01010,%s,NSE,EQ,EQ,buy,false,%d.000000,%.6f,T%d,O%d,%sT10:00:00\n"
                     % (day, qty, cost, i, i, day))
    kd = os.path.join(d, "kite")
    os.makedirs(kd)
    stamp = "2026-10-26T10:00:00+05:30"
    with open(os.path.join(kd, "quotes.json"), "w") as fh:
        json.dump({"fetched_at": stamp, "data": {"NSE:ABC": {"last_price": price}}}, fh)
    with open(os.path.join(kd, "trades.json"), "w") as fh:
        json.dump({"fetched_at": stamp, "data": []}, fh)
    if holdings:
        qty = held if held is not None else sum(b[1] for b in buys)
        with open(os.path.join(kd, "holdings.json"), "w") as fh:
            json.dump({"fetched_at": stamp, "data": [{"tradingsymbol": "ABC", "exchange": "NSE", "quantity": qty,
                                                      "t1_quantity": 0, "last_price": price}]}, fh)
    return ["--tradebook", tb, "--lots", os.path.join(d, "none.csv"), "--fmv", os.path.join(d, "none2.csv"),
            "--kite-dir", kd, "--config", CFG, "--now", NOW]


class HarvestSafety(unittest.TestCase):
    def harvest(self, buys, price, extra=(), **kw):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            code, text, err = run(["harvest", "--min-loss", "500", "--write", out] + list(extra)
                                  + abc_inputs(d, buys, price, **kw))
            orders = None
            if os.path.exists(out):
                with open(out) as fh:
                    orders = json.load(fh)["orders"]
        return code, text, err, orders

    def test_a_cut_order_that_would_book_a_gain_is_not_proposed(self):
        _, text, _, orders = self.harvest([("2024-01-02", 10, 1000), ("2026-06-01", 10, 2500)], 1500)
        self.assertIsNone(orders)
        self.assertIn("ABC: selling only 6 of 20", text)
        self.assertIn("would book a gain", text)

    def test_a_cut_order_states_the_real_loss(self):
        _, text, _, orders = self.harvest([("2026-06-01", 10, 2500)], 1500)
        self.assertEqual([(o["quantity"], o["why"]) for o in orders],
                         [("6", "book a Rs 6,000 loss (trader-tax harvest)")])
        self.assertIn("Proposed LIVE orders:", text)
        self.assertIn("book a Rs 6,000 loss", text)

    def test_one_share_dearer_than_the_max_order(self):
        _, text, _, orders = self.harvest([("2026-06-01", 10, 25000)], 12000)
        self.assertIsNone(orders)
        self.assertIn("ABC: one share costs more than your max order; not proposed", text)
        self.assertNotIn("selling 0 of", text)

    def test_one_symbol_never_gets_a_loss_and_a_gain_sell(self):
        _, _, _, orders = self.harvest([("2024-01-02", 10, 100), ("2026-06-01", 10, 300)], 150,
                                       extra=["--include-gains"])
        self.assertEqual([(o["tradingsymbol"], o["quantity"]) for o in orders], [("ABC", "20")])

    def test_nothing_to_propose_removes_the_old_orders_file(self):
        for extra in ([], ["--json"]):
            with tempfile.TemporaryDirectory() as d:
                out = os.path.join(d, "orders.json")
                with open(out, "w") as fh:
                    fh.write("{}")
                _, text, _ = run(["harvest", "--min-loss", "99999", "--write", out] + extra
                                 + abc_inputs(d, [("2026-06-01", 10, 2500)], 1500))
                self.assertFalse(os.path.exists(out))
                if not extra:
                    self.assertIn("Removed the old %s: nothing to propose." % out, text)

    def test_lots_that_do_not_match_kite_are_skipped(self):
        _, text, _, orders = self.harvest([("2026-06-01", 20, 2500)], 1500, held=35)
        self.assertIsNone(orders)
        self.assertIn("ABC skipped: the trades give 20 shares but Kite holds 35, so the oldest-first tax "
                      "figures would be wrong", text)
        self.assertNotIn("SELL 20 ABC", text)

    def test_write_needs_a_fresh_holdings_snapshot(self):
        _, _, err, orders = self.harvest([("2026-06-01", 10, 2500)], 1500, holdings=False)
        self.assertIn("needs a fresh Kite holdings snapshot", err)
        self.assertIsNone(orders)
        with tempfile.TemporaryDirectory() as d:
            code, text, _ = run(["harvest", "--min-loss", "500"] + abc_inputs(d, [("2026-06-01", 10, 2500)], 1500,
                                                                              holdings=False))
        self.assertEqual(code, 0)
        self.assertIn("could not check the lots", text)

    def test_headroom_used_up_by_a_loss_sale_never_gives_a_negative_order(self):
        with tempfile.TemporaryDirectory() as d:
            argv = abc_inputs(d, [("2024-01-02", 1000, 100), ("2026-06-01", 1000, 600)], 300)
            with open(os.path.join(d, "tb.csv"), "a") as fh:
                fh.write("XYZ,INE000A01011,2024-01-02,NSE,EQ,EQ,buy,false,10.000000,100.000000,TX,OX,"
                         "2024-01-02T10:00:00\n")
            for name, row in (("quotes", None), ("holdings", None)):
                path = os.path.join(d, "kite", name + ".json")
                with open(path) as fh:
                    doc = json.load(fh)
                if name == "quotes":
                    doc["data"]["NSE:XYZ"] = {"last_price": 200}
                else:
                    doc["data"].append({"tradingsymbol": "XYZ", "exchange": "NSE", "quantity": 10,
                                        "t1_quantity": 0, "last_price": 200})
                with open(path, "w") as fh:
                    json.dump(doc, fh)
            out = os.path.join(d, "orders.json")
            _, text, _ = run(["harvest", "--min-loss", "500", "--include-gains", "--write", out] + argv)
            orders = []
            if os.path.exists(out):
                with open(out) as fh:
                    orders = json.load(fh)["orders"]
        self.assertTrue(all(int(o["quantity"]) >= 1 for o in orders), orders)
        self.assertNotIn("XYZ", [o["tradingsymbol"] for o in orders])
        self.assertNotIn("SELL -", text)

    def test_a_refused_write_removes_the_old_orders_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            with open(out, "w") as fh:
                fh.write("{}")
            code, _, err = run(["harvest", "--write", out] + abc_inputs(d, [("2026-06-01", 10, 2500)], 1500,
                                                                         holdings=False))
            self.assertEqual(code, 1)
            self.assertIn("needs a fresh Kite holdings snapshot", err)
            self.assertFalse(os.path.exists(out))

    def test_break_even_is_not_a_loss(self):
        with tempfile.TemporaryDirectory() as d:
            _, text, _ = run(["harvest", "--min-loss", "0", "--json"] + abc_inputs(d, [("2026-06-01", 10, 1500)], 1500))
        self.assertEqual(json.loads(text)["losses"], [])

    def test_a_negative_min_loss_is_refused(self):
        code, _, err = run(["harvest", "--min-loss", "-1"] + args())
        self.assertEqual(code, 1)
        self.assertIn("--min-loss", err)


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
