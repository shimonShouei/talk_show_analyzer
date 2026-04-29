"""Ad time aggregation and reporting."""

from dataclasses import dataclass
from loguru import logger

from talk_show_analyzer.analysis.segmenter import Segment


@dataclass
class AdsReport:
    """Aggregated ad statistics for a show."""

    total_duration: float  # Total show duration in seconds
    ad_duration: float  # Total ad time in seconds
    ad_percentage: float  # Ad time as percentage (0-100)
    ad_count: int  # Number of ad segments
    ad_segments: list[Segment]  # All ad segments


def aggregate_ads(segments: list[Segment], show_duration: float) -> AdsReport:
    """
    Aggregate ad statistics from segmented transcript.

    Args:
        segments: List of Segment objects from segmenter
        show_duration: Total duration of the show in seconds

    Returns:
        AdsReport with ad metrics
    """
    ad_segments = [seg for seg in segments if seg.type == "ad"]

    ad_duration = sum(seg.end - seg.start for seg in ad_segments)
    ad_percentage = (ad_duration / show_duration * 100) if show_duration > 0 else 0

    logger.info(
        f"Ad analysis: {len(ad_segments)} ads, {ad_duration:.0f}s / {show_duration:.0f}s "
        f"({ad_percentage:.1f}%)"
    )

    return AdsReport(
        total_duration=show_duration,
        ad_duration=ad_duration,
        ad_percentage=ad_percentage,
        ad_count=len(ad_segments),
        ad_segments=ad_segments,
    )
