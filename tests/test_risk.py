import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

check = load("trader-risk", "check")
cal_mod = check.nse_calendar

CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
RDIR = os.path.join(FIX, "trader-risk")
KDIR = os.path.join(RDIR, "kite")
ORDERS_PATH = os.path.join(RDIR, "orders-example.json")
CAL = cal_mod.Calendar(dict(cal_mod.HOLIDAYS), cal_mod.YEARS)


def ist(text):
    return cal_mod.parse_now(text)


NOW = ist("2026-10-26T10:01")


def cfg(**over):
    with open(CFG_PATH) as fh:
        c = json.load(fh)
    c.update(over)
    return c


def example_orders():
    with open(ORDERS_PATH) as fh:
        return json.load(fh)["orders"]


def data(now=NOW, **over):
    d = check.load_data(KDIR, now)
    d.update(copy.deepcopy(over))
    return d


MISSING = object()


def order(sym="INFY", side="BUY", qty="6", price="1612.50", product="CNC", **over):
    o = {"exchange": "NSE", "tradingsymbol": sym, "transaction_type": side, "quantity": qty, "product": product,
         "order_type": "LIMIT", "price": price, "validity": "DAY", "variety": "regular",
         "est_charges": "0.00"}
    o.update(over)
    o = {k: v for k, v in o.items() if v is not MISSING}
    return o


def run_check(orders, c=None, d=None, now=NOW):
    return check.check(orders, c if c is not None else cfg(), d if d is not None else data(now), now, CAL)


def why(res, i=0):
    return " | ".join(res["results"][i]["reasons"])


def verdicts(res):
    return [r["verdict"] for r in res["results"]]


class Example(unittest.TestCase):
    def test_the_example_orders_pass_on_the_example_account(self):
        res = run_check(example_orders())
        self.assertEqual(verdicts(res), ["PASS"] * 4, [r["reasons"] for r in res["results"]])
        self.assertEqual(res["cash_after"], 21411.62)
        self.assertIs(res["live"], True)
        self.assertEqual(res["results"][0]["amount"], "6 x Rs 1,612.50 = Rs 9,675")
        self.assertIn("LIVE", res["warnings"][0])
        self.assertEqual(res["date"], "2026-10-26")

    def test_a_fifth_order_hits_the_daily_limit_and_is_a_duplicate(self):
        res = run_check(example_orders() + [order(qty="1")])
        self.assertEqual(verdicts(res), ["PASS"] * 4 + ["BLOCK"])
        self.assertIn("daily limit: 1 orders in Kite's order book today plus 4 passed", why(res, 4))
        self.assertIn("duplicate:", why(res, 4))


class Format(unittest.TestCase):
    def test_each_malformed_order_is_blocked(self):
        cases = [
            (order(sym="INFY.NS"), "format: tradingsymbol must be the bare NSE symbol"),
            (order(exchange="BSE"), "asset: only NSE"),
            (order(sym="NIFTY26OCTFUT"), "F&O contract"),
            (order(sym="NIFTY26OCT25000CE"), "F&O contract"),
            (order(qty="1.5"), "format: quantity must be a whole number"),
            (order(qty="0"), "format: quantity"),
            (order(side="HOLD"), "format: transaction_type"),
            (order(order_type="SL"), "stop-loss"),
            (order(price=None), "a LIMIT order needs a price"),
            (order(validity="IOC"), "validity must be DAY"),
            (order(variety="co"), "variety must be regular"),
            (order(product="NRML"), "product: 'NRML' is not supported"),
        ]
        for o, text in cases:
            res = run_check([o])
            self.assertEqual(verdicts(res), ["BLOCK"], o)
            self.assertIn(text, why(res), o)

    def test_numbers_should_be_strings(self):
        res = run_check([order(qty=6)])
        self.assertEqual(verdicts(res), ["PASS"])
        self.assertIn("send quantity as a string", res["results"][0]["warnings"][0])

    def test_blocked_list(self):
        self.assertIn("blocked: INFY", why(run_check([order()], cfg(blocked=["INFY"]))))


