import datetime
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

news = load("trader-news", "news")

NDIR = os.path.join(FIX, "trader-news")
NOW = "2026-10-26T10:00"


def fixture():
    with open(os.path.join(NDIR, "announcements-INFY.json")) as fh:
        return json.load(fh)


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = news.main(argv)
    return code, out.getvalue(), err.getvalue()


class Parse(unittest.TestCase):
    def test_real_announcements(self):
        items = news.parse(fixture(), "INFY")
        self.assertEqual(len(items), 6)
        self.assertEqual([i["category"] for i in items],
                         ["other", "results", "analyst meet", "results", "dividend", "deal"])
        first = items[0]
        self.assertEqual((first["symbol"], first["title"], first["id"]), ("INFY", "Copy of Newspaper Publication",
                                                                         "106827749"))
        self.assertEqual(first["when"].strftime("%Y-%m-%d %H:%M %z"), "2026-10-24 19:43 +0530")
        self.assertTrue(first["link"].startswith("https://nsearchives.nseindia.com/"))

    def test_categories(self):
        self.assertEqual(news.category("Outcome of Board Meeting", "Financial Results for the quarter"), "results")
        self.assertEqual(news.category("Board Meeting Intimation", "to consider buyback"), "dividend")
        self.assertEqual(news.category("Board Meeting Intimation", "to consider fund raising"), "board meeting")
        self.assertEqual(news.category("Disclosure of creation of pledge", ""), "pledge")
        self.assertEqual(news.category("Copy of Newspaper Publication", ""), "other")

    def test_not_a_list_is_an_error(self):
        with self.assertRaises(news.NewsError):
            news.parse({"error": "blocked"}, "INFY")


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "news.json")

    def tearDown(self):
        self.tmp.cleanup()

    def news(self, *extra):
        return run(["--symbols", "infy.ns", "--offline", NDIR, "--state", self.state, "--now", NOW] + list(extra))

    def test_new_items_show_once(self):
        code, text, _ = self.news("--days", "7")
        self.assertEqual(code, 0)
        self.assertIn("2026-10-24 19:43  INFY       [other] Copy of Newspaper Publication", text)
        self.assertIn("[results] Outcome of Board Meeting", text)
        self.assertNotIn("Dividend", text)
        self.assertIn("Not financial advice", text)
        code, text, _ = self.news("--days", "7")
        self.assertEqual(code, 1)
        self.assertIn("Nothing new.", text)
        code, text, _ = self.news("--days", "7", "--all")
        self.assertEqual(code, 0)
        self.assertIn("Copy of Newspaper Publication", text)

    def test_window_and_json(self):
        code, text, _ = self.news("--days", "1200", "--json", "--dry-run")
        items = json.loads(text)["items"]
        self.assertEqual(len(items), 6)
        self.assertEqual(items[0]["when"], "2026-10-24T19:43:00+05:30")
        self.assertFalse(os.path.exists(self.state))

    def test_one_file_for_one_symbol(self):
        path = os.path.join(NDIR, "announcements-INFY.json")
        code, text, _ = run(["--symbols", "INFY", "--file", path, "--state", self.state, "--now", NOW])
        self.assertEqual(code, 0)
        code, _, err = run(["--symbols", "INFY", "TCS", "--file", path, "--state", self.state, "--now", NOW])
        self.assertEqual(code, 1)
        self.assertIn("exactly one", err)

    def test_missing_offline_file_is_an_error_line(self):
        code, text, _ = run(["--symbols", "INFY", "TCS", "--offline", NDIR, "--state", self.state, "--now", NOW])
        self.assertEqual(code, 0)
        self.assertIn("error: TCS: no saved announcements", text)

    def test_seen_ids_older_than_90_days_are_forgotten(self):
        with open(self.state, "w") as fh:
            json.dump({"seen": {"old": "2026-01-01T10:00:00+05:30", "new": "2026-10-20T10:00:00+05:30"}}, fh)
        self.news("--dry-run")
        self.news()
        with open(self.state) as fh:
            seen = json.load(fh)["seen"]
        self.assertNotIn("old", seen)
        self.assertIn("new", seen)
        self.assertIn("106827749", seen)


class Blocked(unittest.TestCase):
    def test_a_blocked_symbol_exits_2_with_the_file_hint(self):
        class Client:
            def get_json(self, url):
                raise news.nse.NseBlocked(url, "HTTP 403")
        items, errors, blocked = news.collect(["INFY"], Client())
        self.assertEqual((items, errors), ([], []))
        self.assertIn("--file", blocked[0])
        self.assertIn("symbol=INFY", blocked[0])


class Watch(unittest.TestCase):
    def test_holdings_and_targets(self):
        with tempfile.TemporaryDirectory() as d:
            kd = os.path.join(d, "kite")
            news.kite_snapshot.save("holdings", [{"tradingsymbol": "INFY"}, {"tradingsymbol": "TCS"}], kd,
                                    now=datetime.datetime(2026, 1, 1, tzinfo=news.nse_calendar.IST))
            targets = os.path.join(d, "targets.json")
            with open(targets, "w") as fh:
                json.dump({"weights": [{"symbol": "TCS", "weight": 1}, {"symbol": "HDFCBANK", "weight": 1}]}, fh)
            self.assertEqual(news.watchlist.watch_list(kd, targets), ["INFY", "TCS", "HDFCBANK"])
            code, _, err = run(["--kite-dir", os.path.join(d, "none"), "--targets", os.path.join(d, "none.json"),
                                "--now", NOW])
            self.assertEqual(code, 1)
            self.assertIn("which stocks?", err)


if __name__ == "__main__":
    unittest.main()
