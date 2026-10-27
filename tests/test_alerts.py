import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

alerts = load("trader-alerts", "alerts")
ks = load("trader-alerts", "kite_snapshot")

ADIR = os.path.join(FIX, "trader-alerts")
KDIR = os.path.join(ADIR, "kite")
MASTER = os.path.join(ADIR, "nse-holiday-master.json")
CAL = alerts.nse_calendar.Calendar(dict(alerts.nse_calendar.HOLIDAYS), alerts.nse_calendar.YEARS)


def ist(text):
    return alerts.nse_calendar.parse_now(text)


def quotes():
    with open(os.path.join(KDIR, "quotes.json")) as fh:
        return ks.quotes(json.load(fh)["data"])


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = alerts.main(argv)
    return code, out.getvalue(), err.getvalue()


class Money(unittest.TestCase):
    def test_indian_grouping(self):
        self.assertEqual(alerts.inr(125000), "Rs 1,25,000")
        self.assertEqual(alerts.inr(1612.5), "Rs 1,612.50")
        self.assertEqual(alerts.inr(1234567.891), "Rs 12,34,567.89")
        self.assertEqual(alerts.inr(999), "Rs 999")
        self.assertEqual(alerts.inr(-950), "-Rs 950")
        self.assertEqual(alerts.inr(0.5), "Rs 0.50")


class Quotes(unittest.TestCase):
    def test_snapshot_quotes_and_missing_symbols(self):
        q, errors = alerts.get_quotes(["INFY", "TCS"], KDIR, ist("2026-10-26T15:30"))
        self.assertEqual(sorted(q), ["INFY"])
        self.assertEqual(errors, ["TCS is not in the Kite quotes snapshot: add NSE:TCS to the quotes call"])

    def test_stale_snapshot_is_refused(self):
        q, errors = alerts.get_quotes(["INFY"], KDIR, ist("2026-10-26T15:31:01"))
        self.assertEqual(q, {})
        self.assertIn("s old", errors[0])