class Hours(unittest.TestCase):
    def test_closed_market_blocks_unless_amo_is_allowed(self):
        late = ist("2026-10-26T15:30")
        d = data()
        res = run_check([order()], d=d, now=late)
        self.assertIn("hours: NSE is closed (after the close", why(res))
        res = run_check([order(variety="amo")], cfg(allow_amo=True), d, late)
        self.assertNotIn("hours:", why(res))
        self.assertIn("hours: an amo", why(run_check([order(variety="amo")], cfg(allow_amo=True))))

    def test_holiday_and_unknown_year(self):
        diwali = ist("2026-11-10T10:00")
        self.assertIn("Diwali-Balipratipada", why(run_check([order()], d=data(), now=diwali)))
        later = ist("2027-01-04T10:00")
        self.assertIn("holiday list for 2027 is not loaded", why(run_check([order()], d=data(), now=later)))


class Price(unittest.TestCase):
    def test_market_orders_are_off_by_default(self):
        mkt = order(order_type="MARKET", price=None)
        self.assertIn("price: MARKET orders are off", why(run_check([mkt])))
        self.assertEqual(verdicts(run_check([mkt], cfg(allow_market_orders=True))), ["PASS"])

    def test_limit_far_from_the_last_price(self):
        res = run_check([order(price="1700")])
        self.assertIn("price: limit Rs 1,700 is 5.43% from the last price Rs 1,612.50, over your 2% limit", why(res))

    def test_circuit_band(self):
        res = run_check([order(qty="5", price="1800")], cfg(max_limit_deviation_pct="20"))
        self.assertIn("price: Rs 1,800 is outside today's circuit band Rs 1,451.25 to Rs 1,773.75", why(res))

    def test_no_quote_for_the_symbol(self):
        self.assertIn("data: no fresh Kite quote for NSE:ITC", why(run_check([order(sym="ITC", price="400")])))


class Size(unittest.TestCase):
    def test_min_and_max(self):
        self.assertIn("size: Rs 16,125 is over your Rs 10,000 max order", why(run_check([order(qty="10")])))
        self.assertIn("under your Rs 2,000 minimum", why(run_check([order(qty="1")], cfg(min_order_value="2000"))))


class Cash(unittest.TestCase):
    def test_buffer_and_not_enough_cash(self):
        small = {"equity": {"net": 10000.0, "available": {"cash": 10000.0, "live_balance": 10000.0}}}
        res = run_check([order(est_charges="11.49")], d=data(margins=small))
        self.assertIn("cash: leaves Rs 313.51, under your 10% buffer of Rs 1,280.46", why(res))
        tiny = {"equity": {"net": 5000.0, "available": {"live_balance": 5000.0}}}
        self.assertIn("cash: needs Rs 9,686.49 with charges but only Rs 5,000 is available",
                      why(run_check([order(est_charges="11.49")], d=data(margins=tiny))))

    def test_position_cap(self):
        lots = [{"tradingsymbol": "RELIANCE", "exchange": "NSE", "quantity": 10, "t1_quantity": 0,
                 "last_price": 1402.3}]
        res = run_check([order("RELIANCE", qty="7", price="1402.30")], d=data(holdings=lots))
        self.assertIn("position: RELIANCE would be Rs 23,839.10", why(res))


class Short(unittest.TestCase):
    def test_delivery_sale_needs_the_shares(self):
        self.assertIn("short: selling 3 RELIANCE but you hold 2",
                      why(run_check([order("RELIANCE", "SELL", "3", "1402.30")])))
        self.assertEqual(verdicts(run_check([order("RELIANCE", "SELL", "2", "1402.30")])), ["PASS"])


