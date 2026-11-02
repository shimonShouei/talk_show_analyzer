"""Unified per-chunk analysis: speaker roles + topic segmentation + structural classification.

Each 5-minute window of the transcript gets a single Claude API call that returns:
  - speaker_roles: role + name identification for each speaker in this window
  - topics: topic-coherent sub-segments within the window
  - part_type: interview / host_talk / unknown

Results are then clustered across chunks (no extra API calls) to produce:
  - Consolidated speaker identities (via consolidate_speakers in llm_identifier)
  - Merged topics fed into Stage 2 + Stage 3 of ThematicAnalyzer
  - Assembled structural parts (via assemble_parts_from_chunks in structural_segmenter)
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import anthropic
from loguru import logger

from talk_show_analyzer.config import settings
from talk_show_analyzer.analysis.utils import (
    create_sliding_windows,
    extract_fenced_json,
    safe_response_text,
)
from talk_show_analyzer.transcription.transcriber import SpeakerSegment, TranscriptionResult

_MAX_WINDOW_CHARS = 80_000

CHUNK_SYSTEM_PROMPT = """You are an expert Israeli media analyst. You receive a segment of a Hebrew radio talk show transcript with speaker labels (SPEAKER_00, SPEAKER_01, etc.) assigned by automatic diarization.

Your task: analyze this segment and return a single JSON object with three keys.

## 1. speaker_roles
For each speaker label that appears in this segment, infer their role and name (if mentioned).

Roles (choose one):
- "host" — regular show presenter: asks questions, controls flow, short turns, bookends conversation
- "guest" — external expert/figure invited to the studio or by phone for an interview
- "caller" — member of the public calling in; greeted by name, brief appearance
- "media_clip" — a played RECORDING of someone (politician speech, archive clip, news soundbite). Cues: host introduces with "שמעו מה אמר", "הנה הקלטה", "זה אמר X", "הנה קטע"; the segment is a monologue with no conversational response; hosts comment ABOUT the speaker afterwards, never speak TO them
- "unknown" — cannot determine

## 2. topics
Identify topic-coherent sub-segments within this window. A new topic starts when the conversation pivots to a different subject, a new guest joins, or an explicit "let's move on" from the host.

## 3. part_type
Classify the overall nature of this segment (ignore media_clip speakers — they are not live participants):
- "interview" — a host is interviewing an EXTERNAL guest or a caller (someone from outside the studio)
- "host_talk" — only the regular show hosts are present (co-hosts discussing, monologue, transition, intro/outro, or playing clips). Two hosts talking to each other = host_talk. Hosts + media_clips only = host_talk.
- "news" — a structured news bulletin: formulaic Hebrew ("חדשות", "בשעה X", "מערכת החדשות"), anchor read with reporter sign-offs, no host participation
- "commercial" — advertisement block: brand names, phone numbers, prices, "התקשרו עכשיו", "בחסות", jingle stings between ads, clearly not show content
- "jingle" — very short station ident or musical sting; transcript is near-empty, garbled, or just sound descriptions
- "unknown" — cannot determine

Key rule: if all LIVE speakers are hosts (guests/callers = 0), classify as "host_talk". "interview" requires a live non-host participant. Prioritize "news"/"commercial"/"jingle" over "host_talk" when the content clearly matches those patterns.

## JSON Schema

First reason inside <thinking>...</thinking>, then output ONLY a fenced ```json``` block:

```json
{
  "speaker_roles": [
    {
      "speaker_label": "SPEAKER_00",
      "role": "host",
      "name_he": "שם בעברית או Unknown",
      "name_en": "Name or Unknown",
      "confidence": 0.85,
      "evidence": "exact quote that establishes role/name, or empty string"
    }
  ],
  "topics": [
    {
      "start": 0.0,
      "end": 142.5,
      "speakers": ["SPEAKER_00", "SPEAKER_01"],
      "tentative_title_he": "כותרת קצרה עד 8 מילים",
      "tentative_summary_he": "תקציר של 1-2 משפטים"
    }
  ],
  "part_type": "interview"
}
```

