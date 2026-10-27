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
        self.assertEqual(news.category("Board Meeting Intimation", "to consider buyback"), "board meeting")
        self.assertEqual(news.category("Board Meeting Intimation", "to consider fund raising"), "board meeting")
        self.assertEqual(news.category("Disclosure of creation of pledge", ""), "pledge")
        self.assertEqual(news.category("Copy of Newspaper Publication", ""), "other")

    def test_categories_do_not_mislabel_common_subjects(self):
        c = news.category
        self.assertEqual(c("Board Meeting Intimation", "to consider and approve the Financial Results"),
                         "board meeting")
        self.assertEqual(c("Disclosure under SEBI Takeover Regulations", ""), "insider")
        self.assertEqual(c("Disclosure under Regulation 31 of SEBI SAST", "encumbrance of promoter shares"), "pledge")
        self.assertEqual(c("Closure of Trading Window", "after declaration of financial results"), "other")
        self.assertEqual(c("Press Release", "operating margin improved"), "other")
        self.assertEqual(c("Updates", "Board of Directors approved the plan"), "other")
        self.assertEqual(c("Credit Rating", ""), "rating")

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
        self.assertEqual(code, 2)
        self.assertIn("exactly one", err)

    def test_missing_offline_file_is_an_error_line(self):
        code, text, _ = run(["--symbols", "INFY", "TCS", "--offline", NDIR, "--state", self.state, "--now", NOW])
        self.assertEqual(code, 2)
        self.assertIn("error: TCS: no saved announcements", text)

    def test_a_short_window_does_not_hide_older_items_from_a_longer_one(self):
        code, _, _ = self.news("--days", "2")
        self.assertEqual(code, 0)
        code, text, _ = self.news("--days", "30")
        self.assertEqual(code, 0)
        self.assertIn("2026-10-23", text)
        self.assertIn("Outcome of Board Meeting", text)

    def test_a_crash_in_the_state_file_exits_2(self):
        with open(self.state, "w") as fh:
            fh.write("[]")
        code, _, err = self.news()
        self.assertEqual(code, 2)
        self.assertIn("unexpected", err)

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
            def get_json(self, url, cache=True):
                raise news.nse.NseBlocked(url, "HTTP 403")
        items, errors, blocked = news.collect(["INFY"], Client())
        self.assertEqual((items, errors), ([], []))
        self.assertIn("--file", blocked[0])
        self.assertIn("symbol=INFY", blocked[0])


class Requests(unittest.TestCase):
    def test_collect_asks_fresh_and_encodes_the_symbol(self):
        class Client:
            def __init__(self):
                self.calls = []

            def get_json(self, url, cache=True):
                self.calls.append((url, cache))
                return []
        c = Client()
        news.collect(["INFY", "M&M"], c)
        self.assertEqual([x[1] for x in c.calls], [False, False])
        self.assertTrue(c.calls[1][0].endswith("symbol=M%26M"))


class Exit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "news.json")
        self.real_client = news.nse.Client

    def tearDown(self):
        news.nse.Client = self.real_client
        self.tmp.cleanup()

    def test_main_exits_2_and_prints_the_blocked_url(self):
        class Client:
            def __init__(self, *a, **k):
                pass

            def get_json(self, url, cache=True):
                raise news.nse.NseBlocked(url, "HTTP 403")
        news.nse.Client = Client
        code, text, _ = run(["--symbols", "INFY", "--state", self.state, "--now", NOW])
        self.assertEqual(code, 2)
        self.assertIn("blocked: ", text)
        self.assertIn("symbol=INFY", text)


class Watch(unittest.TestCase):
    def test_a_corrupt_holdings_file_is_an_error_and_null_weights_are_none(self):
        with tempfile.TemporaryDirectory() as d:
            kd = os.path.join(d, "kite")
            os.makedirs(kd)
            with open(os.path.join(kd, "holdings.json"), "w") as fh:
                fh.write("{garbage")
            with self.assertRaises(news.watchlist.WatchError):
                news.watchlist.watch_list(kd, None)
            code, _, err = run(["--kite-dir", kd, "--targets", os.path.join(d, "none.json"), "--now", NOW])
            self.assertEqual(code, 2)
            self.assertIn("holdings.json", err)
            targets = os.path.join(d, "targets.json")
            with open(targets, "w") as fh:
                json.dump({"weights": None}, fh)
            self.assertEqual(news.watchlist.watch_list(os.path.join(d, "none"), targets), [])
            with open(targets, "w") as fh:
                json.dump({"weights": ["x", {"symbol": "TCS"}]}, fh)
            self.assertEqual(news.watchlist.watch_list(os.path.join(d, "none"), targets), ["TCS"])

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
            self.assertEqual(code, 2)
            self.assertIn("which stocks?", err)


if __name__ == "__main__":
    unittest.main()
