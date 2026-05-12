"""Tests for per-Part thematic analysis and orchestrator wiring."""

from unittest.mock import MagicMock, patch

from talk_show_analyzer.analysis.structural_segmenter import Part, PartType
from talk_show_analyzer.analysis.thematic_analyzer import ThematicAnalyzer, TopicAnalysis
from talk_show_analyzer.transcription.transcriber import SpeakerSegment, TranscriptionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_segments(n: int, start: float = 0.0, duration: float = 30.0) -> list[SpeakerSegment]:
    segs = []
    for i in range(n):
        s = start + i * duration
        segs.append(SpeakerSegment(start=s, end=s + duration, speaker=f"SPEAKER_0{i % 2}", text=f"text {i}"))
    return segs


def _make_part(n_segs: int = 5, duration: float = 300.0, ptype: PartType = PartType.INTERVIEW) -> Part:
    segs = _make_segments(n_segs, start=10.0, duration=duration / n_segs)
    return Part(
        type=ptype,
        start=10.0,
        end=10.0 + duration,
        segments=segs,
        host_labels={"SPEAKER_00"},
        guest_labels={"SPEAKER_01"},
    )


def _fake_topic_analysis(topic_id: str = "t0") -> TopicAnalysis:
    return TopicAnalysis(
        topic_id=topic_id,
        merged_title_he="כותרת",
        merged_title_en="Title",
        category="politics",
        thematic_flow_he="זרימה",
        time_spans=[(10.0, 310.0)],
        chunk_ids=["c0"],
    )


def _make_analyzer() -> ThematicAnalyzer:
    """Return a ThematicAnalyzer with a dummy anthropic client (never called in mocked tests)."""
    with patch("talk_show_analyzer.analysis.thematic_analyzer.anthropic.Anthropic"):
        analyzer = ThematicAnalyzer()
    return analyzer


# ---------------------------------------------------------------------------
# Test (a): analyze_part on substantive interview returns topics with correct part_idx
# (part_idx tagging happens at orchestrator level; here we verify analyze_part returns topics)
# ---------------------------------------------------------------------------

def test_analyze_part_substantive_returns_topics():
    analyzer = _make_analyzer()
    part = _make_part(n_segs=5, duration=300.0, ptype=PartType.INTERVIEW)
    expected = [_fake_topic_analysis("t0"), _fake_topic_analysis("t1")]

    with patch.object(analyzer, "analyze", return_value=expected) as mock_analyze:
        result = analyzer.analyze_part(part)

    mock_analyze.assert_called_once()
    assert result == expected


# ---------------------------------------------------------------------------
# Test (b): analyze_part on a <60s part returns [] without calling the LLM
# ---------------------------------------------------------------------------

def test_analyze_part_short_returns_empty():
    analyzer = _make_analyzer()
    # 2 segments, 20s total — too short
    segs = _make_segments(2, start=0.0, duration=10.0)
    part = Part(type=PartType.INTERVIEW, start=0.0, end=20.0, segments=segs)

    with patch.object(analyzer, "analyze") as mock_analyze:
        result = analyzer.analyze_part(part)

    mock_analyze.assert_not_called()
    assert result == []


def test_analyze_part_few_segments_returns_empty():
    """Even if duration is long, <3 segments should be skipped."""
    analyzer = _make_analyzer()
    segs = _make_segments(2, start=0.0, duration=40.0)  # 2 segs, 80s total
    part = Part(type=PartType.INTERVIEW, start=0.0, end=80.0, segments=segs)

    with patch.object(analyzer, "analyze") as mock_analyze:
        result = analyzer.analyze_part(part)

    mock_analyze.assert_not_called()
    assert result == []


# ---------------------------------------------------------------------------
# Test (c): _step_thematic with parts calls analyze_part twice and tags part_idx
# ---------------------------------------------------------------------------

def test_step_thematic_with_parts_tags_part_idx():
    from unittest.mock import patch as _patch
    from talk_show_analyzer.pipeline.orchestrator import PipelineOrchestrator

    with _patch("talk_show_analyzer.pipeline.orchestrator.Transcriber"), \
         _patch("talk_show_analyzer.pipeline.orchestrator.UnifiedSpeakerIdentifier"), \
         _patch("talk_show_analyzer.pipeline.orchestrator.HostResolver"), \
         _patch("talk_show_analyzer.analysis.thematic_analyzer.anthropic.Anthropic"):
        orch = PipelineOrchestrator()

    p1 = _make_part(n_segs=5, duration=300.0, ptype=PartType.INTERVIEW)
    p2 = _make_part(n_segs=4, duration=200.0, ptype=PartType.HOST_TALK)

    ta_p1 = [_fake_topic_analysis("t0")]
    ta_p2 = [_fake_topic_analysis("t1"), _fake_topic_analysis("t2")]

    def fake_analyze_part(part):
        if part is p1:
            return [_fake_topic_analysis("t0")]
        return [_fake_topic_analysis("t1"), _fake_topic_analysis("t2")]

    with _patch.object(orch.thematic_analyzer, "analyze_part", side_effect=fake_analyze_part) as mock_ap:
        # Build a minimal transcript (not actually used when parts is provided)
        transcript = TranscriptionResult(
            raw_text="",
            language="he",
            duration=500.0,
            word_count=0,
            segments=[],
        )
        result = orch._step_thematic(transcript, [p1, p2])

    assert mock_ap.call_count == 2
    assert len(result) == 3
    # p1 topics tagged 0, p2 topics tagged 1
    assert result[0].part_idx == 0
    assert result[1].part_idx == 1
    assert result[2].part_idx == 1


# ---------------------------------------------------------------------------
# Test (d): _step_thematic with parts=None or parts=[] falls back to analyze()
# ---------------------------------------------------------------------------

def test_step_thematic_no_parts_falls_back_to_analyze():
    from unittest.mock import patch as _patch
    from talk_show_analyzer.pipeline.orchestrator import PipelineOrchestrator

    with _patch("talk_show_analyzer.pipeline.orchestrator.Transcriber"), \
         _patch("talk_show_analyzer.pipeline.orchestrator.UnifiedSpeakerIdentifier"), \
         _patch("talk_show_analyzer.pipeline.orchestrator.HostResolver"), \
         _patch("talk_show_analyzer.analysis.thematic_analyzer.anthropic.Anthropic"):
        orch = PipelineOrchestrator()

    transcript = TranscriptionResult(
        raw_text="",
        language="he",
        duration=500.0,
        word_count=0,
        segments=[],
    )
    expected = [_fake_topic_analysis("t0")]

    with _patch.object(orch.thematic_analyzer, "analyze", return_value=expected) as mock_analyze, \
         _patch.object(orch.thematic_analyzer, "analyze_part") as mock_ap:

        result_none = orch._step_thematic(transcript, None)
        result_empty = orch._step_thematic(transcript, [])

    assert mock_ap.call_count == 0
    assert mock_analyze.call_count == 2
    assert result_none == expected
    assert result_empty == expected


# ---------------------------------------------------------------------------
# Test: host_talk part with sufficient content is still analyzed
# ---------------------------------------------------------------------------

def test_analyze_part_host_talk_substantive_is_analyzed():
    analyzer = _make_analyzer()
    part = _make_part(n_segs=5, duration=300.0, ptype=PartType.HOST_TALK)
    expected = [_fake_topic_analysis("t0")]

    with patch.object(analyzer, "analyze", return_value=expected):
        result = analyzer.analyze_part(part)

    assert result == expected
