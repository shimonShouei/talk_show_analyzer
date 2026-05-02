"""LLM-based speaker identification using Claude."""

import json
from collections import defaultdict

import anthropic
from loguru import logger
from sqlalchemy.orm import Session

from talk_show_analyzer.config import settings
from talk_show_analyzer.models import Person, SpeakerIdentity
from talk_show_analyzer.transcription.transcriber import TranscriptionResult


class LLMSpeakerIdentifier:
    """Identify speakers using Claude LLM."""

    PROMPT_TEMPLATE = """You are analyzing a Hebrew talk show transcript. Your task is to identify
the speaker ONLY if they explicitly introduce themselves or are clearly identified by name in the text.

CRITICAL RULES:
1. ONLY identify speakers who EXPLICITLY mention their own name or are explicitly named in the transcript
2. Do NOT guess or infer names - if the speaker doesn't say "I am X" or isn't introduced as "X", return Unknown
3. Do NOT use external knowledge about radio station staff unless they identify themselves in THIS episode
4. Check the utterances carefully - the person's name should actually appear in their own speech or be stated by others

SPEAKER UTTERANCES:
{speaker_utterances}

SURROUNDING CONTEXT (other speakers):
{context}

Return a JSON object with exactly these fields:
{{
    "name_he": "Name in Hebrew (only if explicitly stated in text, else 'Unknown')",
    "name_en": "Name in English (only if explicitly stated in text, else 'Unknown')",
    "role": "host or guest or caller or unknown",
    "confidence": 0.0 to 1.0 (only high confidence if name explicitly appears in utterances),
    "name_appears_in_text": true/false (whether the name actually appears in the speaker's utterances),
    "reasoning": "Exactly where in the utterances or context the name was found, or why Unknown"
}}

CONFIDENCE GUIDELINES:
- 0.95: Speaker explicitly says "I am X" or "My name is X"
- 0.85: Another speaker introduces them by name ("Welcome to X from Y")
- 0.0: No explicit name mention - always return Unknown in this case
- NEVER guess based on voice, context, or external knowledge"""

    def __init__(self):
        """Initialize identifier with Claude client."""
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def identify_speakers(
        self, transcript: TranscriptionResult, episode_id: int, session: Session
    ) -> dict[str, "ResolvedSpeaker"]:
        """
        Identify speakers in a transcript using Claude.

        Args:
            transcript: TranscriptionResult from diarization
            episode_id: Episode ID for storage
            session: SQLAlchemy session for DB queries

        Returns:
            Dict mapping speaker_label -> ResolvedSpeaker
        """
        logger.info("Identifying speakers via LLM...")

        # Group segments by speaker
        speaker_segments = defaultdict(list)
        for seg in transcript.segments:
            speaker_segments[seg.speaker].append(seg)

        # Process each speaker
        results = {}
        for speaker_label in sorted(speaker_segments.keys()):
            segments = speaker_segments[speaker_label]
            identity = self._identify_single_speaker(
                speaker_label, segments, transcript, episode_id, session
            )
            results[speaker_label] = identity

        logger.info(f"Identified {len(results)} speakers")
        return results

    def _identify_single_speaker(
        self,
        speaker_label: str,
        speaker_segments: list,
        transcript: TranscriptionResult,
        episode_id: int,
        session: Session,
    ) -> "ResolvedSpeaker":
        """Identify a single speaker using Claude."""
        # Check if this is a commercial/ad speaker
        speaker_text_raw = " ".join([seg.text for seg in speaker_segments]).lower()
        ad_keywords = {
            "מבצע", "הנחה", "קניה", "משקפי", "מקרר", "רכב", "ניסן",
            "אלקטרה", "מזגן", "משכנתא", "הלוואה", "פרסום", "כפוף לתקנון",
            "מוצר", "שנים על דלק", "עד 40%", "קוד", "כוכבית"
        }
        is_ad = any(keyword in speaker_text_raw for keyword in ad_keywords)

        if is_ad:
            logger.info(f"  {speaker_label} -> [AD/COMMERCIAL - skipped]")
            return ResolvedSpeaker(
                speaker_label=speaker_label,
                name_he="Unknown",
                name_en="Unknown",
                role="unknown",
                confidence=0.0,
                person_id=None,
            )

        # Build speaker utterances
        speaker_text = "\n".join(
            [f"  [{seg.start:.0f}s] {seg.text}" for seg in speaker_segments]
        )

        # Build context (other speakers, focus on first/last segments)
        context_segments = [seg for seg in transcript.segments if seg.speaker != speaker_label]
        context_text = "\n".join(
            [
                f"  [{seg.speaker}] {seg.start:.0f}s: {seg.text[:100]}"
                for seg in context_segments[:10]  # Limit context
            ]
        )

        prompt = self.PROMPT_TEMPLATE.format(
            speaker_utterances=speaker_text, context=context_text
        )

        try:
            response = self.client.messages.create(
                model="claude-opus-4-7",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text
            result = json.loads(content)

            # Determine confidence level
            confidence = float(result.get("confidence", 0.0))
            name_he = result.get("name_he", "Unknown")
            name_en = result.get("name_en", "Unknown")
            role = result.get("role", "unknown").lower()
            name_appears_in_text = result.get("name_appears_in_text", False)

            # Validation: if LLM claims high confidence but name doesn't appear in text, downgrade
            if confidence >= 0.8 and not name_appears_in_text and name_en != "Unknown":
                logger.warning(
                    f"  {speaker_label}: LLM claimed confidence {confidence:.2f} for '{name_en}' "
                    f"but name doesn't appear in text - downgrading to Unknown"
                )
                name_he = "Unknown"
                name_en = "Unknown"
                confidence = 0.0
                role = "unknown"

            # Look up or create Person ONLY for high confidence (>= 0.8)
            person_id = None
            person = None
            if name_en != "Unknown" and confidence >= 0.8:
                person = session.query(Person).filter(
                    Person.name_en == name_en
                ).first()
                if not person:
                    person = Person(
                        name_he=name_he,
                        name_en=name_en,
                        role=role,
                    )
                    session.add(person)
                    session.flush()
                person_id = person.id

            # Determine method based on confidence
            method = "llm_confident" if confidence >= 0.8 else "llm"

            # Store identity
            identity = SpeakerIdentity(
                episode_id=episode_id,
                speaker_label=speaker_label,
                person_id=person_id,
                role=role,
                confidence=confidence,
                method=method,
                evidence={
                    "llm_reasoning": result.get("reasoning", ""),
                    "utterance_count": len(speaker_segments),
                    "total_duration": sum(seg.end - seg.start for seg in speaker_segments),
                },
            )
            session.add(identity)
            session.flush()

            logger.info(
                f"  {speaker_label} -> {name_en} ({role}, conf={confidence:.2f})"
            )

            return ResolvedSpeaker(
                speaker_label=speaker_label,
                name_he=name_he,
                name_en=name_en,
                role=role,
                confidence=confidence,
                person_id=person_id,
            )

        except (json.JSONDecodeError, ValueError, AttributeError) as e:
            logger.warning(f"Failed to identify {speaker_label}: {e}")
            identity = SpeakerIdentity(
                episode_id=episode_id,
                speaker_label=speaker_label,
                person_id=None,
                role="unknown",
                confidence=0.0,
                method="unresolved",
                evidence={"error": str(e)},
            )
            session.add(identity)
            session.flush()

            return ResolvedSpeaker(
                speaker_label=speaker_label,
                name_he="Unknown",
                name_en="Unknown",
                role="unknown",
                confidence=0.0,
                person_id=None,
            )


class ResolvedSpeaker:
    """Result of speaker identification for one speaker."""

    def __init__(
        self,
        speaker_label: str,
        name_he: str,
        name_en: str,
        role: str,
        confidence: float,
        person_id: int | None = None,
    ):
        self.speaker_label = speaker_label
        self.name_he = name_he
        self.name_en = name_en
        self.role = role
        self.confidence = confidence
        self.person_id = person_id

    def __repr__(self) -> str:
        return f"<ResolvedSpeaker {self.speaker_label}->{self.name_en} ({self.role}, {self.confidence:.2f})>"
