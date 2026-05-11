"""Shared utilities for analysis modules."""

from talk_show_analyzer.transcription.transcriber import (
    SpeakerSegment,
    TranscriptionResult,
)


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
