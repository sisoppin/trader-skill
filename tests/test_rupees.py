import unittest

from _load import load

ru = load("trader-alerts", "rupees")


class Inr(unittest.TestCase):
    def test_indian_grouping(self):
        self.assertEqual(ru.inr(125000), "Rs 1,25,000")
        self.assertEqual(ru.inr(1612.5), "Rs 1,612.50")
        self.assertEqual(ru.inr(1234567.891), "Rs 12,34,567.89")
        self.assertEqual(ru.inr(999), "Rs 999")
        self.assertEqual(ru.inr(-950), "-Rs 950")
        self.assertEqual(ru.inr(0.5), "Rs 0.50")
        self.assertEqual(ru.inr("10000"), "Rs 10,000")


if __name__ == "__main__":
    unittest.main()
