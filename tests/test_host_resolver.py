"""Tests for HostResolver — schedule × identified-speaker matching."""

from datetime import datetime

from talk_show_analyzer.identification.host_resolver import HostResolver
from talk_show_analyzer.identification.llm_identifier import ResolvedSpeaker
from talk_show_analyzer.recorder.schedules.base import ScheduledShow


def _show(*hosts: str) -> ScheduledShow:
    return ScheduledShow(
        station="103fm",
        show_name=" ו".join(hosts),
        start_time=datetime(2024, 1, 1, 7, 0),
        end_time=datetime(2024, 1, 1, 9, 0),
        hosts=list(hosts),
    )


def _host(label: str, name_he: str, name_en: str, confidence: float = 0.9) -> ResolvedSpeaker:
    return ResolvedSpeaker(
        speaker_label=label,
        name_he=name_he,
        name_en=name_en,
        role="host",
        confidence=confidence,
    )


def _resolver(show):
    return HostResolver(schedule_fetcher=lambda station, when: show)


def test_all_expected_hosts_confirmed():
    show = _show("גדעון אוקו", "עמיחי אתאלי")
    speakers = {
        "SPEAKER_00": _host("SPEAKER_00", "גדעון אוקו", "Gideon Oko"),
        "SPEAKER_01": _host("SPEAKER_01", "עמיחי אתאלי", "Amichai Ataeli"),
    }
    res = _resolver(show).resolve("103fm", datetime(2024, 1, 1, 7, 30), speakers)

    assert res.schedule_available
    assert len(res.confirmed) == 2
    assert {name for _, name in res.confirmed} == {"גדעון אוקו", "עמיחי אתאלי"}
    assert res.missing_expected == []
    assert res.substitutes == []


def test_substitute_when_one_host_replaced():
    show = _show("גדעון אוקו", "עמיחי אתאלי")
    speakers = {
        "SPEAKER_00": _host("SPEAKER_00", "גדעון אוקו", "Gideon Oko"),
        "SPEAKER_01": _host("SPEAKER_01", "דני סתן", "Danny Stand-in"),
    }
    res = _resolver(show).resolve("103fm", datetime(2024, 1, 1, 7, 30), speakers)

    assert len(res.confirmed) == 1
    assert res.confirmed[0] == ("SPEAKER_00", "גדעון אוקו")
    assert len(res.substitutes) == 1
    assert res.substitutes[0][0] == "SPEAKER_01"
    assert res.missing_expected == ["עמיחי אתאלי"]


def test_no_schedule_returns_unavailable():
    resolver = HostResolver(schedule_fetcher=lambda station, when: None)
    speakers = {
        "SPEAKER_00": _host("SPEAKER_00", "פלוני אלמוני", "Ploni"),
    }
    res = resolver.resolve("galatz", datetime(2024, 1, 1, 7, 30), speakers)

    assert res.schedule_available is False
    assert res.expected_hosts == []
    assert res.confirmed == []
    assert res.unknown_hosts == []  # name is known, just no schedule to match against


def test_unknown_host_speaker_flagged():
    show = _show("גדעון אוקו")
    speakers = {
        "SPEAKER_00": ResolvedSpeaker(
            speaker_label="SPEAKER_00",
            name_he="Unknown",
            name_en="Unknown",
            role="host",
            confidence=0.0,
        ),
    }
    res = _resolver(show).resolve("103fm", datetime(2024, 1, 1, 7, 30), speakers)

    assert "SPEAKER_00" in res.unknown_hosts
    assert res.confirmed == []
    assert res.missing_expected == ["גדעון אוקו"]


def test_guest_role_speakers_ignored():
    """Speakers with role != 'host' don't participate in matching."""
    show = _show("גדעון אוקו")
    speakers = {
        "SPEAKER_00": _host("SPEAKER_00", "גדעון אוקו", "Gideon Oko"),
        "SPEAKER_01": ResolvedSpeaker(
            speaker_label="SPEAKER_01",
            name_he="אורח כלשהו",
            name_en="Some Guest",
            role="guest",
            confidence=0.9,
        ),
    }
    res = _resolver(show).resolve("103fm", datetime(2024, 1, 1, 7, 30), speakers)

    assert len(res.confirmed) == 1
    assert res.substitutes == []
