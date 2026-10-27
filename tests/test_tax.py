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
            # The TCS short-term loss (Rs 748.50) would only offset this FY's Rs 1,000 long-term gain, which is
            # inside the exemption anyway: it saves no tax and nothing carries forward, so it is not proposed.
            code, text, _ = run(["harvest", "--min-loss", "500", "--write", out] + args())
            self.assertEqual(code, 0)
            self.assertIn("No loss of Rs 500 or more is worth booking this year", text)
            self.assertIn("TCS: booking this loss saves no tax this year", text)
            self.assertIn("SELL 6 INFY at Rs 1,612.50: long-term gain Rs 2,775", text)
            self.assertIn("no wash-sale rule", text)
            self.assertFalse(os.path.exists(out))
            code, text, _ = run(["harvest", "--min-loss", "500", "--include-gains", "--write", out] + args())
            with open(out) as fh:
                doc = json.load(fh)
            self.assertIs(doc["live"], True)
            orders = doc["orders"]
            self.assertEqual([(o["tradingsymbol"], o["quantity"]) for o in orders],
                             [("HDFCBANK", "4"), ("INFY", "6"), ("RELIANCE", "2")])
            self.assertIn("INFY: selling 6 of 8 now keeps the order under your Rs 10,000 max order", text)
            self.assertEqual(orders[1]["why"],
                             "book Rs 2,775 of long-term gain: no tax this year and no carried loss used up")

    def test_nothing_to_harvest(self):
        code, text, _ = run(["harvest", "--min-loss", "5000"] + args())
        self.assertIn("No position would book a loss of Rs 5,000 or more", text)

    def test_a_harvest_sell_passes_the_risk_check(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            run(["harvest", "--min-loss", "500", "--include-gains", "--write", out] + args())
            with open(out) as fh:
                orders = json.load(fh)["orders"]
        now = check.nse_calendar.parse_now(NOW)
        data = check.load_data(KDIR, now)
        data.update(positions={"net": [], "day": []}, orders=[],
                    margins={"equity": {"net": 50000.0, "available": {"live_balance": 50000.0}}})
        cal = check.nse_calendar.Calendar(dict(check.nse_calendar.HOLIDAYS), check.nse_calendar.YEARS)
        with open(CFG) as fh:
            res = check.check(orders, json.load(fh), data, now, cal)
        self.assertEqual([r["verdict"] for r in res["results"]], ["PASS"] * 3, res["results"])


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
    with open(os.path.join(kd, "orders.json"), "w") as fh:
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
                         [("6", "book a Rs 6,000 loss (Rs 6,000 carries forward)")])
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
        # The cut ABC sale would book a gain, so it is not proposed and uses no exemption: XYZ's Rs 1,000
        # long-term gain still fits.
        self.assertEqual([(o["tradingsymbol"], o["quantity"]) for o in orders], [("XYZ", "10")])
        self.assertIn("ABC: selling only 33 of 2000", text)
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



STAMP = "2026-10-26T10:00:00+05:30"


def snap(kd, kind, data, stamp=STAMP):
    with open(os.path.join(kd, kind + ".json"), "w") as fh:
        json.dump({"fetched_at": stamp, "data": data}, fh)


