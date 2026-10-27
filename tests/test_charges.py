import unittest

from _load import load

ch = load("trader-budget", "charges")


class Estimate(unittest.TestCase):
    def test_delivery_buy_and_sell(self):
        buy = ch.estimate("CNC", "BUY", 9675)
        self.assertEqual(buy, {"brokerage": 0.0, "stt": 9.68, "transaction": 0.3, "sebi": 0.01,
                               "stamp": 1.45, "dp": 0.0, "gst": 0.06, "total": 11.49})
        sell = ch.estimate("cnc", "sell", "9675")
        # Rs 10.04 of STT, exchange and SEBI charges + the Rs 13 DP charge + 18% GST on it (Rs 2.34)
        self.assertEqual((sell["stamp"], sell["dp"], sell["total"]), (0.0, 13.0, 25.38))

    def test_dp_charge_is_delivery_sells_only(self):
        self.assertEqual(ch.estimate("CNC", "BUY", 9675)["dp"], 0.0)
        self.assertEqual(ch.estimate("MIS", "SELL", 9675)["dp"], 0.0)
        self.assertEqual(ch.estimate("CNC", "SELL", 9675, {"dp_cnc_sell": "0"})["total"], 10.04)

    def test_intraday_brokerage_is_capped_at_rs_20(self):
        self.assertEqual(ch.estimate("MIS", "BUY", 9675)["brokerage"], 2.9)
        big = ch.estimate("MIS", "SELL", 100000)
        self.assertEqual((big["brokerage"], big["stt"], big["total"]), (20.0, 25.0, 52.34))

    def test_config_overrides(self):
        self.assertEqual(ch.estimate("CNC", "BUY", 9675, {"gst_pct": "0"})["total"], 11.43)
        with self.assertRaises(ch.ChargesError):
            ch.estimate("CNC", "BUY", 9675, {"gst": 0})
        with self.assertRaises(ch.ChargesError):
            ch.estimate("CNC", "BUY", 9675, {"gst_pct": "lots"})

    def test_unsupported_products_and_sides(self):
        with self.assertRaises(ch.ChargesError):
            ch.estimate("NRML", "BUY", 1000)
        with self.assertRaises(ch.ChargesError):
            ch.estimate("CNC", "HOLD", 1000)


if __name__ == "__main__":
    unittest.main()
