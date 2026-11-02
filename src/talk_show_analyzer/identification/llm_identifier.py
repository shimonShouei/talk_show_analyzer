"""Unified speaker identification using cross-speaker name mentions."""

import json
import re
from collections import defaultdict
from dataclasses import dataclass

import anthropic
import numpy as np
from loguru import logger
from sklearn.cluster import AgglomerativeClustering
from sqlalchemy.orm import Session

from talk_show_analyzer.config import settings
from talk_show_analyzer.models import Person, SpeakerIdentity
from talk_show_analyzer.transcription.transcriber import (
    SpeakerSegment,
    TranscriptionResult,
)

# Max characters of utterances to include per speaker to keep prompt manageable
_MAX_CHARS_PER_SPEAKER = 3000
# Fallback head-of-show segment count when naming-moment scan returns nothing
_FALLBACK_HEAD_SEGMENTS = 20

# Hebrew high-signal markers for naming moments. Each pattern is a substring.
HEBREW_NAMING_PATTERNS = [
    # Greetings — host welcoming a guest by name
    "שלום ל",
    "ברוך הבא",
    "ברוכה הבאה",
    "ערב טוב",
    "בוקר טוב",
    # Titles — typically precede a name
    "פרופסור",
    "דוקטור",
    'ד"ר',
    "הכתב",
    "הכתבת",
    "שר ",
    "שרת ",
    # Direct address phrasing
    "מה דעתך",
    "תגיד ",
    "תגידי ",
]

_JINGLE_WINDOW_SECONDS = 90  # analyse first 90s for host-name mentions in opening jingle

JINGLE_SYSTEM_PROMPT = """You are analyzing the opening segment of an Israeli Hebrew radio talk show.
Opening jingles and intro segments frequently announce the show's host(s) by name, using phrases like:
- "עם [name]" / "עם [first] [last]"  (with [name])
- "מגיש: [name]" / "מגישה: [name]"  (presented by / hosted by)
- "מנחה [name]"  (host: [name])
- Singing or chanting the host's name directly

Your task: extract every personal name (first name, full name) that is mentioned in this opening segment as a host or presenter of the show. Return ONLY names that are clearly being announced as show hosts — not guests.

Return a JSON object:
{
  "host_names": ["name1", "name2"],   // Hebrew or transliterated names of hosts found; empty list if none
  "evidence": "short quote showing where the name(s) appear"
}

If no host names are clearly stated, return {"host_names": [], "evidence": ""}."""

JINGLE_PROMPT = """Opening segment transcript (first {seconds}s of the episode):

{text}

Extract any host names announced in this opening jingle/intro."""


SYSTEM_PROMPT = """You are analyzing a Hebrew radio talk show transcript. Each speaker is labeled
SPEAKER_NN by an automatic diarization system (acoustically deduplicated before you see it).

Your task: identify who each speaker really is, using ONLY evidence found in the transcript itself.

KEY INSIGHT: On Israeli radio, hosts address guests by name and guests address hosts by name.
Look for patterns like:
- "ברוך הבא X" / "שלום X" (welcome X / hello X) — the addressed person is that speaker
- "אמרת X שאתה..." — the speaking person is X
- "פרופסור X, מה דעתך" — the addressed speaker is Professor X
- "אני X" / "שמי X" — self-introduction
- "עם X מ-Y" (with X from Y) — guest introduction
- Any explicit name address between speakers

ANCHOR vs GUEST — structural roles you can use to disambiguate:
- The ANCHOR (host) asks ~50% of all questions, takes short turns, and bookends segments
  (opens, hands off, returns to wrap up). Hosts rarely speak in extended monologues.
- The GUEST takes significantly longer turns (narrative/expert function) and answers far more
  than they ask. An expert guest is typically introduced once with a title (פרופסור, ד"ר,
  הכתב) and then carries the explanation.
- A CALLER appears briefly, is greeted by the host ("שלום X מ-Y"), speaks once or twice, exits.

CONFIDENCE TIERS — apply strictly:
- 0.9+: an explicit named greeting or self-introduction is in the transcript
  (e.g. "ברוך הבא פרופסור כהן" → that speaker is Prof. Cohen).
- 0.7-0.89: consistent direct address by the host across multiple turns, or a strong
  title+answer pattern, but no single explicit naming moment.
- below 0.7: do NOT guess. Return Unknown. Hallucinated names are worse than gaps.

IMPORTANT:
- Only assign names when you find EXPLICIT textual evidence in the transcript.
- A speaker can be identified from what OTHERS say TO them, not just what they say themselves.
- If no name is found for a speaker, return "Unknown".
- Do NOT use any prior knowledge of who usually hosts which show."""