def book_inputs(d, rows, prices, today=(), holdings=None, orders=(), positions=None, cfg=None, trades_stamp=STAMP):
    """Temp inputs. rows: Console tradebook [(sym, date, side, qty, price)]; today: Kite trades
    [(sym, side, qty, price)]; holdings default to the net of rows and today; orders=None leaves out
    orders.json, holdings=False leaves out holdings.json. Returns the common args."""
    tb = os.path.join(d, "tb.csv")
    with open(tb, "w") as fh:
        fh.write(HEAD)
        for i, (sym, day, side, qty, price) in enumerate(rows):
            fh.write("%s,INE000A01010,%s,NSE,EQ,EQ,%s,false,%d,%.6f,T%d,O%d,%sT10:00:00\n"
                     % (sym, day, side.lower(), qty, price, i, i, day))
    kd = os.path.join(d, "kite")
    os.makedirs(kd)
    snap(kd, "quotes", {"NSE:" + s: {"last_price": p} for s, p in prices.items()})
    snap(kd, "trades", [{"trade_id": "K%d" % i, "order_id": "OK%d" % i, "exchange": "NSE", "tradingsymbol": s,
                         "product": "CNC", "transaction_type": side, "quantity": q, "average_price": p,
                         "fill_timestamp": "2026-10-26 09:30:00"} for i, (s, side, q, p) in enumerate(today)],
         trades_stamp)
    if holdings is None:
        holdings = {}
        for sym, _, side, qty, _ in rows:
            holdings[sym] = holdings.get(sym, 0) + (qty if side.upper() == "BUY" else -qty)
        for sym, side, qty, _ in today:
            holdings[sym] = holdings.get(sym, 0) + (qty if side.upper() == "BUY" else -qty)
    if holdings is not False:
        snap(kd, "holdings", [{"tradingsymbol": s, "exchange": "NSE", "quantity": q, "t1_quantity": 0}
                              for s, q in sorted(holdings.items()) if q])
    if orders is not None:
        snap(kd, "orders", list(orders))
    if positions is not None:
        snap(kd, "positions", {"net": positions, "day": []})
    with open(CFG) as fh:
        c = json.load(fh)
    c.update(cfg or {})
    cp = os.path.join(d, "config.json")
    with open(cp, "w") as fh:
        json.dump(c, fh)
    return ["--tradebook", tb, "--lots", os.path.join(d, "none.csv"), "--fmv", os.path.join(d, "none2.csv"),
            "--kite-dir", kd, "--config", cp, "--now", NOW]


def harvest_json(argv):
    code, text, err = run(["harvest", "--json"] + argv)
    return code, (json.loads(text) if text.strip() else None), err


