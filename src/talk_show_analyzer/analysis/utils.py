"""Shared utilities for analysis modules."""

import json
import re
from typing import Any

from talk_show_analyzer.transcription.transcriber import (
    SpeakerSegment,
    TranscriptionResult,
)


def extract_fenced_json(text: str) -> Any:
    """Pull the first ```json...``` block out of a CoT-style response.

    Strips an optional `<thinking>...</thinking>` preamble, then parses the
    first fenced block. Falls back to the raw text if no fence is present.
    """
    if not text or not text.strip():
        raise ValueError("empty response from model")
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL).strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", cleaned, flags=re.DOTALL)
    payload = fence.group(1) if fence else cleaned
    return json.loads(payload)


def safe_response_text(response) -> str:
    """Extract text from a Claude response, raising ValueError if empty."""
    if not response.content:
        raise ValueError(f"empty content list (stop_reason={response.stop_reason!r})")
    text = response.content[0].text
    if not text or not text.strip():
        raise ValueError(f"empty response text (stop_reason={response.stop_reason!r})")
    return text


def create_sliding_windows(
    transcript: TranscriptionResult,
    window_size_seconds: float = 5 * 60,
    overlap_seconds: float = 60,
) -> list[list[SpeakerSegment]]:
    """Create overlapping windows of speaker segments.

    Used by both Segmenter (legacy) and ThematicAnalyzer for consistent windowing.

    Args:
        transcript: TranscriptionResult
        window_size_seconds: Size of each window (default 5 minutes)
        overlap_seconds: Overlap between consecutive windows (default 1 minute)

    Returns:
        List of windows, each window is a list of SpeakerSegment
    """
    segments = transcript.segments
    if not segments:
        return []

    windows: list[list[SpeakerSegment]] = []
    start = 0.0
    while start < transcript.duration:
        end = min(start + window_size_seconds, transcript.duration)
        window = [s for s in segments if s.start < end and s.end > start]
        if window:
            windows.append(window)
        start += window_size_seconds - overlap_seconds
    return windows
