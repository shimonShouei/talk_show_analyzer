"""Transcript segmentation using Claude API."""

import json
from dataclasses import dataclass
from typing import Optional

import anthropic
from loguru import logger

from talk_show_analyzer.config import settings
from talk_show_analyzer.transcription.transcriber import TranscriptionResult
from talk_show_analyzer.analysis.prompts.segmentation import (
    SYSTEM_PROMPT,
    format_window,
)


@dataclass
class Segment:
    """A logical segment in the transcript."""

    type: str  # interview, panel, news, ad, jingle, music, caller, weather, commentary
    start: float  # seconds
    end: float  # seconds
    speakers: list[str]  # e.g. ["SPEAKER_00", "SPEAKER_01"]
    summary: str  # 1-2 sentence summary
    raw_text: str  # original text of segment


class Segmenter:
    """Segment transcript into logical content types using Claude."""

    WINDOW_SIZE_SECONDS = 5 * 60  # 5 minutes — tight enough to catch 30s ads
    OVERLAP_SECONDS = 60  # 1 minute
    MERGE_GAP_SECONDS = 15  # merge same-type segments < 15s apart

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        """Initialize segmenter.

        Args:
            model: Claude model to use for segmentation
        """
        self.model = model
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def segment(self, transcript: TranscriptionResult) -> list[Segment]:
        """
        Segment a transcript into logical content types.

        Args:
            transcript: TranscriptionResult from transcriber

        Returns:
            List of Segment objects
        """
        logger.info(
            f"Segmenting transcript: {transcript.duration:.0f}s, "
            f"{len(transcript.segments)} speaker segments"
        )

        # Create windows with overlap
        windows = self._create_windows(transcript)
        logger.info(f"Created {len(windows)} analysis windows")

        # Process each window with Claude
        all_segments = []
        for i, window in enumerate(windows):
            logger.info(
                f"Processing window {i+1}/{len(windows)} "
                f"({window[0].start:.0f}s - {window[-1].end:.0f}s)"
            )
            window_segments = self._analyze_window(window)
            all_segments.extend(window_segments)

        # Merge overlapping/adjacent segments
        merged = self._merge_segments(all_segments)
        logger.info(f"Merged to {len(merged)} final segments")

        return merged

    def _create_windows(
        self, transcript: TranscriptionResult
    ) -> list[list]:
        """Create overlapping windows of speaker segments.

        Args:
            transcript: TranscriptionResult

        Returns:
            List of windows, each window is a list of SpeakerSegment
        """
        segments = transcript.segments
        if not segments:
            return []

        windows = []
        window_start = 0.0

        while window_start < transcript.duration:
            window_end = min(window_start + self.WINDOW_SIZE_SECONDS, transcript.duration)

            # Get segments that fall within [window_start, window_end)
            window_segments = [
                seg
                for seg in segments
                if seg.start < window_end and seg.end > window_start
            ]

            if window_segments:
                windows.append(window_segments)

            # Advance window with overlap
            window_start += self.WINDOW_SIZE_SECONDS - self.OVERLAP_SECONDS

        return windows

    def _analyze_window(self, segments: list) -> list[Segment]:
        """Send a window of segments to Claude for classification.

        Args:
            segments: List of SpeakerSegment in this window

        Returns:
            List of Segment objects parsed from Claude response
        """
        # Format segments as prompt input
        transcript_text = format_window(segments)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0,  # deterministic classification
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": f"Segment this transcript window:\n\n{transcript_text}",
                    }
                ],
            )

            # Extract JSON from response
            response_text = response.content[0].text.strip()

            # Try to parse JSON
            try:
                data = json.loads(response_text)
            except json.JSONDecodeError:
                # If Claude's response isn't pure JSON, try to extract it
                import re
                json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    logger.warning(f"Could not parse Claude response: {response_text}")
                    return []

            # Convert to Segment objects
            result_segments = []
            for item in data:
                segment = Segment(
                    type=item.get("type", "commentary"),
                    start=float(item.get("start", 0)),
                    end=float(item.get("end", 0)),
                    speakers=item.get("speakers", []),
                    summary=item.get("summary", ""),
                    raw_text="",  # Will be filled by merge
                )
                result_segments.append(segment)

            return result_segments

        except Exception as e:
            logger.error(f"Failed to segment window: {e}")
            return []

    def _merge_segments(self, segments: list[Segment]) -> list[Segment]:
        """Merge overlapping and adjacent segments.

        Merges:
        - Segments with overlapping times
        - Same-type segments with gap < MERGE_GAP_SECONDS

        Args:
            segments: List of Segment from all windows

        Returns:
            List of merged Segment objects
        """
        if not segments:
            return []

        # Sort by start time
        sorted_segments = sorted(segments, key=lambda s: s.start)

        merged = [sorted_segments[0]]

        for current in sorted_segments[1:]:
            last = merged[-1]

            # Check if overlapping or should merge
            gap = current.start - last.end
            is_overlapping = gap < 0
            is_same_type_and_close = (
                current.type == last.type and gap < self.MERGE_GAP_SECONDS
            )

            if is_overlapping or is_same_type_and_close:
                # Merge: extend last segment
                merged_speakers = list(set(last.speakers + current.speakers))
                merged_segment = Segment(
                    type=last.type,
                    start=last.start,
                    end=max(last.end, current.end),
                    speakers=sorted(merged_speakers),
                    summary=f"{last.summary} / {current.summary}",
                    raw_text=last.raw_text,
                )
                merged[-1] = merged_segment
            else:
                merged.append(current)

        return merged
