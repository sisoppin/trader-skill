import datetime
import json
import os
import tempfile
import unittest

from _load import load, FIX

cal = load("trader-alerts", "nse_calendar")

MASTER = os.path.join(FIX, "trader-alerts", "nse-holiday-master.json")


def ist(text):
    return cal.parse_now(text)


def hm(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


class Time(unittest.TestCase):
    def test_parse_now(self):
        t = ist("2026-10-26T09:15")
        self.assertEqual(t.utcoffset(), datetime.timedelta(hours=5, minutes=30))
        self.assertEqual(hm(t), "2026-10-26 09:15")
        self.assertEqual(ist("2026-10-26T03:45:00Z"), t)
        self.assertEqual(hm(ist("2026-10-26T00:00:00-04:00")), "2026-10-26 09:30")
        self.assertIsNotNone(cal.parse_now().tzinfo)
        with self.assertRaises(cal.CalendarError):
            ist("tomorrow")


class Holidays(unittest.TestCase):
    def test_bundled_list_matches_the_nse_master(self):
        with open(MASTER) as fh:
            self.assertEqual(cal.parse_holiday_master(json.load(fh)), cal.HOLIDAYS)
        self.assertEqual(cal.HOLIDAYS["2026-11-08"], "Diwali Laxmi Pujan")

    def test_bad_master(self):
        with self.assertRaises(cal.CalendarError):
            cal.parse_holiday_master({"FO": []})
        with self.assertRaises(cal.CalendarError):
            cal.parse_holiday_master({"CM": [{"tradingDate": "2026-01-26"}]})

    def test_cache_replaces_its_years_and_adds_new_ones(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "holidays.json")
            years = cal.save_holidays({"2026-12-25": "Christmas", "2027-01-26": "Republic Day"}, p)
            self.assertEqual(years, [2026, 2027])
            h, y = cal.load_holidays(p)
            self.assertEqual(y, {2026, 2027})
            self.assertNotIn("2026-10-02", h)
            self.assertEqual(h["2027-01-26"], "Republic Day")

    def test_no_cache_is_the_bundled_list(self):
        with tempfile.TemporaryDirectory() as d:
            h, y = cal.load_holidays(os.path.join(d, "missing.json"))
        self.assertEqual(h, cal.HOLIDAYS)
        self.assertEqual(y, {2026})

    def test_broken_cache(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "holidays.json")
            with open(p, "w") as fh:
                fh.write("[]")
            with self.assertRaises(cal.CalendarError) as e:
                cal.load_holidays(p)
            self.assertIn("holidays refresh", str(e.exception))


class Status(unittest.TestCase):
    def setUp(self):
        self.c = cal.Calendar(dict(cal.HOLIDAYS), cal.YEARS)

    def st(self, text):
        return self.c.status(ist(text))

    def test_a_normal_day(self):
        st = self.st("2026-10-26T10:00")
        self.assertTrue(st["open"])
        self.assertEqual(st["phase"], "open")
        self.assertEqual((st["opens"], st["closes"], st["mis_square_off"]), ("09:15", "15:30", "15:20"))
        self.assertNotIn("next_open", st)
        pre = self.st("2026-10-26T09:05")
        self.assertFalse(pre["open"])
        self.assertEqual(pre["phase"], "pre_open")
        self.assertEqual(pre["next_open"], "2026-10-26 09:15")
        early = self.st("2026-10-26T08:59")
        self.assertEqual(early["reason"], "before the open")
        self.assertEqual(early["next_open"], "2026-10-26 09:15")
        self.assertTrue(self.st("2026-10-26T15:29")["open"])
        after = self.st("2026-10-26T15:30")
        self.assertFalse(after["open"])
        self.assertEqual(after["reason"], "after the close")
        self.assertEqual(after["next_open"], "2026-10-27 09:15")

    def test_holidays_and_weekends(self):
        diwali = self.st("2026-11-10T10:00")
        self.assertFalse(diwali["open"])
        self.assertIn("Diwali-Balipratipada", diwali["reason"])
        self.assertEqual(diwali["next_open"], "2026-11-11 09:15")
        self.assertEqual(self.st("2026-12-25T10:00")["next_open"], "2026-12-28 09:15")
        self.assertEqual(self.st("2026-11-08T18:00")["reason"], "weekend")
        self.assertEqual(self.st("2026-10-24T10:00")["reason"], "weekend")
        self.assertNotIn("opens", self.st("2026-10-24T10:00"))

    def test_unknown_year(self):
        st = self.st("2027-01-04T10:00")
        self.assertFalse(st["calendar_known"])
        self.assertTrue(st["open"])
        self.assertTrue(self.st("2026-06-01T10:00")["calendar_known"])

    def test_next_open_over_a_long_weekend(self):
        self.assertEqual(hm(self.c.next_open(ist("2026-04-02T16:00"))), "2026-04-06 09:15")


if __name__ == "__main__":
    unittest.main()