IDENTIFICATION_PROMPT = """Below is the full transcript. Use cross-speaker name mentions,
greetings, titles, and direct address to identify each speaker.
{jingle_section}
FULL TRANSCRIPT:
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
  "evidence": "exact quote or address from the transcript that establishes the name, or empty string",
  "reasoning": "1-2 sentence chain-of-thought explaining the mapping (e.g. 'SPEAKER_00 greeted SPEAKER_01 as Professor Cohen, and SPEAKER_01 then provided a long expert explanation, so SPEAKER_01 = Cohen and SPEAKER_00 is the host.')"
}}

Confidence rules (strict — Unknown is preferable to a guess):
- 0.9+: name explicitly stated to/by this speaker (greeting or self-introduction)
- 0.7-0.89: consistent host direct-address or title+answer pattern across multiple turns
- below 0.7: return Unknown for this speaker

Apply the ANCHOR vs GUEST heuristic: short, question-heavy, bookending turns → host;
long, narrative, answer-heavy turns introduced with a title → guest.

Return ONLY a valid JSON array, nothing else."""


def _recover_partial_json(raw: str) -> list[dict]:
    """Extract complete JSON objects from a truncated array response."""
    objects = []
    depth = 0
    start = None
    in_string = False
    escape = False
    for i, ch in enumerate(raw):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    objects.append(json.loads(raw[start : i + 1]))
                except json.JSONDecodeError:
                    pass
                start = None
    return objects


def _label_sort_key(label: str) -> tuple[int, str]:
    """Sort labels so 'SPEAKER_03' comes before 'SPEAKER_07' regardless of zero-padding.

    Falls back to lexical ordering when no trailing number is present.
    """
    m = re.search(r"(\d+)$", label)
    if m:
        return (int(m.group(1)), label)
    return (10**9, label)


def _merge_speakers_acoustic(
    embeddings: dict[str, np.ndarray],
    threshold: float,
) -> dict[str, str]:
    """Cluster speaker embeddings; return {original_label -> canonical_label}.

    Canonical = lowest-numbered original label per cluster (e.g. SPEAKER_03+07 → SPEAKER_03).
    Labels without embeddings are not in the input dict; callers add identity entries for those.

    Args:
        embeddings: mapping of speaker label → 1D embedding vector.
        threshold: cosine *similarity* above which two speakers are merged. Internally
            converted to sklearn distance (1 - threshold).
    """
    labels = sorted(embeddings.keys(), key=_label_sort_key)
    n = len(labels)
    if n == 0:
        return {}
    if n == 1:
        return {labels[0]: labels[0]}

    matrix = np.stack([embeddings[lab] for lab in labels])
    distance_threshold = max(1e-6, 1.0 - threshold)
    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=distance_threshold,
    )
    cluster_ids = clustering.fit_predict(matrix)

    # Group originals by cluster id, then pick the lowest-numbered as canonical.
    groups: dict[int, list[str]] = defaultdict(list)
    for lab, cid in zip(labels, cluster_ids):
        groups[int(cid)].append(lab)

    mapping: dict[str, str] = {}
    for members in groups.values():
        members.sort(key=_label_sort_key)
        canonical = members[0]
        for lab in members:
            mapping[lab] = canonical

    n_canonical = len(groups)
    logger.info(f"acoustic merge: {n} → {n_canonical} speakers")
    return mapping


