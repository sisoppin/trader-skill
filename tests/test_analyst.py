import datetime
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

res = load("trader-analyst", "results")
screen = load("trader-screener", "screen")

ADIR = os.path.join(FIX, "trader-analyst")
NOW = "2026-10-27T10:00"
INFY_Q2 = "INTEGRATED_FILING_INDAS_1745058_23102026082117_WEB.xml"
BANK = "INTEGRATED_FILING_BANKING_1740912_17102026054806_WEB.xml"


def read(name):
    with open(os.path.join(ADIR, name), encoding="utf-8") as fh:
        return fh.read()


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = res.main(argv)
    return code, out.getvalue(), err.getvalue()


class Xbrl(unittest.TestCase):
    def test_infy_quarter(self):
        f = res.parse_xbrl(read(INFY_Q2))
        self.assertEqual(f["period_end"], datetime.date(2026, 9, 30))
        q = res.figures(f)
        self.assertEqual((q["revenue"], q["net_profit"], q["eps"], q["bank"]), (492440000000.0, 78230000000.0, 19.32, False))
        self.assertEqual(q["operating_profit"], 110630000000.0 + 1150000000.0 - 8480000000.0)

    def test_bank_format(self):
        q = res.figures(res.parse_xbrl(read(BANK)))
        self.assertEqual((q["revenue"], q["net_profit"], q["eps"], q["bank"], q["operating_profit"]),
                         (834266000000.0, 195099600000.0, 12.66, True, None))

    def test_block_page_is_an_error(self):
        with self.assertRaises(res.ResultsError):
            res.parse_xbrl("<html><body>Access Denied</body></html>")


class Labels(unittest.TestCase):
    def test_fiscal_quarters(self):
        self.assertEqual([res.fy_label(datetime.date(*d)) for d in ((2026, 9, 30), (2026, 3, 31), (2025, 12, 31))],
                         ["Q2 FY27", "Q4 FY26", "Q3 FY26"])

    def test_quarter_steps(self):
        self.assertEqual(res._months_back(datetime.date(2026, 3, 31), 3), datetime.date(2025, 12, 31))
        self.assertEqual(res._months_back(datetime.date(2026, 9, 30), 12), datetime.date(2025, 9, 30))
        self.assertEqual(res._months_back(datetime.date(2026, 6, 30), 3), datetime.date(2026, 3, 31))


