"""Task 4: chunk JSON retry ladder, schedule host parsing, multi-show host
resolution, voice-merge planning, and person-name normalisation."""

from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from talk_show_analyzer.analysis.utils import extract_fenced_json
from talk_show_analyzer.identification.host_resolver import HostResolver
from talk_show_analyzer.identification.llm_identifier import ResolvedSpeaker
from talk_show_analyzer.identification.person_registry import (
    is_generic_name, normalize_he, upgrade_partial_names,
)
from talk_show_analyzer.recorder.schedules.base import ScheduledShow
from talk_show_analyzer.recorder.schedules.fm103 import _hosts_from_description
from talk_show_analyzer.transcription.speaker_merge import plan_merges
from talk_show_analyzer.transcription.transcriber import SpeakerSegment


# --- tolerant JSON -----------------------------------------------------------

def test_extract_fenced_json_takes_last_valid_block_and_ignores_trailing_prose():
    text = 'thinking ```json\n{"broken": \n``` more\n```json\n{"ok": 1}\n```\nThanks!'
    assert extract_fenced_json(text) == {"ok": 1}


# --- schedule host parsing ---------------------------------------------------

def test_hosts_from_description_splits_names_and_strips_titles():
    desc = "תוכנית אקטואליה יומית עם רון קופמן ופרופ' אריה אלדד"
    hosts = _hosts_from_description(desc)
    assert "רון קופמן" in hosts and "אריה אלדד" in hosts


def _rs(label, he, en, role="host"):
    return ResolvedSpeaker(label, he, en, role, 0.9)


def test_host_resolver_uses_all_shows_in_window():
    t0 = datetime(2026, 11, 2, 15, 39, tzinfo=timezone.utc)
    shows = [
        ScheduledShow("103fm", "חמש בערב", t0, t0, hosts=["רון קופמן", "אריה אלדד"]),
        ScheduledShow("103fm", "ספורט", t0, t0, hosts=["משה פרימו"]),
    ]
    res = HostResolver(window_fetcher=lambda st, a, b: shows).resolve(
        "103fm", t0,
        {"A": _rs("A", "רון קופמן", "Ron Kofman"), "B": _rs("B", "משה פרימו", "Moshe Primo")},
        duration_seconds=3300,
    )
    assert res.show_name == "חמש בערב + ספורט"
    assert {name for _, name in res.confirmed} >= {"רון קופמן", "משה פרימו"} or len(res.confirmed) == 2
    assert not res.substitutes


# --- voice merge -------------------------------------------------------------

def _seg(spk, a, b):
    return SpeakerSegment(start=a, end=b, speaker=spk, text="x")


def test_plan_merges_merges_same_voice_but_not_conversing_pair():
    e = {
        "A": np.array([1.0, 0.0, 0.0]),
        "A2": np.array([0.99, 0.141, 0.0]) / np.linalg.norm([0.99, 0.141, 0.0]),
        "B": np.array([0.8, 0.6, 0.0]),   # similar to A but talks with A
        "C": np.array([0.0, 0.0, 1.0]),
    }
    segs = [_seg("A", 0, 10), _seg("B", 10, 20), _seg("A", 20, 30), _seg("B", 30, 40),
            _seg("A", 40, 50), _seg("C", 50, 60), _seg("A2", 100, 105)]
    m = plan_merges(e, segs, threshold=0.75)
    assert m["A2"] == "A"           # same voice, never converses -> merged
    assert m.get("B", "B") == "B"            # sim 0.8 but many turn changes with A -> kept apart
    assert m.get("C", "C") == "C"


# --- names -------------------------------------------------------------------

def test_normalize_he_strips_titles_and_quote_variants():
    assert normalize_he('ד"ר יורי פסקוביץ') == normalize_he("דוקטור יורי פסקוביץ") == "יורי פסקוביץ"
    assert normalize_he("ח״כ אביחי בוארון") == "אביחי בוארון"


def test_generic_role_words_are_not_people():
    assert is_generic_name("מגיש/מנחה", "Announcer")
    assert not is_generic_name("רון קופמן", "Ron Kofman")


def test_upgrade_partial_names_only_when_unique():
    resolved = {
        "A": _rs("A", "יוני", "Yoni"),
        "B": _rs("B", "אלדד", "Eldad"),
        "C": _rs("C", "משה", "Moshe"),
    }
    changed = upgrade_partial_names(resolved, ["יוני הללי", "אריה אלדד", "משה פרימו", "משה כהן"])
    assert resolved["A"].name_he == "יוני הללי"
    assert resolved["B"].name_he == "אריה אלדד"
    assert resolved["C"].name_he == "משה"   # ambiguous -> unchanged
    assert set(changed) == {"A", "B"}


def test_deferred_resolve_never_gives_one_name_to_two_labels():
    import json as _json
    from talk_show_analyzer.identification.llm_identifier import deferred_resolve_speakers
    from talk_show_analyzer.transcription.transcriber import TranscriptionResult

    reply = _json.dumps([
        {"speaker_label": "S1", "name_he": "משה פרימו", "name_en": "Moshe Primo", "role": "host", "confidence": 0.90},
        {"speaker_label": "S2", "name_he": "משה פרימו", "name_en": "Moshe Primo", "role": "host", "confidence": 0.85},
    ])
    client = SimpleNamespace(messages=SimpleNamespace(
        create=lambda **k: SimpleNamespace(content=[SimpleNamespace(text=reply)])))
    tr = TranscriptionResult(raw_text="", language="he", duration=20, word_count=2,
                             segments=[_seg("S1", 0, 10), _seg("S2", 10, 20)])
    unk = {s: ResolvedSpeaker(s, "Unknown", "Unknown", "unknown", 0.0) for s in ("S1", "S2")}
    out = deferred_resolve_speakers(tr, unk, client)
    assert out["S1"].name_en == "Moshe Primo"
    assert out["S2"].name_en == "Unknown"