def _analyze_opening_jingle(
    transcript: TranscriptionResult,
    client: anthropic.Anthropic,
    model: str,
    window_seconds: float = _JINGLE_WINDOW_SECONDS,
) -> list[str]:
    """Return host names found in the opening jingle/intro of the episode.

    Looks at the first `window_seconds` of transcript text and asks Claude to
    extract any names announced as show hosts. Returns an empty list when none
    are found or the call fails.
    """
    opening_segs = [s for s in transcript.segments if s.start < window_seconds]
    if not opening_segs:
        logger.debug("jingle analysis: no segments in first %.0fs", window_seconds)
        return []

    text = "\n".join(
        f"[{s.start:.0f}s] {s.speaker}: {s.text}" for s in opening_segs
    )
    prompt = JINGLE_PROMPT.format(seconds=int(window_seconds), text=text)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=256,
            temperature=0,
            system=JINGLE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        if not response.content or not response.content[0].text.strip():
            raise ValueError(f"empty response (stop_reason={response.stop_reason!r})")
        from talk_show_analyzer.analysis.utils import extract_fenced_json
        raw = response.content[0].text.strip()
        parsed = extract_fenced_json(raw)
        names: list[str] = parsed.get("host_names", [])
        evidence: str = parsed.get("evidence", "")
        if names:
            logger.info(f"jingle analysis found host names: {names} (evidence: {evidence!r})")
        else:
            logger.debug("jingle analysis: no host names found in opening segment")
        return names
    except Exception as exc:
        logger.warning(f"jingle analysis failed: {exc}")
        return []


