import datetime
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

cc = load("trader-copycat", "copycat")
shp = cc.shp
amc = cc.amc
size = load("trader-budget", "size")

CDIR = os.path.join(FIX, "trader-copycat")
SYMS = os.path.join(FIX, "trader-alerts", "EQUITY_L-sample.csv")
NOW = "2026-10-27T10:00"
TITAN_Q2 = "SHP_1738880_15102026035926_WEB.xml"
NCC_Q2 = "SHP_1733674_07102026121837_WEB.xml"
OCT = os.path.join(CDIR, "fund-oct.csv")
SEP = os.path.join(CDIR, "fund-sep.csv")


def read(name):
    with open(os.path.join(CDIR, name), encoding="utf-8") as fh:
        return fh.read()


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cc.main(argv)
    return code, out.getvalue(), err.getvalue()


class Shareholding(unittest.TestCase):
    def test_titan_two_accounts_add_up(self):
        doc = shp.parse(read(TITAN_Q2))
        self.assertEqual((doc["symbol"], doc["quarter"], doc["total_shares"]),
                         ("TITAN", datetime.date(2026, 9, 30), 887786160))
        h = shp.holding(doc, "Rekha Jhunjhunwala")
        self.assertEqual((h["shares"], h["pct"], h["names"]), (47184470, 5.31, ["REKHA JHUNJHUNWALA"]))

    def test_persons_acting_in_concert_are_not_counted_twice(self):
        h = shp.holding(shp.parse(read(NCC_Q2)), "rekha jhunjhunwala")
        self.assertEqual((h["shares"], h["pct"]), (66733266 + 11600000, 12.48))

    def test_name_matching(self):
        self.assertTrue(shp.matches("Rakesh Jhunjhunwala", "Estate of Late Mr.Rakesh Jhunjhunwala"))
        self.assertFalse(shp.matches("Rekha Jhunjhunwala", "Rajesh Kumar Radheshyam Jhunjhunwala"))
        self.assertFalse(shp.matches("", "Anyone"))

    def test_master_newest_first_and_errors(self):
        got = shp.parse_master(json.loads(read("shp-TITAN.json")), "TITAN")
        self.assertEqual([g["quarter"] for g in got], [datetime.date(2026, 9, 30), datetime.date(2026, 6, 30)])
        with self.assertRaises(shp.ShpError):
            shp.parse_master({"data": []}, "TITAN")
        with self.assertRaises(shp.ShpError):
            shp.parse("<html>blocked")

    def test_quarter_changes(self):
        h = lambda n: {"shares": n}
        self.assertEqual([shp.change(h(5), None), shp.change(None, h(5)), shp.change(h(6), h(5)),
                          shp.change(h(4), h(5)), shp.change(h(5), h(5))],
                         ["new", "gone", "added", "trimmed", "same"])


class FundSheet(unittest.TestCase):
    def test_october_sheet(self):
        rows = {r["isin"]: r for r in amc.parse(read("fund-oct.csv"))}
        self.assertEqual(len(rows), 6)
        infy = rows["INE009A01021"]
        self.assertEqual((round(infy["pct"], 2), infy["quantity"]), (5.0, 4200000.0))
        for skipped in ("US02079K3059", "INE040A08AB1"):
            self.assertNotIn(skipped, rows)

    def test_equity_isins(self):
        self.assertEqual([amc.is_equity(i) for i in ("INE009A01021", "INE040A08AB1", "US02079K3059", "", "INE009A0102")],
                         [True, False, False, False, False])

    def test_fractions_become_percent_and_no_quantity_compares_pct(self):
        rows = amc.parse("Company Name,ISIN,% of NAV\nInfosys,INE009A01021,0.06\nTCS,INE467B01029,0.04\n")
        self.assertEqual([r["pct"] for r in rows], [6.0, 4.0])
        self.assertEqual(amc.change(rows[0], dict(rows[0], pct=5.0)), "added")

    def test_not_a_portfolio_sheet(self):
        with self.assertRaises(amc.AmcError):
            amc.parse("Date,Symbol,Price\n2026-10-01,INFY,1500\n")


