"""Unified speaker identification using cross-speaker name mentions."""

import json
import re
from collections import defaultdict
from dataclasses import dataclass

import anthropic
from loguru import logger
from sqlalchemy.orm import Session

from talk_show_analyzer.config import settings
from talk_show_analyzer.models import Person, SpeakerIdentity
from talk_show_analyzer.transcription.transcriber import TranscriptionResult

# Max characters of utterances to include per speaker to keep prompt manageable
_MAX_CHARS_PER_SPEAKER = 3000
# Max total segments from the transcript to use as cross-speaker context
_MAX_CONTEXT_SEGMENTS = 80

SYSTEM_PROMPT = """You are analyzing a Hebrew radio talk show transcript. Each speaker is labeled
SPEAKER_00, SPEAKER_01, etc. by an automatic diarization system.

Your task: identify who each speaker really is, using ONLY evidence found in the transcript itself.

KEY INSIGHT: On Israeli radio, hosts address guests by name and guests address hosts by name.
Look for patterns like:
- "ברוך הבא X" / "שלום X" (welcome X / hello X) — the addressed person is that speaker
- "אמרת X שאתה..." — the speaking person is X
- "פרופסור X, מה דעתך" — the addressed speaker is Professor X
- "אני X" / "שמי X" — self-introduction
- "עם X מ-Y" (with X from Y) — guest introduction
- Any explicit name address between speakers

IMPORTANT:
- Only assign names when you find EXPLICIT textual evidence in the transcript
- A speaker can be identified from what OTHERS say TO them, not just what they say themselves
- If no name is found for a speaker, return "Unknown"
- Hosts typically speak the most and ask questions; guests typically answer; callers are brief
- Do NOT use any knowledge of who usually hosts which show"""

IDENTIFICATION_PROMPT = """Below is a sample of the transcript showing all speakers. Use cross-speaker
name mentions to identify each speaker.

TRANSCRIPT SAMPLE:
{transcript_sample}

SPEAKER SUMMARIES (all their utterances):
{speaker_summaries}

For each speaker label found in the summaries, return a JSON array where each element is:
{{
  "speaker_label": "SPEAKER_NN",
  "name_he": "Name in Hebrew or Unknown",
  "name_en": "Name in English or Unknown",
  "role": "host" | "guest" | "caller" | "unknown",
  "confidence": 0.0-1.0,
  "evidence": "exact quote or address from the transcript that establishes the name, or empty string"
}}

Confidence guidelines:
- 0.9+: Name is explicitly stated to/by this speaker in the transcript
- 0.7-0.89: Strong contextual evidence (e.g. host greeting pattern, repeated address)
- below 0.7: Uncertain — prefer Unknown over a guess

Return ONLY a valid JSON array, nothing else."""


@dataclass
class ResolvedSpeaker:
    """Identification result for one speaker label."""

    speaker_label: str
    name_he: str
    name_en: str
    role: str
    confidence: float
    person_id: int | None = None

    def __repr__(self) -> str:
        return f"<ResolvedSpeaker {self.speaker_label}->{self.name_en} ({self.role}, {self.confidence:.2f})>"


