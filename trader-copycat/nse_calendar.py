#!/usr/bin/env python3
"""NSE trading calendar in IST for the trader skills. Standard library only.

Pre-open 09:00 to 09:15, normal session 09:15 to 15:30 IST, Monday to
Friday, minus NSE trading holidays. Zerodha squares MIS (intraday)
positions off from about 15:25 (moved from 15:20 in December 2025; Zerodha
can change it, see zerodha.com/marketintel/bulletin) and charges Rs 50 + GST
for each position it closes.

India has no daylight saving time, so a fixed +05:30 offset is exact.

Holidays: HOLIDAYS below is NSE's capital-market list for 2026 as published
by https://www.nseindia.com/api/holiday-master?type=trading (read
2026-10-26). save_holidays() caches a newer list (alerts.py holidays
refresh) and load_holidays() merges it in, replacing the bundled years it
covers. A year in neither is unknown, and status() then says
calendar_known false.

Special sessions (Muhurat trading on Diwali, a Saturday budget-day session)
are not in NSE's holiday list. Add each one when NSE announces it
(alerts.py holidays session ...): load_sessions() reads them from
trader/cache/nse/special_sessions.json, and the clock is open only inside
that window on that day. MIS square-off times differ on those days, so
mis_square_off is None for a special session.

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
SQUARE_OFF = datetime.time(15, 25)
URL = "https://www.nseindia.com/api/holiday-master?type=trading"
CACHE = os.path.join("trader", "cache", "nse", "holidays.json")
SESSIONS = os.path.join("trader", "cache", "nse", "special_sessions.json")

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


def parse_iso(text):
    """ISO time -> aware IST datetime. No offset means IST. No clock check: use it for stored times."""
    try:
        t = datetime.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise CalendarError("--now wants an ISO time like 2026-10-26T09:20 (IST) or ...Z (UTC)")
    return t.replace(tzinfo=IST) if t.tzinfo is None else t.astimezone(IST)


def parse_now(text=None):
    """The --now value -> aware IST datetime. None means the real clock. A given time must be within
    5 seconds of the real clock unless TRADER_TEST_CLOCK=1 (tests): live checks never run on a fake clock."""
    real = datetime.datetime.now(IST).replace(microsecond=0)
    if not text:
        return real
    t = parse_iso(text)
    off = abs((t - real).total_seconds())
    if off > 5 and os.environ.get("TRADER_TEST_CLOCK") != "1":
        raise CalendarError("--now is for tests only: it is %d s from the real clock "
                            "(set TRADER_TEST_CLOCK=1 to simulate)" % off)
    return t


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


def _hhmm(text, what):
    try:
        return datetime.datetime.strptime(str(text), "%H:%M").time()
    except ValueError:
        raise CalendarError("%s wants a time like 18:15, got %r" % (what, text))


def load_sessions(path=SESSIONS):
    """{"YYYY-MM-DD": {"open": time, "close": time, "name": str}} from the special sessions file."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        out = {}
        for d, s in doc["sessions"].items():
            datetime.date.fromisoformat(d)
            o, c = _hhmm(s["open"], "open"), _hhmm(s["close"], "close")
            if not o < c:
                raise ValueError("%s closes before it opens" % d)
            out[d] = {"open": o, "close": c, "name": str(s.get("name") or "special session")}
        return out
    except (ValueError, KeyError, TypeError, AttributeError, CalendarError) as e:
        raise CalendarError("%s is not a special sessions file (%s): fix it or run alerts.py holidays session"
                            % (path, e))


def save_session(date, opens, closes, name, path=SESSIONS, remove=False):
    """Add (or remove) one special session and write the file. Returns the sessions left."""
    sessions = load_sessions(path)
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise CalendarError("--date wants a date like 2026-11-08, got %r" % date)
    if remove:
        sessions.pop(date, None)
    else:
        o, c = _hhmm(opens, "--open"), _hhmm(closes, "--close")
        if not o < c:
            raise CalendarError("the session must close after it opens")
        sessions[date] = {"open": o, "close": c, "name": name or "special session"}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    doc = {"sessions": {d: {"open": s["open"].strftime("%H:%M"), "close": s["close"].strftime("%H:%M"),
                            "name": s["name"]} for d, s in sessions.items()}}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return sessions


class Calendar:
    def __init__(self, holidays=None, years=None, sessions=None):
        if holidays is None:
            holidays, years = load_holidays()
        self.holidays = holidays
        self.years = set(years if years is not None else YEARS)
        self.sessions = load_sessions() if sessions is None else sessions

    def known(self, d):
        return d.year in self.years

    def session(self, d):
        """(opens, closes, special session or None) for a trading day."""
        sp = self.sessions.get(d.isoformat())
        if sp:
            return sp["open"], sp["close"], sp
        return OPEN, CLOSE, None

    def trading_day(self, d):
        """(is_trading_day, reason). An unknown year counts every weekday as a trading day."""
        sp = self.sessions.get(d.isoformat())
        if sp:
            return True, "special session: " + sp["name"]
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
        if not (self.trading_day(d)[0] and now.time() < self.session(d)[0]):
            d += datetime.timedelta(days=1)
        for _ in range(15):
            if self.trading_day(d)[0]:
                return datetime.datetime.combine(d, self.session(d)[0], tzinfo=IST)
            d += datetime.timedelta(days=1)
        return None

    def status(self, now):
        now = now.astimezone(IST)
        d, t = now.date(), now.time()
        ok, reason = self.trading_day(d)
        st = {"now_ist": now.strftime("%Y-%m-%d %H:%M"), "date": d.isoformat(), "weekday": now.strftime("%A"),
              "calendar_known": self.known(d), "open": False, "phase": "closed", "reason": reason,
              "special": None}
        if ok:
            opens, closes, sp = self.session(d)
            st.update(opens=opens.strftime("%H:%M"), closes=closes.strftime("%H:%M"),
                      mis_square_off=None if sp else SQUARE_OFF.strftime("%H:%M"),
                      special=sp["name"] if sp else None)
            if opens <= t < closes:
                st.update(open=True, phase="open", reason="special session: %s" % sp["name"] if sp else "normal session")
            elif sp and t < opens:
                st["reason"] = "before the special session (%s)" % sp["name"]
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
