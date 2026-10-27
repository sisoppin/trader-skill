import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

ins = load("trader-insider", "insider")

IDIR = os.path.join(FIX, "trader-insider")
NOW = "2026-10-26T18:00"


def read(name):
    with open(os.path.join(IDIR, name)) as fh:
        return fh.read()


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = ins.main(argv)
    return code, out.getvalue(), err.getvalue()


class Pit(unittest.TestCase):
    def test_real_infy_rows(self):
        rows = ins.parse_pit(json.loads(read("pit-INFY.json")), "INFY")
        self.assertEqual(len(rows), 5)
        self.assertEqual(len({r["id"] for r in rows}), 5)
        first = rows[0]
        self.assertEqual((first["name"], first["mode"], first["side"], first["shares"], first["value"]),
                         ("Infosys Employee benefits Trust", "Off Market", "-", 25, 31743.0))
        self.assertEqual(first["when"].strftime("%Y-%m-%d %H:%M"), "2026-04-06 16:07")
        self.assertFalse(any(r["market"] for r in rows))
        self.assertFalse(any(r["insider"] for r in rows))
        self.assertEqual([r["side"] for r in rows[3:]], ["BUY", "BUY"])

    def test_promoter_market_buy_and_director_sale(self):
        rows = ins.parse_pit(json.loads(read("pit-ABC.json")), "ABC")
        self.assertEqual([(r["side"], r["market"], r["insider"]) for r in rows],
                         [("BUY", True, True), ("SELL", True, True), ("-", False, True)])
        self.assertIsNone(rows[2]["value"])

    def test_not_a_pit_answer(self):
        with self.assertRaises(ins.InsiderError):
            ins.parse_pit([{"x": 1}], "INFY")


class Deals(unittest.TestCase):
    def test_real_bulk_and_empty_block(self):
        bulk = ins.parse_deals(read("bulk.csv"), "bulk")
        self.assertEqual(len(bulk), 6)
        self.assertEqual((bulk[0]["symbol"], bulk[0]["name"], bulk[0]["side"], bulk[0]["shares"], bulk[0]["price"]),
                         ("APOLLO", "QE SECURITIES LLP", "BUY", 2465951, 410.93))
        self.assertEqual(ins.parse_deals(read("block.csv"), "block"), [])
        self.assertEqual(len({r["id"] for r in bulk}), 6)

    def test_bad_csv(self):
        with self.assertRaises(ins.InsiderError):
            ins.parse_deals("<html>blocked</html>\n", "bulk")
        with self.assertRaises(ins.InsiderError):
            ins.parse_deals("Date,Symbol,Client Name\nyesterday,ABC,X\n", "bulk")


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "state.json")
        self.out = os.path.join(self.tmp.name, "insider.json")

    def tearDown(self):
        self.tmp.cleanup()

    def ins(self, *args):
        return run(list(args) + ["--offline", IDIR, "--state", self.state, "--out", self.out, "--now", NOW])

    def test_check_alerts_once_and_writes_the_rows(self):
        code, text, _ = self.ins("--symbols", "ABC", "APOLLO", "--days", "30")
        self.assertEqual(code, 2)
        self.assertIn("2026-10-21 10:00  ABC        insider SELL A Director 1200 shares (Equity Shares), Market Sale, "
                      "Director [market] [insider]", text)
        self.assertIn("APOLLO     bulk deal BUY 2465951 shares at Rs 410.93 by QE SECURITIES LLP", text)
        self.assertNotIn("An Employee", text)
        self.assertIn("error: APOLLO: cannot read", text)
        self.assertIn("Not financial advice", text)
        with open(self.out) as fh:
            doc = json.load(fh)
        self.assertEqual(len(doc["rows"]), 4)
        self.assertEqual((doc["complete"], doc["cmd"], len(doc["errors"])), (False, "check", 1))
        code, text, _ = self.ins("--symbols", "ABC", "APOLLO", "--days", "30")
        self.assertEqual(code, 2)
        self.assertIn("Nothing new.", text)

    def test_deals_for_every_symbol(self):
        code, text, _ = self.ins("deals", "--symbols", "INFY", "--json", "--dry-run")
        self.assertEqual(json.loads(text)["rows"], [])
        code, text, _ = self.ins("deals", "--every-symbol", "--json", "--dry-run")
        self.assertEqual(len(json.loads(text)["rows"]), 6)
        self.assertFalse(os.path.exists(self.state))

    def test_deals_without_a_watch_list(self):
        empty = os.path.join(self.tmp.name, "empty")
        base = ["deals", "--kite-dir", empty, "--targets", os.path.join(empty, "t.json"), "--offline", IDIR,
                "--state", self.state, "--out", self.out, "--now", NOW]
        code, _, err = run(base)
        self.assertEqual(code, 2)
        self.assertIn("which stocks?", err)
        code, text, _ = run(base + ["--every-symbol"])
        self.assertEqual(code, 0)
        self.assertIn("bulk deal", text)

    def test_file_only_for_one_symbol_pit(self):
        path = os.path.join(IDIR, "pit-INFY.json")
        code, text, _ = run(["pit", "--symbols", "INFY", "--file", path, "--days", "365", "--state", self.state,
                             "--out", self.out, "--now", NOW])
        self.assertEqual(code, 0)
        self.assertIn("Atul Chaturvedi", text)
        code, _, err = run(["deals", "--symbols", "INFY", "--file", path, "--now", NOW])
        self.assertEqual(code, 2)
        self.assertIn("--file holds one symbol", err)


