#!/usr/bin/env python3
"""NSE website access for the trader skills. Standard library only.

NSE answers scripts only with a session cookie from one of its pages and a
browser User-Agent, and it still blocks often. So every caller also takes
--file: when a fetch raises NseBlocked, open the address it names in a
browser, save what it shows, and run again with --file <saved file>.

Answers are cached per day in trader/cache/nse/<date>/ so a rerun does not
ask NSE again, and requests are at least PAUSE seconds apart.

This file is copied into every skill that reads NSE. Keep the copies
identical: tests/test_repo.py checks.
"""

import datetime
import hashlib
import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.request

HOME = "https://www.nseindia.com/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
PAUSE = 1.0
BLOCK_CODES = (401, 403, 429, 503)
CACHE = os.path.join("trader", "cache", "nse")


class NseError(Exception):
    pass


class NseBlocked(NseError):
    def __init__(self, url, why):
        self.url = url
        NseError.__init__(self, "NSE blocked %s (%s). Open that address in a browser, save the page "
                                "as a file, and run again with --file <saved file>." % (url, why))


def read_file(path):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return fh.read()
    except OSError as e:
        raise NseError("cannot read %s: %s" % (path, e.strerror))


def read_json_file(path):
    try:
        return json.loads(read_file(path))
    except ValueError as e:
        raise NseError("%s is not JSON: %s" % (path, e))


class Client:
    def __init__(self, cache=CACHE, opener=None, pause=PAUSE, sleep=time.sleep, today=None):
        self.cache = cache
        self.pause = pause
        self.sleep = sleep
        self.today = today or datetime.date.today().isoformat()
        self._opener = opener
        self._warm = False
        self._calls = 0

    def _open(self, url, accept):
        if self._opener is None:
            jar = http.cookiejar.CookieJar()
            self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        if self._calls and self.pause:
            self.sleep(self.pause)
        self._calls += 1
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Referer": HOME,
                                                   "Accept-Language": "en-IN,en;q=0.9"})
        try:
            with self._opener.open(req, timeout=20) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in BLOCK_CODES:
                raise NseBlocked(url, "HTTP %d" % e.code)
            raise NseError("%s answered HTTP %d" % (url, e.code))
        except urllib.error.URLError as e:
            raise NseError("could not reach %s: %s" % (url.split("/")[2], e.reason))

    def _cache_path(self, url):
        name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".txt"
        return os.path.join(self.cache, self.today, name)

    def get_text(self, url, cookie=True):
        p = self._cache_path(url)
        if os.path.exists(p):
            return read_file(p)
        if cookie and not self._warm:
            self._warm = True
            try:
                self._open(HOME, "text/html")  # sets the cookie even when it answers 403
            except NseError:
                pass
        text = self._open(url, "application/json,text/csv,*/*")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return text

    def get_json(self, url):
        text = self.get_text(url)
        try:
            return json.loads(text)
        except ValueError:
            os.remove(self._cache_path(url))
            raise NseBlocked(url, "the answer was not JSON, probably a block page")