class RealTaxEffect(unittest.TestCase):
    """I1: a harvest order's stated effect comes from india_tax with the full set-off."""

    def test_a_carried_loss_blocks_a_long_term_gain_sale(self):
        with tempfile.TemporaryDirectory() as d:
            argv = book_inputs(d, [("AAA", "2023-01-02", "BUY", 100, 2000), ("AAA", "2025-06-02", "SELL", 100, 1000),
                                   ("BBB", "2024-01-02", "BUY", 100, 1000)], {"BBB": 2000},
                               cfg={"max_order_value": "500000"})
            _, res, _ = harvest_json(["--include-gains", "--min-loss", "500"] + argv)
        self.assertEqual(res["orders"], [])
        self.assertEqual(res["gains"], [])
        self.assertIn("BBB: a long-term gain now would use up Rs 1,00,000 of loss that is worth more later; "
                      "not proposed", res["notes"])

    def test_a_loss_that_only_offsets_exempt_gains_is_not_proposed(self):
        with tempfile.TemporaryDirectory() as d:
            argv = book_inputs(d, [("CCC", "2024-01-02", "BUY", 100, 1000), ("CCC", "2026-05-04", "SELL", 100, 1500),
                                   ("DDD", "2026-06-01", "BUY", 10, 1000)], {"DDD": 800})
            _, res, _ = harvest_json(["--min-loss", "500"] + argv)
        self.assertEqual(res["orders"], [])
        self.assertEqual(res["losses"], [])
        self.assertIn("DDD: booking this loss saves no tax this year (it would only offset gains already inside "
                      "the exemption) and nothing would carry forward; not proposed", res["notes"])

    def test_two_competing_losses_claim_one_saving(self):
        with tempfile.TemporaryDirectory() as d:
            argv = book_inputs(d, [("CCC", "2024-01-02", "BUY", 100, 1000), ("CCC", "2026-05-04", "SELL", 100, 2350),
                                   ("DDD", "2026-06-01", "BUY", 10, 2000), ("EEE", "2026-06-01", "BUY", 10, 2000)],
                               {"DDD": 1000, "EEE": 1000}, cfg={"max_order_value": "500000"})
            _, res, _ = harvest_json(["--min-loss", "500"] + argv)
        self.assertEqual([(o["tradingsymbol"], o["why"]) for o in res["orders"]],
                         [("DDD", "book a Rs 10,000 loss (saves about Rs 1,250 this year)")])
        self.assertEqual([(c["symbol"], c["saves"]) for c in res["losses"]], [("DDD", 1250.0)])
        self.assertIn("EEE: booking this loss saves no tax this year (it would only offset gains already inside "
                      "the exemption) and nothing would carry forward; not proposed", res["notes"])

    def test_two_losses_that_both_help_claim_the_true_combined_saving(self):
        with tempfile.TemporaryDirectory() as d:
            argv = book_inputs(d, [("CCC", "2026-05-01", "BUY", 100, 1000), ("CCC", "2026-05-04", "SELL", 100, 1300),
                                   ("DDD", "2026-06-01", "BUY", 10, 2000), ("EEE", "2026-06-01", "BUY", 10, 2000)],
                               {"DDD": 1000, "EEE": 1000}, cfg={"max_order_value": "500000"})
            _, res, _ = harvest_json(["--min-loss", "500"] + argv)
        self.assertEqual([(o["tradingsymbol"], o["why"]) for o in res["orders"]],
                         [("DDD", "book a Rs 10,000 loss (saves about Rs 2,000 this year)"),
                          ("EEE", "book a Rs 10,000 loss (saves about Rs 2,000 this year)")])
        self.assertEqual(sum(c["saves"] for c in res["losses"]), 4000.0)

    def test_a_loss_against_short_term_gain_states_the_saving(self):
        with tempfile.TemporaryDirectory() as d:
            argv = book_inputs(d, [("EEE", "2026-05-01", "BUY", 100, 100), ("EEE", "2026-06-01", "SELL", 100, 200),
                                   ("FFF", "2026-06-01", "BUY", 10, 1000)], {"FFF": 500})
            code, res, _ = harvest_json(["--min-loss", "500"] + argv)
        self.assertEqual(code, 0)
        self.assertEqual([(o["tradingsymbol"], o["quantity"], o["why"]) for o in res["orders"]],
                         [("FFF", "10", "book a Rs 5,000 loss (saves about Rs 1,000 this year)")])

    def test_a_loss_that_saves_tax_and_carries_forward(self):
        with tempfile.TemporaryDirectory() as d:
            argv = book_inputs(d, [("EEE", "2026-05-01", "BUY", 100, 100), ("EEE", "2026-06-01", "SELL", 100, 200),
                                   ("FFF", "2026-06-01", "BUY", 20, 1000)], {"FFF": 400})
            _, res, _ = harvest_json(["--min-loss", "500"] + argv)
        self.assertEqual([o["why"] for o in res["orders"]],
                         ["book a Rs 12,000 loss (saves about Rs 2,000 this year, Rs 2,000 carries forward)"])

    def test_a_cut_loss_order_that_nets_zero_is_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            argv = book_inputs(d, [("ABC", "2026-01-02", "BUY", 10, 1500), ("ABC", "2026-06-01", "BUY", 10, 2500)],
                               {"ABC": 1500})
            _, res, _ = harvest_json(["--min-loss", "0"] + argv)
        self.assertEqual(res["orders"], [])
        self.assertFalse(any("Rs 0 loss" in n for n in res["notes"]))
        self.assertIn("ABC: booking this loss saves no tax this year (it would only offset gains already inside "
                      "the exemption) and nothing would carry forward; not proposed", res["notes"])

    def test_a_gain_sale_is_cut_to_leave_the_tax_unchanged(self):
        # 1,20,000 of long-term gain already this FY: only 5,000 of exemption left, so 50 GGG shares (Rs 100 each)
        with tempfile.TemporaryDirectory() as d:
            argv = book_inputs(d, [("CCC", "2024-01-02", "BUY", 100, 1000), ("CCC", "2026-05-04", "SELL", 100, 2200),
                                   ("GGG", "2024-01-02", "BUY", 100, 100)], {"GGG": 200})
            _, res, _ = harvest_json(["--include-gains", "--min-loss", "500"] + argv)
        self.assertEqual([(o["tradingsymbol"], o["quantity"], o["why"]) for o in res["orders"]],
                         [("GGG", "50", "book Rs 5,000 of long-term gain: no tax this year and no carried loss "
                                        "used up")])


