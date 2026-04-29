"""Sentiment analysis using Claude API."""

import json
import re
from dataclasses import dataclass

import anthropic
from loguru import logger

from talk_show_analyzer.config import settings
from talk_show_analyzer.analysis.segmenter import Segment
from talk_show_analyzer.analysis.topics import TopicAnalysis
from talk_show_analyzer.analysis.prompts.sentiment import (
    SYSTEM_PROMPT,
    format_segment_for_sentiment,
)


@dataclass
class Sentiment:
    """Sentiment analysis for a speaker on a topic."""

    speaker_label: str  # SPEAKER_00, etc
    topic: str  # Topic name
    score: float  # -1.0 to +1.0
    tone: str  # angry, calm, enthusiastic, dismissive, neutral, concerned
    quotes: list[str]  # 2-3 supporting quotes


@dataclass
class SentimentAnalysis:
    """Sentiment analysis results for a segment."""

    topic_analysis: TopicAnalysis
    sentiments: list[Sentiment]


class SentimentAnalyzer:
    """Analyze sentiment using Claude API."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        """Initialize sentiment analyzer.

        Args:
            model: Claude model to use
        """
        self.model = model
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def analyze_sentiments(
        self, topic_analyses: list[TopicAnalysis]
    ) -> list[SentimentAnalysis]:
        """
        Analyze sentiment for all topic analyses.

        Args:
            topic_analyses: List of TopicAnalysis from topic extractor

        Returns:
            List of SentimentAnalysis with sentiment per topic
        """
        logger.info(f"Analyzing sentiment for {len(topic_analyses)} topics")

        results = []
        for i, analysis in enumerate(topic_analyses):
            logger.info(
                f"Analyzing sentiment {i+1}/{len(topic_analyses)} "
                f"(topic: {analysis.main_topic.name_en}, segment {analysis.segment.type})"
            )

            sentiment_analysis = self._analyze_topic(analysis)
            if sentiment_analysis:
                results.append(sentiment_analysis)

        logger.info(f"Analyzed sentiment for {len(results)} topics")
        return results

    def _analyze_topic(self, topic_analysis: TopicAnalysis) -> SentimentAnalysis | None:
        """Analyze sentiment for a single topic.

        Args:
            topic_analysis: TopicAnalysis to analyze

        Returns:
            SentimentAnalysis or None if extraction fails
        """
        segment = topic_analysis.segment
        main_topic = topic_analysis.main_topic.name_en

        segment_text = format_segment_for_sentiment(segment, main_topic)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
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
                        "content": (
                            f"Analyze sentiment of speakers discussing this topic:\n\n{segment_text}"
                        ),
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
                    logger.warning(
                        f"Could not parse sentiment response for {main_topic}"
                    )
                    return SentimentAnalysis(topic_analysis=topic_analysis, sentiments=[])

            # Convert to Sentiment objects
            sentiments = [
                Sentiment(
                    speaker_label=s.get("speaker_label", "SPEAKER_UNKNOWN"),
                    topic=s.get("topic", main_topic),
                    score=float(s.get("score", 0)),
                    tone=s.get("tone", "neutral"),
                    quotes=s.get("quotes", []),
                )
                for s in data
            ]

            return SentimentAnalysis(topic_analysis=topic_analysis, sentiments=sentiments)

        except Exception as e:
            logger.error(f"Failed to analyze sentiment: {e}")
            return SentimentAnalysis(topic_analysis=topic_analysis, sentiments=[])
