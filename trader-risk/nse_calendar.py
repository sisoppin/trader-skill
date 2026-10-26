#!/usr/bin/env python3
"""NSE trading calendar in IST for the trader skills. Standard library only.

Pre-open 09:00 to 09:15, normal session 09:15 to 15:30 IST, Monday to
Friday, minus NSE trading holidays. Zerodha squares MIS (intraday)
positions off from about 15:20.

India has no daylight saving time, so a fixed +05:30 offset is exact.

Holidays: HOLIDAYS below is NSE's capital-market list for 2026 as published
by https://www.nseindia.com/api/holiday-master?type=trading (read
2026-10-26). save_holidays() caches a newer list (alerts.py holidays
refresh) and load_holidays() merges it in, replacing the bundled years it
covers. A year in neither is unknown, and status() then says
calendar_known false.

Special sessions (Muhurat trading on Diwali) are not modelled: the clock says
closed on those days.

This file is copied into every skill that needs the market clock. Keep the
copies identical: tests/test_repo.py checks.
"""

import datetime
import json
import os

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
PRE_OPEN = datetime.time(9, 0)
OPEN = datetime.time(9, 15)
CLOSE = datetime.time(15, 30)
SQUARE_OFF = datetime.time(15, 20)
URL = "https://www.nseindia.com/api/holiday-master?type=trading"
CACHE = os.path.join("trader", "cache", "nse", "holidays.json")

HOLIDAYS = {
    "2026-01-15": "Municipal Corporation Election - Maharashtra",
    "2026-01-26": "Republic Day",
    "2026-02-15": "Mahashivratri",
    "2026-03-03": "Holi",
    "2026-03-21": "Id-Ul-Fitr (Ramadan Eid)",
    "2026-03-26": "Shri Ram Navami",
    "2026-03-31": "Shri Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-08-15": "Independence Day",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali Laxmi Pujan",
    "2026-11-10": "Diwali-Balipratipada",
    "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas",
}
YEARS = (2026,)


class CalendarError(Exception):
    pass


def parse_now(text=None):
    """ISO time -> aware IST datetime. No offset means IST. None means now."""
    if not text:
        return datetime.datetime.now(IST).replace(microsecond=0)
    try:
        t = datetime.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        raise CalendarError("--now wants an ISO time like 2026-10-26T09:20 (IST) or ...Z (UTC)")
    return t.replace(tzinfo=IST) if t.tzinfo is None else t.astimezone(IST)


def parse_holiday_master(doc):
    """NSE holiday-master JSON -> {"YYYY-MM-DD": name} for the capital market (CM)."""
    rows = doc.get("CM") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        raise CalendarError("not an NSE holiday master: no CM list")
    out = {}
    for r in rows:
        try:
            d = datetime.datetime.strptime(r["tradingDate"], "%d-%b-%Y").date()
        except (KeyError, TypeError, ValueError):
            raise CalendarError("bad holiday row: %r" % (r,))
        out[d.isoformat()] = str(r.get("description", "")).strip().rstrip("*").strip()
    return out


def save_holidays(holidays, path=CACHE):
    years = sorted({int(d[:4]) for d in holidays})
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"source": URL, "years": years, "holidays": holidays}, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return years


def load_holidays(path=CACHE):
    """(holidays, years known): the bundled list, with any cached years replacing it."""
    holidays, years = dict(HOLIDAYS), set(YEARS)
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            cached = {int(y) for y in doc["years"]}
            holidays = {d: n for d, n in holidays.items() if int(d[:4]) not in cached}
            holidays.update(doc["holidays"])
            years |= cached
        except (ValueError, KeyError, TypeError) as e:
            raise CalendarError("%s is not a holiday cache (%s): run alerts.py holidays refresh" % (path, e))
    return holidays, years


class Calendar:
    def __init__(self, holidays=None, years=None):
        if holidays is None:
            holidays, years = load_holidays()
        self.holidays = holidays
        self.years = set(years if years is not None else YEARS)

    def known(self, d):
        return d.year in self.years

    def trading_day(self, d):
        """(is_trading_day, reason). An unknown year counts every weekday as a trading day."""
        if d.weekday() >= 5:
            return False, "weekend"
        name = self.holidays.get(d.isoformat())
        if name:
            return False, "NSE holiday: " + name
        return True, ""

    def next_open(self, now):
        """The next session open after now (today's if it is before 09:15), aware IST."""
        now = now.astimezone(IST)
        d = now.date()
        if not (self.trading_day(d)[0] and now.time() < OPEN):
            d += datetime.timedelta(days=1)
        for _ in range(15):
            if self.trading_day(d)[0]:
                return datetime.datetime.combine(d, OPEN, tzinfo=IST)
            d += datetime.timedelta(days=1)
        return None

    def status(self, now):
        now = now.astimezone(IST)
        d, t = now.date(), now.time()
        ok, reason = self.trading_day(d)
        st = {"now_ist": now.strftime("%Y-%m-%d %H:%M"), "date": d.isoformat(), "weekday": now.strftime("%A"),
              "calendar_known": self.known(d), "open": False, "phase": "closed", "reason": reason}
        if ok:
            st.update(opens=OPEN.strftime("%H:%M"), closes=CLOSE.strftime("%H:%M"),
                      mis_square_off=SQUARE_OFF.strftime("%H:%M"))
            if OPEN <= t < CLOSE:
                st.update(open=True, phase="open", reason="normal session")
            elif PRE_OPEN <= t < OPEN:
                st.update(phase="pre_open", reason="pre-open session (nothing trades until 09:15)")
            elif t < PRE_OPEN:
                st["reason"] = "before the open"
            else:
                st["reason"] = "after the close"
        if not st["open"]:
            nxt = self.next_open(now)
            if nxt:
                st["next_open"] = nxt.strftime("%Y-%m-%d %H:%M")
        return st
