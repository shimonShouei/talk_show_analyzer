"""Smoke tests for the new orchestrator step wiring (resolve_hosts + structural_segment).

These bypass the heavy stages (record/transcribe/LLM) and verify that the new step
methods exist, accept the right shapes, and produce sensible outputs.
"""

from datetime import datetime

from talk_show_analyzer.analysis.structural_segmenter import Part, PartType
from talk_show_analyzer.identification.host_resolver import HostResolution
from talk_show_analyzer.identification.llm_identifier import ResolvedSpeaker
from talk_show_analyzer.pipeline.orchestrator import PipelineOrchestrator
from talk_show_analyzer.recorder.schedules.base import ScheduledShow
from talk_show_analyzer.transcription.transcriber import (
    SpeakerSegment,
    TranscriptionResult,
)


def _make_orchestrator() -> PipelineOrchestrator:
    """Build an orchestrator without invoking Transcriber.__init__ (needs GPU/model)."""
    orch = PipelineOrchestrator.__new__(PipelineOrchestrator)
    from talk_show_analyzer.identification.host_resolver import HostResolver
    orch.host_resolver = HostResolver(
        schedule_fetcher=lambda station, when: ScheduledShow(
            station=station,
            show_name="גדעון אוקו ועמיחי אתאלי",
            start_time=datetime(2024, 1, 1, 7, 0),
            end_time=datetime(2024, 1, 1, 9, 0),
            hosts=["גדעון אוקו", "עמיחי אתאלי"],
        ),
    )
    return orch


def test_step_resolve_hosts_returns_host_resolution():
    orch = _make_orchestrator()
    resolved = {
        "SPEAKER_00": ResolvedSpeaker(
            speaker_label="SPEAKER_00",
            name_he="גדעון אוקו",
            name_en="Gideon Oko",
            role="host",
            confidence=0.95,
        ),
        "SPEAKER_01": ResolvedSpeaker(
            speaker_label="SPEAKER_01",
            name_he="עמיחי אתאלי",
            name_en="Amichai Ataeli",
            role="host",
            confidence=0.90,
        ),
    }
    res = orch._step_resolve_hosts("103fm", datetime(2024, 1, 1, 7, 30), resolved)
    assert isinstance(res, HostResolution)
    assert res.schedule_available
    assert len(res.confirmed) == 2


def test_step_structural_segment_produces_parts():
    orch = _make_orchestrator()
    segs = []
    t = 0.0
    for i in range(20):
        speaker = "H" if i % 2 == 0 else "G"
        segs.append(SpeakerSegment(start=t, end=t + 5, speaker=speaker, text="x"))
        t += 5
    transcript = TranscriptionResult(
        raw_text="x", language="he", duration=t, word_count=20, segments=segs
    )
    resolved = {
        "H": ResolvedSpeaker(
            speaker_label="H", name_he="H", name_en="H", role="host", confidence=0.9
        ),
        "G": ResolvedSpeaker(
            speaker_label="G", name_he="G", name_en="G", role="guest", confidence=0.9
        ),
    }
    parts = orch._step_structural_segment(transcript, resolved)
    assert len(parts) == 1
    assert isinstance(parts[0], Part)
    assert parts[0].type == PartType.INTERVIEW


def test_orchestrator_steps_contain_new_stages():
    """resolve_hosts and structural_segment must appear between identify_speakers and thematic."""
    steps = PipelineOrchestrator.STEPS
    assert "resolve_hosts" in steps
    assert "structural_segment" in steps
    assert steps.index("identify_speakers") < steps.index("resolve_hosts")
    assert steps.index("resolve_hosts") < steps.index("structural_segment")
    assert steps.index("structural_segment") < steps.index("thematic")
