import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from _load import FIX, ROOT, load

scr = load("trader-screener", "screen")
DIR = os.path.join(FIX, "trader-screener")
METRICS = os.path.join(DIR, "metrics.json")
PRICES = os.path.join(DIR, "prices.json")
RULES = os.path.join(ROOT, "trader-screener", "rules.example.json")


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = scr.main(args)
    return code, out.getvalue(), err.getvalue()


def companies(prices=True):
    rows = scr.load_metrics(METRICS)
    if prices:
        scr.add_prices(rows, PRICES)
    return rows


# metrics.json: real trader-analyst rows for six NSE stocks (results to the Sep or Jun 2026 quarter, read
# 2026-10-27); prices.json: illustrative prices, labelled as such; companies.csv: the same numbers as a CSV
# with rupee units.


class Prices(unittest.TestCase):
    def test_pe_and_earnings_yield(self):
        by = {c["ticker"]: c for c in companies()}
        self.assertEqual(by["INFY"]["pe"], 19.8)       # 1500 / 75.69
        self.assertEqual(by["TCS"]["pe"], 21.0)        # 3000 / 142.64
        self.assertEqual(by["HDFCBANK"]["earnings_yield"], 5.48)
        self.assertEqual(by["M&M"]["price"], 3400.0)

    def test_rupee_units(self):
        self.assertEqual([scr.to_number(v) for v in ("Rs. 1,23,456.50", "INR 12", "\u20b9 5", "rs 7%", "Rsx", "-")],
                         [123456.5, 12.0, 5.0, 7.0, "Rsx", None])

    def test_no_pe_for_losses(self):
        rows = [{"ticker": "LOSS", "eps_ttm": -1.0}]
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "prices.json")
            with open(p, "w") as fh:
                json.dump({"prices": {"LOSS": 10}}, fh)
            scr.add_prices(rows, p)
        self.assertNotIn("pe", rows[0])
        self.assertEqual(rows[0]["earnings_yield"], -10.0)


class Screen(unittest.TestCase):
    def setUp(self):
        self.spec = scr.load_rules(RULES)
        self.results = scr.screen(companies(), self.spec)

    def test_the_example_screen(self):
        passed = [(r["ticker"], r["score"]) for r in self.results if r["passed"]]
        self.assertEqual(passed, [("M&M", 0.667), ("TCS", 0.5), ("INFY", 0.417), ("ITC", 0.417)])
        fails = {r["ticker"]: r["fails"] for r in self.results if not r["passed"]}
        self.assertEqual(fails["RELIANCE"], ["operating_margin 10.4, needs >= 15"])
        self.assertEqual(fails["HDFCBANK"], ["revenue_growth_yoy 9.4, needs >= 10",
                                             "operating_margin is missing"])

    def test_a_bank_can_skip_the_operating_margin_rule(self):
        rules = [dict(r, value=9) if r["metric"] == "revenue_growth_yoy" else r for r in self.spec["rules"]]
        spec = dict(self.spec, rules=rules, missing="skip")
        res = {r["ticker"]: r for r in scr.screen(companies(), spec)}
        self.assertTrue(res["HDFCBANK"]["passed"])
        self.assertEqual(res["HDFCBANK"]["skipped"], ["operating_margin is missing"])
        self.assertIn("operating_margin", res["HDFCBANK"]["rank_gaps"])

    def test_every_op(self):
        c = {"ticker": "ITC", "sector": "Diversified FMCG", "pe": 28.3}
        cases = [({"metric": "pe", "op": "between", "value": [10, 30]}, True),
                 ({"metric": "pe", "op": "between", "value": [10, 20]}, False),
                 ({"metric": "pe", "op": "<", "value": 28.3}, False),
                 ({"metric": "pe", "op": "!=", "value": 1}, True),
                 ({"metric": "ticker", "op": "in", "value": ["itc", "hul"]}, True),
                 ({"metric": "ticker", "op": "not in", "value": ["ITC"]}, False),
                 ({"metric": "sector", "op": "==", "value": "diversified fmcg"}, True),
                 ({"metric": "sector", "op": ">", "value": 3}, False),
                 ({"metric": "beta", "op": "<", "value": 1}, None)]
        for rule, want in cases:
            self.assertEqual(scr.check(c, rule)[0], want, rule)

    def test_bad_rules_are_refused(self):
        for bad in ({"rules": [{"metric": "pe", "op": "~", "value": 1}]},
                    {"rules": [{"metric": "pe", "op": "between", "value": 3}]},
                    {"rules": [{"metric": "pe", "op": "<"}]},
                    {"rules": [], "rank": [{"metric": "pe", "order": "up"}]},
                    {"rules": [], "missing": "maybe"}):
            with self.assertRaises(scr.ScreenError):
                scr.check_rules(bad)


