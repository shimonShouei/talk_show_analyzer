"""Topic extraction using Claude API."""

import json
import re
from dataclasses import dataclass

import anthropic
from loguru import logger

from talk_show_analyzer.config import settings
from talk_show_analyzer.analysis.legacy.segmenter import Segment
from talk_show_analyzer.analysis.prompts.topics import SYSTEM_PROMPT, format_segment


@dataclass
class Topic:
    """A topic extracted from a segment."""

    name_he: str  # Hebrew name
    name_en: str  # English name
    category: str  # politics, security, economy, social, legal, international, sports, culture, other
    summary_he: str  # Hebrew summary
    summary_en: str  # English summary


@dataclass
class TopicAnalysis:
    """Topic analysis for a segment."""

    segment: Segment
    main_topic: Topic
    subtopics: list[Topic]


class TopicExtractor:
    """Extract topics from transcript segments using Claude."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        """Initialize topic extractor.

        Args:
            model: Claude model to use
        """
        self.model = model
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        # Segments to skip topic extraction
        self.skip_types = {"ad", "jingle", "music"}

    def extract_topics(self, segments: list[Segment]) -> list[TopicAnalysis]:
        """
        Extract topics from all segments.

        Args:
            segments: List of Segment objects

        Returns:
            List of TopicAnalysis with topics per segment
        """
        logger.info(f"Extracting topics from {len(segments)} segments")

        results = []
        for i, seg in enumerate(segments):
            if seg.type in self.skip_types:
                logger.info(f"Skipping {seg.type} segment: {seg.summary}")
                continue

            logger.info(
                f"Extracting topics from segment {i+1}/{len(segments)} "
                f"({seg.type}, {seg.start:.0f}s - {seg.end:.0f}s)"
            )

            analysis = self._analyze_segment(seg)
            if analysis:
                results.append(analysis)

        logger.info(f"Extracted topics from {len(results)} segments")
        return results

    def _analyze_segment(self, segment: Segment) -> TopicAnalysis | None:
        """Analyze a single segment for topics.

        Args:
            segment: Segment to analyze

        Returns:
            TopicAnalysis or None if extraction fails
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
                        "content": f"Extract topics from this segment:\n\n{segment_text}",
                    }
                ],
            )

            response_text = response.content[0].text.strip()

            # Parse JSON
            try:
                data = json.loads(response_text)
            except json.JSONDecodeError:
                json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    logger.warning(f"Could not parse response for segment {segment.summary}")
                    return None

            # Convert to Topic objects
            main_topic = Topic(
                name_he=data["main_topic"].get("name_he", ""),
                name_en=data["main_topic"].get("name_en", ""),
                category=data["main_topic"].get("category", "other"),
                summary_he=data["main_topic"].get("summary_he", ""),
                summary_en=data["main_topic"].get("summary_en", ""),
            )

            subtopics = [
                Topic(
                    name_he=t.get("name_he", ""),
                    name_en=t.get("name_en", ""),
                    category=t.get("category", "other"),
                    summary_he=t.get("summary_he", ""),
                    summary_en=t.get("summary_en", ""),
                )
                for t in data.get("subtopics", [])
            ]

            return TopicAnalysis(
                segment=segment,
                main_topic=main_topic,
                subtopics=subtopics,
            )

        except Exception as e:
            logger.error(f"Failed to extract topics: {e}")
            return None
