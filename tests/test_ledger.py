import datetime
import os
import unittest

from _load import load, FIX

tb = load("trader-tax", "tradebook")
ledger = load("trader-tax", "ledger")

TDIR = os.path.join(FIX, "trader-tax")
D = datetime.date


def all_trades():
    import json
    book, _ = tb.read_tradebook(os.path.join(TDIR, "tradebook-sample.csv"))
    with open(os.path.join(TDIR, "kite", "trades.json")) as fh:
        kite = tb.kite_trades(json.load(fh)["data"])
    return tb.merge(tb.read_lots(os.path.join(TDIR, "lots.csv")), book, kite)


def trade(d, sym, side, qty, price, tid):
    return {"date": d, "symbol": sym, "side": side, "qty": qty, "price": price, "id": tid, "source": "t"}


class Terms(unittest.TestCase):
    def test_more_than_twelve_months_is_long_term(self):
        self.assertEqual(ledger.term(D(2025, 1, 10), D(2026, 1, 10)), "STCG")
        self.assertEqual(ledger.term(D(2025, 1, 10), D(2026, 1, 11)), "LTCG")
        self.assertEqual(ledger.anniversary(D(2024, 2, 29)), D(2025, 2, 28))
        self.assertEqual(ledger.term(D(2024, 2, 29), D(2025, 2, 28)), "STCG")
        self.assertEqual(ledger.term(D(2024, 2, 29), D(2025, 3, 1)), "LTCG")


class Build(unittest.TestCase):
    def setUp(self):
        self.book = ledger.build(all_trades(), {"INFY": 1150.0})

    def test_realised_gains_by_kind(self):
        got = [(g["symbol"], g["kind"], g["sold"], g["qty"], g["gain"]) for g in self.book["realised"]]
        self.assertEqual(got, [
            ("TCS", "LTCG", D(2025, 3, 3), 5, 3500.0),
            ("HDFCBANK", "STCG", D(2025, 6, 2), 4, -400.0),
            ("RELIANCE", "STCG", D(2026, 1, 10), 5, 750.0),
            ("RELIANCE", "LTCG", D(2026, 1, 12), 3, 510.0),
            ("INFY", "LTCG", D(2026, 5, 4), 2, 900.0),
            ("HDFCBANK", "LTCG", D(2026, 10, 26), 2, 100.0),
        ])
        infy = self.book["realised"][4]
        self.assertTrue(infy["grandfathered"])
        self.assertEqual(infy["buy_price"], 1150.0)

    def test_same_day_buy_and_sell_is_intraday(self):
        got = [(g["symbol"], g["sold"], g["qty"], g["gain"]) for g in self.book["speculative"]]
        self.assertEqual(got, [("ITC", D(2025, 2, 3), 20, -100.0), ("INFY", D(2026, 5, 4), 2, 20.0)])

    def test_open_lots(self):
        lots = {s: [(l["date"], l["qty"]) for l in ls] for s, ls in self.book["lots"].items()}
        self.assertEqual(lots, {"INFY": [(D(2017, 6, 15), 8)], "HDFCBANK": [(D(2024, 7, 10), 4)],
                                "RELIANCE": [(D(2025, 1, 10), 2)], "TCS": [(D(2026, 8, 3), 3)]})
        self.assertEqual(self.book["problems"], [])


