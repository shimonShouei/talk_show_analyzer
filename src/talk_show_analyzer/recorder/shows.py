"""Show registry and definitions for Israeli radio stations."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ShowDefinition:
    """Definition of a recurring radio show."""

    station: str  # "galatz", "kan_bet", "103fm"
    name_he: str  # Hebrew name
    name_en: str  # English name
    start_time: str  # "08:00" (24-hour format)
    end_time: str  # "10:00"
    duration_minutes: int  # Total show length (e.g., 120 for 2 hours)

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
            "Daily news update. Two-hour show with flexible segment structure."
        ),
    ),
    "kan_bet": ShowDefinition(
        station="kan_bet",
        name_he="רדיו ישראל",
        name_en="Kan Reshet Bet Radio",
        start_time="08:00",
        end_time="10:00",
        duration_minutes=120,
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
            "Daily news update. Two-hour show with flexible segment structure."
        ),
    ),
    "103fm": ShowDefinition(
        station="103fm",
        name_he="רדיו 103 FM",
        name_en="103FM Radio",
        start_time="09:00",
        end_time="11:00",
        duration_minutes=120,
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
            "Daily news update. Two-hour show with flexible segment structure."
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


def format_show_context(show: ShowDefinition) -> str:
    """
    Format show information for inclusion in analysis prompts.

    Args:
        show: ShowDefinition

    Returns:
        Formatted string describing the show format and participants
    """
    context = f"""
SHOW CONTEXT:
=============
Station: {show.name_en} ({show.name_he})
Time: {show.start_time}-{show.end_time}
Duration: {show.duration_minutes} minutes

Description:
{show.description}

FLEXIBLE SHOW FORMAT:
====================
This show has a flexible, unpredictable structure:

• OPENING NEWS: ~5-6 minutes of news headlines (typically at start)
  - Delivered by newsreader
  - Multiple news stories

• MAIN CONTENT: Mix of interviews and manifests
  - INTERVIEW: Host(s) + guest(s) discussing a topic
  - MANIFEST: Host(s) only - could be 1 host talking alone OR both hosts discussing
  - Can transition between interview and manifest multiple times
  - No fixed order or timing

• AD BREAKS: Commercial advertisements
  - Appear at unpredictable times (not at fixed intervals)
  - Duration varies (typically 2-5 minutes)
  - Not announced in advance

KNOWN PARTICIPANTS:
===================
Hosts: {', '.join(show.hosts)}
Newsreaders: {', '.join(show.newsreaders)}

SEGMENTATION HINTS:
===================
• News segment typically appears at the start, lasts 5-6 minutes
• Distinguish by GUEST PRESENCE (not speaker count):
  - MANIFEST: Host(s) only, no guests. Could be 1 host talking alone OR both hosts discussing.
  - INTERVIEW: Host(s) + 1+ guests. Identify by presence of guest voice(s).
  - PANEL: Host(s) + multiple distinct guest voices (2+ guests). More debate-oriented.
• Ad blocks have commercial language ("call now", "visit", "special offer")
• Transitions between interview and manifest are common
• Known host names help identify when a speaker is host vs guest
"""

    return context


__all__ = [
    "ShowDefinition",
    "SHOWS",
    "get_show",
    "format_show_context",
]