class Intraday(unittest.TestCase):
    def mis(self, **over):
        return order(product="MIS", **over)

    def test_mis_is_off_by_default(self):
        self.assertIn("product: MIS (intraday) is off", why(run_check([self.mis()])))

    def test_mis_rules_when_allowed(self):
        on = cfg(allow_mis=True)
        self.assertEqual(verdicts(run_check([self.mis()], on)), ["PASS"])
        late = ist("2026-10-26T15:00")
        self.assertIn("intraday: no new MIS positions after 15:00 IST",
                      why(run_check([self.mis()], on, data(), late)))
        self.assertIn("short: this MIS sell would leave you short 6 INFY",
                      why(run_check([self.mis(transaction_type="SELL")], on)))
        self.assertEqual(verdicts(run_check([self.mis(transaction_type="SELL")], cfg(allow_mis=True, allow_short=True))),
                         ["PASS"])
        small = {"equity": {"net": 10000.0, "available": {"live_balance": 10000.0}}}
        self.assertIn("intraday: MIS exposure would be Rs 9,675, over 50% of your Rs 10,000 equity margin",
                      why(run_check([self.mis()], on, data(margins=small))))
        losing = {"net": [], "day": [{"tradingsymbol": "TCS", "product": "MIS", "quantity": 0, "pnl": -2500.0}]}
        self.assertIn("intraday: today's loss Rs 2,500 has reached your Rs 2,000 daily loss limit",
                      why(run_check([self.mis()], on, data(positions=losing))))

    def test_selling_past_the_position_opens_a_short(self):
        held = {"net": [{"tradingsymbol": "INFY", "product": "MIS", "quantity": 4, "last_price": 1612.5}], "day": []}
        res = run_check([self.mis(transaction_type="SELL")], cfg(allow_mis=True), data(positions=held))
        self.assertIn("short: this MIS sell would leave you short 2 INFY", why(res))

    def test_closing_an_mis_position_after_the_cutoff_is_allowed(self):
        held = {"net": [{"tradingsymbol": "INFY", "product": "MIS", "quantity": 6, "last_price": 1612.5}], "day": []}
        late = ist("2026-10-26T15:10")
        res = run_check([self.mis(transaction_type="SELL")], cfg(allow_mis=True),
                        data(positions=held), late)
        self.assertEqual(verdicts(res), ["PASS"], why(res))


class Data(unittest.TestCase):
    def test_missing_and_stale_snapshots_block(self):
        d = data(margins="no margins snapshot in trader/kite: call the Kite connector for margins")
        self.assertIn("data: no margins snapshot", why(run_check([order()], d=d)))
        stale = run_check(example_orders(), d=data(now=ist("2026-10-26T10:03")), now=ist("2026-10-26T10:03"))
        self.assertEqual(verdicts(stale), ["BLOCK"] * 4)
        self.assertIn("data: the quotes snapshot is", why(stale))

    def test_a_missing_snapshot_only_blocks_the_rules_that_need_it(self):
        d = data(positions="no positions snapshot in trader/kite: call the Kite connector for positions")
        self.assertIn("data: no positions snapshot", why(run_check([order()], d=d)))
        self.assertIn("data: no positions snapshot", why(run_check([order(product="MIS")], cfg(allow_mis=True), d)))
        d = data(margins="no margins snapshot in trader/kite: call the Kite connector for margins")
        self.assertEqual(verdicts(run_check([order("RELIANCE", "SELL", "2", "1402.30")], d=d)), ["PASS"])

    def test_a_us_shaped_order_is_blocked_not_crashed(self):
        us = {"symbol": "AAPL", "side": "buy", "notional": "1250", "type": "market", "time_in_force": "day"}
        res = run_check([us])
        self.assertEqual(verdicts(res), ["BLOCK"])
        for text in ("format: no tradingsymbol", "asset: only NSE", "format: transaction_type",
                     "format: quantity", "format: order_type"):
            self.assertIn(text, why(res))

    def test_config_problems(self):
        self.assertIn("ignored US-era config keys: paper",
                      " ".join(run_check([order()], cfg(paper=True))["warnings"]))
        with self.assertRaises(check.RiskError):
            run_check([order()], cfg(mis_cutoff="3pm"))
        with self.assertRaises(check.RiskError):
            run_check([order()], cfg(max_order_value="lots"))

    def test_fingerprint_covers_the_kite_fields_only(self):
        o = order()
        self.assertEqual(check.fingerprint(o), check.fingerprint(dict(o, why="x", est_value="1", est_charges="2")))
        self.assertNotEqual(check.fingerprint(o), check.fingerprint(dict(o, quantity="7")))


