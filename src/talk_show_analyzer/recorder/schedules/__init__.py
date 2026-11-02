"""Schedule scrapers for radio stations."""

from talk_show_analyzer.recorder.schedules.base import (
    ScheduledShow,
    ScheduleProvider,
    SCHEDULE_PROVIDERS,
    register_provider,
    get_scheduled_show,
    get_scheduled_shows,
)
from talk_show_analyzer.recorder.schedules.fm103 import FM103ScheduleProvider

register_provider(FM103ScheduleProvider())

__all__ = [
    "ScheduledShow",
    "ScheduleProvider",
    "SCHEDULE_PROVIDERS",
    "register_provider",
    "get_scheduled_show",
    "get_scheduled_shows",
    "FM103ScheduleProvider",
]
