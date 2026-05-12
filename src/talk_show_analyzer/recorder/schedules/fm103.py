"""103FM (103fm.maariv.co.il) schedule scraper.

The schedule page renders the whole week in seven `<ol id="innerList_N">` blocks
where N is the Israeli day index (1=Sunday … 7=Saturday). Each entry exposes a
start time and a show name; end time is derived from the next entry.
"""

import re
from datetime import datetime, date, time
from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo

_IDT = ZoneInfo("Asia/Jerusalem")

import requests
from loguru import logger

from talk_show_analyzer.recorder.schedules.base import (
    ScheduleProvider,
    ScheduledShow,
)

SCHEDULE_URL = "https://103fm.maariv.co.il/brodcasts/"

# Python weekday() (Mon=0..Sun=6) → Israeli day_id (1=Sunday..7=Saturday)
_PY_WEEKDAY_TO_ISRAELI = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 7, 6: 1}


def _israeli_day_id(d: date) -> int:
    return _PY_WEEKDAY_TO_ISRAELI[d.weekday()]


_DAY_LIST_RE = re.compile(
    r'<ol[^>]*\bid="innerList_(?P<day>\d+)"[^>]*>(?P<body>.*?)</ol>',
    re.DOTALL,
)

_ENTRY_RE = re.compile(
    r'<li[^>]*\bshedule_day_item\b[^>]*>.*?'
    r'<div[^>]*\bshedule_time\b[^>]*>\s*(?P<time>\d{1,2}:\d{2})\s*</div>.*?'
    r'<a[^>]*\bshedule_program_name\b[^>]*>\s*<div[^>]*>\s*(?P<name>[^<]+?)\s*</div>\s*</a>',
    re.DOTALL,
)

_HREF_RE = re.compile(r'href="([^"]*)"')


def _extract_hosts(show_name: str) -> list[str]:
    """Best-effort host extraction from show name.

    Splits on the Hebrew connector " ו" (and) when followed by a Hebrew letter,
    which is the dominant pattern on 103FM ("פלוני ואלמוני"). If no split point
    is found, returns the full show name as a single candidate — downstream
    resolution substring-matches against speaker names, so generic show titles
    just won't match anything (correct outcome).
    """
    name = show_name.strip()
    if not name:
        return []
    parts = re.split(r"\s+ו(?=[א-ת])", name)
    hosts: list[str] = []
    for part in parts:
        p = part.strip()
        if len(p) >= 2 and p not in hosts:
            hosts.append(p)
    return hosts


class FM103ScheduleProvider(ScheduleProvider):
    """Scrape weekly schedule from 103fm.maariv.co.il."""

    station = "103fm"

    def __init__(self, timeout: float = 10.0):
        self._timeout = timeout

    def fetch_for_datetime(self, when: datetime) -> Optional[ScheduledShow]:
        # Schedule times are in Israeli local time; convert if caller passed UTC/aware dt
        when_local = when.astimezone(_IDT) if when.tzinfo is not None else when
        target_date = when_local.date()
        target_t = when_local.time()
        day_id = _israeli_day_id(target_date)

        entries = _fetch_and_parse(target_date, day_id, self._timeout)
        if not entries:
            logger.warning(
                f"103fm: no entries parsed for {target_date} (day_id={day_id})"
            )
            return None

        for i, (t, name, href) in enumerate(entries):
            start = t
            end = entries[i + 1][0] if i + 1 < len(entries) else time(23, 59, 59)
            if _time_in_range(target_t, start, end):
                return ScheduledShow(
                    station=self.station,
                    show_name=name,
                    start_time=datetime.combine(target_date, start),
                    end_time=datetime.combine(target_date, end),
                    hosts=_extract_hosts(name),
                    program_url=(
                        f"https://103fm.maariv.co.il{href}"
                        if href and href.startswith("/")
                        else (href or None)
                    ),
                )
        return None


# Cache parsed entries per (date, day_id). Schedules don't change intra-day, and
# the seven-day grid is small, so 14 entries (two weeks of distinct keys) is plenty.
@lru_cache(maxsize=14)
def _fetch_and_parse(target_date: date, day_id: int, timeout: float) -> tuple:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    }
    resp = requests.get(SCHEDULE_URL, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return _parse(resp.text, day_id)


def _parse(html: str, day_id: int) -> tuple:
    for m in _DAY_LIST_RE.finditer(html):
        if int(m.group("day")) != day_id:
            continue
        entries: list[tuple] = []
        for em in _ENTRY_RE.finditer(m.group("body")):
            hh, mm = em.group("time").split(":")
            href_m = _HREF_RE.search(em.group(0))
            entries.append(
                (
                    time(int(hh), int(mm)),
                    em.group("name").strip(),
                    href_m.group(1) if href_m else "",
                )
            )
        return tuple(entries)
    return ()


def _time_in_range(t: time, start: time, end: time) -> bool:
    """[start, end), wrapping past midnight if start > end (overnight shows)."""
    if start <= end:
        return start <= t < end
    return t >= start or t < end
