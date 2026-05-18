"""Structural segmenter — split an episode into high-level parts.

Given a transcript (diarized segments) and the resolved speakers from the
identification stage, this module groups segments into structural parts:

  - INTERVIEW   — host(s) and at least one non-host speaker active together
  - HOST_TALK   — only host speakers active (transition / monologue / open)
  - NEWS        — structured news bulletin (no host participation)
  - COMMERCIAL  — advertisement block
  - JINGLE      — short station ident / musical sting
  - UNKNOWN     — neither host nor guest classified (rare)

segment_into_parts() uses role labels from the identification stage (heuristic).
assemble_parts_from_chunks() uses LLM-classified part_type from ChunkAnalyzer,
which also detects news/commercial/jingle from transcript content patterns.

Algorithm:
  1. Classify each diarized segment by inspecting the speaker cohort within a
     short window around it. If hosts AND a guest both speak within the window,
     that region is INTERVIEW; if only hosts, HOST_TALK.
  2. Walk the segments left-to-right, grouping adjacent same-type segments into
     a Part. Break on a long silence gap or a type change.
  3. Merge parts shorter than `min_part_duration_s` into their neighbour so we
     don't emit transient flickers when the window straddles a transition.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional

from loguru import logger

from talk_show_analyzer.identification.llm_identifier import ResolvedSpeaker
from talk_show_analyzer.transcription.transcriber import SpeakerSegment


class PartType(str, Enum):
    """High-level structural part categories."""

    INTERVIEW = "interview"
    HOST_TALK = "host_talk"
    NEWS = "news"
    JINGLE = "jingle"
    COMMERCIAL = "commercial"
    UNKNOWN = "unknown"


@dataclass
class Part:
    """A contiguous structural part of an episode."""

    type: PartType
    start: float
    end: float
    segments: list[SpeakerSegment] = field(default_factory=list)
    host_labels: set[str] = field(default_factory=set)
    guest_labels: set[str] = field(default_factory=set)
    unknown_labels: set[str] = field(default_factory=set)

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def all_speakers(self) -> set[str]:
        return self.host_labels | self.guest_labels | self.unknown_labels


DEFAULT_WINDOW_S = 30.0
DEFAULT_GAP_THRESHOLD_S = 30.0
DEFAULT_MIN_PART_DURATION_S = 20.0


def _classify_speaker(label: str, resolved: dict[str, ResolvedSpeaker]) -> str:
    """Map a diarization label to "host" | "guest" | "unknown"."""
    rs = resolved.get(label)
    if rs is None:
        return "unknown"
    if rs.role == "host":
        return "host"
    if rs.role in ("guest", "caller"):
        return "guest"
    return "unknown"


def _part_type_for(host: bool, guest: bool) -> PartType:
    if guest and host:
        return PartType.INTERVIEW
    if guest:
        return PartType.INTERVIEW  # rare: guests-only block, still a discourse
    if host:
        return PartType.HOST_TALK
    return PartType.UNKNOWN


def _classify_segment_with_window(
    idx: int,
    segs: list[SpeakerSegment],
    resolved: dict[str, ResolvedSpeaker],
    half_window_s: float,
) -> PartType:
    """Type of a segment based on roles active within ±half_window_s of it."""
    s = segs[idx]
    lo = s.start - half_window_s
    hi = s.end + half_window_s
    host = False
    guest = False
    # Walk outward from idx for speed (segments are time-sorted).
    for j in range(idx, -1, -1):
        if segs[j].end < lo:
            break
        role = _classify_speaker(segs[j].speaker, resolved)
        if role == "host":
            host = True
        elif role == "guest":
            guest = True
    for j in range(idx + 1, len(segs)):
        if segs[j].start > hi:
            break
        role = _classify_speaker(segs[j].speaker, resolved)
        if role == "host":
            host = True
        elif role == "guest":
            guest = True
    return _part_type_for(host, guest)


def _add_speaker(part: Part, label: str, role: str) -> None:
    if role == "host":
        part.host_labels.add(label)
    elif role == "guest":
        part.guest_labels.add(label)
    else:
        part.unknown_labels.add(label)


def _merge_short_parts(parts: list[Part], min_duration: float) -> list[Part]:
    """Absorb parts shorter than min_duration into a neighbour."""
    if not parts:
        return parts
    out: list[Part] = []
    for p in parts:
        if out and out[-1].duration < min_duration:
            # Previous part too short — absorb it into the current one.
            prev = out.pop()
            merged = Part(
                type=p.type,
                start=prev.start,
                end=p.end,
                segments=prev.segments + p.segments,
                host_labels=prev.host_labels | p.host_labels,
                guest_labels=prev.guest_labels | p.guest_labels,
                unknown_labels=prev.unknown_labels | p.unknown_labels,
            )
            merged.type = _part_type_for(bool(merged.host_labels), bool(merged.guest_labels))
            out.append(merged)
        else:
            out.append(p)
    # Tail: if last part is short, fold into the one before it.
    if len(out) >= 2 and out[-1].duration < min_duration:
        tail = out.pop()
        prev = out.pop()
        prev.end = tail.end
        prev.segments.extend(tail.segments)
        prev.host_labels |= tail.host_labels
        prev.guest_labels |= tail.guest_labels
        prev.unknown_labels |= tail.unknown_labels
        prev.type = _part_type_for(bool(prev.host_labels), bool(prev.guest_labels))
        out.append(prev)
    return out


# These types act as hard structural boundaries in the broadcast.  Even a 3-second
# jingle marks the real end of one segment and the start of the next, so we never
# absorb them into a neighbour and never merge content across them.
_HARD_BOUNDARY_TYPES = {PartType.JINGLE, PartType.COMMERCIAL, PartType.NEWS}


def _merge_short_parts_by_type(parts: list[Part], min_duration: float) -> list[Part]:
    """Like _merge_short_parts but preserves the absorbing part's type.

    Used when parts come from chunk_analyze (no host/guest label sets populated),
    so we cannot recompute type from labels — instead keep the longer neighbour's type.

    JINGLE / COMMERCIAL / NEWS parts are never absorbed regardless of duration:
    they mark real structural transitions (a sting ends one segment and opens
    the next), so removing them would merge unrelated content across the boundary.
    """
    if not parts:
        return parts
    out: list[Part] = []
    for p in parts:
        # Hard-boundary types are always kept as-is.
        if p.type in _HARD_BOUNDARY_TYPES:
            out.append(p)
            continue
        # Only absorb a short predecessor when neither it nor the part before it
        # is a hard boundary (otherwise the boundary would be silently erased).
        if (
            out
            and out[-1].duration < min_duration
            and out[-1].type not in _HARD_BOUNDARY_TYPES
            and (len(out) < 2 or out[-2].type not in _HARD_BOUNDARY_TYPES)
        ):
            prev = out.pop()
            merged = Part(
                type=p.type,
                start=prev.start,
                end=p.end,
                segments=prev.segments + p.segments,
                host_labels=prev.host_labels | p.host_labels,
                guest_labels=prev.guest_labels | p.guest_labels,
                unknown_labels=prev.unknown_labels | p.unknown_labels,
            )
            out.append(merged)
        else:
            out.append(p)
    # Tail: short content part folds into its predecessor only when no boundary separates them.
    if (
        len(out) >= 2
        and out[-1].duration < min_duration
        and out[-1].type not in _HARD_BOUNDARY_TYPES
        and out[-2].type not in _HARD_BOUNDARY_TYPES
    ):
        tail = out.pop()
        prev = out[-1]
        prev.end = tail.end
        prev.segments.extend(tail.segments)
        prev.host_labels |= tail.host_labels
        prev.guest_labels |= tail.guest_labels
        prev.unknown_labels |= tail.unknown_labels
    return out


def assemble_parts_from_chunks(
    chunk_analyses: list,  # list[ChunkAnalysis] — imported lazily to avoid circular
    *,
    min_part_duration_s: float = DEFAULT_MIN_PART_DURATION_S,
) -> list[Part]:
    """Assemble structural parts from per-chunk part_type classifications.

    Merges adjacent chunks with the same part_type, then applies _merge_short_parts()
    to clean up short fragments. No LLM call — pure post-processing.
    """
    if not chunk_analyses:
        return []

    parts: list[Part] = []
    cur: Optional[Part] = None

    for ca in sorted(chunk_analyses, key=lambda c: c.start):
        try:
            pt = PartType(ca.part_type)
        except ValueError:
            pt = PartType.UNKNOWN

        if cur is None or pt != cur.type:
            if cur is not None:
                parts.append(cur)
            cur = Part(type=pt, start=ca.start, end=ca.end)
        else:
            cur.end = ca.end

    if cur is not None:
        parts.append(cur)

    parts = _merge_short_parts_by_type(parts, min_part_duration_s)

    counts = {pt: sum(1 for p in parts if p.type == pt) for pt in PartType}
    summary = ", ".join(f"{c} {pt.value}" for pt, c in counts.items() if c > 0)
    logger.info(f"assemble_parts_from_chunks: {len(parts)} part(s) — {summary}")
    return parts


def segment_into_parts(
    segments: Iterable[SpeakerSegment],
    resolved_speakers: dict[str, ResolvedSpeaker],
    *,
    window_s: float = DEFAULT_WINDOW_S,
    gap_threshold_s: float = DEFAULT_GAP_THRESHOLD_S,
    min_part_duration_s: float = DEFAULT_MIN_PART_DURATION_S,
) -> list[Part]:
    """Group transcript segments into structural parts.

    Args:
      segments: Diarized speaker segments (any order — they'll be sorted).
      resolved_speakers: Output of UnifiedSpeakerIdentifier.identify_speakers.
      window_s: Total width of the smoothing window used to classify each
        segment (half on each side). Wider = more tolerant of brief host
        interjections during interviews.
      gap_threshold_s: A silence gap at least this long always starts a new part.
      min_part_duration_s: Parts shorter than this are merged into a neighbour.

    Returns:
      Time-ordered list of Part instances spanning the whole transcript.
    """
    segs = sorted(segments, key=lambda s: s.start)
    if not segs:
        return []

    half = window_s / 2.0
    seg_types = [
        _classify_segment_with_window(i, segs, resolved_speakers, half)
        for i in range(len(segs))
    ]

    parts: list[Part] = []
    cur: Optional[Part] = None
    cur_type: Optional[PartType] = None

    for seg, t in zip(segs, seg_types):
        role = _classify_speaker(seg.speaker, resolved_speakers)
        if cur is None:
            cur = Part(type=t, start=seg.start, end=seg.end)
            cur_type = t
        else:
            gap = seg.start - cur.end
            if t != cur_type or gap >= gap_threshold_s:
                parts.append(cur)
                cur = Part(type=t, start=seg.start, end=seg.end)
                cur_type = t
        cur.segments.append(seg)
        cur.end = max(cur.end, seg.end)
        _add_speaker(cur, seg.speaker, role)

    if cur is not None:
        parts.append(cur)

    parts = _merge_short_parts(parts, min_part_duration_s)

    logger.info(
        f"structural segmenter: produced {len(parts)} part(s) — "
        f"{sum(1 for p in parts if p.type == PartType.INTERVIEW)} interview, "
        f"{sum(1 for p in parts if p.type == PartType.HOST_TALK)} host_talk, "
        f"{sum(1 for p in parts if p.type == PartType.UNKNOWN)} unknown"
    )
    return parts
