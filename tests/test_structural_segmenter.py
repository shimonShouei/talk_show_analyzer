"""Tests for the structural segmenter."""

from talk_show_analyzer.analysis.structural_segmenter import (
    Part,
    PartType,
    segment_into_parts,
)
from talk_show_analyzer.identification.llm_identifier import ResolvedSpeaker
from talk_show_analyzer.transcription.transcriber import SpeakerSegment


def _seg(start: float, end: float, speaker: str, text: str = "x") -> SpeakerSegment:
    return SpeakerSegment(start=start, end=end, speaker=speaker, text=text)


def _resolved(role_by_label: dict[str, str]) -> dict[str, ResolvedSpeaker]:
    out: dict[str, ResolvedSpeaker] = {}
    for label, role in role_by_label.items():
        out[label] = ResolvedSpeaker(
            speaker_label=label,
            name_he=label,
            name_en=label,
            role=role,
            confidence=0.9,
        )
    return out


def test_empty_input_returns_empty():
    parts = segment_into_parts([], _resolved({}))
    assert parts == []


def test_single_host_block_is_host_talk():
    segs = [
        _seg(0, 30, "S0"),
        _seg(30, 60, "S0"),
        _seg(60, 90, "S0"),
    ]
    parts = segment_into_parts(segs, _resolved({"S0": "host"}))
    assert len(parts) == 1
    assert parts[0].type == PartType.HOST_TALK
    assert parts[0].host_labels == {"S0"}
    assert parts[0].guest_labels == set()


def test_host_and_guest_together_is_interview():
    # Tight back-and-forth between host and guest.
    segs = []
    t = 0.0
    for i in range(20):
        speaker = "H" if i % 2 == 0 else "G"
        segs.append(_seg(t, t + 5, speaker))
        t += 5
    parts = segment_into_parts(segs, _resolved({"H": "host", "G": "guest"}))
    assert len(parts) == 1
    assert parts[0].type == PartType.INTERVIEW
    assert "H" in parts[0].host_labels
    assert "G" in parts[0].guest_labels


def test_long_gap_breaks_into_two_parts():
    # Host monologue, 60s of silence, then more host monologue.
    segs = [
        _seg(0, 60, "H"),
        _seg(60, 90, "H"),
        _seg(200, 260, "H"),  # 110s gap
        _seg(260, 320, "H"),
    ]
    parts = segment_into_parts(
        segs, _resolved({"H": "host"}), gap_threshold_s=30
    )
    assert len(parts) == 2
    assert all(p.type == PartType.HOST_TALK for p in parts)
    assert parts[0].end <= 90
    assert parts[1].start == 200


def test_host_talk_then_interview_transition():
    # 2 min host alone, then 4 min host+guest dialogue.
    segs = [
        _seg(0, 60, "H"),
        _seg(60, 120, "H"),
    ]
    t = 200.0  # gap > gap_threshold separates the two segments cleanly
    for i in range(16):
        speaker = "H" if i % 2 == 0 else "G"
        segs.append(_seg(t, t + 15, speaker))
        t += 15
    parts = segment_into_parts(
        segs, _resolved({"H": "host", "G": "guest"}), gap_threshold_s=30
    )
    assert len(parts) == 2
    types = [p.type for p in parts]
    assert types == [PartType.HOST_TALK, PartType.INTERVIEW]


def test_short_part_is_merged_into_neighbour():
    # A 5s "host blip" surrounded by a long interview — should not become its own part.
    segs = [_seg(0, 30, "H"), _seg(30, 60, "G"), _seg(60, 90, "H"), _seg(90, 120, "G")]
    # Append a tiny 5s host-only "fragment" near the end then more interview.
    segs += [_seg(120, 125, "H"), _seg(125, 200, "G"), _seg(200, 260, "H")]
    parts = segment_into_parts(
        segs,
        _resolved({"H": "host", "G": "guest"}),
        gap_threshold_s=30,
        min_part_duration_s=20,
    )
    # Whole thing should collapse to one interview part — no 5s blip standalone.
    assert all(p.duration >= 20 for p in parts)
    assert all(p.type == PartType.INTERVIEW for p in parts)


def test_unknown_role_speaker_classified_unknown():
    segs = [_seg(0, 60, "U"), _seg(60, 120, "U")]
    parts = segment_into_parts(segs, _resolved({"U": "unknown"}))
    assert len(parts) == 1
    assert parts[0].type == PartType.UNKNOWN
    assert parts[0].unknown_labels == {"U"}


def test_speakers_not_in_resolved_dict_default_unknown():
    """If the identifier didn't surface a speaker, treat as unknown (not host)."""
    segs = [_seg(0, 60, "MISSING")]
    parts = segment_into_parts(segs, _resolved({}))
    assert len(parts) == 1
    assert parts[0].type == PartType.UNKNOWN


def test_caller_role_treated_as_guest():
    segs = [_seg(0, 30, "H"), _seg(30, 60, "C"), _seg(60, 90, "H"), _seg(90, 120, "C")]
    parts = segment_into_parts(
        segs, _resolved({"H": "host", "C": "caller"})
    )
    assert len(parts) == 1
    assert parts[0].type == PartType.INTERVIEW
    assert "C" in parts[0].guest_labels


def test_part_segments_preserve_order_and_content():
    segs = [_seg(0, 30, "H", "alpha"), _seg(30, 60, "G", "beta"), _seg(60, 90, "H", "gamma")]
    parts = segment_into_parts(segs, _resolved({"H": "host", "G": "guest"}))
    assert len(parts) == 1
    texts = [s.text for s in parts[0].segments]
    assert texts == ["alpha", "beta", "gamma"]


def test_duration_property_matches_endpoints():
    p = Part(type=PartType.INTERVIEW, start=10.0, end=70.0)
    assert p.duration == 60.0