class OpenOrders(unittest.TestCase):
    def run_with(self, orders, *rows):
        base = {"order_id": "1", "status": "OPEN", "exchange": "NSE", "product": "CNC"}
        return run_check(orders, d=data(orders=[dict(base, **r) for r in rows]))

    def sell(self, qty, **over):
        return dict({"tradingsymbol": "RELIANCE", "transaction_type": "SELL", "quantity": qty, "filled_quantity": 0}, **over)

    def test_an_open_sell_reduces_what_can_be_sold_and_is_a_duplicate(self):
        res = self.run_with([order("RELIANCE", "SELL", "1", "1402.30")], self.sell(2))
        self.assertEqual(verdicts(res), ["BLOCK"])
        self.assertIn("short: selling 1 RELIANCE but you hold 2 and 2 are already in open sell orders", why(res))
        self.assertIn("duplicate: an open SELL RELIANCE CNC order is already in Kite's order book; "
                      "wait for it to fill or cancel it", why(res))

    def test_a_part_filled_open_sell_leaves_only_the_pending_shares(self):
        res = self.run_with([order("RELIANCE", "SELL", "1", "1402.30")], self.sell(2, filled_quantity=1))
        self.assertEqual(verdicts(res), ["BLOCK"])
        self.assertNotIn("short:", why(res))
        self.assertIn("duplicate: an open SELL RELIANCE CNC", why(res))
        res = self.run_with([order("RELIANCE", "SELL", "2", "1402.30")], self.sell(5, filled_quantity=0, pending_quantity=1))
        self.assertIn("and 1 are already in open sell orders", why(res))

    def test_an_open_mis_sell_does_not_reduce_cnc_availability(self):
        res = self.run_with([order("RELIANCE", "SELL", "2", "1402.30")], self.sell(1, product="MIS"))
        self.assertEqual(verdicts(res), ["PASS"], why(res))

    def test_a_duplicate_needs_the_same_product(self):
        buy = {"tradingsymbol": "INFY", "transaction_type": "BUY", "quantity": 6, "filled_quantity": 0}
        res = self.run_with([order("INFY", "BUY", "6")], buy)
        self.assertEqual(verdicts(res), ["BLOCK"])
        self.assertIn("duplicate: an open BUY INFY CNC order is already in Kite's order book", why(res))
        res = self.run_with([order("INFY", "BUY", "6")], dict(buy, product="MIS"))
        self.assertEqual(verdicts(res), ["PASS"], why(res))

    def test_finished_orders_are_not_open(self):
        rows = [self.sell(2, status=s) for s in ("COMPLETE", "REJECTED", "cancelled")]
        res = self.run_with([order("RELIANCE", "SELL", "2", "1402.30")], *rows)
        self.assertEqual(verdicts(res), ["PASS"], why(res))

    def test_an_open_order_without_a_usable_quantity_is_a_data_error(self):
        res = self.run_with([order()], self.sell("lots"))
        self.assertEqual(verdicts(res), ["BLOCK"])
        self.assertIn("data: the orders snapshot has an order without a usable quantity", why(res))
        res = self.run_with([order()], self.sell(2, pending_quantity="x"))
        self.assertIn("data: the orders snapshot has an order without a usable quantity", why(res))