class Requests(unittest.TestCase):
    def test_fetches_ask_fresh_and_encode_the_symbol(self):
        class Client:
            def __init__(self):
                self.calls = []

            def get_json(self, url, cache=True):
                self.calls.append((url, cache))
                return {"data": []}

            def get_text(self, url, cookie=True, cache=True):
                self.calls.append((url, cache))
                return "Date,Symbol,Client Name\n"
        c = Client()
        ins.fetch_pit(["M&M"], c)
        ins.fetch_deals(c)
        self.assertTrue(c.calls[0][0].endswith("symbol=M%26M"))
        self.assertEqual([x[1] for x in c.calls], [False, False, False])

    def test_a_crash_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "s.json")
            with open(state, "w") as fh:
                fh.write("[]")
            code, _, err = run(["--symbols", "ABC", "--offline", IDIR, "--state", state,
                                "--out", os.path.join(tmp, "o.json"), "--now", NOW])
        self.assertEqual(code, 2)
        self.assertIn("unexpected", err)


class Blocked(unittest.TestCase):
    def test_blocked_requests_are_reported(self):
        class Client:
            def get_json(self, url, cache=True):
                raise ins.nse.NseBlocked(url, "HTTP 403")

            def get_text(self, url, cookie=True, cache=True):
                raise ins.nse.NseBlocked(url, "HTTP 503")
        _, _, blocked = ins.fetch_pit(["INFY"], Client())
        self.assertIn("symbol=INFY", blocked[0])
        _, _, blocked = ins.fetch_deals(Client())
        self.assertEqual(len(blocked), 2)
        self.assertIn("--file", blocked[0])
        self.assertIn("--bulk-file", blocked[0])
        self.assertIn("--block-file", blocked[1])

    def test_blocked_exits_2_in_main(self):
        class Client:
            def get_json(self, url, cache=True):
                raise ins.nse.NseBlocked(url, "HTTP 403")

            def get_text(self, url, cookie=True, cache=True):
                raise ins.nse.NseBlocked(url, "HTTP 503")
        old = ins.nse.Client
        ins.nse.Client = Client
        try:
            with tempfile.TemporaryDirectory() as tmp:
                code, text, _ = run(["--symbols", "INFY", "--state", os.path.join(tmp, "s.json"),
                                     "--out", os.path.join(tmp, "o.json"), "--now", NOW])
        finally:
            ins.nse.Client = old
        self.assertEqual(code, 2)
        self.assertIn("blocked: ", text)


if __name__ == "__main__":
    unittest.main()
