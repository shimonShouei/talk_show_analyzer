"""Analysis modules for talk show transcripts.

The Thematic Intelligence pipeline (`ThematicAnalyzer`) is the active analyzer.
The legacy `Segmenter` / `TopicExtractor` / `SentimentAnalyzer` modules remain
exported for backwards compatibility (dashboard pages still read from the
old tables) and will be removed in a follow-up.
"""

from talk_show_analyzer.analysis.legacy.segmenter import Segment, Segmenter
from talk_show_analyzer.analysis.legacy.topics import Topic, TopicAnalysis, TopicExtractor
from talk_show_analyzer.analysis.legacy.sentiment import (
    Sentiment,
    SentimentAnalysis,
    SentimentAnalyzer,
)
from talk_show_analyzer.analysis.legacy.ads import AdsReport, aggregate_ads
from talk_show_analyzer.analysis.thematic_analyzer import (
    Entity,
    EntityType,
    HateSpeechIncident,
    HateSpeechLevel,
    SpeakerInsight,
    Stance,
    ThematicAnalyzer,
    TopicAnalysis as ThematicTopicAnalysis,
    TopicCategory,
)

__all__ = [
    # Legacy (deprecated — will be removed once dashboard migrates)
    "Segment",
    "Segmenter",
    "Topic",
    "TopicAnalysis",
    "TopicExtractor",
    "Sentiment",
    "SentimentAnalysis",
    "SentimentAnalyzer",
    "AdsReport",
    "aggregate_ads",
    # Thematic Intelligence pipeline
    "ThematicAnalyzer",
    "ThematicTopicAnalysis",
    "Entity",
    "EntityType",
    "HateSpeechIncident",
    "HateSpeechLevel",
    "SpeakerInsight",
    "Stance",
    "TopicCategory",
]
