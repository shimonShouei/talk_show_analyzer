"""Schedule provider abstractions.

A `ScheduleProvider` answers: which show is airing on station X at datetime T,
and who are its scheduled hosts? Concrete implementations live alongside this
module (one per station) and self-register via `register_provider`.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from loguru import logger


@dataclass(frozen=True)
class ScheduledShow:
    """A show airing at a specific time on a specific station."""

    station: str
    show_name: str
    start_time: datetime
    end_time: datetime
    hosts: list[str] = field(default_factory=list)
    description: Optional[str] = None
    program_url: Optional[str] = None


class ScheduleProvider(ABC):
    """Fetches the broadcast schedule for one station."""

    station: str  # subclasses set this class attribute

    @abstractmethod
    def fetch_for_datetime(self, when: datetime) -> Optional[ScheduledShow]:
        """Return the show airing at `when` (local Israel time), or None."""
        raise NotImplementedError


SCHEDULE_PROVIDERS: dict[str, ScheduleProvider] = {}


def register_provider(provider: ScheduleProvider) -> None:
    """Register a concrete provider keyed by station name."""
    SCHEDULE_PROVIDERS[provider.station] = provider


def get_scheduled_show(station: str, when: datetime) -> Optional[ScheduledShow]:
    """Dispatch to the right provider; return None on missing provider or fetch failure."""
    provider = SCHEDULE_PROVIDERS.get(station)
    if provider is None:
        logger.warning(f"No schedule provider registered for station '{station}'")
        return None
    try:
        return provider.fetch_for_datetime(when)
    except Exception as exc:
        logger.warning(f"Schedule fetch failed for {station} @ {when}: {exc}")
        return None
