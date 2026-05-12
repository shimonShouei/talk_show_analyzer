"""Tests for the NamedQAExtractor — uses a stubbed anthropic client."""

import json
from unittest.mock import MagicMock

from talk_show_analyzer.analysis.qa_extractor import NamedQAExtractor, NamedQAPair
from talk_show_analyzer.analysis.structural_segmenter import Part, PartType
from talk_show_analyzer.transcription.transcriber import SpeakerSegment


def _interview_part() -> Part:
    segs = [
        SpeakerSegment(start=10.0, end=18.0, speaker="SPEAKER_00", text="מה דעתך על המצב?"),
        SpeakerSegment(
            start=18.5, end=60.0, speaker="SPEAKER_01",
            text="המצב הוא חמור מאוד ויש צורך בפעולה דחופה.",
        ),
    ]
    return Part(
        type=PartType.INTERVIEW,
        start=10.0,
        end=60.0,
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


def test_returns_empty_for_non_interview_part():
    part = Part(type=PartType.HOST_TALK, start=0, end=60, segments=[])
    extractor = NamedQAExtractor(client=MagicMock())
    assert extractor.extract(part) == []


def test_returns_empty_for_interview_with_no_segments():
    part = Part(type=PartType.INTERVIEW, start=0, end=60, segments=[])
    extractor = NamedQAExtractor(client=MagicMock())
    assert extractor.extract(part) == []


def test_extract_parses_valid_response():
    payload = [
        {
            "question_text_he": "מה דעתך על המצב?",
            "question_speaker_label": "SPEAKER_00",
            "answer_text_he": "המצב הוא חמור מאוד.",
            "answer_speaker_label": "SPEAKER_01",
            "topic_label_he": "המצב הביטחוני",
            "start_seconds": 10.0,
            "end_seconds": 60.0,
        }
    ]
    extractor = NamedQAExtractor(client=_fake_client(payload))
    pairs = extractor.extract(_interview_part())
    assert len(pairs) == 1
    assert isinstance(pairs[0], NamedQAPair)
    assert pairs[0].question_speaker_label == "SPEAKER_00"
    assert pairs[0].answer_speaker_label == "SPEAKER_01"
    assert pairs[0].topic_label_he == "המצב הביטחוני"


def test_extract_skips_malformed_pairs():
    payload = [
        {  # valid
            "question_text_he": "Q1",
            "question_speaker_label": "SPEAKER_00",
            "answer_text_he": "A1",
            "answer_speaker_label": "SPEAKER_01",
            "topic_label_he": "T1",
            "start_seconds": 10.0,
            "end_seconds": 20.0,
        },
        {  # missing required fields
            "question_text_he": "Q2",
        },
    ]
    extractor = NamedQAExtractor(client=_fake_client(payload))
    pairs = extractor.extract(_interview_part())
    assert len(pairs) == 1
    assert pairs[0].question_text_he == "Q1"


def test_extract_handles_empty_array():
    extractor = NamedQAExtractor(client=_fake_client([]))
    assert extractor.extract(_interview_part()) == []


def test_extract_handles_non_list_response():
    # API returned an object instead of an array — extractor should warn + return []
    extractor = NamedQAExtractor(client=_fake_client({"oops": "wrong shape"}))
    assert extractor.extract(_interview_part()) == []


def test_extract_swallows_api_errors_and_returns_empty():
    client = MagicMock()
    response = MagicMock()
    response.content = []
    response.stop_reason = "max_tokens"
    client.messages.create.return_value = response
    extractor = NamedQAExtractor(client=client)
    # safe_response_text raises ValueError → extractor catches and returns []
    assert extractor.extract(_interview_part()) == []


def test_extract_prompt_contains_transcript_block():
    """Sanity: the user message we send Claude actually contains the segments."""
    client = _fake_client([])
    extractor = NamedQAExtractor(client=client)
    extractor.extract(_interview_part())
    call_kwargs = client.messages.create.call_args.kwargs
    user_msg = call_kwargs["messages"][0]["content"]
    assert "SPEAKER_00" in user_msg
    assert "מה דעתך על המצב?" in user_msg
    assert "[10.0-18.0 SPEAKER_00]" in user_msg
