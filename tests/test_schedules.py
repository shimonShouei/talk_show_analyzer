"""Tests for the station-schedule scrapers."""

from datetime import date, datetime, time

import pytest

from talk_show_analyzer.recorder.schedules.fm103 import (
    FM103ScheduleProvider,
    _extract_hosts,
    _fetch_and_parse,
    _israeli_day_id,
    _parse,
    _time_in_range,
)

# Minimal fixture: one Monday section (innerList_2) with three known shows.
SAMPLE_HTML = """
<ol class="shedule_day_list" id="innerList_2" data-id="2">
  <li class="shedule_day_item">
    <div class="shedule_time">7:00 </div>
    <div class="shedule_program_group">
      <a class="shedule_program_name" href="/program/x.aspx"><div>גדעון אוקו ועמיחי אתאלי</div></a>
    </div>
  </li>
  <li class="shedule_day_item">
    <div class="shedule_time">9:00 </div>
    <div class="shedule_program_group">
      <a class="shedule_program_name" href="/program/y.aspx"><div>ינון מגל ובן כספית</div></a>
    </div>
  </li>
  <li class="shedule_day_item">
    <div class="shedule_time">11:00 </div>
    <div class="shedule_program_group">
      <a class="shedule_program_name" href="/program/z.aspx"><div>גיא פלג</div></a>
    </div>
  </li>
</ol>
"""


def test_israeli_day_id_mapping():
    # 2024-01-07 is a Sunday (Israeli day 1); 2024-01-01 is Monday (day 2);
    # 2024-01-06 is Saturday (day 7).
    assert _israeli_day_id(date(2024, 1, 7)) == 1
    assert _israeli_day_id(date(2024, 1, 1)) == 2
    assert _israeli_day_id(date(2024, 1, 6)) == 7


def test_parse_extracts_entries():
    entries = _parse(SAMPLE_HTML, day_id=2)
    assert len(entries) == 3
    assert entries[0] == (time(7, 0), "גדעון אוקו ועמיחי אתאלי", "/program/x.aspx")
    assert entries[1][0] == time(9, 0)
    assert entries[2][1] == "גיא פלג"


def test_parse_returns_empty_for_wrong_day():
    assert _parse(SAMPLE_HTML, day_id=5) == ()


def test_time_in_range_basic():
    assert _time_in_range(time(8, 0), time(7, 0), time(9, 0)) is True
    assert _time_in_range(time(9, 0), time(7, 0), time(9, 0)) is False
    assert _time_in_range(time(6, 59), time(7, 0), time(9, 0)) is False


def test_time_in_range_wraps_past_midnight():
    assert _time_in_range(time(1, 0), time(23, 0), time(6, 0)) is True
    assert _time_in_range(time(7, 0), time(23, 0), time(6, 0)) is False


def test_extract_hosts_splits_on_hebrew_vav():
    hosts = _extract_hosts("גדעון אוקו ועמיחי אתאלי")
    assert len(hosts) == 2
    assert hosts[0] == "גדעון אוקו"
    assert "אתאלי" in hosts[1]


def test_extract_hosts_single_name_unchanged():
    assert _extract_hosts("גיא פלג") == ["גיא פלג"]


def test_fetch_for_datetime_uses_sample_html(monkeypatch):
    """Integration: stub the HTTP call and verify the right entry is returned."""

    class _Resp:
        text = "<html>" + SAMPLE_HTML + "</html>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "talk_show_analyzer.recorder.schedules.fm103.requests.get",
        lambda *a, **k: _Resp(),
    )
    _fetch_and_parse.cache_clear()

    provider = FM103ScheduleProvider()
    # 2024-01-01 was a Monday → Israeli day_id=2; 08:00 falls in 7:00-9:00 slot.
    show = provider.fetch_for_datetime(datetime(2024, 1, 1, 8, 0))
    assert show is not None
    assert show.station == "103fm"
    assert show.show_name == "גדעון אוקו ועמיחי אתאלי"
    assert show.start_time == datetime(2024, 1, 1, 7, 0)
    assert show.end_time == datetime(2024, 1, 1, 9, 0)
    assert "גדעון אוקו" in show.hosts
    assert show.program_url == "https://103fm.maariv.co.il/program/x.aspx"


def test_fetch_for_datetime_after_last_entry(monkeypatch):
    """Time past the last parsed entry still resolves (end = 23:59:59 fallback)."""

    class _Resp:
        text = "<html>" + SAMPLE_HTML + "</html>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "talk_show_analyzer.recorder.schedules.fm103.requests.get",
        lambda *a, **k: _Resp(),
    )
    _fetch_and_parse.cache_clear()

    provider = FM103ScheduleProvider()
    show = provider.fetch_for_datetime(datetime(2024, 1, 1, 15, 0))
    assert show is not None
    assert show.show_name == "גיא פלג"