class Cli(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = check.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_writes_the_verdicts(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "risk.json")
            code, text, _ = self.run_main(["--orders", ORDERS_PATH, "--config", CFG_PATH, "--kite-dir", KDIR,
                                           "--holidays", os.path.join(d, "h.json"), "--now", "2026-10-26T10:01",
                                           "--out", out])
            self.assertEqual(code, 0, text)
            self.assertIn("PASS  #1 BUY INFY CNC 6 x Rs 1,612.50 = Rs 9,675", text)
            self.assertIn("LIVE account, real money", text)
            self.assertIn("not financial advice", text)
            with open(out) as fh:
                rec = json.load(fh)
            self.assertEqual(rec["checked_at"], "2026-10-26T10:01:00+05:30")
            self.assertEqual(len(rec["results"]), 4)

    def test_blocked_and_broken_runs_exit_1(self):
        with tempfile.TemporaryDirectory() as d:
            base = ["--config", CFG_PATH, "--kite-dir", KDIR, "--holidays", os.path.join(d, "h.json"), "--no-write"]
            code, text, _ = self.run_main(["--orders", ORDERS_PATH, "--now", "2026-10-26T16:00"] + base)
            self.assertEqual(code, 1)
            self.assertIn("BLOCK #1", text)
            code, _, err = self.run_main(["--orders", os.path.join(d, "none.json")] + base)
            self.assertEqual(code, 1)
            self.assertIn("no orders file", err)


class FailOpen(unittest.TestCase):
    def test_switches_must_be_real_booleans(self):
        for k, v in (("allow_mis", "false"), ("allow_market_orders", "no"), ("allow_short", 0), ("allow_amo", None)):
            with self.assertRaises(check.RiskError, msg=k):
                run_check([order()], cfg(**{k: v}))
        try:
            run_check([order()], cfg(allow_mis="false"))
        except check.RiskError as e:
            self.assertIn("config allow_mis must be true or false without quotes, got 'false'", str(e))

    def test_numbers_must_be_finite_and_zero_warns(self):
        with self.assertRaises(check.RiskError):
            run_check([order()], cfg(max_order_value="nan"))
        with self.assertRaises(check.RiskError):
            run_check([order()], cfg(cash_buffer_pct="inf"))
        res = run_check([order(qty="10")], cfg(max_order_value="0", max_position_pct="50"))
        self.assertEqual(verdicts(res), ["PASS"], why(res))
        self.assertIn("max_order_value is 0: no per-order cap", res["warnings"])
        res = run_check([order()], cfg(max_orders_per_day=0, daily_loss_limit="0"))
        self.assertIn("max_orders_per_day is 0: no daily order limit", res["warnings"])
        self.assertIn("daily_loss_limit is 0: no daily loss limit", res["warnings"])

    def test_bad_snapshot_shapes_block(self):
        odd = {"commodity": {"net": 1.0}}
        self.assertIn("data: the margins snapshot", why(run_check([order()], d=data(margins=odd))))
        self.assertIn("data: the margins snapshot", why(run_check([order(product="MIS")], cfg(allow_mis=True),
                                                                  data(margins=odd))))
        nonet = {"equity": {"available": {"live_balance": 5000.0}}}
        self.assertIn("data: the margins snapshot", why(run_check([order()], d=data(margins=nonet))))
        self.assertIn("data: the holdings snapshot",
                      why(run_check([order("RELIANCE", "SELL", "1", "1402.30")], d=data(holdings={"x": 1}))))
        self.assertIn("data: the positions snapshot",
                      why(run_check([order()], d=data(positions={"net": "x", "day": []}))))
        self.assertIn("data: the orders snapshot", why(run_check([order()], d=data(orders={"x": 1}))))

    def test_non_finite_quantity_is_a_format_block(self):
        for q in ("nan", "inf"):
            res = run_check([order(qty=q)])
            self.assertEqual(verdicts(res), ["BLOCK"])
            self.assertIn("format: quantity", why(res))

    def test_todays_delivery_trades_count_as_held(self):
        pos = {"net": [{"tradingsymbol": "RELIANCE", "product": "CNC", "quantity": 10, "last_price": 1402.3}],
               "day": []}
        big = cfg(max_order_value="20000")
        d = data(positions=pos)
        self.assertEqual(verdicts(run_check([order("RELIANCE", "SELL", "12", "1402.30")], big, d)), ["PASS"])
        res = run_check([order("RELIANCE", "SELL", "13", "1402.30")], big, d)
        self.assertIn("you hold 12", why(res))
        res = run_check([order("RELIANCE", qty="7", price="1402.30")], d=d)
        self.assertIn("position: RELIANCE would be Rs 26,643.70", why(res))

    def test_blocked_must_be_a_list(self):
        with self.assertRaises(check.RiskError):
            run_check([order()], cfg(blocked="INFY"))

    def test_a_failed_run_leaves_no_earlier_pass_behind(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "risk.json")
            with open(out, "w") as fh:
                fh.write("{}")
            code = io.StringIO()
            with redirect_stdout(code), redirect_stderr(code):
                rc = check.main(["--orders", os.path.join(d, "none.json"), "--config", CFG_PATH,
                                 "--kite-dir", KDIR, "--holidays", os.path.join(d, "h.json"), "--out", out])
            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(out))


