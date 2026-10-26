import datetime
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

ks = load("trader-alerts", "kite_snapshot")

KDIR = os.path.join(FIX, "trader-alerts", "kite")
T0 = datetime.datetime(2026, 10, 26, 15, 29, 0, tzinfo=ks.IST)
SEC = datetime.timedelta(seconds=1)


def raw(name):
    with open(os.path.join(KDIR, name)) as fh:
        return json.load(fh)


class Save(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_stamps_and_unwraps(self):
        p = ks.save("quotes", raw("quotes-raw.json"), self.d, now=T0)
        with open(p) as fh:
            doc = json.load(fh)
        self.assertEqual(doc["fetched_at"], "2026-10-26T15:29:00+05:30")
        self.assertIn("NSE:INFY", doc["data"])
        self.assertNotIn("status", doc["data"])

    def test_bare_answer_is_kept(self):
        ks.save("positions", {"net": [], "day": []}, self.d, now=T0)
        self.assertEqual(ks.load("positions", self.d, now=T0), {"net": [], "day": []})

    def test_kite_error_is_refused(self):
        with self.assertRaises(ks.SnapshotError) as c:
            ks.save("quotes", {"status": "error", "message": "Incorrect api_key or access_token."}, self.d)
        self.assertIn("access_token", str(c.exception))

    def test_unknown_kind(self):
        with self.assertRaises(ks.SnapshotError):
            ks.save("orders", {}, self.d)


class Load(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        ks.save("quotes", raw("quotes-raw.json"), self.d, now=T0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh(self):
        self.assertIn("NSE:INFY", ks.load("quotes", self.d, now=T0 + 120 * SEC))

    def test_stale(self):
        with self.assertRaises(ks.SnapshotError) as c:
            ks.load("quotes", self.d, now=T0 + 121 * SEC)
        self.assertIn("121 s old", str(c.exception))
        self.assertIn("kite_snapshot.py save quotes", str(c.exception))

    def test_max_age_override(self):
        self.assertIn("NSE:INFY", ks.load("quotes", self.d, now=T0 + 500 * SEC, max_age=600))

    def test_missing(self):
        with self.assertRaises(ks.SnapshotError) as c:
            ks.load("margins", self.d, now=T0)
        self.assertIn("no margins snapshot", str(c.exception))

    def test_future(self):
        with self.assertRaises(ks.SnapshotError) as c:
            ks.load("quotes", self.d, now=T0 - 61 * SEC)
        self.assertIn("future", str(c.exception))

    def test_not_a_snapshot(self):
        with open(os.path.join(self.d, "quotes.json"), "w") as fh:
            json.dump({"NSE:INFY": {}}, fh)
        with self.assertRaises(ks.SnapshotError) as c:
            ks.load("quotes", self.d, now=T0)
        self.assertIn("not a snapshot", str(c.exception))


class Quotes(unittest.TestCase):
    def test_normalised(self):
        q = ks.quotes(ks.unwrap(raw("quotes-raw.json")))
        self.assertEqual(sorted(q), ["INFY", "M&M", "RELIANCE"])
        i = q["INFY"]
        self.assertEqual((i["price"], i["prev_close"], i["open"]), (1612.5, 1590.0, 1598.0))
        self.assertEqual((i["upper_circuit"], i["lower_circuit"]), (1773.75, 1451.25))
        self.assertEqual(i["time"], "2026-10-26 15:29:57")
        self.assertEqual(i["exchange"], "NSE")

    def test_ltp_only_and_other_exchanges(self):
        q = ks.quotes({"BSE:INFY": {"last_price": 1611}, "NSE:TCS": {"last_price": "3050.5"},
                       "NSE:BAD": {"last_price": None}})
        self.assertEqual(sorted(q), ["BSE:INFY", "TCS"])
        self.assertEqual(q["TCS"]["price"], 3050.5)
        self.assertIsNone(q["TCS"]["prev_close"])


class Cli(unittest.TestCase):
    def test_save_and_show(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "raw.json")  # a fresh file, as Claude writes one per connector call
            with open(src, "w") as fh:
                json.dump(raw("quotes-raw.json"), fh)
            with redirect_stdout(io.StringIO()):
                code = ks.main(["save", "quotes", "--from", src, "--dir", d])
            self.assertEqual(code, 0)
            out = io.StringIO()
            with redirect_stdout(out):
                ks.main(["show", "--dir", d])
            self.assertRegex(out.getvalue(), r"quotes\s+\d+ s old")
            self.assertRegex(out.getvalue(), r"margins\s+none")

    def test_save_rejects_non_json(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.txt")
            with open(bad, "w") as fh:
                fh.write("Kite says hi")
            err = io.StringIO()
            with redirect_stderr(err):
                code = ks.main(["save", "quotes", "--from", bad, "--dir", d])
            self.assertEqual(code, 1)
            self.assertIn("not JSON", err.getvalue())


class ReviewFixes(unittest.TestCase):
    def test_an_old_raw_file_is_not_restamped_as_fresh(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "raw.json")
            with open(src, "w") as fh:
                json.dump({"NSE:INFY": {"last_price": 1600}}, fh)
            old = os.path.getmtime(src) - 600
            os.utime(src, (old, old))
            err = io.StringIO()
            with redirect_stderr(err):
                code = ks.main(["save", "quotes", "--from", src, "--dir", d])
            self.assertEqual(code, 1)
            self.assertIn("written 600 s ago", err.getvalue())
            self.assertFalse(os.path.exists(os.path.join(d, "quotes.json")))

    def test_quote_time_and_zero_price(self):
        q = ks.quotes({"NSE:INFY": {"last_price": 1600, "timestamp": "2026-10-26 15:29:58"},
                       "NSE:TCS": {"last_price": 0}})
        self.assertEqual(sorted(q), ["INFY"])
        self.assertEqual(q["INFY"]["quote_time"], "2026-10-26 15:29:58")


if __name__ == "__main__":
    unittest.main()
