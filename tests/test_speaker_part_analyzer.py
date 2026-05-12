"""Tests for SpeakerPartAnalyzer with a stubbed anthropic client."""

import json
from unittest.mock import MagicMock

from talk_show_analyzer.analysis.speaker_part_analyzer import (
    SpeakerPartAnalysis,
    SpeakerPartAnalyzer,
)
from talk_show_analyzer.analysis.structural_segmenter import Part, PartType
from talk_show_analyzer.transcription.transcriber import SpeakerSegment


def _interview_part() -> Part:
    segs = [
        SpeakerSegment(start=10.0, end=18.0, speaker="SPEAKER_00", text="שאלה ראשונה"),
        SpeakerSegment(
            start=18.5, end=60.0, speaker="SPEAKER_01",
            text="תשובה שיש בה אמירה גסה כלפי קבוצה.",
        ),
        SpeakerSegment(start=60.0, end=80.0, speaker="SPEAKER_00", text="תודה"),
    ]
    return Part(
        type=PartType.INTERVIEW,
        start=10.0,
        end=80.0,
        segments=segs,
        host_labels={"SPEAKER_00"},
        guest_labels={"SPEAKER_01"},
    )


def _fake_client(payload) -> MagicMock:
    text = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    client = MagicMock()
    response = MagicMock()
    block = MagicMock()
    block.text = text
    response.content = [block]
    response.stop_reason = "end_turn"
    client.messages.create.return_value = response
    return client


def test_empty_part_short_circuits():
    part = Part(type=PartType.INTERVIEW, start=0, end=0, segments=[])
    analyzer = SpeakerPartAnalyzer(client=MagicMock())
    assert analyzer.analyze(part) == []


def test_parses_per_speaker_records():
    payload = [
        {
            "speaker_label": "SPEAKER_00",
            "hate_score": 0.05,
            "hate_level_max": "none",
            "incidents": [],
            "stance_summary_he": "ניטרלי",
            "topics_he": ["נושא א"],
        },
        {
            "speaker_label": "SPEAKER_01",
            "hate_score": 0.65,
            "hate_level_max": "insulting",
            "incidents": [
                {
                    "speaker_label": "SPEAKER_01",
                    "level": "insulting",
                    "target": "קבוצה X",
                    "phrase_he": "אמירה גסה",
                    "context_he": "תשובה שיש בה אמירה גסה כלפי קבוצה.",
                    "rationale_en": "Insulting phrase directed at group X.",
                }
            ],
            "stance_summary_he": "ביקורתי וגס",
            "topics_he": ["נושא א"],
        },
    ]
    analyzer = SpeakerPartAnalyzer(client=_fake_client(payload))
    results = analyzer.analyze(_interview_part())
    assert len(results) == 2
    assert {r.speaker_label for r in results} == {"SPEAKER_00", "SPEAKER_01"}
    bad = next(r for r in results if r.speaker_label == "SPEAKER_01")
    assert bad.hate_score == 0.65
    assert bad.hate_level_max == "insulting"
    assert len(bad.incidents) == 1
    assert bad.incidents[0].target == "קבוצה X"


def test_drops_fabricated_speaker_labels():
    """If the model invents a speaker not in the part, drop it."""
    payload = [
        {
            "speaker_label": "SPEAKER_00",
            "hate_score": 0.0,
            "hate_level_max": "none",
            "incidents": [],
            "stance_summary_he": "",
            "topics_he": [],
        },
        {
            "speaker_label": "SPEAKER_99",  # not in the part
            "hate_score": 0.0,
            "hate_level_max": "none",
            "incidents": [],
            "stance_summary_he": "",
            "topics_he": [],
        },
    ]
    analyzer = SpeakerPartAnalyzer(client=_fake_client(payload))
    results = analyzer.analyze(_interview_part())
    assert {r.speaker_label for r in results} == {"SPEAKER_00"}


def test_validates_hate_score_range():
    """A hate_score outside [0,1] should be dropped via pydantic validation."""
    payload = [
        {
            "speaker_label": "SPEAKER_00",
            "hate_score": 1.5,  # invalid
            "hate_level_max": "none",
            "incidents": [],
            "stance_summary_he": "",
            "topics_he": [],
        },
        {
            "speaker_label": "SPEAKER_01",
            "hate_score": 0.3,
            "hate_level_max": "discrediting",
            "incidents": [],
            "stance_summary_he": "",
            "topics_he": [],
        },
    ]
    analyzer = SpeakerPartAnalyzer(client=_fake_client(payload))
    results = analyzer.analyze(_interview_part())
    # Only the valid one survives.
    assert [r.speaker_label for r in results] == ["SPEAKER_01"]


def test_non_list_response_returns_empty():
    analyzer = SpeakerPartAnalyzer(client=_fake_client({"oops": True}))
    assert analyzer.analyze(_interview_part()) == []


def test_api_error_swallowed():
    client = MagicMock()
    response = MagicMock()
    response.content = []
    response.stop_reason = "error"
    client.messages.create.return_value = response
    analyzer = SpeakerPartAnalyzer(client=client)
    assert analyzer.analyze(_interview_part()) == []


def test_host_talk_part_still_analyzed():
    """host_talk parts go through the analyzer too — hosts can show hate."""
    part = Part(
        type=PartType.HOST_TALK,
        start=0,
        end=60,
        segments=[
            SpeakerSegment(start=0, end=60, speaker="H", text="מונולוג")
        ],
        host_labels={"H"},
    )
    payload = [{
        "speaker_label": "H",
        "hate_score": 0.1,
        "hate_level_max": "none",
        "incidents": [],
        "stance_summary_he": "מונולוג ניטרלי",
        "topics_he": [],
    }]
    analyzer = SpeakerPartAnalyzer(client=_fake_client(payload))
    out = analyzer.analyze(part)
    assert len(out) == 1
    assert out[0].speaker_label == "H"


def test_returns_speaker_part_analysis_instances():
    payload = [{
        "speaker_label": "SPEAKER_00",
        "hate_score": 0.0,
        "hate_level_max": "none",
        "incidents": [],
        "stance_summary_he": "",
        "topics_he": [],
    }]
    analyzer = SpeakerPartAnalyzer(client=_fake_client(payload))
    out = analyzer.analyze(_interview_part())
    assert isinstance(out[0], SpeakerPartAnalysis)
