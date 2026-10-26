import datetime
import unittest

from _load import load

tax = load("trader-tax", "india_tax")

D = datetime.date


def g(kind, sold, gain):
    return {"kind": kind, "sold": sold, "gain": float(gain)}


class FinancialYear(unittest.TestCase):
    def test_april_to_march(self):
        self.assertEqual(tax.fy_of(D(2026, 3, 31)), "2025-26")
        self.assertEqual(tax.fy_of(D(2026, 4, 1)), "2026-27")
        self.assertEqual(tax.fy_of(D(2099, 12, 1)), "2099-00")


class Summarise(unittest.TestCase):
    def test_the_example_years(self):
        realised = [g("LTCG", D(2025, 3, 3), 3500), g("STCG", D(2025, 6, 2), -400), g("STCG", D(2026, 1, 10), 750),
                    g("LTCG", D(2026, 1, 12), 510), g("LTCG", D(2026, 5, 4), 900), g("LTCG", D(2026, 10, 26), 100)]
        spec = [g("SPECULATIVE", D(2025, 2, 3), -100), g("SPECULATIVE", D(2026, 5, 4), 20)]
        years = tax.summarise(realised, spec)
        self.assertEqual([y["fy"] for y in years], ["2024-25", "2025-26", "2026-27"])
        y24, y25, y26 = years
        self.assertIsNone(y24["estimate"])
        self.assertIn("no tax estimate for 2024-25", y24["notes"][0])
        self.assertEqual([(c["kind"], c["amount"], c["last_fy"]) for c in y24["carry_forward"]],
                         [("SPEC", 100.0, "2028-29")])
        self.assertEqual((y25["st_net"], y25["lt_net"], y25["estimate"]),
                         (350.0, 510.0, {"stcg": 70.0, "ltcg": 0.0, "total": 70.0}))
        self.assertEqual((y25["exemption_used"], y25["exemption_left"]), (510.0, 124490.0))
        self.assertEqual((y26["lt_net"], y26["speculative_net"], y26["exemption_left"]), (1000.0, 0.0, 124000.0))
        self.assertEqual([c["amount"] for c in y26["carry_forward"]], [80.0])
        self.assertIn("speculative loss carried from 2024-25: Rs 20 used against speculative income", y26["notes"])

    def test_set_off_order(self):
        y = tax.summarise([g("STCG", D(2026, 5, 1), 200), g("STCG", D(2026, 5, 2), -1000),
                           g("LTCG", D(2026, 5, 3), 5000)], [])[0]
        self.assertEqual((y["st_net"], y["lt_net"]), (0.0, 4200.0))
        self.assertIn("short-term loss Rs 800 set off against long-term gain", y["notes"])
        y = tax.summarise([g("STCG", D(2026, 5, 1), 1000), g("LTCG", D(2026, 5, 2), -500)], [])[0]
        self.assertEqual((y["st_net"], y["lt_net"], y["estimate"]["stcg"]), (1000.0, -500.0, 200.0))
        self.assertEqual([(c["kind"], c["amount"]) for c in y["carry_forward"]], [("LT", 500.0)])
        y = tax.summarise([g("STCG", D(2026, 5, 1), 1000)], [g("SPECULATIVE", D(2026, 5, 2), -400)])[0]
        self.assertEqual((y["st_net"], y["speculative_net"]), (1000.0, -400.0))

    def test_exemption_and_rates(self):
        y = tax.summarise([g("LTCG", D(2026, 5, 1), 200000)], [])[0]
        self.assertEqual((y["lt_taxable"], y["estimate"]["ltcg"], y["exemption_left"]), (75000.0, 9375.0, 0.0))
        y = tax.summarise([g("STCG", D(2026, 5, 1), 1000)], [], {"stcg_pct": "15"})[0]
        self.assertEqual(y["estimate"]["stcg"], 150.0)

    def test_carried_losses_are_used_oldest_first_and_expire(self):
        years = tax.summarise([g("STCG", D(2024, 5, 1), -1000), g("LTCG", D(2026, 5, 1), 600),
                               g("STCG", D(2027, 5, 1), 300)], [])
        self.assertEqual([y["fy"] for y in years], ["2024-25", "2026-27", "2027-28"])
        self.assertEqual((years[1]["lt_net"], years[1]["carry_forward"][0]["amount"]), (0.0, 400.0))
        self.assertEqual((years[2]["st_net"], years[2]["carry_forward"][0]["amount"]), (0.0, 100.0))
        late = tax.summarise([g("STCG", D(2024, 5, 1), -1000), g("STCG", D(2033, 5, 1), 300)], [])
        self.assertEqual([y["fy"] for y in late], ["2024-25", "2033-34"])
        self.assertEqual(late[1]["st_net"], 300.0)

    def test_bad_rules(self):
        for bad in ({"gst": 1}, {"stcg_pct": "nan"}, {"ltcg_pct": -1}, {"estimate_from_fy": "2025"}):
            with self.assertRaises(tax.TaxRuleError):
                tax.rules(bad)

    def test_nothing_realised(self):
        self.assertEqual(tax.summarise([], []), [])


if __name__ == "__main__":
    unittest.main()