class Rules(unittest.TestCase):
    def setUp(self):
        self.q = quotes()
        self.now = ist("2026-10-26T10:00")
        self.open = CAL.status(self.now)

    def ev(self, rules, state=None, status=None, now=None):
        return alerts.evaluate(rules, self.q, status or self.open, state or {}, now or self.now)

    def test_a_target_rings_once(self):
        rules = [{"id": "infy-1600", "symbol": "INFY", "type": "above", "price": 1600}]
        rings, st = self.ev(rules)
        self.assertEqual([r["message"] for r in rings], ["INFY is Rs 1,612.50: at or above your target Rs 1,600."])
        self.assertTrue(st["rung"]["infy-1600"].startswith("2026-10-26T10:00:00+05:30"))
        self.assertEqual(self.ev(rules, st)[0], [])

    def test_stop_and_rearm(self):
        rules = [{"id": "rel-stop", "symbol": "RELIANCE", "type": "stop", "price": 1410, "rearm": True}]
        rings, st = self.ev(rules)
        self.assertIn("at or below your stop Rs 1,410", rings[0]["message"])
        self.q["RELIANCE"]["price"] = 1420.0
        rings, st = self.ev(rules, st)
        self.assertEqual(rings, [])
        self.assertNotIn("rel-stop", st["rung"])
        self.q["RELIANCE"]["price"] = 1405.0
        self.assertEqual(len(self.ev(rules, st)[0]), 1)

    def test_pct_move_from_previous_close(self):
        self.assertEqual(self.ev([{"id": "r2", "symbol": "RELIANCE", "type": "pct_move", "pct": 2}])[0], [])
        small = [{"id": "r1", "symbol": "RELIANCE", "type": "pct_move", "pct": 1, "direction": "down"}]
        rings, st = self.ev(small)
        self.assertEqual(rings[0]["message"], "RELIANCE moved -1.01% to Rs 1,402.30 (from Rs 1,416.60).")
        self.assertEqual(self.ev(small, st)[0], [])
        up = [{"id": "ru", "symbol": "RELIANCE", "type": "pct_move", "pct": 1, "direction": "up"}]
        self.assertEqual(self.ev(up)[0], [])

    def test_opening_bell_once_per_trading_day(self):
        rules = [{"id": "bell", "type": "opening_bell"}]
        pre = ist("2026-10-26T09:10")
        self.assertEqual(self.ev(rules, status=CAL.status(pre), now=pre)[0], [])
        rings, st = self.ev(rules)
        self.assertEqual(rings[0]["message"], "Opening bell: NSE is open (2026-10-26 10:00 IST).")
        later = ist("2026-10-26T11:00")
        self.assertEqual(self.ev(rules, st, CAL.status(later), later)[0], [])
        nxt = ist("2026-10-27T09:16")
        self.assertEqual(len(self.ev(rules, st, CAL.status(nxt), nxt)[0]), 1)
        diwali = ist("2026-11-10T10:00")
        self.assertEqual(self.ev(rules, status=CAL.status(diwali), now=diwali)[0], [])

    def test_bad_rules(self):
        with self.assertRaises(alerts.AlertError):
            self.ev([{"id": "x", "type": "moon"}])
        with self.assertRaises(alerts.AlertError):
            self.ev([{"id": "x", "type": "above", "symbol": "INFY"}])


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.rules = os.path.join(self.d, "alerts.json")
        self.state = os.path.join(self.d, "state", "alerts.json")
        self.prices = os.path.join(self.d, "prices.json")
        self.hol = os.path.join(self.d, "holidays.json")

    def tearDown(self):
        shutil.rmtree(self.d)

    def check(self, now):
        return run(["check", "--rules", self.rules, "--state", self.state, "--prices-out", self.prices,
                    "--kite-dir", KDIR, "--holidays", self.hol, "--now", now])

    def test_a_day_of_alerts(self):
        for args in (["--opening-bell"], ["--symbol", "infy.ns", "--above", "1600"],
                     ["--symbol", "RELIANCE", "--stop", "1350"]):
            self.assertEqual(run(["add", "--rules", self.rules] + args)[0], 0)
        code, _, err = run(["add", "--rules", self.rules, "--symbol", "INFY", "--above", "1600"])
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)

        code, text, _ = self.check("2026-10-26T15:30")
        self.assertEqual(code, 0)
        self.assertIn("ALERT INFY last traded at Rs 1,612.50: at or above your target Rs 1,600.", text)
        self.assertNotIn("Opening bell", text)
        self.assertIn("not an order", text)
        with open(self.prices) as fh:
            doc = json.load(fh)
        self.assertEqual(doc["prices"], {"INFY": 1612.5, "RELIANCE": 1402.3})
        self.assertEqual(doc["currency"], "INR")

        code, text, _ = self.check("2026-10-27T09:16")
        self.assertEqual(code, 0)
        self.assertIn("ALERT Opening bell: NSE is open (2026-10-27 09:16 IST).", text)
        self.assertIn("error: the quotes snapshot is", text)

        code, text, _ = self.check("2026-10-27T09:20")
        self.assertEqual(code, 2)
        self.assertIn("error: the quotes snapshot is", text)

        code, text, _ = run(["list", "--rules", self.rules, "--state", self.state])
        self.assertIn("rang", text)
        self.assertEqual(run(["reset", "opening-bell", "--state", self.state])[0], 0)
        self.assertEqual(run(["reset", "opening-bell", "--state", self.state])[0], 1)

    def test_quote_write_merges(self):
        code, text, _ = run(["quote", "INFY", "nse:m&m", "--kite-dir", KDIR, "--write", self.prices,
                             "--now", "2026-10-26T15:30"])
        self.assertEqual(code, 0)
        self.assertRegex(text, r"INFY\s+Rs 1,612.50 \(\+1.42% vs prev close Rs 1,590\)")
        run(["quote", "RELIANCE", "--kite-dir", KDIR, "--write", self.prices, "--now", "2026-10-26T15:30"])
        with open(self.prices) as fh:
            doc = json.load(fh)
        self.assertEqual(sorted(doc["prices"]), ["INFY", "M&M", "RELIANCE"])
        self.assertEqual(doc["detail"]["M&M"]["upper_circuit"], 3520.0)

    def test_quote_everything_in_the_snapshot(self):
        code, text, _ = run(["quote", "--kite-dir", KDIR, "--now", "2026-10-26T15:30", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(json.loads(text)["quotes"]), ["INFY", "M&M", "RELIANCE"])

    def test_quote_stale(self):
        code, _, err = run(["quote", "--kite-dir", KDIR, "--now", "2026-10-26T16:00"])
        self.assertEqual(code, 1)
        self.assertIn("s old", err)

    def test_clock(self):
        code, text, _ = run(["clock", "--now", "2026-10-26T10:00", "--holidays", self.hol])
        self.assertEqual(code, 0)
        self.assertIn("NSE OPEN", text)
        self.assertIn("about 15:25", text)
        code, text, _ = run(["clock", "--now", "2026-12-25T10:00", "--holidays", self.hol])
        self.assertEqual(code, 1)
        self.assertIn("NSE holiday: Christmas", text)
        self.assertIn("Next open: 2026-12-28 09:15 IST.", text)

    def test_special_session(self):
        ses = os.path.join(self.d, "special_sessions.json")
        code, text, _ = run(["holidays", "session", "--date", "2026-11-08", "--open", "18:00", "--close", "19:00",
                             "--name", "Muhurat trading", "--sessions", ses])
        self.assertEqual(code, 0)
        self.assertIn("2026-11-08  18:00 to 19:00  Muhurat trading", text)
        code, text, _ = run(["clock", "--now", "2026-11-08T18:30", "--holidays", self.hol, "--sessions", ses])
        self.assertEqual(code, 0)
        self.assertIn("NSE OPEN, special session: Muhurat trading", text)
        self.assertIn("Today's special session (Muhurat trading): 18:00 to 19:00 IST", text)
        code, text, _ = run(["clock", "--now", "2026-11-08T10:00", "--holidays", self.hol, "--sessions", ses])
        self.assertEqual(code, 1)
        self.assertIn("Next open: 2026-11-08 18:00 IST.", text)
        code, _, err = run(["holidays", "session", "--date", "2026-11-08", "--sessions", ses])
        self.assertEqual(code, 1)
        self.assertIn("--open and --close", err)
        self.assertEqual(run(["holidays", "session", "--date", "2026-11-08", "--remove", "--sessions", ses])[0], 0)
        _, text, _ = run(["clock", "--now", "2027-01-04T10:00", "--holidays", self.hol])
        self.assertIn("holiday list for 2027 is not loaded", text)

    def test_holidays_refresh_from_file(self):
        code, text, _ = run(["holidays", "refresh", "--file", MASTER, "--holidays", self.hol])
        self.assertEqual(code, 0)
        self.assertIn("Saved 20 NSE holidays for 2026", text)
        self.assertTrue(os.path.exists(self.hol))
        code, _, err = run(["holidays", "refresh", "--file", os.path.join(KDIR, "quotes.json"),
                            "--holidays", self.hol])
        self.assertEqual(code, 1)
        self.assertIn("no CM list", err)

    def test_check_without_rules(self):
        code, _, err = run(["check", "--rules", self.rules, "--kite-dir", KDIR])
        self.assertEqual(code, 2)
        self.assertIn("no rules", err)

    def test_bad_symbol(self):
        code, _, err = run(["add", "--rules", self.rules, "--symbol", "BSE:INFY", "--above", "1"])
        self.assertEqual(code, 1)
        self.assertIn("only NSE symbols", err)


class MisWarning(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(KDIR, "positions.json")) as fh:
            self.pos = json.load(fh)["data"]
        self.rules = [{"id": "mis", "type": "mis_warning", "at": "15:05"}]

    def ev(self, when, state=None, pos=None):
        now = ist(when)
        return alerts.evaluate(self.rules, {}, CAL.status(now), state or {}, now,
                               self.pos if pos is None else pos)

    def test_rings_once_after_the_time_with_open_mis(self):
        self.assertEqual(self.ev("2026-10-26T15:04")[0], [])
        rings, st = self.ev("2026-10-26T15:05")
        self.assertEqual(rings[0]["message"],
                         "MIS positions still open at 15:05 IST: INFY +5. Zerodha squares MIS off from about "
                         "15:25 IST and charges Rs 50 + GST for each one; close them yourself first if you "
                         "want to choose the price.")
        self.assertEqual(self.ev("2026-10-26T15:10", st)[0], [])

    def test_quiet_without_open_mis_or_outside_the_session(self):
        flat = {"net": [{"tradingsymbol": "INFY", "exchange": "NSE", "product": "MIS", "quantity": 0}]}
        self.assertEqual(self.ev("2026-10-26T15:06", pos=flat)[0], [])
        self.assertEqual(self.ev("2026-10-26T15:31")[0], [])
        self.assertEqual(self.ev("2026-11-10T15:06")[0], [])

    def test_short_mis_shows_a_minus(self):
        short = {"net": [{"tradingsymbol": "TCS", "exchange": "NSE", "product": "MIS", "quantity": -3}]}
        self.assertIn("TCS -3", self.ev("2026-10-26T15:06", pos=short)[0][0]["message"])

    def test_bad_time(self):
        now = ist("2026-10-26T15:06")
        with self.assertRaises(alerts.AlertError):
            alerts.evaluate([{"id": "m", "type": "mis_warning", "at": "3pm"}], {}, CAL.status(now), {}, now,
                            self.pos)

    def test_check_reads_the_positions_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            rules = os.path.join(d, "alerts.json")
            run(["add", "--rules", rules, "--mis-warning"])
            code, text, _ = run(["check", "--rules", rules, "--state", os.path.join(d, "state.json"),
                                 "--prices-out", os.path.join(d, "prices.json"), "--kite-dir", KDIR,
                                 "--holidays", os.path.join(d, "h.json"), "--now", "2026-10-26T15:06"])
            self.assertEqual(code, 0)
            self.assertIn("ALERT MIS positions still open at 15:06 IST: INFY +5.", text)
            code, text, _ = run(["check", "--rules", rules, "--state", os.path.join(d, "state2.json"),
                                 "--no-write", "--kite-dir", KDIR, "--holidays", os.path.join(d, "h.json"),
                                 "--now", "2026-10-26T15:12"])
            self.assertEqual(code, 2)
            self.assertIn("positions snapshot is", text)


class Need(unittest.TestCase):
    def test_lists_what_to_ask_kite_for(self):
        with tempfile.TemporaryDirectory() as d:
            rules = os.path.join(d, "alerts.json")
            run(["add", "--rules", rules, "--symbol", "infy", "--above", "1700"])
            run(["add", "--rules", rules, "--symbol", "m&m", "--pct", "2"])
            run(["add", "--rules", rules, "--opening-bell"])
            run(["add", "--rules", rules, "--mis-warning", "--at", "15:00"])
            code, text, _ = run(["need", "--rules", rules, "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(text), {"quotes": ["NSE:INFY", "NSE:M&M"], "positions": True})
            self.assertEqual(run(["need", "--rules", os.path.join(d, "none.json")])[0], 1)


class ReviewFixes(unittest.TestCase):
    """Findings from the phase 1 whole-branch review."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.rules = os.path.join(self.d, "alerts.json")

    def tearDown(self):
        self.tmp.cleanup()

    def write_rules(self, rules):
        with open(self.rules, "w") as fh:
            json.dump({"rules": rules}, fh)

    def check(self, now, kite_dir=KDIR):
        return run(["check", "--rules", self.rules, "--state", os.path.join(self.d, "state.json"),
                    "--prices-out", os.path.join(self.d, "prices.json"), "--kite-dir", kite_dir,
                    "--holidays", os.path.join(self.d, "h.json"), "--now", now])

    def test_hand_written_rule_symbols_are_normalised(self):
        self.write_rules([{"id": "a", "symbol": "nse:infy", "type": "above", "price": 1600},
                          {"id": "b", "symbol": "infy.ns", "type": "above", "price": 1600}])
        code, text, _ = run(["need", "--rules", self.rules, "--json"])
        self.assertEqual(json.loads(text)["quotes"], ["NSE:INFY"])
        code, text, _ = self.check("2026-10-26T15:30")
        self.assertEqual(code, 0)
        self.assertEqual(text.count("ALERT INFY"), 2)
        self.assertNotIn("NSE:NSE", text)

    def test_bad_rule_symbol_is_an_error(self):
        self.write_rules([{"id": "a", "symbol": "BSE:INFY", "type": "above", "price": 1}])
        code, _, err = self.check("2026-10-26T15:30")
        self.assertEqual(code, 2)
        self.assertIn("only NSE symbols", err)

    def test_unknown_year_is_flagged_in_check(self):
        self.write_rules([{"id": "bell", "type": "opening_bell"}])
        code, text, _ = self.check("2027-01-26T09:30")
        self.assertIn("holiday list for 2027 is not loaded", text)
        self.assertIn("may be an NSE holiday", text)

    def test_errors_never_look_like_nothing_hit(self):
        self.write_rules([{"id": "x", "type": "above", "symbol": "INFY"}])
        self.assertEqual(self.check("2026-10-26T15:30")[0], 2)
        self.write_rules([{"id": "i", "symbol": "INFY", "type": "above", "price": 9000},
                          {"id": "t", "symbol": "TCS", "type": "above", "price": 9000}])
        code, text, _ = self.check("2026-10-26T15:30")
        self.assertEqual(code, 2)
        self.assertIn("add NSE:TCS", text)

    def test_old_quote_inside_a_fresh_snapshot_is_refused_in_session(self):
        now = ist("2026-10-26T15:00")
        ks.save("quotes", {"NSE:INFY": {"last_price": 1600, "timestamp": "2026-10-26 14:50:00",
                                        "ohlc": {"close": 1590}}}, self.d, now=now)
        q, errors = alerts.get_quotes(["INFY"], self.d, now, session_open=True)
        self.assertEqual(q, {})
        self.assertIn("Kite's quote for NSE:INFY is from 2026-10-26 14:50:00", errors[0])
        q, errors = alerts.get_quotes(["INFY"], self.d, now, session_open=False)
        self.assertEqual(sorted(q), ["INFY"])

    def test_zero_price_is_not_a_price(self):
        now = ist("2026-10-26T15:00")
        ks.save("quotes", {"NSE:TCS": {"last_price": 0}}, self.d, now=now)
        q, errors = alerts.get_quotes(["TCS"], self.d, now)
        self.assertEqual(q, {})
        self.assertEqual(errors, ["Kite gave no usable price for NSE:TCS"])

    def test_prices_json_dates_each_symbol(self):
        path = os.path.join(self.d, "prices.json")
        alerts.write_prices(path, {"INFY": quotes()["INFY"]}, ist("2026-10-26T15:30"))
        with open(path) as fh:
            doc = json.load(fh)
        self.assertEqual(doc["detail"]["INFY"]["as_of"], "2026-10-26T15:30:00+05:30")


if __name__ == "__main__":
    unittest.main()