class Pick(unittest.TestCase):
    def f(self, q, basis, filed, link="x.xml"):
        return {"quarter": datetime.date(*q), "basis": basis, "xbrl": link, "filed": datetime.date(*filed),
                "broadcast": "", "name": "X"}

    def test_revised_filing_replaces_the_original_and_consolidated_wins(self):
        got = res.pick([self.f((2026, 9, 30), "consolidated", (2026, 10, 20), "a.xml"),
                        self.f((2026, 9, 30), "consolidated", (2026, 10, 25), "b.xml"),
                        self.f((2026, 9, 30), "standalone", (2026, 10, 26), "c.xml")])
        self.assertEqual([g["xbrl"] for g in got], ["b.xml"])

    def test_standalone_only_company(self):
        got = res.pick([self.f((2026, 9, 30), "standalone", (2026, 10, 20))])
        self.assertEqual(got[0]["basis"], "standalone")

    def test_not_a_list(self):
        with self.assertRaises(res.ResultsError):
            res.parse_list([], "INFY")


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_infy_metrics(self):
        code, text, _ = run(["--symbols", "INFY", "--offline", ADIR, "--now", NOW, "--json"])
        self.assertEqual(code, 0)
        r = json.loads(text)["companies"][0]
        self.assertEqual((r["quarter"], r["basis"], r["filed"]), ("Q2 FY27", "consolidated", "2026-10-23"))
        self.assertEqual((r["revenue_growth_yoy"], r["revenue_growth_qoq"], r["net_profit_growth_yoy"],
                          r["net_profit_growth_qoq"], r["eps_growth_yoy"]), (10.7, 2.1, 6.2, 0.7, 8.8))
        self.assertEqual((r["operating_margin"], r["net_margin"], r["eps_ttm"]), (21.0, 15.9, 75.69))
        self.assertIsNone(r["note"])
        self.assertEqual(r["shares"], 20260000000.0 / 5)

    def split_copy(self):
        d = os.path.join(self.tmp.name, "split")
        shutil.copytree(ADIR, d)
        p = os.path.join(d, INFY_Q2)
        with open(p, encoding="utf-8") as fh:
            x = fh.read()
        x, n1 = re.subn(r'(<in-capmkt:FaceValueOfEquityShareCapital[^>]*>)[^<]*', r"\g<1>2.5", x)
        x, n2 = re.subn(r'(<in-capmkt:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations[^>]*>)[^<]*',
                        r"\g<1>9.66", x)
        self.assertEqual((n1, n2), (1, 1))
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(x)
        return d

    def test_split_leaves_out_eps_growth_and_ttm(self):
        d = self.split_copy()
        code, text, _ = run(["--symbols", "INFY", "--offline", d, "--now", NOW, "--json"])
        self.assertEqual(code, 0)
        r = json.loads(text)["companies"][0]
        self.assertEqual((r["eps_ttm"], r["eps_growth_yoy"], r["revenue_growth_yoy"]), (None, None, 10.7))
        self.assertIn("share count changed", r["note"])
        code, text, _ = run(["--symbols", "INFY", "--offline", d, "--now", NOW])
        self.assertIn("    note        share count changed", text)

    def test_wrong_quarter_in_a_list_row_is_an_error(self):
        d = os.path.join(self.tmp.name, "mix")
        shutil.copytree(ADIR, d)
        pj = os.path.join(d, "results-INFY.json")
        with open(pj) as fh:
            doc = json.load(fh)
        n = 0
        for r in doc["data"]:
            if r["qe_Date"] == "30-JUN-2026" and r["consolidated"].lower() == "consolidated":
                r["xbrl"] = r["xbrl"].rsplit("/", 1)[0] + "/" + INFY_Q2
                n += 1
        self.assertEqual(n, 1)
        with open(pj, "w") as fh:
            json.dump(doc, fh)
        code, text, _ = run(["--symbols", "INFY", "--offline", d, "--now", NOW])
        self.assertEqual(code, 2)
        self.assertIn("but NSE lists it for", text)

    def test_text_report(self):
        code, text, _ = run(["--symbols", "INFY", "--offline", ADIR, "--now", NOW])
        self.assertIn("INFY  Q2 FY27 (2026-09-30, consolidated)", text)
        self.assertIn("revenue     Rs 49,244 cr  (+10.7% YoY, +2.1% QoQ)", text)
        self.assertIn("Not financial advice", text)

    def test_bank_with_one_quarter(self):
        code, text, _ = run(["--symbols", "HDFCBANK", "--standalone", "--offline", ADIR, "--now", NOW, "--json"])
        self.assertEqual(code, 0)
        r = json.loads(text)["companies"][0]
        self.assertEqual((r["bank"], r["operating_margin"], r["revenue_growth_yoy"], r["eps_ttm"]), (True, None, None, None))

    def test_missing_quarter_leaves_qoq_and_ttm_empty(self):
        d = os.path.join(self.tmp.name, "gap")
        shutil.copytree(ADIR, d)
        with open(os.path.join(d, "results-INFY.json")) as fh:
            doc = json.load(fh)
        doc["data"] = [r for r in doc["data"] if r["qe_Date"] != "30-JUN-2026"]
        with open(os.path.join(d, "results-INFY.json"), "w") as fh:
            json.dump(doc, fh)
        code, text, _ = run(["--symbols", "INFY", "--offline", d, "--now", NOW, "--json"])
        r = json.loads(text)["companies"][0]
        self.assertEqual((r["revenue_growth_qoq"], r["eps_ttm"], r["revenue_growth_yoy"]), (None, None, 10.7))

    def test_write_marks_partial_runs_and_the_screener_reads_it(self):
        out = os.path.join(self.tmp.name, "metrics.json")
        code, text, _ = run(["--symbols", "INFY", "TCS", "--offline", ADIR, "--now", NOW, "--write", out])
        self.assertEqual(code, 2)
        self.assertIn("error: TCS: cannot read", text)
        with open(out) as fh:
            doc = json.load(fh)
        self.assertEqual((doc["complete"], len(doc["companies"]), len(doc["errors"])), (False, 1, 1))
        self.assertEqual([c["symbol"] for c in screen.load_metrics(out)], ["INFY"])

    def test_no_symbols(self):
        code, _, err = run(["--kite-dir", self.tmp.name, "--targets", os.path.join(self.tmp.name, "none.json"),
                            "--offline", ADIR, "--now", NOW])
        self.assertEqual(code, 2)
        self.assertIn("which stocks?", err)


class Network(unittest.TestCase):
    def tearDown(self):
        if hasattr(self, "real"):
            res.nse.Client = self.real

    def test_symbol_is_encoded_and_a_bad_xbrl_is_forgotten(self):
        doc = json.loads(read("results-INFY.json"))

        class Client:
            urls, forgot, caches = [], [], []

            def get_json(self, url, cache=True):
                self.urls.append(url)
                self.caches.append(cache)
                return doc

            def get_text(self, url, cookie=True, cache=True):
                return "<html>blocked</html>"

            def forget(self, url):
                self.forgot.append(url)
        c = Client()
        with self.assertRaises(res.ResultsError):
            res.fetch("M&M", c)
        self.assertTrue(c.urls[0].endswith("symbol=M%26M&type=Integrated%20Filing-%20Financials"))
        self.assertEqual(c.caches, [False])
        self.assertEqual(len(c.forgot), 1)

    def test_blocked_exits_2_with_the_offline_hint(self):
        class Client:
            def get_json(self, url, cache=True):
                raise res.nse.NseBlocked(url, "HTTP 403")
        self.real = res.nse.Client
        res.nse.Client = Client
        code, text, _ = run(["--symbols", "INFY", "--now", NOW])
        self.assertEqual(code, 2)
        self.assertIn("blocked: ", text)
        self.assertIn("--offline", text)


if __name__ == "__main__":
    unittest.main()
