import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from _load import load, FIX

sy = load("trader-alerts", "nse_symbols")

SAMPLE = os.path.join(FIX, "trader-alerts", "EQUITY_L-sample.csv")


def sample_text():
    with open(SAMPLE, encoding="utf-8") as fh:
        return fh.read()


class Normalize(unittest.TestCase):
    def test_forms(self):
        for s in ("INFY", "infy", " nse:infy ", "INFY.NS", "NSE:INFY", "infy.ns"):
            self.assertEqual(sy.normalize(s), "INFY", s)
        self.assertEqual(sy.normalize("m&m"), "M&M")
        self.assertEqual(sy.normalize("bajaj-auto"), "BAJAJ-AUTO")
        self.assertEqual(sy.kite_key("m&m.ns"), "NSE:M&M")
        for bad in ("BSE:INFY", "", "  ", None, "NSE:"):
            with self.assertRaises(sy.SymbolError):
                sy.normalize(bad)


class Master(unittest.TestCase):
    def setUp(self):
        self.m = sy.load(SAMPLE)

    def test_lookup_and_isin(self):
        r = self.m.lookup("infy.ns")
        self.assertEqual((r["name"], r["isin"], r["series"]), ("Infosys Limited", "INE009A01021", "EQ"))
        self.assertEqual(self.m.by_isin("ine002a01018")["symbol"], "RELIANCE")
        self.assertIsNone(self.m.lookup("NIFTYBEES"))
        self.assertIsNone(self.m.by_isin("US0378331005"))
        self.assertEqual(len(self.m.rows), 7)

    def test_missing_list(self):
        with self.assertRaises(sy.SymbolError) as e:
            sy.load(os.path.join(tempfile.gettempdir(), "no-such-dir", "EQUITY_L.csv"))
        self.assertIn("refresh", str(e.exception))

    def test_not_a_symbol_list(self):
        for text in ("", "hello\n", "<html>blocked</html>\n"):
            with self.assertRaises(sy.SymbolError):
                sy.parse(text)


class Refresh(unittest.TestCase):
    def test_from_file_and_from_nse(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def get_text(self, url, cookie=True):
                self.calls.append((url, cookie))
                return sample_text()

        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "EQUITY_L.csv")
            self.assertEqual(sy.refresh(dest, file=SAMPLE), 7)
            self.assertEqual(sy.load(dest).lookup("TCS")["isin"], "INE467B01029")
            fc = FakeClient()
            self.assertEqual(sy.refresh(dest, client=fc), 7)
            self.assertEqual(fc.calls, [(sy.URL, False)])

    def test_garbage_keeps_the_old_list(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "EQUITY_L.csv")
            sy.refresh(dest, file=SAMPLE)
            bad = os.path.join(d, "bad.csv")
            with open(bad, "w") as fh:
                fh.write("<html>blocked</html>\n")
            with self.assertRaises(sy.SymbolError):
                sy.refresh(dest, file=bad)
            self.assertEqual(len(sy.load(dest).rows), 7)

    def test_cli_lookup(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = sy.main(["lookup", "infy", "NIFTYBEES", "--list", SAMPLE])
        self.assertEqual(code, 1)
        self.assertIn("Infosys Limited", out.getvalue())
        self.assertRegex(out.getvalue(), r"NIFTYBEES\s+not in NSE's equity list")


class BlockedRefresh(unittest.TestCase):
    def test_html_with_200_is_blocked_and_not_cached(self):
        nse = sy.nse

        class Opener:
            calls = 0

            def open(self, req, timeout=None):
                Opener.calls += 1
                return io.BytesIO(b"<html>Access Denied</html>")

        with tempfile.TemporaryDirectory() as d:
            c = nse.Client(cache=d, opener=Opener(), sleep=lambda s: None, today="2026-10-26")
            with self.assertRaises(nse.NseBlocked) as e:
                sy.refresh(os.path.join(d, "EQUITY_L.csv"), client=c)
            self.assertIn("--file", str(e.exception))
            with self.assertRaises(nse.NseBlocked):
                sy.refresh(os.path.join(d, "EQUITY_L.csv"), client=c)
            self.assertEqual(Opener.calls, 2)


if __name__ == "__main__":
    unittest.main()