def _extract_naming_moments(
    transcript: TranscriptionResult,
    label_map: dict[str, str],
    content_labels: set[str],
    context_n: int,
    max_total: int,
) -> list[SpeakerSegment]:
    """Scan transcript for Hebrew naming patterns; return hit segment + next `context_n`.

    Speaker labels in the returned segments are *post-merge* (rewritten via `label_map`).
    Dedupes by (start, end, original_speaker). Caps total length at `max_total`.
    Only segments whose original speaker is in `content_labels` are considered.
    Falls back to the first `_FALLBACK_HEAD_SEGMENTS` content segments if no hits.
    """
    segs = transcript.segments
    selected: list[SpeakerSegment] = []
    seen: set[tuple[float, float, str]] = set()

    def _emit(seg: SpeakerSegment) -> bool:
        key = (seg.start, seg.end, seg.speaker)
        if key in seen:
            return False
        if seg.speaker not in content_labels:
            return False
        seen.add(key)
        rewritten = SpeakerSegment(
            start=seg.start,
            end=seg.end,
            speaker=label_map.get(seg.speaker, seg.speaker),
            text=seg.text,
        )
        selected.append(rewritten)
        return True

    for i, seg in enumerate(segs):
        if seg.speaker not in content_labels:
            continue
        text = seg.text or ""
        if not any(pat in text for pat in HEBREW_NAMING_PATTERNS):
            continue
        _emit(seg)
        for j in range(i + 1, min(i + 1 + context_n, len(segs))):
            _emit(segs[j])
        if len(selected) >= max_total:
            break

    if not selected:
        # Fallback: head of show — greetings frequently happen in the first minute.
        head_count = 0
        for seg in segs:
            if seg.speaker not in content_labels:
                continue
            _emit(seg)
            head_count += 1
            if head_count >= _FALLBACK_HEAD_SEGMENTS:
                break
        logger.debug(
            f"naming-moment scan: 0 hits, falling back to head-of-show "
            f"({len(selected)} segments)"
        )
    else:
        logger.debug(f"naming-moment scan: {len(selected)} context segments selected")

    return selected[:max_total]


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

    Pipeline (per episode):
      1. Acoustic merge — collapse over-segmented pyannote labels via cosine clustering.
      2. Naming-moment extraction — focus the LLM context on greetings/titles/direct-address.
      3. Single Claude call — emit per-speaker JSON with explicit reasoning.
      4. Strict confidence — names below 0.7 are dropped to Unknown.
      5. Per-original persistence — each merged-from label gets its own SpeakerIdentity row
         pointing at the same Person, so downstream code keyed on original labels still works.
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
        """Identify all speakers in one unified Claude call.

        Uses only utterances from non-ad content segments to avoid letting commercial
        voice-overs pollute the speaker pool. Returns a dict keyed by ORIGINAL speaker
        labels (pre-merge) so downstream consumers (orchestrator, dashboard, store) keep
        working against the labels stored in `content_segments`.
        """
        logger.info("Identifying speakers via unified cross-speaker analysis...")

        # ---- Opening jingle analysis ----
        jingle_names = _analyze_opening_jingle(transcript, self.client, self.model)

        # Collect speaker labels that appear in content segments only
        content_speaker_labels: set[str] = set()
        for seg in content_segments:
            # SpeakerSegment has .speaker (str); legacy Segment has .speakers (list[str])
            speakers = getattr(seg, "speakers", None) or [seg.speaker]
            for sp in speakers:
                content_speaker_labels.add(sp)

        if not content_speaker_labels:
            logger.warning("No content-segment speakers found — skipping identification")
            return {}

        # ---- Acoustic merge ----
        # Restrict embedding domain to content speakers, then cluster.
        content_embeddings = {
            label: emb
            for label, emb in transcript.speaker_embeddings.items()
            if label in content_speaker_labels
        }
        if settings.acoustic_merge_enabled and len(content_embeddings) >= 2:
            label_map = _merge_speakers_acoustic(
                content_embeddings, settings.acoustic_merge_threshold
            )
        else:
            if not content_embeddings:
                logger.warning(
                    "No speaker embeddings available — skipping acoustic merge "
                    "(diarization may have fallen back to single-speaker mode)"
                )
            label_map = {}

        # Pass-through identity entries for content labels without embeddings.
        for label in content_speaker_labels:
            label_map.setdefault(label, label)

        # Inverse map: canonical label → list of original labels (sorted).
        merged_to_originals: dict[str, list[str]] = defaultdict(list)
        for original, canonical in label_map.items():
            merged_to_originals[canonical].append(original)
        for canonical in merged_to_originals:
            merged_to_originals[canonical].sort(key=_label_sort_key)

        # ---- Group transcript segments by canonical speaker (content only) ----
        speaker_utterances: dict[str, list] = defaultdict(list)
        for ts in transcript.segments:
            if ts.speaker not in content_speaker_labels:
                continue
            canonical = label_map[ts.speaker]
            speaker_utterances[canonical].append(ts)

        # ---- Build per-canonical-speaker summaries (truncated) ----
        speaker_summaries = []
        for label in sorted(speaker_utterances.keys(), key=_label_sort_key):
            segs = speaker_utterances[label]
            total_chars = 0
            lines = []
            for s in segs:
                line = f"  [{s.start:.0f}s] {s.text}"
                if total_chars + len(line) > _MAX_CHARS_PER_SPEAKER:
                    break
                lines.append(line)
                total_chars += len(line)
            originals = merged_to_originals.get(label, [label])
            origin_note = (
                f" (merged from: {', '.join(originals)})" if len(originals) > 1 else ""
            )
            block = f"=== {label}{origin_note} ===\n" + "\n".join(lines)
            speaker_summaries.append(block)

        # ---- Full transcript (all content segments) ----
        transcript_sample = "\n".join(
            f"[{s.start:.0f}s] {label_map.get(s.speaker, s.speaker)}: {s.text}"
            for s in transcript.segments
            if s.speaker in content_speaker_labels
        )

        if jingle_names:
            names_str = ", ".join(f'"{n}"' for n in jingle_names)
            jingle_section = (
                f"\nOPENING JINGLE ANALYSIS: The show's opening jingle explicitly announced "
                f"the following host name(s): {names_str}. "
                f"Match these names to the speaker who most plausibly is the host "
                f"(short turns, many questions, bookending). Treat a jingle name match as "
                f"high-confidence (0.9+) when combined with host structural cues.\n"
            )
        else:
            jingle_section = ""

        prompt = IDENTIFICATION_PROMPT.format(
            jingle_section=jingle_section,
            transcript_sample=transcript_sample,
            speaker_summaries="\n\n".join(speaker_summaries),
        )

        try:
            # Budget ~250 tokens per speaker object (now includes reasoning) + overhead
            max_tokens = max(2048, len(merged_to_originals) * 250)

            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=0,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": prompt}],
            )

            if not response.content or not response.content[0].text.strip():
                raise ValueError(f"empty response (stop_reason={response.stop_reason!r})")
            raw = response.content[0].text.strip()
            # Strip markdown fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw).strip()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as parse_err:
                logger.warning(f"JSON parse failed ({parse_err}), attempting partial recovery")
                data = _recover_partial_json(raw)
                if data:
                    logger.info(
                        f"Partial recovery succeeded: {len(data)} speaker objects recovered"
                    )
                else:
                    raise

        except Exception as e:
            logger.error(f"Unified speaker identification failed: {e}")
            data = []

        # ---- Build result map and persist (one row per ORIGINAL label) ----
        results: dict[str, ResolvedSpeaker] = {}
        identified_originals: set[str] = set()

        for item in data:
            canonical = item.get("speaker_label", "")
            if not canonical:
                continue
            if canonical not in merged_to_originals:
                logger.warning(
                    f"LLM returned label '{canonical}' not in merged speaker set — dropping"
                )
                continue

            name_he_raw = item.get("name_he", "Unknown") or "Unknown"
            name_en_raw = item.get("name_en", "Unknown") or "Unknown"
            role_raw = (item.get("role") or "unknown").lower()
            confidence = float(item.get("confidence", 0.0))
            evidence = item.get("evidence", "") or ""
            reasoning = item.get("reasoning", "") or ""

            # Strict confidence enforcement: anything below 0.7 → Unknown.
            if confidence < 0.7 or name_en_raw == "Unknown":
                name_he, name_en, role = "Unknown", "Unknown", "unknown"
                method = "unresolved"
            else:
                name_he, name_en = name_he_raw, name_en_raw
                role = role_raw
                method = "llm_explicit" if confidence >= 0.9 else "llm_address"

            # Persist Person once per cluster (shared across original labels).
            person_id = None
            if name_en != "Unknown":
                person = session.query(Person).filter_by(name_en=name_en).first()
                if not person:
                    person = Person(name_he=name_he, name_en=name_en, role=role)
                    session.add(person)
                    session.flush()
                person_id = person.id

            originals = merged_to_originals[canonical]
            for original_label in originals:
                identity = SpeakerIdentity(
                    episode_id=episode_id,
                    speaker_label=original_label,
                    person_id=person_id,
                    role=role,
                    confidence=confidence,
                    method=method,
                    evidence={
                        "evidence_quote": evidence,
                        "reasoning": reasoning,
                        "merged_from": originals,
                        "canonical_label": canonical,
                        "utterance_count": len(speaker_utterances.get(canonical, [])),
                    },
                )
                session.add(identity)
                session.flush()

                results[original_label] = ResolvedSpeaker(
                    speaker_label=original_label,
                    name_he=name_he,
                    name_en=name_en,
                    role=role,
                    confidence=confidence,
                    person_id=person_id,
                )
                identified_originals.add(original_label)

            merge_note = f" (merged from {len(originals)})" if len(originals) > 1 else ""
            logger.info(
                f"  {canonical}{merge_note} -> {name_en} ({role}, conf={confidence:.2f})"
            )

        # ---- Unresolved fill-in for any content speaker the LLM didn't return ----
        for label in content_speaker_labels - identified_originals:
            canonical = label_map.get(label, label)
            identity = SpeakerIdentity(
                episode_id=episode_id,
                speaker_label=label,
                person_id=None,
                role="unknown",
                confidence=0.0,
                method="unresolved",
                evidence={
                    "merged_from": merged_to_originals.get(canonical, [label]),
                    "canonical_label": canonical,
                },
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

        identified_count = sum(1 for r in results.values() if r.name_en != "Unknown")
        logger.info(
            f"Speaker identification complete: {identified_count} identified out of "
            f"{len(results)} content speakers ({len(merged_to_originals)} canonical)"
        )
        return results


DEFERRED_RESOLVE_SYSTEM = """You are doing a second-pass identification of unrecognized speakers in an Israeli Hebrew radio transcript.

A first identification pass has already named some speakers. Your task is to identify the REMAINING UNKNOWN speakers by looking for indirect attributions anywhere in the transcript — especially near the end of speaking segments.

Common Israeli radio patterns that reveal a speaker's identity:
- Host thanks guest at end: "תודה רבה [NAME]" / "תודה [NAME] על הדברים" → that guest is [NAME]
- Host retrospective: "דיברנו עם [NAME]" / "היה אתנו [NAME]" → that guest was [NAME]
- Direct address by host: "בוא [NAME]", "תגיד לי [NAME]", "פרופסור [NAME]" → addressed speaker is [NAME]
- Self-introduction: "אני [NAME]" / "שמי [NAME]" → speaking speaker is [NAME]
- Caller greeting: "שלום [NAME] מ-[CITY]" → that caller is [NAME]
- Attribution: "כך אמר [NAME]" immediately after a long monologue → that speaker was [NAME]

STRICT rules:
- Only assign names with confidence ≥ 0.7 and explicit textual evidence
- Do NOT guess from context alone
- Unknown is always better than a wrong name
- Do not re-identify already-named speakers"""

DEFERRED_RESOLVE_PROMPT = """Unknown speakers to identify: {unknown_labels}

Already identified (for context only — do not change these):
{known_summary}

Full transcript excerpt (focus on segments involving the unknown speakers and what others say TO or ABOUT them):
{transcript_excerpt}

Return a JSON array — one object per unknown speaker you can identify with confidence ≥ 0.7.
Skip speakers you cannot identify. Return an empty array [] if none can be resolved.

[
  {{
    "speaker_label": "SPEAKER_NN",
    "name_he": "שם בעברית",
    "name_en": "Name in English",
    "role": "host|guest|caller|unknown",
    "confidence": 0.0-1.0,
    "evidence": "exact quote proving the identification"
  }}
]"""

_DEFERRED_MAX_TRANSCRIPT_CHARS = 10_000


def deferred_resolve_speakers(
    transcript: "TranscriptionResult",
    resolved: dict[str, "ResolvedSpeaker"],
    client: anthropic.Anthropic,
    model: str = "claude-haiku-4-5-20251001",
) -> dict[str, "ResolvedSpeaker"]:
    """Second-pass identification: fill in Unknown speakers using indirect attributions.

    Looks for patterns the per-chunk pass misses — thank-you closings, retrospective
    mentions, host direct address to the guest — which appear scattered across the
    full transcript rather than concentrated in naming-moment windows.

    Returns an updated copy of `resolved`; existing non-Unknown entries are unchanged.
    Makes at most one Haiku API call; skips entirely if all speakers are already resolved.
    """
    unknown_labels = [label for label, rs in resolved.items() if rs.name_en == "Unknown"]
    if not unknown_labels:
        logger.debug("deferred_resolve: all speakers already identified, skipping")
        return resolved

    logger.info(f"deferred_resolve: {len(unknown_labels)} unknown speaker(s): {unknown_labels}")

    known_summary = "\n".join(
        f"  {label} = {rs.name_en} ({rs.role})"
        for label, rs in sorted(resolved.items())
        if rs.name_en != "Unknown"
    ) or "  (none yet)"

    # Build a focused transcript excerpt: lines where an unknown speaker speaks
    # plus lines where other speakers address them (search up to 3 segs after each unknown line).
    unknown_set = set(unknown_labels)
    selected_lines: list[str] = []
    seen_indices: set[int] = set()
    segs = transcript.segments

    for i, seg in enumerate(segs):
        if seg.speaker not in unknown_set:
            continue
        for j in range(max(0, i - 1), min(len(segs), i + 4)):
            if j not in seen_indices:
                s = segs[j]
                selected_lines.append(f"[{s.start:.0f}s] {s.speaker}: {s.text}")
                seen_indices.add(j)

    # If very few lines selected, also include segments where known speakers
    # might be addressing or thanking an unknown speaker.
    if len(selected_lines) < 20:
        for i, seg in enumerate(segs):
            if seg.speaker in unknown_set:
                continue
            text = seg.text or ""
            if any(pat in text for pat in HEBREW_NAMING_PATTERNS + ["תודה", "היה אתנו", "דיברנו"]):
                if i not in seen_indices:
                    selected_lines.append(f"[{seg.start:.0f}s] {seg.speaker}: {text}")
                    seen_indices.add(i)

    transcript_excerpt = "\n".join(selected_lines)
    if len(transcript_excerpt) > _DEFERRED_MAX_TRANSCRIPT_CHARS:
        transcript_excerpt = transcript_excerpt[:_DEFERRED_MAX_TRANSCRIPT_CHARS] + "\n[truncated]"

    prompt = DEFERRED_RESOLVE_PROMPT.format(
        unknown_labels=", ".join(unknown_labels),
        known_summary=known_summary,
        transcript_excerpt=transcript_excerpt,
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=0,
            system=[{"type": "text", "text": DEFERRED_RESOLVE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip() if response.content else ""
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()
        from talk_show_analyzer.analysis.utils import parse_leading_json

        data: list[dict] = parse_leading_json(raw) if raw else []
    except Exception as exc:
        logger.warning(f"deferred_resolve: API call failed: {exc}")
        return resolved

    updated = dict(resolved)
    resolved_count = 0
    for item in data:
        label = item.get("speaker_label", "")
        if label not in unknown_set:
            continue
        confidence = float(item.get("confidence", 0.0))
        name_en = item.get("name_en", "Unknown") or "Unknown"
        if confidence < 0.7 or name_en == "Unknown":
            continue
        updated[label] = ResolvedSpeaker(
            speaker_label=label,
            name_he=item.get("name_he", "Unknown") or "Unknown",
            name_en=name_en,
            role=(item.get("role") or "unknown").lower(),
            confidence=confidence,
        )
        logger.info(
            f"  deferred_resolve: {label} → {name_en} "
            f"(conf={confidence:.2f}, evidence={item.get('evidence', '')!r})"
        )
        resolved_count += 1

    logger.info(
        f"deferred_resolve complete: {resolved_count}/{len(unknown_labels)} unknown speaker(s) resolved"
    )
    return updated


def consolidate_speakers(
    chunk_analyses: list,  # list[ChunkAnalysis] — imported lazily to avoid circular
    label_map: dict[str, str],  # original_label → canonical_label from acoustic merge
) -> dict[str, ResolvedSpeaker]:
    """Aggregate per-chunk speaker role votes into one resolved identity per original label.

    For each canonical speaker (post acoustic-merge), collects all ChunkSpeakerRole
    votes across all chunks and picks the highest-confidence non-unknown assignment.
    Returns a dict keyed by ORIGINAL speaker labels so downstream code is unchanged.
    """
    # canonical → list of (confidence, role, name_he, name_en)
    votes: dict[str, list] = defaultdict(list)
    for ca in chunk_analyses:
        for sr in ca.speaker_roles:
            canonical = label_map.get(sr.speaker_label, sr.speaker_label)
            votes[canonical].append((sr.confidence, sr.role, sr.name_he, sr.name_en))

    # canonical → list of original labels
    merged_to_originals: dict[str, list[str]] = defaultdict(list)
    for original, canonical in label_map.items():
        merged_to_originals[canonical].append(original)
    # Ensure canonicals that weren't in label_map (no embeddings) map to themselves
    for ca in chunk_analyses:
        for sr in ca.speaker_roles:
            canonical = label_map.get(sr.speaker_label, sr.speaker_label)
            merged_to_originals[canonical]  # touch to create key

    results: dict[str, ResolvedSpeaker] = {}

    all_canonicals = set(votes.keys()) | set(merged_to_originals.keys())
    for canonical in all_canonicals:
        role_votes = votes.get(canonical, [])
        # Prefer live roles (host/guest/caller) with name, then media_clip, then unknown
        live_valid = [
            (conf, role, he, en)
            for conf, role, he, en in role_votes
            if conf >= 0.7 and role in ("host", "guest", "caller") and en != "Unknown"
        ]
        clip_votes = [
            (conf, role, he, en)
            for conf, role, he, en in role_votes
            if role == "media_clip"
        ]
        if live_valid:
            conf, role, name_he, name_en = max(live_valid, key=lambda x: x[0])
        elif clip_votes:
            conf, role, name_he, name_en = max(clip_votes, key=lambda x: x[0])
            # Use the name if mentioned, otherwise Unknown
        else:
            conf, role, name_he, name_en = 0.0, "unknown", "Unknown", "Unknown"

        originals = merged_to_originals.get(canonical, [canonical])
        for original in originals:
            results[original] = ResolvedSpeaker(
                speaker_label=original,
                name_he=name_he,
                name_en=name_en,
                role=role,
                confidence=conf,
            )
        merge_note = f" (merged from {len(originals)})" if len(originals) > 1 else ""
        logger.info(f"  {canonical}{merge_note} → {name_en} ({role}, conf={conf:.2f})")

    identified = sum(1 for r in results.values() if r.name_en != "Unknown")
    clips = sum(1 for r in results.values() if r.role == "media_clip")
    logger.info(f"Speaker consolidation: {identified}/{len(results)} identified, {clips} media_clip")
    return results