class Cli(unittest.TestCase):
    def test_text_report_and_shortlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "trader", "shortlist.json")
            code, text, err = run([METRICS, "--rules", RULES, "--prices", PRICES, "--out", out])
            self.assertEqual(code, 0, err)
            with open(out) as fh:
                sl = json.load(fh)
        self.assertIn("4 of 6 companies pass", text)
        self.assertIn("Prices as of 2026-10-27T15:30:00+05:30", text)
        self.assertIn("    FAIL RELIANCE   operating_margin 10.4, needs >= 15", text)
        self.assertIn("not a recommendation", text)
        self.assertNotIn("WARNING", text)
        self.assertNotIn(chr(0x2014), text)
        self.assertEqual([p["ticker"] for p in sl["passed"]], ["M&M", "TCS", "INFY", "ITC"])
        self.assertEqual((len(sl["failed"]), sl["metrics_missing"]), (2, []))

    def test_a_partial_metrics_file_is_called_out(self):
        with open(METRICS) as fh:
            doc = json.load(fh)
        doc["complete"], doc["errors"] = False, ["TCS: cannot read the results list"]
        doc["companies"] = [c for c in doc["companies"] if c["symbol"] != "TCS"]
        doc["companies"][0]["note"] = "share count changed by more than 5%"
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "metrics.json")
            with open(p, "w") as fh:
                json.dump(doc, fh)
            code, text, _ = run([p, "--rules", RULES, "--prices", PRICES])
            _, js, _ = run([p, "--rules", RULES, "--prices", PRICES, "--json"])
        self.assertIn("WARNING: the metrics file is partial", text)
        self.assertIn("    TCS: cannot read the results list", text)
        self.assertIn("        note  share count changed by more than 5%", text)
        self.assertEqual(json.loads(js)["metrics_missing"], ["TCS: cannot read the results list"])

    def test_csv_with_units_and_nothing_passing(self):
        csv_path = os.path.join(DIR, "companies.csv")
        rows = scr.load_metrics(csv_path)
        self.assertEqual((rows[0]["ticker"], rows[0]["eps_ttm"], rows[1]["eps_ttm"]), ("INFY", 75.69, 142.64))
        self.assertEqual(rows[0]["revenue_growth_yoy"], 10.7)
        self.assertIsNone(rows[2]["operating_margin"])
        code, text, _ = run([csv_path, "--rules", RULES])
        self.assertEqual(code, 1)   # no prices, so no pe: nothing passes
        self.assertIn("pe is missing", text)

    def test_a_csv_row_with_extra_cells_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "m.csv")
            with open(p, "w") as fh:
                fh.write("symbol,eps_ttm,operating_margin\nBBB,Rs.5,12,INR 1,23,456\n")
            code, _, err = run([p, "--rules", RULES])
        self.assertEqual(code, 2)
        self.assertIn("more cells than the header", err)

    def test_price_date_is_the_oldest_price_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "prices.json")
            now = "2026-10-27T15:30:00+05:30"
            with open(p, "w") as fh:
                json.dump({"as_of": now, "prices": {"INFY": 1500, "TCS": 3500},
                           "detail": {"INFY": {"as_of": "2026-10-01T15:30:00+05:30"},
                                      "TCS": {"as_of": now}}}, fh)
            code, text, _ = run([METRICS, "--rules", RULES, "--prices", p])
        self.assertIn("Prices as of 2026-10-01T15:30:00+05:30", text)

    def test_bad_input_exit_2(self):
        code, _, err = run(["/nonexistent.json", "--rules", RULES])
        self.assertEqual(code, 2)
        self.assertIn("no such file", err)

    def test_top_limits_the_shortlist(self):
        code, text, _ = run([METRICS, "--rules", RULES, "--prices", PRICES, "--top", "1",
                             "--json"])
        self.assertEqual(code, 0)
        self.assertEqual([p["ticker"] for p in json.loads(text)["passed"]], ["M&M"])


if __name__ == "__main__":
    unittest.main()
