"""Show registry and definitions for Israeli radio stations."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SegmentTemplate:
    """Expected segment in a show's recurring structure."""

    type: str  # "interview", "manifest", "news", "ads", "jingle"
    expected_minute: int  # When this segment typically starts (0 = :00, 25 = :25, etc.)
    expected_duration: int  # Duration in minutes
    description: str  # For validation prompts


@dataclass
class ShowDefinition:
    """Definition of a recurring radio show."""

    station: str  # "galatz", "kan_bet", "103fm"
    name_he: str  # Hebrew name
    name_en: str  # English name
    start_time: str  # "08:00" (24-hour format)
    end_time: str  # "10:00"
    duration_minutes: int  # Total show length (e.g., 120 for 2 hours)

    # Recurring structure (repeats every hour)
    hourly_segments: list[SegmentTemplate]

    # Known people on the show
    hosts: list[str]  # Names of regular hosts
    newsreaders: list[str]  # Names of newsreaders

    description: str  # For prompts


# Show definitions for each station
SHOWS = {
    "galatz": ShowDefinition(
        station="galatz",
        name_he="בוקר טוב ישראל",
        name_en="Good Morning Israel",
        start_time="08:00",
        end_time="10:00",
        duration_minutes=120,
        hourly_segments=[
            SegmentTemplate(
                type="interview",
                expected_minute=0,
                expected_duration=25,
                description="In-depth interview with guest(s) or manifesto discussion",
            ),
            SegmentTemplate(
                type="ads",
                expected_minute=25,
                expected_duration=4,
                description="Commercial ad block",
            ),
            SegmentTemplate(
                type="news",
                expected_minute=29,
                expected_duration=5,
                description="News headlines and stories (~5 min newsreader)",
            ),
            SegmentTemplate(
                type="interview",
                expected_minute=34,
                expected_duration=26,
                description="Return to interview or next segment",
            ),
        ],
        hosts=[
            "רננה הראל",  # Rona Harel (example)
            "גלעד שליט",    # Gilad Shalit (example)
        ],
        newsreaders=[
            "דניה קלמן",    # Dani Kalman (example newsreader)
        ],
        description=(
            "Galatz morning show (08:00-10:00). "
            "Features interviews with political figures, journalists, and experts. "
            "Hourly news at :29. Ad blocks at :25. Two complete cycles per day."
        ),
    ),
    "kan_bet": ShowDefinition(
        station="kan_bet",
        name_he="רדיו ישראל",
        name_en="Kan Reshet Bet Radio",
        start_time="08:00",
        end_time="10:00",
        duration_minutes=120,
        hourly_segments=[
            SegmentTemplate(
                type="interview",
                expected_minute=0,
                expected_duration=25,
                description="In-depth interview or panel discussion",
            ),
            SegmentTemplate(
                type="ads",
                expected_minute=25,
                expected_duration=4,
                description="Commercial ad block",
            ),
            SegmentTemplate(
                type="news",
                expected_minute=29,
                expected_duration=5,
                description="News headlines and stories",
            ),
            SegmentTemplate(
                type="interview",
                expected_minute=34,
                expected_duration=26,
                description="Return to interview or next topic",
            ),
        ],
        hosts=[
            "מוניקה תסונה",    # Monika Tasuna (example)
            "רונית סנדר",      # Ronit Sander (example)
        ],
        newsreaders=[
            "יוסי לנדאו",      # Yossi Landau (example newsreader)
        ],
        description=(
            "Kan Reshet Bet morning show (08:00-10:00). "
            "Features discussions on current events, politics, and social issues. "
            "Hourly news updates. Ad blocks at :25. Two complete cycles per day."
        ),
    ),
    "103fm": ShowDefinition(
        station="103fm",
        name_he="רדיו 103 FM",
        name_en="103FM Radio",
        start_time="09:00",
        end_time="11:00",
        duration_minutes=120,
        hourly_segments=[
            SegmentTemplate(
                type="interview",
                expected_minute=0,
                expected_duration=25,
                description="In-depth interview with personalities",
            ),
            SegmentTemplate(
                type="ads",
                expected_minute=25,
                expected_duration=4,
                description="Commercial ad block",
            ),
            SegmentTemplate(
                type="news",
                expected_minute=29,
                expected_duration=5,
                description="News headlines and stories",
            ),
            SegmentTemplate(
                type="interview",
                expected_minute=34,
                expected_duration=26,
                description="Return to interview or next segment",
            ),
        ],
        hosts=[
            "עמירה עמיר",      # Amira Amir (example)
            "ניר ישראלי",      # Nir Israeli (example)
        ],
        newsreaders=[
            "אורן כרמלי",      # Oren Carmeli (example newsreader)
        ],
        description=(
            "103FM morning show (09:00-11:00). "
            "Features cultural discussion, music, and current events. "
            "Hourly news at :29. Ad blocks at :25. Two complete cycles per day."
        ),
    ),
}


def get_show(station: str, time: Optional[str] = None) -> Optional[ShowDefinition]:
    """
    Get show definition for a station.

    Args:
        station: Station key ("galatz", "kan_bet", "103fm")
        time: Time in HH:MM format (optional, for validation)

    Returns:
        ShowDefinition if found and time is within show window, else None
    """
    show = SHOWS.get(station.lower())

    if not show or not time:
        return show

    # Check if time is within show window
    start_h, start_m = map(int, show.start_time.split(":"))
    end_h, end_m = map(int, show.end_time.split(":"))
    time_h, time_m = map(int, time.split(":"))

    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m
    time_minutes = time_h * 60 + time_m

    if start_minutes <= time_minutes < end_minutes:
        return show

    return None


def get_segment_at_minute(show: ShowDefinition, minute_in_hour: int) -> Optional[SegmentTemplate]:
    """
    Get expected segment template at a specific minute within the hour.

    Args:
        show: ShowDefinition
        minute_in_hour: Minute within the hour (0-59)

    Returns:
        SegmentTemplate if found, else None
    """
    for segment in show.hourly_segments:
        if (segment.expected_minute <= minute_in_hour <
            segment.expected_minute + segment.expected_duration):
            return segment

    return None


def format_show_context(show: ShowDefinition) -> str:
    """
    Format show information for inclusion in analysis prompts.

    Args:
        show: ShowDefinition

    Returns:
        Formatted string describing the show and its structure
    """
    context = f"""
SHOW CONTEXT:
=============
Station: {show.name_en} ({show.name_he})
Time: {show.start_time}-{show.end_time}
Duration: {show.duration_minutes} minutes

Description:
{show.description}

RECURRING HOURLY STRUCTURE:
==========================
This show repeats the same structure every hour. Expect:
"""

    for segment in show.hourly_segments:
        context += f"\n  • {segment.type.upper()} at minute {segment.expected_minute} (~{segment.expected_duration} min)"
        context += f"\n    {segment.description}"

    context += f"\n\nKNOWN PARTICIPANTS:"
    context += f"\n  Hosts: {', '.join(show.hosts)}"
    context += f"\n  Newsreaders: {', '.join(show.newsreaders)}"

    context += """

SEGMENTATION HINTS:
===================
• News segments appear at :29 of each hour and last ~5 minutes
• Ad blocks appear at :25 of each hour and last ~4 minutes
• Use these time markers to validate your segment predictions
• If segments don't match the expected structure, flag low confidence
"""

    return context


__all__ = [
    "ShowDefinition",
    "SegmentTemplate",
    "SHOWS",
    "get_show",
    "get_segment_at_minute",
    "format_show_context",
]
