"""Shared pytest fixtures for all tests."""

import json
from pathlib import Path

from talk_show_analyzer.transcription.transcriber import (
    TranscriptionResult,
    SpeakerSegment,
)


def load_transcript_from_json(path: Path | str) -> TranscriptionResult:
    """Load a TranscriptionResult from a JSON transcript file.

    Used across multiple test files to avoid repeated boilerplate.
    JSON structure: {"raw_text", "language", "duration", "word_count", "segments": [...]}
    Each segment: {"start", "end", "speaker", "text"}
    """
    path = Path(path)
    with open(path) as f:
        data = json.load(f)

    segments = [
        SpeakerSegment(
            start=seg["start"],
            end=seg["end"],
            speaker=seg["speaker"],
            text=seg["text"],
        )
        for seg in data["segments"]
    ]

    return TranscriptionResult(
        raw_text=data["raw_text"],
        language=data["language"],
        duration=data["duration"],
        word_count=data["word_count"],
        segments=segments,
    )
