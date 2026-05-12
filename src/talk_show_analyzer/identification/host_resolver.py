"""Match scheduled hosts against LLM-identified speakers.

Given an episode's `recorded_at` datetime and the speaker-identification output,
this resolver fetches the scheduled hosts (via `recorder.schedules`) and partitions
identified host-role speakers into: confirmed (matched a scheduled host),
substitutes (named host but not scheduled — likely fill-ins), and unknown
(role=host but name resolved as Unknown). It also reports which scheduled hosts
are missing entirely from the episode.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from loguru import logger

from talk_show_analyzer.identification.llm_identifier import ResolvedSpeaker
from talk_show_analyzer.recorder.schedules import (
    ScheduledShow,
    get_scheduled_show,
)


@dataclass
class HostResolution:
    """Outcome of matching scheduled hosts against identified speakers."""

    schedule_available: bool
    show_name: Optional[str] = None
    expected_hosts: list[str] = field(default_factory=list)
    confirmed: list[tuple[str, str]] = field(default_factory=list)
    substitutes: list[tuple[str, str]] = field(default_factory=list)
    missing_expected: list[str] = field(default_factory=list)
    unknown_hosts: list[str] = field(default_factory=list)


def _normalize(s: str) -> str:
    return re.sub(r"[\s.,'\"׳״\-–—]+", "", (s or "").strip()).lower()


def _matches(expected: str, candidate: str) -> bool:
    e, c = _normalize(expected), _normalize(candidate)
    if not e or not c:
        return False
    return e in c or c in e


ScheduleFetcher = Callable[[str, datetime], Optional[ScheduledShow]]


class HostResolver:
    """Reconcile schedule-provided hosts with LLM-identified speakers."""

    def __init__(self, schedule_fetcher: Optional[ScheduleFetcher] = None):
        self._fetch = schedule_fetcher or get_scheduled_show

    def resolve(
        self,
        station: str,
        recorded_at: datetime,
        resolved_speakers: dict[str, ResolvedSpeaker],
    ) -> HostResolution:
        host_speakers = {
            label: rs
            for label, rs in resolved_speakers.items()
            if rs.role == "host"
        }

        show = self._fetch(station, recorded_at)

        if show is None:
            unknown = [
                lab for lab, rs in host_speakers.items() if rs.name_en == "Unknown"
            ]
            logger.info(
                f"host resolution (no schedule): unknown={len(unknown)} of "
                f"{len(host_speakers)} host-role speakers"
            )
            return HostResolution(
                schedule_available=False,
                unknown_hosts=unknown,
            )

        expected = list(show.hosts)

        confirmed: list[tuple[str, str]] = []
        matched_expected: set[str] = set()
        substitutes: list[tuple[str, str]] = []
        unknown: list[str] = []

        for label, rs in host_speakers.items():
            if rs.name_en == "Unknown" or rs.name_he == "Unknown":
                unknown.append(label)
                continue
            matched_name: Optional[str] = None
            for exp in expected:
                if exp in matched_expected:
                    continue
                if _matches(exp, rs.name_he) or _matches(exp, rs.name_en):
                    matched_name = exp
                    break
            if matched_name is not None:
                confirmed.append((label, matched_name))
                matched_expected.add(matched_name)
            else:
                substitutes.append((label, rs.name_he or rs.name_en))

        missing = [e for e in expected if e not in matched_expected]

        logger.info(
            f"host resolution: confirmed={len(confirmed)} substitutes={len(substitutes)} "
            f"missing={len(missing)} unknown={len(unknown)} "
            f"(show: {show.show_name!r})"
        )

        return HostResolution(
            schedule_available=True,
            show_name=show.show_name,
            expected_hosts=expected,
            confirmed=confirmed,
            substitutes=substitutes,
            missing_expected=missing,
            unknown_hosts=unknown,
        )
