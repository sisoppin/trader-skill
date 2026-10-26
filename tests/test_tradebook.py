import datetime
import json
import os
import tempfile
import unittest

from _load import load, FIX

tb = load("trader-tax", "tradebook")

TDIR = os.path.join(FIX, "trader-tax")
BOOK = os.path.join(TDIR, "tradebook-sample.csv")
HEADER = "symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,trade_id,order_id,order_execution_time\n"


def write(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w") as fh:
        fh.write(text)
    return p


class Tradebook(unittest.TestCase):
    def test_reads_the_console_csv(self):
        trades, skipped = tb.read_tradebook(BOOK)
        self.assertEqual((len(trades), skipped), (12, 1))
        self.assertEqual(trades[0], {"date": datetime.date(2024, 3, 1), "symbol": "TCS", "side": "BUY", "qty": 5,
                                     "price": 3400.0, "id": "T1", "source": "tradebook-sample.csv"})
        self.assertEqual({t["side"] for t in trades}, {"BUY", "SELL"})

    def test_not_a_tradebook(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "x.csv", "symbol,quantity\nINFY,1\n")
            with self.assertRaises(tb.TradeError) as e:
                tb.read_tradebook(p)
            self.assertIn("no trade_date", str(e.exception))

    def test_bad_rows_name_the_line(self):
        rows = {
            "TCS,,2024-03-01,NSE,EQ,EQ,buy,false,1.5,3400,T1,O1,\n": "quantity must be a whole number",
            "TCS,,2024-03-01,NSE,EQ,EQ,buy,false,1,0,T1,O1,\n": "price must be a rupee amount",
            "TCS,,2024-03-01,NSE,EQ,EQ,hold,false,1,3400,T1,O1,\n": "trade_type must be buy or sell",
            "TCS,,yesterday,NSE,EQ,EQ,buy,false,1,3400,T1,O1,\n": "is not a date",
            "TCS,,2024-03-01,NSE,EQ,EQ,buy,false,nan,3400,T1,O1,\n": "quantity must be a whole number",
        }
        with tempfile.TemporaryDirectory() as d:
            for row, text in rows.items():
                p = write(d, "b.csv", HEADER + row)
                with self.assertRaises(tb.TradeError) as e:
                    tb.read_tradebook(p)
                self.assertIn("b.csv line 2", str(e.exception))
                self.assertIn(text, str(e.exception))

    def test_dd_mm_yyyy_dates(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "b.csv", HEADER + "TCS,,01-03-2024,NSE,EQ,EQ,BUY,false,1,3400,T1,O1,\n")
            self.assertEqual(tb.read_tradebook(p)[0][0]["date"], datetime.date(2024, 3, 1))


class OtherSources(unittest.TestCase):
    def test_kite_trades(self):
        with open(os.path.join(TDIR, "kite", "trades.json")) as fh:
            data = json.load(fh)["data"]
        data.append({"trade_id": "B1", "exchange": "BSE", "tradingsymbol": "INFY", "transaction_type": "BUY",
                     "quantity": 1, "average_price": 1600, "fill_timestamp": "2026-10-26 10:00:00"})
        self.assertEqual(tb.kite_trades(data), [{"date": datetime.date(2026, 10, 26), "symbol": "HDFCBANK",
                                                 "side": "SELL", "qty": 2, "price": 1650.0, "id": "K1",
                                                 "source": "kite"}])

    def test_lots_and_fmv(self):
        lots = tb.read_lots(os.path.join(TDIR, "lots.csv"))
        self.assertEqual([(t["date"], t["symbol"], t["side"], t["qty"], t["price"]) for t in lots],
                         [(datetime.date(2017, 6, 15), "INFY", "BUY", 10, 480.0)])
        self.assertEqual(tb.read_fmv(os.path.join(TDIR, "fmv_2018.csv")), {"INFY": 1150.0})
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(tb.TradeError):
                tb.read_lots(write(d, "l.csv", "symbol,quantity\nINFY,1\n"))

    def test_merge_dedupes_by_trade_id_and_keeps_day_order(self):
        a = [{"date": datetime.date(2026, 5, 4), "id": "T10", "side": "SELL"},
             {"date": datetime.date(2026, 5, 4), "id": "T11", "side": "BUY"}]
        b = [{"date": datetime.date(2026, 1, 1), "id": "T1", "side": "BUY"}, dict(a[0], side="BUY")]
        merged = tb.merge(a, b)
        self.assertEqual([(t["id"], t["side"]) for t in merged], [("T1", "BUY"), ("T10", "SELL"), ("T11", "BUY")])


if __name__ == "__main__":
    unittest.main()