Confidence rules (strict):
- 0.9+: name explicitly stated to/by this speaker (greeting, self-introduction)
- 0.7-0.89: consistent direct address or title+answer pattern across multiple turns
- below 0.7: return "Unknown" for name"""


def _format_window(segments: list[SpeakerSegment]) -> str:
    return "\n".join(
        f"[{s.start:.0f}s-{s.end:.0f}s] {s.speaker}: {s.text}" for s in segments
    )


@dataclass
class ChunkSpeakerRole:
    speaker_label: str
    role: str           # host / guest / caller / unknown
    name_he: str
    name_en: str
    confidence: float
    evidence: str


@dataclass
class ChunkTopic:
    start: float
    end: float
    speakers: list[str] = field(default_factory=list)
    tentative_title_he: str = ""
    tentative_summary_he: str = ""


@dataclass
class ChunkAnalysis:
    chunk_id: str
    start: float
    end: float
    part_type: str      # interview / host_talk / unknown
    speaker_roles: list[ChunkSpeakerRole] = field(default_factory=list)
    topics: list[ChunkTopic] = field(default_factory=list)
    raw_text: str = ""  # formatted window text (used as raw_text for Stage 3)


class ChunkAnalyzer:
    """Analyze each 5-minute transcript window in one parallel API call."""

    WINDOW_SIZE_SECONDS = 300.0
    OVERLAP_SECONDS = 60.0
    MAX_WORKERS = 4

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        self.model = model
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def analyze_all(self, transcript: TranscriptionResult) -> list[ChunkAnalysis]:
        """Analyze all windows in parallel. Returns list sorted by chunk start time."""
        windows = create_sliding_windows(
            transcript, self.WINDOW_SIZE_SECONDS, self.OVERLAP_SECONDS
        )
        if not windows:
            return []

        total = len(windows)
        episode_duration = transcript.duration or (windows[-1][-1].end if windows else 0)
        logger.info(
            f"ChunkAnalyzer: {total} windows, "
            f"max {self.MAX_WORKERS} parallel API calls"
        )

        results: list[ChunkAnalysis] = []
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as pool:
            futures = {
                pool.submit(self._analyze_window, i, window, total, episode_duration): i
                for i, window in enumerate(windows)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    ca = future.result()
                    if ca is not None:
                        results.append(ca)
                        logger.debug(
                            f"  chunk {idx} ({ca.start:.0f}s-{ca.end:.0f}s): "
                            f"{len(ca.speaker_roles)} roles, {len(ca.topics)} topics, "
                            f"part={ca.part_type}"
                        )
                except Exception as e:
                    logger.error(f"  chunk {idx} failed: {e}")

        results.sort(key=lambda c: c.start)
        n_failed = sum(1 for c in results if getattr(c, "failed", False))
        n_ok = len(results) - n_failed
        logger.info(f"ChunkAnalyzer: {n_ok}/{total} chunks completed ({n_failed} failed)")
        if total and n_ok == 0:
            raise RuntimeError(f"ChunkAnalyzer: all {total} chunk API calls failed - aborting")
        return results

    def _analyze_window(
        self,
        idx: int,
        window: list[SpeakerSegment],
        total_windows: int = 1,
        episode_duration: float = 0.0,
    ) -> ChunkAnalysis:
        start = window[0].start
        end = window[-1].end
        chunk_id = f"c{idx}"

        text = _format_window(window)
        # Evenly sample if window text is too long
        if len(text) > _MAX_WINDOW_CHARS:
            n_keep = max(1, len(window) * _MAX_WINDOW_CHARS // len(text))
            step = max(1, len(window) // n_keep)
            window = window[::step]
            text = _format_window(window)

        # Build a time-position hint so the model knows where in the episode this falls.
        # Opening minutes are likely jingle/intro; closing minutes often wrap-up/sign-off.
        position_pct = (start / episode_duration * 100) if episode_duration > 0 else 0
        if position_pct < 5:
            position_hint = "opening segment (likely intro jingle or host welcome)"
        elif episode_duration > 0 and (episode_duration - end) < episode_duration * 0.05:
            position_hint = "closing segment (likely sign-off or outro)"
        else:
            position_hint = f"{position_pct:.0f}% through the episode"

        context_header = (
            f"[Window {idx + 1}/{total_windows} | {start:.0f}s–{end:.0f}s | {position_hint}]\n\n"
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=6000,
                temperature=0,
                system=[
                    {
                        "type": "text",
                        "text": CHUNK_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": f"{context_header}Analyze this segment:\n\n{text}",
                    }
                ],
            )
            data = extract_fenced_json(safe_response_text(response))
        except Exception as e:
            logger.warning(f"Chunk {chunk_id} ({start:.0f}s-{end:.0f}s) analysis failed: {e}")
            ca = ChunkAnalysis(
                chunk_id=chunk_id, start=start, end=end, part_type="unknown", raw_text=text
            )
            ca.failed = True  # type: ignore[attr-defined]
            return ca

        speaker_roles = []
        for item in data.get("speaker_roles", []):
            try:
                speaker_roles.append(
                    ChunkSpeakerRole(
                        speaker_label=str(item["speaker_label"]),
                        role=str(item.get("role", "unknown")).lower() if str(item.get("role", "unknown")).lower() in ("host", "guest", "caller", "media_clip", "unknown") else "unknown",
                        name_he=str(item.get("name_he") or "Unknown"),
                        name_en=str(item.get("name_en") or "Unknown"),
                        confidence=float(item.get("confidence", 0.0)),
                        evidence=str(item.get("evidence") or ""),
                    )
                )
            except (KeyError, TypeError, ValueError) as e:
                logger.debug(f"Skipping malformed speaker_role item: {e}")

        topics = []
        for item in data.get("topics", []):
            try:
                topics.append(
                    ChunkTopic(
                        start=float(item["start"]),
                        end=float(item["end"]),
                        speakers=list(item.get("speakers", [])),
                        tentative_title_he=str(item.get("tentative_title_he") or ""),
                        tentative_summary_he=str(item.get("tentative_summary_he") or ""),
                    )
                )
            except (KeyError, TypeError, ValueError) as e:
                logger.debug(f"Skipping malformed topic item: {e}")

        part_type = str(data.get("part_type", "unknown")).lower()
        if part_type not in ("interview", "host_talk", "news", "commercial", "jingle", "unknown"):
            part_type = "unknown"

        return ChunkAnalysis(
            chunk_id=chunk_id,
            start=start,
            end=end,
            part_type=part_type,
            speaker_roles=speaker_roles,
            topics=topics,
            raw_text=text,
        )


def chunk_analyses_to_thematic_chunks(
    chunk_analyses: list[ChunkAnalysis],
    transcript: TranscriptionResult,
) -> list[dict]:
    """Convert ChunkAnalysis topic lists to the dict format expected by ThematicAnalyzer Stage 2.

    Each ChunkTopic becomes a dict with chunk_id, start, end, speakers,
    tentative_title_he, tentative_summary_he, raw_text.
    """
    result = []
    next_id = 0
    for ca in chunk_analyses:
        for topic in ca.topics:
            # Gather the actual transcript text for this topic's time range
            raw_text = "\n".join(
                f"[{s.start:.0f}-{s.end:.0f}] {s.speaker}: {s.text}"
                for s in transcript.segments
                if s.end > topic.start and s.start < topic.end
            )
            result.append(
                {
                    "chunk_id": f"c{next_id}",
                    "start": topic.start,
                    "end": topic.end,
                    "speakers": topic.speakers,
                    "tentative_title_he": topic.tentative_title_he,
                    "tentative_summary_he": topic.tentative_summary_he,
                    "raw_text": raw_text or ca.raw_text,
                }
            )
            next_id += 1
    return result
