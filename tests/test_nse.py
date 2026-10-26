import io
import os
import tempfile
import unittest
import urllib.error

from _load import load

nse = load("trader-alerts", "nse")

API = "https://www.nseindia.com/api/holiday-master?type=trading"


class FakeOpener:
    """Answers by URL: a str is the body, an int is an HTTP error code, an Exception is raised."""

    def __init__(self, answers):
        self.answers = answers
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        a = self.answers.get(req.full_url, 404)
        if isinstance(a, Exception):
            raise a
        if isinstance(a, int):
            raise urllib.error.HTTPError(req.full_url, a, "error", {}, None)
        return io.BytesIO(a.encode("utf-8"))


class Client(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sleeps = []

    def tearDown(self):
        self.tmp.cleanup()

    def client(self, answers):
        self.op = FakeOpener(answers)
        return nse.Client(cache=self.tmp.name, opener=self.op, sleep=self.sleeps.append, today="2026-10-26")

    def test_warms_up_then_asks_with_browser_headers(self):
        c = self.client({nse.HOME: 403, API: '{"CM": []}'})
        self.assertEqual(c.get_json(API), {"CM": []})
        self.assertEqual([r.full_url for r in self.op.requests], [nse.HOME, API])
        req = self.op.requests[1]
        self.assertIn("Mozilla", req.get_header("User-agent"))
        self.assertEqual(req.get_header("Referer"), nse.HOME)
        self.assertEqual(self.sleeps, [nse.PAUSE])

    def test_cached_answer_is_not_asked_again(self):
        c = self.client({nse.HOME: "<html>", API: '{"CM": []}'})
        c.get_json(API)
        c.get_json(API)
        self.assertEqual(len(self.op.requests), 2)
        c2 = self.client({})
        self.assertEqual(c2.get_json(API), {"CM": []})
        self.assertEqual(self.op.requests, [])

    def test_blocked_codes_name_the_url_and_the_file_fallback(self):
        for code in (401, 403, 429, 503):
            c = self.client({nse.HOME: "<html>", API: code})
            with self.assertRaises(nse.NseBlocked) as e:
                c.get_json(API)
            self.assertEqual(e.exception.url, API)
            self.assertIn("--file", str(e.exception))
            self.assertIn("HTTP %d" % code, str(e.exception))

    def test_block_page_with_200_is_blocked_and_not_cached(self):
        c = self.client({nse.HOME: "<html>", API: "<html>Access Denied</html>"})
        with self.assertRaises(nse.NseBlocked):
            c.get_json(API)
        self.assertFalse(os.path.exists(c._cache_path(API)))

    def test_other_errors_are_not_blocks(self):
        c = self.client({nse.HOME: "<html>", API: 500})
        with self.assertRaises(nse.NseError) as e:
            c.get_json(API)
        self.assertNotIsInstance(e.exception, nse.NseBlocked)
        c = self.client({nse.HOME: "<html>", API: urllib.error.URLError("no network")})
        with self.assertRaises(nse.NseError) as e:
            c.get_json(API)
        self.assertIn("could not reach www.nseindia.com", str(e.exception))

    def test_no_cookie_for_archives(self):
        url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        c = self.client({url: "SYMBOL\n"})
        self.assertEqual(c.get_text(url, cookie=False), "SYMBOL\n")
        self.assertEqual([r.full_url for r in self.op.requests], [url])


class Files(unittest.TestCase):
    def test_read_json_file(self):
        with tempfile.TemporaryDirectory() as d:
            good = os.path.join(d, "good.json")
            with open(good, "w", encoding="utf-8-sig") as fh:
                fh.write('{"a": 1}')
            self.assertEqual(nse.read_json_file(good), {"a": 1})
            bad = os.path.join(d, "bad.json")
            with open(bad, "w") as fh:
                fh.write("nope")
            with self.assertRaises(nse.NseError) as e:
                nse.read_json_file(bad)
            self.assertIn("is not JSON", str(e.exception))
            with self.assertRaises(nse.NseError) as e:
                nse.read_file(os.path.join(d, "missing.json"))
            self.assertIn("cannot read", str(e.exception))


if __name__ == "__main__":
    unittest.main()