class UnifiedSpeakerIdentifier:
    """
    Identify all speakers in a single Claude call using cross-speaker name mentions.

    Unlike the old per-speaker approach, this sends all speakers together so Claude
    can see that e.g. SPEAKER_00 addresses SPEAKER_01 as "פרופסור כהן" — which is
    impossible to detect when analyzing each speaker in isolation.
    """

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = model

    def identify_speakers(
        self,
        transcript: TranscriptionResult,
        content_segments: list,  # Segment dataclasses (non-ad only)
        episode_id: int,
        session: Session,
    ) -> dict[str, ResolvedSpeaker]:
        """
        Identify all speakers in one unified Claude call.

        Uses only utterances from non-ad content segments to avoid letting
        commercial voice-overs pollute the speaker pool.

        Returns:
            Dict mapping speaker_label -> ResolvedSpeaker
        """
        logger.info("Identifying speakers via unified cross-speaker analysis...")

        # Collect speaker labels that appear in content segments only
        content_speaker_labels: set[str] = set()
        for seg in content_segments:
            for sp in seg.speakers:
                content_speaker_labels.add(sp)

        if not content_speaker_labels:
            logger.warning("No content-segment speakers found — skipping identification")
            return {}

        # Group transcript segments by speaker (content only)
        speaker_utterances: dict[str, list] = defaultdict(list)
        for ts in transcript.segments:
            if ts.speaker in content_speaker_labels:
                speaker_utterances[ts.speaker].append(ts)

        # Build per-speaker summaries (truncated)
        speaker_summaries = []
        for label in sorted(speaker_utterances.keys()):
            segs = speaker_utterances[label]
            total_chars = 0
            lines = []
            for s in segs:
                line = f"  [{s.start:.0f}s] {s.text}"
                if total_chars + len(line) > _MAX_CHARS_PER_SPEAKER:
                    break
                lines.append(line)
                total_chars += len(line)
            block = f"=== {label} ===\n" + "\n".join(lines)
            speaker_summaries.append(block)

        # Build a cross-speaker transcript sample (interleaved, up to limit)
        content_ts_segs = [
            ts for ts in transcript.segments if ts.speaker in content_speaker_labels
        ]
        sample_segs = content_ts_segs[:_MAX_CONTEXT_SEGMENTS]
        transcript_sample = "\n".join(
            f"[{s.start:.0f}s] {s.speaker}: {s.text}" for s in sample_segs
        )

        prompt = IDENTIFICATION_PROMPT.format(
            transcript_sample=transcript_sample,
            speaker_summaries="\n\n".join(speaker_summaries),
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                temperature=0,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()
            # Strip markdown fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw).strip()

            data = json.loads(raw)

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Unified speaker identification failed: {e}")
            data = []

        # Build result map from Claude's response
        results: dict[str, ResolvedSpeaker] = {}
        identified_labels = set()

        for item in data:
            label = item.get("speaker_label", "")
            if not label:
                continue
            identified_labels.add(label)

            name_he = item.get("name_he", "Unknown") or "Unknown"
            name_en = item.get("name_en", "Unknown") or "Unknown"
            role = (item.get("role") or "unknown").lower()
            confidence = float(item.get("confidence", 0.0))
            evidence = item.get("evidence", "")

            # Persist to DB
            person_id = None
            if name_en != "Unknown" and confidence >= 0.7:
                person = session.query(Person).filter_by(name_en=name_en).first()
                if not person:
                    person = Person(name_he=name_he, name_en=name_en, role=role)
                    session.add(person)
                    session.flush()
                person_id = person.id

            method = "llm_confident" if confidence >= 0.7 else "unresolved"
            identity = SpeakerIdentity(
                episode_id=episode_id,
                speaker_label=label,
                person_id=person_id,
                role=role,
                confidence=confidence,
                method=method,
                evidence={"evidence_quote": evidence, "utterance_count": len(speaker_utterances.get(label, []))},
            )
            session.add(identity)
            session.flush()

            resolved = ResolvedSpeaker(
                speaker_label=label,
                name_he=name_he,
                name_en=name_en,
                role=role,
                confidence=confidence,
                person_id=person_id,
            )
            results[label] = resolved
            logger.info(f"  {label} -> {name_en} ({role}, conf={confidence:.2f})")

        # Any content speaker Claude didn't return → store as unresolved
        for label in content_speaker_labels - identified_labels:
            identity = SpeakerIdentity(
                episode_id=episode_id,
                speaker_label=label,
                person_id=None,
                role="unknown",
                confidence=0.0,
                method="unresolved",
                evidence={},
            )
            session.add(identity)
            session.flush()
            results[label] = ResolvedSpeaker(
                speaker_label=label,
                name_he="Unknown",
                name_en="Unknown",
                role="unknown",
                confidence=0.0,
            )
            logger.info(f"  {label} -> Unknown (not identified)")

        logger.info(
            f"Speaker identification complete: {sum(1 for r in results.values() if r.name_en != 'Unknown')} "
            f"identified out of {len(results)} content speakers"
        )
        return results
