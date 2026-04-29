"""Guest identification using Claude API."""

import json
import re
from dataclasses import dataclass

import anthropic
from loguru import logger

from talk_show_analyzer.config import settings
from talk_show_analyzer.analysis.segmenter import Segment
from talk_show_analyzer.analysis.prompts.guests import SYSTEM_PROMPT, format_segment


@dataclass
class Guest:
    """A guest identified from a segment."""

    name_he: str  # Hebrew name
    name_en: str  # English transliteration
    title: str  # Job title/role
    affiliation: str  # Party/organization/publication
    speaker_label: str  # SPEAKER_00 or SPEAKER_UNKNOWN
    confidence: float  # 0.0-1.0


@dataclass
class GuestAnalysis:
    """Guest analysis for a segment."""

    segment: Segment
    guests: list[Guest]


class GuestIdentifier:
    """Identify guests from transcript segments using Claude."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        """Initialize guest identifier.

        Args:
            model: Claude model to use
        """
        self.model = model
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        # Only analyze segments where guests appear
        self.analyze_types = {"interview", "panel", "caller"}

    def identify_guests(self, segments: list[Segment]) -> list[GuestAnalysis]:
        """
        Identify guests from all segments.

        Args:
            segments: List of Segment objects

        Returns:
            List of GuestAnalysis with guests per segment
        """
        logger.info(f"Identifying guests from {len(segments)} segments")

        results = []
        for i, seg in enumerate(segments):
            if seg.type not in self.analyze_types:
                logger.info(f"Skipping {seg.type} segment for guest identification")
                continue

            logger.info(
                f"Identifying guests from segment {i+1}/{len(segments)} "
                f"({seg.type}, {seg.start:.0f}s - {seg.end:.0f}s)"
            )

            analysis = self._analyze_segment(seg)
            if analysis:
                results.append(analysis)

        logger.info(f"Identified guests in {len(results)} segments")
        return results

    def _analyze_segment(self, segment: Segment) -> GuestAnalysis | None:
        """Analyze a single segment for guests.

        Args:
            segment: Segment to analyze

        Returns:
            GuestAnalysis or None if extraction fails
        """
        segment_text = format_segment(segment)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                temperature=0,
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
                        "content": f"Identify guests from this segment:\n\n{segment_text}",
                    }
                ],
            )

            response_text = response.content[0].text.strip()

            # Parse JSON
            try:
                data = json.loads(response_text)
            except json.JSONDecodeError:
                json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    logger.warning(f"Could not parse response for segment {segment.summary}")
                    return GuestAnalysis(segment=segment, guests=[])

            # Convert to Guest objects
            guests = [
                Guest(
                    name_he=g.get("name_he", ""),
                    name_en=g.get("name_en", ""),
                    title=g.get("title", ""),
                    affiliation=g.get("affiliation", ""),
                    speaker_label=g.get("speaker_label", "SPEAKER_UNKNOWN"),
                    confidence=float(g.get("confidence", 0.5)),
                )
                for g in data
            ]

            return GuestAnalysis(segment=segment, guests=guests)

        except Exception as e:
            logger.error(f"Failed to identify guests: {e}")
            return GuestAnalysis(segment=segment, guests=[])