class TodaysTrades(unittest.TestCase):
    """I2 and I3: a sale today is matched intraday first, and only today's Kite trades count."""

    def test_selling_shares_bought_today_is_intraday(self):
        with tempfile.TemporaryDirectory() as d:
            argv = book_inputs(d, [("X", "2024-01-02", "BUY", 10, 100)], {"X": 140}, today=[("X", "BUY", 10, 150)])
            code, text, err = run(["sell", "X", "10", "--json"] + argv)
        self.assertEqual(code, 0, err)
        self.assertEqual([(g["kind"], g["qty"], g["gain"]) for g in json.loads(text)["gains"]],
                         [("SPECULATIVE", 10, -100.0)])

    def test_harvest_sale_of_shares_bought_today_is_intraday(self):
        with tempfile.TemporaryDirectory() as d:
            argv = book_inputs(d, [("X", "2026-06-01", "BUY", 10, 100)], {"X": 50}, today=[("X", "BUY", 10, 150)],
                               holdings={"X": 10}, positions=[{"tradingsymbol": "X", "product": "CNC",
                                                               "quantity": 10}])
            _, res, _ = harvest_json(["--min-loss", "500"] + argv)
        self.assertEqual([(c["symbol"], c["qty"], c["by_term"]) for c in res["losses"]],
                         [("X", 20, {"STCG": -500.0, "LTCG": 0.0, "SPECULATIVE": -1000.0})])

    def test_a_trades_snapshot_from_yesterday_is_not_included(self):
        with tempfile.TemporaryDirectory() as d:
            argv = book_inputs(d, [("X", "2024-01-02", "BUY", 10, 100)], {"X": 140}, today=[("X", "SELL", 4, 150)],
                               trades_stamp="2026-10-25T15:40:00+05:30")
            code, text, _ = run(["report", "--json"] + argv)
        self.assertEqual(code, 0)
        doc = json.loads(text)
        self.assertEqual([r["lot"]["qty"] for r in doc["lots"]], [10])
        self.assertIn("today's Kite trades are not included (the snapshot is from 2026-10-25)", doc["notes"])

    def test_harvest_skips_a_symbol_with_an_open_order(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            argv = book_inputs(d, [("ABC", "2026-06-01", "BUY", 4, 2500)], {"ABC": 1500},
                               orders=[{"tradingsymbol": "ABC", "status": "OPEN"},
                                       {"tradingsymbol": "ZZZ", "status": "COMPLETE"}])
            _, res, _ = harvest_json(["--min-loss", "500", "--write", out] + argv)
            self.assertFalse(os.path.exists(out))
        self.assertEqual(res["orders"], [])
        self.assertIn("ABC has an open order in Kite: skipped", res["notes"])

    def test_harvest_write_needs_a_fresh_orders_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            with open(out, "w") as fh:
                fh.write("{}")
            argv = book_inputs(d, [("ABC", "2026-06-01", "BUY", 4, 2500)], {"ABC": 1500}, orders=None)
            code, _, err = run(["harvest", "--min-loss", "500", "--write", out] + argv)
            self.assertEqual(code, 1)
            self.assertIn("harvest --write needs a fresh Kite orders snapshot", err)
            self.assertFalse(os.path.exists(out))
            code, text, _ = run(["harvest", "--min-loss", "500"] + argv)
        self.assertEqual(code, 0)
        self.assertIn("could not check Kite's open orders", text)
        self.assertIn("SELL 4 ABC", text)


class FinalMinors(unittest.TestCase):
    def test_any_error_under_write_removes_the_old_orders_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            with open(out, "w") as fh:
                json.dump({"created_by": "trader-rebalance", "orders": []}, fh)
            code, _, err = run(["harvest", "--write", out] + args(now="2026-10-26T10:05"))
            self.assertEqual(code, 1)
            self.assertIn("quotes snapshot is", err)
            self.assertFalse(os.path.exists(out))
            self.assertIn("Removed the old %s (proposals from trader-rebalance)" % out, err)

    def test_removing_the_old_file_names_who_wrote_it(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "orders.json")
            with open(out, "w") as fh:
                json.dump({"created_by": "trader-rebalance", "orders": []}, fh)
            _, text, _ = run(["harvest", "--min-loss", "99999", "--write", out]
                             + abc_inputs(d, [("2026-06-01", 10, 2500)], 1500))
            self.assertFalse(os.path.exists(out))
        self.assertIn("Removed the old %s (proposals from trader-rebalance): nothing to propose." % out, text)

    def test_todays_delivery_trades_count_in_the_holdings_check(self):
        rows = [("ABC", "2026-06-01", "BUY", 4, 2500)]
        today = [("ABC", "BUY", 2, 2400)]
        pos = [{"tradingsymbol": "ABC", "product": "CNC", "quantity": 2},
               {"tradingsymbol": "ABC", "product": "MIS", "quantity": 7}]
        with tempfile.TemporaryDirectory() as d:
            _, res, _ = harvest_json(["--min-loss", "500"]
                                     + book_inputs(d, rows, {"ABC": 1500}, today=today, holdings={"ABC": 4},
                                                   positions=pos))
        self.assertEqual([(c["symbol"], c["qty"]) for c in res["losses"]], [("ABC", 6)])
        self.assertNotIn("today's delivery trades are not checked (no positions snapshot)", res["notes"])
        with tempfile.TemporaryDirectory() as d:
            _, res, _ = harvest_json(["--min-loss", "500"]
                                     + book_inputs(d, rows, {"ABC": 1500}, today=today, holdings={"ABC": 4}))
        self.assertEqual(res["losses"], [])
        self.assertIn("today's delivery trades are not checked (no positions snapshot)", res["notes"])
        with tempfile.TemporaryDirectory() as d:
            _, text, _ = run(["report"] + book_inputs(d, rows, {"ABC": 1500}, today=today, holdings={"ABC": 4}))
        self.assertIn("today's delivery trades are not checked (no positions snapshot)", text)

    def test_blocked_symbols_are_never_harvested(self):
        with tempfile.TemporaryDirectory() as d:
            _, res, _ = harvest_json(["--min-loss", "500"]
                                     + book_inputs(d, [("ABC", "2026-06-01", "BUY", 4, 2500)], {"ABC": 1500},
                                                   cfg={"blocked": ["abc.ns"]}))
        self.assertEqual(res["orders"], [])
        self.assertIn("ABC is on your blocked list: skipped", res["notes"])

    def test_a_held_symbol_without_a_quote_is_noted(self):
        with tempfile.TemporaryDirectory() as d:
            _, res, _ = harvest_json(["--min-loss", "500"]
                                     + book_inputs(d, [("ABC", "2026-06-01", "BUY", 4, 2500),
                                                       ("XYZ", "2026-06-01", "BUY", 4, 2500)], {"ABC": 1500}))
        self.assertEqual([o["tradingsymbol"] for o in res["orders"]], ["ABC"])
        self.assertIn("XYZ: no Kite quote, skipped", res["notes"])


if __name__ == "__main__":
    unittest.main()
