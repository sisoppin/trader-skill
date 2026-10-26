import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

ticket = load("trader-broker", "ticket")
check = load("trader-risk", "check")

CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
RDIR = os.path.join(FIX, "trader-risk")
ORDERS_PATH = os.path.join(RDIR, "orders-example.json")
KDIR = os.path.join(RDIR, "kite")
INFY = {"exchange": "NSE", "tradingsymbol": "INFY", "transaction_type": "BUY", "quantity": "6", "product": "CNC",
        "order_type": "LIMIT", "price": "1612.50", "validity": "DAY", "variety": "regular",
        "est_value": "9675.00", "est_charges": "11.49", "why": "25.00% of the stock sleeve"}
BATCH = ["INFY", "RELIANCE", "TCS", "HDFCBANK"]


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = ticket.main(argv)
    return code, out.getvalue(), err.getvalue()


class ExplicitYes(unittest.TestCase):
    def yes(self, reply, order=INFY):
        return ticket.parse_yes(reply, order, BATCH)[0]

    def test_plain_yes_counts(self):
        for r in ("yes", "Yes.", "YES", "y", "yes place it", "Yes, buy it", "yes INFY", "yes 6 INFY",
                  "yes 6 shares at 1612.50", "yes 9,675"):
            self.assertTrue(self.yes(r), r)

    def test_anything_else_does_not(self):
        for r in ("", "sure", "ok", "okay", "go", "do it", "yeah", "haan", "absolutely", "send it",
                  "yes to all", "yes, all of them", "yes to the rest", "yes both",
                  "yes TCS", "yes HDFCBANK too", "yes 7", "yes but make it 5", "yes?", "no", "not yes",
                  "yes, wait", "yes if it is under 1600"):
            self.assertFalse(self.yes(r), r)


class TicketShape(unittest.TestCase):
    def test_plain_words_and_tool_input(self):
        self.assertEqual(ticket.plain(INFY), "BUY 6 shares of INFY, limit Rs 1,612.50, delivery (CNC), good for today")
        self.assertEqual(ticket.estimate(INFY), "estimated Rs 9,675 + Rs 11.49 charges = Rs 9,686.49 out")
        sell = dict(INFY, transaction_type="SELL", quantity="1", product="MIS", variety="amo")
        self.assertEqual(ticket.plain(sell),
                         "SELL 1 share of INFY, limit Rs 1,612.50, intraday (MIS), good for today, after-market order")
        self.assertIn("Rs 9,663.51 in", ticket.estimate(sell))
        self.assertEqual(set(ticket.tool_input(INFY)), set(ticket.KITE_FIELDS) - {"trigger_price"})
        self.assertNotIn("est_value", ticket.tool_input(INFY))

    def test_fingerprint_is_shared_with_the_risk_check(self):
        with open(ORDERS_PATH) as fh:
            for o in json.load(fh)["orders"]:
                self.assertEqual(check.fingerprint(o), ticket.fingerprint(o))


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.risk = os.path.join(d, "risk.json")
        self.state = os.path.join(d, "broker.json")
        self.hol = os.path.join(d, "h.json")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, now="2026-10-26T10:01", orders=ORDERS_PATH):
        with redirect_stdout(io.StringIO()):
            return check.main(["--orders", orders, "--config", CFG_PATH, "--kite-dir", KDIR,
                               "--holidays", self.hol, "--now", now, "--out", self.risk])

    def t(self, cmd, *args, now="2026-10-26T10:02", orders=ORDERS_PATH):
        return run([cmd, "--orders", orders, "--risk", self.risk, "--state", self.state, "--now", now] + list(args))

    def test_risk_pass_then_one_yes_then_the_result(self):
        self.assertEqual(self.check(), 0)
        code, text, _ = self.t("show")
        self.assertEqual(code, 0)
        self.assertIn("ORDER 1 of 4: LIVE ORDER, real money, Zerodha Kite", text)
        self.assertIn("READY: trader-risk PASS", text)
        self.assertIn("\"tradingsymbol\": \"INFY\"", text)
        self.assertIn("not financial advice", text)

        code, text, _ = self.t("approve", "--index", "1", "--reply", "yes to all")
        self.assertEqual(code, 1)
        self.assertIn("Not recorded", text)
        code, text, _ = self.t("approve", "--index", "1", "--reply", "yes 6 INFY")
        self.assertEqual(code, 0)
        self.assertIn("place_order", text)
        code, _, err = self.t("approve", "--index", "1", "--reply", "yes")
        self.assertEqual(code, 1)
        self.assertIn("APPROVED by you", err)

        code, text, _ = self.t("result", "--index", "1", "--status", "placed", "--broker-id", "261026000123456")
        self.assertEqual(code, 0)
        code, text, _ = run(["log", "--state", self.state, "--now", "2026-10-26T10:05"])
        self.assertIn("approved  BUY 6 shares of INFY", text)
        self.assertIn("id 261026000123456", text)
        self.assertIn("1 placed today", text)
        with open(self.state) as fh:
            recs = json.load(fh)["orders"]
        self.assertEqual([(r["status"], r["symbol"], r["side"]) for r in recs],
                         [("approved", "INFY", "BUY"), ("placed", "INFY", "BUY")])
        self.assertIs(recs[0]["live"], True)

    def test_an_old_risk_check_is_not_ready(self):
        self.check()
        code, text, _ = self.t("show", "--index", "1", now="2026-10-26T10:12")
        self.assertEqual(code, 1)
        self.assertIn("NOT READY: the risk check is from 2026-10-26T10:01:00+05:30, 11 minutes ago", text)

    def test_a_changed_order_and_a_blocked_order_are_not_ready(self):
        self.check()
        with open(ORDERS_PATH) as fh:
            doc = json.load(fh)
        doc["orders"][0]["quantity"] = "7"
        changed = os.path.join(self.tmp.name, "orders.json")
        with open(changed, "w") as fh:
            json.dump(doc, fh)
        self.assertIn("was not in the last risk check", self.t("show", "--index", "1", orders=changed)[1])
        self.assertEqual(self.check(orders=changed), 1)
        code, text, _ = self.t("show", "--index", "1", "--json", orders=changed)
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED by trader-risk", json.loads(text)["status"])

    def test_result_needs_an_approval_and_decline_records_a_no(self):
        self.check()
        code, _, err = self.t("result", "--index", "2", "--status", "placed")
        self.assertEqual(code, 1)
        self.assertIn("no yes recorded", err)
        code, text, _ = self.t("decline", "--index", "2")
        self.assertEqual(code, 0)
        self.assertIn("Nothing was sent", text)
        self.assertIn("DONE: declined", self.t("show", "--index", "2")[1])


if __name__ == "__main__":
    unittest.main()