class FinalReview(unittest.TestCase):
    def test_no_same_batch_credit_for_a_short_sale(self):
        on = cfg(allow_mis=True)
        res = run_check([order(product="MIS", qty="5"), order(product="MIS", side="SELL", qty="5")], on)
        self.assertEqual(verdicts(res), ["PASS", "BLOCK"])
        self.assertIn("short:", why(res, 1))

    def test_same_batch_buy_is_not_held_for_a_delivery_sale(self):
        res = run_check([order("RELIANCE", qty="1", price="1402.30"),
                         order("RELIANCE", "SELL", "3", "1402.30")])
        self.assertEqual(verdicts(res)[1], "BLOCK")
        self.assertIn("short:", why(res, 1))

    def test_blocked_list_is_normalised(self):
        for entry in ("NSE:INFY", "infy.ns", " Infy "):
            self.assertIn("blocked: INFY", why(run_check([order()], cfg(blocked=[entry]))), entry)
        with self.assertRaises(check.RiskError):
            run_check([order()], cfg(blocked=["BSE:INFY"]))

    def test_nan_price_and_missing_circuits(self):
        raw = {"NSE:INFY": {"last_price": float("nan"), "upper_circuit_limit": 1773.75,
                            "lower_circuit_limit": 1451.25}}
        res = run_check([order()], d=data(quotes=check.kite_snapshot.quotes(raw)))
        self.assertIn("data: no fresh Kite quote", why(res))
        raw = {"NSE:INFY": {"last_price": 1612.5}}
        res = run_check([order()], d=data(quotes=check.kite_snapshot.quotes(raw)))
        self.assertEqual(verdicts(res), ["BLOCK"])
        self.assertIn("data: the Kite quote for NSE:INFY has no circuit limits; use the full quotes call",
                      why(res))

    def test_orders_per_day_is_a_whole_number(self):
        with self.assertRaises(check.RiskError):
            run_check([order()], cfg(max_orders_per_day=0.5))

    def test_positions_need_net_and_day(self):
        for pos in ({"net": []}, {"day": []}):
            res = run_check([order()], d=data(positions=pos))
            self.assertIn("data: the positions snapshot", why(res))

    def test_est_charges_are_required(self):
        for bad in (MISSING, "-1", "abc", None, True):
            res = run_check([order(est_charges=bad)])
            self.assertEqual(verdicts(res), ["BLOCK"], bad)
            self.assertIn("format: est_charges must be a rupee amount of at least 0 (trader-budget writes it)",
                          why(res), bad)

    def test_no_write_removes_an_old_pass(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "risk.json")
            with open(out, "w") as fh:
                fh.write('{"block": 0}')
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                check.main(["--orders", ORDERS_PATH, "--config", CFG_PATH, "--kite-dir", KDIR,
                            "--holidays", os.path.join(d, "h.json"), "--now", "2026-10-26T10:01",
                            "--out", out, "--no-write"])
            self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
