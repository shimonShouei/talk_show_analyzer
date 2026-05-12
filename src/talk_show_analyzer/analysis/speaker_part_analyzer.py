"""Per-(part, speaker) analyzer — produces hate scores + incidents per speaker.

For each structural Part this analyzer makes a single LLM call that asks Claude
to evaluate every speaker who appears in the part. The output is a list of
`SpeakerPartAnalysis` records — one per (part, speaker) — each carrying:

  • a continuous hate_score in [0, 1]
  • the worst hate_level the speaker exhibited in this part
  • a list of HateSpeechIncident records (reused from `thematic_analyzer`)
  • a brief Hebrew stance summary
  • short topic labels the speaker engaged with

One call per part keeps total cost well under the $2/episode budget
(3-4 parts/episode × ~$0.10/call ≈ $0.30-$0.40).
"""

from __future__ import annotations

import json
from typing import Optional

import anthropic
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from talk_show_analyzer.analysis.structural_segmenter import Part, PartType
from talk_show_analyzer.analysis.thematic_analyzer import (
    HateSpeechIncident,
    HateSpeechLevel,
)
from talk_show_analyzer.analysis.utils import extract_fenced_json, safe_response_text
from talk_show_analyzer.config import settings


class SpeakerPartAnalysis(BaseModel):
    """One speaker's behavior within one structural part."""

    model_config = ConfigDict(extra="forbid")

    speaker_label: str
    hate_score: float = Field(ge=0.0, le=1.0)
    hate_level_max: HateSpeechLevel = "none"
    incidents: list[HateSpeechIncident] = Field(default_factory=list)
    stance_summary_he: str = ""
    topics_he: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = """You are analyzing an Israeli Hebrew radio talk-show segment.

The transcript below is diarized — every utterance is tagged with a speaker
label (e.g. SPEAKER_00) plus start–end timestamps. For each speaker who appears
in the segment, evaluate their discourse:

For each speaker label, return an object with the following fields:

  • speaker_label   — the diarization label exactly as it appears
  • hate_score      — float in [0.0, 1.0]; 0 = neutral / civil, 1 = sustained
                      severe hate speech. Account for frequency AND severity.
  • hate_level_max  — the single worst incident level for this speaker, drawn
                      from this enum (lower is milder, higher is more severe):
                        none, offensive_language, discrediting, insulting,
                        hate_speech, threat
  • incidents       — list of distinct hate-speech / evaluative incidents.
                      Each incident object must have:
                        speaker_label (echo the speaker)
                        level          (one of the values above; not "none")
                        target         (who/what is targeted)
                        phrase_he      (exact Hebrew phrase from the utterance)
                        context_he     (1-2 sentences of surrounding Hebrew
                                        context that frame the phrase)
                        rationale_en   (one English sentence explaining why
                                        this rises to the chosen level)
                      Empty list if no incidents.
  • stance_summary_he — 1-2 Hebrew sentences summarizing the speaker's stance
                        and tone in this part.
  • topics_he         — short Hebrew labels (3-8 words each) for the topics
                        this speaker engaged with in this part.

Return ONLY a fenced JSON array of these per-speaker objects. No prose.
Example:
```json
[
  {
    "speaker_label": "SPEAKER_00",
    "hate_score": 0.05,
    "hate_level_max": "none",
    "incidents": [],
    "stance_summary_he": "...",
    "topics_he": ["..."]
  }
]
```
If a speaker appears only in non-substantive ways (mh-hmm, back-channel),
include them with hate_score=0.0 and empty incidents."""


def _format_part_for_prompt(part: Part) -> str:
    """Render a Part's segments as a labeled, timestamped transcript."""
    return "\n".join(
        f"[{seg.start:.1f}-{seg.end:.1f} {seg.speaker}] {seg.text.strip()}"
        for seg in part.segments
    )


class SpeakerPartAnalyzer:
    """LLM-driven per-(part, speaker) hate-speech + stance analyzer."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        client: Optional[anthropic.Anthropic] = None,
    ):
        self.model = model
        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def analyze(self, part: Part) -> list[SpeakerPartAnalysis]:
        """Produce per-speaker analyses for the given Part.

        Returns an empty list for parts with no segments or when the model fails
        to return a usable response. Errors are logged and swallowed — this is
        enrichment, not pipeline-critical.
        """
        if not part.segments:
            return []
        # Even host_talk parts are worth analyzing — hosts can show hate too.
        # We accept any non-empty part.

        transcript_block = _format_part_for_prompt(part)
        user_msg = (
            f"Segment ({part.type.value}, {part.start:.0f}–{part.end:.0f}s, "
            f"{part.duration:.0f}s total):\n\n{transcript_block}\n\n"
            "Evaluate every speaker label that appears. Return the fenced JSON array."
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=6000,
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
            logger.warning(
                f"Per-speaker analysis failed for part {part.start:.0f}s: {e}"
            )
            return []

        if not isinstance(data, list):
            logger.warning(
                f"Per-speaker analyzer expected a list, got {type(data).__name__}"
            )
            return []

        out: list[SpeakerPartAnalysis] = []
        for item in data:
            try:
                out.append(SpeakerPartAnalysis(**item))
            except ValidationError as e:
                logger.warning(f"Skipping malformed per-speaker record: {e}")

        # Restrict to speakers that actually appear in the part — Claude is
        # occasionally creative about inventing labels.
        present = {s.speaker for s in part.segments}
        kept = [a for a in out if a.speaker_label in present]
        if len(kept) != len(out):
            dropped = {a.speaker_label for a in out} - present
            logger.warning(
                f"Dropping fabricated speaker labels not in part: {dropped}"
            )

        logger.info(
            f"Per-speaker analysis: {len(kept)} speaker(s) in part "
            f"{part.start:.0f}-{part.end:.0f}s ({part.type.value})"
        )
        return kept