class Rules(unittest.TestCase):
    def test_2018_rule_is_capped_at_the_sale_price_and_never_below_cost(self):
        old = [trade(D(2017, 6, 15), "INFY", "BUY", 10, 480.0, "a")]
        high = ledger.build(old + [trade(D(2026, 5, 4), "INFY", "SELL", 1, 1000.0, "b")], {"INFY": 1150.0})
        self.assertEqual(high["realised"][0]["gain"], 0.0)
        low = ledger.build(old + [trade(D(2026, 5, 4), "INFY", "SELL", 1, 1000.0, "b")], {"INFY": 300.0})
        self.assertEqual((low["realised"][0]["gain"], low["realised"][0]["grandfathered"]), (520.0, False))
        none = ledger.build(old + [trade(D(2026, 5, 4), "INFY", "SELL", 1, 1000.0, "b")], {})
        self.assertIn("no 31 Jan 2018 price for INFY", none["problems"][0])

    def test_fifo_across_lots_and_overselling(self):
        t = [trade(D(2025, 1, 1), "TCS", "BUY", 2, 3000.0, "a"), trade(D(2025, 6, 1), "TCS", "BUY", 2, 3500.0, "b"),
             trade(D(2026, 3, 1), "TCS", "SELL", 5, 4000.0, "c")]
        book = ledger.build(t)
        self.assertEqual([(g["kind"], g["qty"], g["gain"]) for g in book["realised"]],
                         [("LTCG", 2, 2000.0), ("STCG", 2, 1000.0)])
        self.assertIn("sold 1 more TCS on 2026-03-01", book["problems"][0])

    def test_what_if(self):
        lots = ledger.build(all_trades(), {"INFY": 1150.0})["lots"]
        gains, short = ledger.what_if(lots["INFY"], 3, 1612.5, D(2026, 10, 26), {"INFY": 1150.0})
        self.assertEqual(([(g["kind"], g["gain"], g["grandfathered"]) for g in gains], short),
                         ([("LTCG", 1387.5, True)], 0))
        self.assertEqual(ledger.what_if(lots["INFY"], 20, 1612.5, D(2026, 10, 26))[1], 12)
        self.assertEqual(lots["INFY"][0]["qty"], 8)



class SaleEffect(unittest.TestCase):
    def test_a_sale_today_is_matched_intraday_first(self):
        trades = [trade(D(2024, 1, 2), "X", "BUY", 10, 100.0, "A"), trade(D(2026, 10, 26), "X", "BUY", 10, 150.0, "B")]
        gains, short = ledger.sale_effect(trades, "X", 10, 140.0, D(2026, 10, 26))
        self.assertEqual(short, 0)
        self.assertEqual([(g["kind"], g["qty"], g["gain"]) for g in gains], [("SPECULATIVE", 10, -100.0)])
        gains, short = ledger.sale_effect(trades, "X", 15, 140.0, D(2026, 10, 26))
        self.assertEqual(sorted((g["kind"], g["qty"], g["gain"]) for g in gains),
                         [("LTCG", 5, 200.0), ("SPECULATIVE", 10, -100.0)])
        self.assertEqual(ledger.sale_effect(trades, "X", 25, 140.0, D(2026, 10, 26))[1], 5)

    def test_an_earlier_intraday_trade_today_is_not_counted_twice(self):
        trades = [trade(D(2024, 1, 2), "X", "BUY", 10, 100.0, "A"), trade(D(2026, 10, 26), "X", "BUY", 10, 150.0, "B"),
                  trade(D(2026, 10, 26), "X", "SELL", 4, 160.0, "C")]
        gains, short = ledger.sale_effect(trades, "X", 6, 140.0, D(2026, 10, 26))
        self.assertEqual(short, 0)
        self.assertEqual([(g["kind"], g["qty"], g["gain"]) for g in gains], [("SPECULATIVE", 6, -60.0)])

    def test_no_trade_today_is_plain_fifo(self):
        trades = [trade(D(2024, 1, 2), "X", "BUY", 10, 100.0, "A"), trade(D(2026, 6, 1), "X", "BUY", 10, 150.0, "B"),
                  trade(D(2025, 1, 2), "Y", "BUY", 1, 10.0, "C")]
        gains, short = ledger.sale_effect(trades, "X", 12, 140.0, D(2026, 10, 26))
        self.assertEqual([(g["kind"], g["qty"], g["gain"]) for g in gains], [("LTCG", 10, 400.0), ("STCG", 2, -20.0)])
        self.assertEqual(short, 0)


if __name__ == "__main__":
    unittest.main()
