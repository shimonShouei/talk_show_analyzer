"""Tolerance for Haiku output quirks (extra prose after JSON, extra keys)."""

from talk_show_analyzer.analysis.thematic_analyzer import TopicAnalysis, _drop_extra_keys
from talk_show_analyzer.analysis.utils import extract_fenced_json, parse_leading_json


def test_parse_leading_json_ignores_trailing_prose():
    assert parse_leading_json('[{"a": 1}]\n\nNote: done') == [{"a": 1}]
    assert extract_fenced_json('<thinking>x</thinking>\n{"b": 2}\nExplanation...') == {"b": 2}


def test_drop_extra_keys_top_level():
    data = {
        "topic_id": "t0", "merged_title_he": "x", "merged_title_en": "x",
        "category": "politics", "thematic_flow_he": "", "thematic_flow_en": "extra",
        "time_spans": [], "chunk_ids": [], "entities": [],
        "hate_speech_incidents": [], "speaker_insights": {},
    }
    cleaned = _drop_extra_keys(data)
    assert "thematic_flow_en" not in cleaned
    TopicAnalysis.model_validate(cleaned)
