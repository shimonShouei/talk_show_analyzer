"""Named Q&A pair extraction from interview parts.

Given a structural Part of type=INTERVIEW, this module asks Claude to identify
each distinct question→answer pair: who asked it, who answered, what topic it
covered, and the time span. One LLM call per interview part keeps cost low
(~$0.05/call × 3-4 interviews/episode well within the $2/episode budget).

Q&A pairs are the discourse-scheme primitive: downstream per-(part, speaker)
analyses (hate scoring, sentiment, stance) ground their evidence in these
quoted units rather than rescanning raw transcript chunks.
"""

from __future__ import annotations

import json
from typing import Optional

import anthropic
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from talk_show_analyzer.analysis.structural_segmenter import Part, PartType
from talk_show_analyzer.analysis.utils import extract_fenced_json, safe_response_text
from talk_show_analyzer.config import settings


class NamedQAPair(BaseModel):
    """One question→answer exchange within an interview."""

    model_config = ConfigDict(extra="forbid")

    question_text_he: str
    question_speaker_label: str
    answer_text_he: str
    answer_speaker_label: str
    topic_label_he: str = Field(default="")
    start_seconds: float
    end_seconds: float


SYSTEM_PROMPT = """You are analyzing an Israeli Hebrew radio talk-show interview segment.

The transcript is diarized — every utterance is tagged with a speaker label
(e.g. SPEAKER_00) and a start–end timestamp. Some speakers are radio hosts
(asking the questions), others are guests (answering).

Your task: identify every distinct question→answer pair in the segment.

A Q&A pair is a focused exchange where:
  • A host asks a substantive question (not "אהה", not throat-clearing).
  • A guest gives a substantive answer that addresses that question.
  • Brief host follow-ups that ride the same theme stay in the same pair.

For each pair, return:
  • question_text_he       — exact Hebrew text of the question(s), concatenated
  • question_speaker_label — the host's speaker label (e.g. SPEAKER_00)
  • answer_text_he         — exact Hebrew text of the answer(s)
  • answer_speaker_label   — the guest's speaker label
  • topic_label_he         — short Hebrew label describing what the pair is about
                             (3-8 words, e.g. "המצב הביטחוני בגבול הצפון")
  • start_seconds          — start timestamp of the question
  • end_seconds            — end timestamp of the final answer in the pair

Return ONLY a fenced JSON array of objects. No prose, no thinking.
Example:
```json
[
  {
    "question_text_he": "...",
    "question_speaker_label": "SPEAKER_00",
    "answer_text_he": "...",
    "answer_speaker_label": "SPEAKER_01",
    "topic_label_he": "...",
    "start_seconds": 12.5,
    "end_seconds": 95.2
  }
]
```
If the segment contains no substantive Q&A pairs (pure chatter, fragmented),
return an empty JSON array: `[]`."""


def _format_part_for_prompt(part: Part) -> str:
    """Render a Part's segments as a labeled, timestamped transcript."""
    lines = []
    for seg in part.segments:
        lines.append(
            f"[{seg.start:.1f}-{seg.end:.1f} {seg.speaker}] {seg.text.strip()}"
        )
    return "\n".join(lines)


class NamedQAExtractor:
    """Extract named Q&A pairs from interview parts via Claude."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        client: Optional[anthropic.Anthropic] = None,
    ):
        self.model = model
        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def extract(self, part: Part) -> list[NamedQAPair]:
        """Extract Q&A pairs from one interview Part.

        Returns an empty list for non-interview parts or when the model returns
        nothing usable. Errors are logged but never re-raised — Q&A extraction
        is best-effort enrichment and must not break the pipeline.
        """
        if part.type != PartType.INTERVIEW:
            return []
        if not part.segments:
            return []

        transcript_block = _format_part_for_prompt(part)
        user_msg = (
            f"Interview segment ({part.start:.0f}–{part.end:.0f}s, "
            f"{part.duration:.0f}s total):\n\n{transcript_block}\n\n"
            "Extract all Q&A pairs as the fenced JSON array described."
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=12000,  # long interview parts can exceed 4000 tokens of pairs
                temperature=0,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_msg}],
            )
            data = extract_fenced_json(safe_response_text(response))
        except (json.JSONDecodeError, anthropic.APIError, ValueError) as e:
            logger.warning(f"Q&A extraction failed for part {part.start:.0f}s: {e}")
            return []

        if not isinstance(data, list):
            logger.warning(f"Q&A extractor expected a list, got {type(data).__name__}")
            return []

        pairs: list[NamedQAPair] = []
        for item in data:
            try:
                pairs.append(NamedQAPair(**item))
            except ValidationError as e:
                logger.warning(f"Skipping malformed Q&A pair: {e}")

        logger.info(
            f"Extracted {len(pairs)} Q&A pair(s) from interview "
            f"{part.start:.0f}-{part.end:.0f}s"
        )
        return pairs