class Investor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.prices = os.path.join(self.tmp.name, "prices.json")
        self.out = os.path.join(self.tmp.name, "targets.json")
        self.price({"TITAN": 3400.0, "CRISIL": 5100.0, "NCC": 290.0})

    def tearDown(self):
        self.tmp.cleanup()

    def price(self, p):
        with open(self.prices, "w") as fh:
            json.dump({"as_of": "2026-10-27T15:30:00+05:30", "prices": p}, fh)

    def cc(self, *args):
        return run(["investor", "Rekha Jhunjhunwala", "--offline", CDIR, "--prices", self.prices, "--now", NOW]
                   + list(args))

    def test_weights_by_holding_value_and_budget_reads_them(self):
        code, text, _ = self.cc("--symbols", "TITAN", "CRISIL", "NCC", "--write", self.out)
        self.assertEqual(code, 0)
        self.assertIn("NCC         7,83,33,266 shares  12.48% of the company  same", text)
        with open(self.out) as fh:
            doc = json.load(fh)
        self.assertEqual(doc["kind"], "investor")
        self.assertEqual([(w["symbol"], w["weight"]) for w in doc["weights"]],
                         [("TITAN", 79.22), ("NCC", 11.22), ("CRISIL", 9.57)])
        self.assertIn("partial portfolio", doc["method"])
        self.assertEqual([r["ticker"] for r in size.parse_weights(doc)], ["TITAN", "NCC", "CRISIL"])

    def test_someone_not_named(self):
        code, text, _ = run(["investor", "Radhakishan Damani", "--symbols", "TITAN", "--offline", CDIR,
                             "--prices", self.prices, "--now", NOW])
        self.assertEqual(code, 0)
        self.assertIn("TITAN      not named (holds under 1%, or none)", text)
        self.assertIn("nobody named 'Radhakishan Damani' in any of these patterns", text)

    def test_missing_price_refuses_to_write(self):
        self.price({"TITAN": 3400.0})
        code, text, _ = self.cc("--symbols", "TITAN", "NCC", "--write", self.out)
        self.assertEqual(code, 2)
        self.assertIn("no price for NCC", text)
        self.assertIn("not written: no price for NCC", text)
        self.assertFalse(os.path.exists(self.out))

    def test_partial_read_refuses_to_write(self):
        code, text, _ = self.cc("--symbols", "TITAN", "INFY", "--write", self.out)
        self.assertEqual(code, 2)
        self.assertIn("error: INFY: cannot read", text)
        self.assertIn("not written: 1 stock(s) could not be read", text)
        self.assertFalse(os.path.exists(self.out))


class Fund(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.tmp.name, "targets.json")

    def tearDown(self):
        self.tmp.cleanup()

    def cc(self, *args):
        return run(["fund", "Example Flexi Cap", "--file", OCT, "--previous", SEP, "--symbols-file", SYMS,
                    "--now", "2026-11-05T10:00", "--write", self.out] + list(args))

    def test_top_four_with_changes(self):
        code, text, _ = self.cc("--top", "4")
        self.assertEqual(code, 0)
        for line in ("HDFCBANK     8.12% of NAV  added     weight 42.74", "INFY         5.00% of NAV  trimmed",
                     "M&M          2.49% of NAV  new", "TCS          0.00% of NAV  sold"):
            self.assertIn(line, text)
        with open(self.out) as fh:
            doc = json.load(fh)
        self.assertEqual([(w["symbol"], w["weight"]) for w in doc["weights"]],
                         [("HDFCBANK", 42.74), ("INFY", 26.32), ("RELIANCE", 17.84), ("M&M", 13.11)])
        self.assertAlmostEqual(sum(r["weight"] for r in size.parse_weights(doc)), 100, delta=0.05)

    def test_unlisted_stock_inside_the_top_refuses_to_write(self):
        code, text, _ = self.cc("--top", "5")
        self.assertEqual(code, 2)
        self.assertIn("not written: ITC Limited would be in the copied holdings", text)
        self.assertFalse(os.path.exists(self.out))

    def test_missing_symbol_list(self):
        code, _, err = run(["fund", "X", "--file", OCT, "--symbols-file", os.path.join(self.tmp.name, "none.csv"),
                            "--now", NOW])
        self.assertEqual(code, 2)
        self.assertIn("nse_symbols.py refresh", err)


class Network(unittest.TestCase):
    def test_symbol_is_encoded_and_a_block_page_is_forgotten(self):
        master = json.loads(read("shp-TITAN.json"))

        class Client:
            urls, forgot = [], []

            def get_json(self, url, cache=True):
                self.urls.append(url)
                return master

            def get_text(self, url, cookie=True, cache=True):
                return "<html>Access Denied"

            def forget(self, url):
                self.forgot.append(url)
        c = Client()
        rows, absent, errors, blocked = cc.investor("Rekha Jhunjhunwala", ["M&M"], c)
        self.assertTrue(c.urls[0].endswith("symbol=M%26M"))
        self.assertEqual((rows, len(errors), len(c.forgot)), ([], 1, 1))

    def test_blocked_names_the_offline_fallback(self):
        class Client:
            def get_json(self, url, cache=True):
                raise cc.nse.NseBlocked(url, "HTTP 403")
        rows, absent, errors, blocked = cc.investor("Rekha Jhunjhunwala", ["TITAN"], Client())
        self.assertIn("--offline", blocked[0])
        self.assertIn("symbol=TITAN", blocked[0])


if __name__ == "__main__":
    unittest.main()
