"""Prompt templates for the Thematic Intelligence pipeline.

The agent runs in three reasoning stages:

1. LOCAL_SEGMENT_PROMPT — split a window of the show into topic-coherent
   chunks (a topic shift = boundary).
2. THEMATIC_JOINER_PROMPT — given the local chunks for the *whole* show,
   identify which ones are actually the same topic (e.g., the show returns
   to a political scandal after a commercial) and merge them.
3. TOPIC_ANALYSIS_PROMPT — for each merged topic, produce the full
   Pydantic-shaped record: entities, hate-speech incidents, and per-speaker
   stance + opinion summary.

All prompts use Chain-of-Thought: the model is told to *think* before
answering. We extract the final JSON from a fenced ```json``` block so the
preceding reasoning does not have to be parsed.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 1 — local topic segmentation
# ---------------------------------------------------------------------------

LOCAL_SEGMENT_PROMPT = """You are an expert Israeli media analyst segmenting a radio talk show by topic.

A "topic chunk" is a continuous span of conversation about ONE coherent subject. A new chunk begins whenever the discussion pivots: a new guest, a new news item, a return from commercial to a different subject, or an explicit "let's move on" from the host.

Ignore non-content segments (jingles, ads, station IDs, music, weather) — emit them only if they fall *inside* a topic chunk you must keep intact.

## Reasoning

First, think step-by-step inside <thinking>...</thinking> tags about the flow of the window: who is speaking, what subject they're on, where the pivots are. This is private scratch space.

Keep the <thinking> block SHORT: at most ~120 words of terse notes (bullet fragments, no full prose, do not restate the transcript). Then, after </thinking>, output ONLY a fenced ```json``` block.

## JSON output

```json
[
  {
    "chunk_id": "c1",
    "start": 0.0,
    "end": 142.5,
    "speakers": ["SPEAKER_00", "SPEAKER_01"],
    "tentative_title_he": "...",
    "tentative_summary_he": "..."
  }
]
```

Rules:
- `start`/`end` in seconds, taken from the [start - end] timestamps in the input.
- Chunks must NOT overlap and must be in chronological order.
- `tentative_title_he` is short (≤ 8 words) — it is what the global joiner will compare across the show.
- `tentative_summary_he` is 1-2 sentences."""


def format_local_window(speaker_segments: list) -> str:
    """Format a window of SpeakerSegment objects for the local segmenter."""
    lines = []
    for seg in speaker_segments:
        lines.append(
            f"[{_hhmmss(seg.start)} - {_hhmmss(seg.end)}] {seg.speaker}: {seg.text}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stage 2 — thematic joiner (global merging)
# ---------------------------------------------------------------------------

THEMATIC_JOINER_PROMPT = """You are the "Thematic Joiner". You receive the list of topic chunks discovered locally across an entire 30-minute Israeli talk show. Your job: figure out which chunks are talking about the SAME underlying topic — even when the show drifts away and returns later (after ads, after a caller, after a news brief).

## What counts as "the same topic"

Two chunks belong to the same merged topic when a knowledgeable Israeli listener would describe them with the same one-line headline. Heuristics:
- Same news event, scandal, person, or piece of legislation.
- Same guest continuing after an interruption.
- Same policy debate framed two different ways (cost-of-living and the housing crisis can be one topic if the discussion is genuinely the same; keep them separate if framings diverge).

Do NOT merge superficially-similar chunks that are actually different events.

## Reasoning

Inside <thinking>...</thinking>, walk through the show's thematic flow: list the headlines you would give a listener, note returns, note transitions. Justify each merge.

Keep the <thinking> block SHORT: at most ~120 words of terse notes (bullet fragments, no full prose, do not restate the transcript). After </thinking>, emit ONLY a fenced ```json``` block.

## JSON output

```json
[
  {
    "topic_id": "t1",
    "merged_title_he": "...",
    "merged_title_en": "...",
    "category": "politics|security|economy|social|legal|international|sports|culture|other",
    "chunk_ids": ["c1", "c4", "c7"]
  }
]
```

Rules:
- Every input chunk_id must appear in exactly one merged topic (partition).
- `merged_title_he` is the headline a listener would use; ≤ 10 words.
- Order topics by first appearance in the show."""


# ---------------------------------------------------------------------------
# Stage 3 — per-topic deep analysis (NER + hate speech + stance)
# ---------------------------------------------------------------------------

TOPIC_ANALYSIS_PROMPT = """You are an expert analyst of Israeli political discourse. For one merged topic spanning multiple parts of a radio show, produce a complete structured analysis: entities mentioned, hate-speech incidents, and each speaker's stance + opinion.

## Hate-speech taxonomy (6 levels)

Use exactly one of:
- **none**: No evaluative or hostile language.
- **offensive_language**: Crude or rude language without a target group.
- **discrediting**: Casting doubt on someone's credibility, motives, or competence (e.g., calling a politician a liar).
- **insulting**: Personal insults aimed at an individual or group's dignity.
- **hate_speech**: Disparaging language targeting a protected group (ethnic, religious, national, political camp). Pay special attention to "Evaluative Talk" — disparaging Hebrew terms used in Israeli political discourse such as "פרזיטים" (parasites), "בוגדים" (traitors), "אנרכיסטים", "משתמטים", labels weaponized against groups.
- **threat**: Explicit or implicit calls for harm.

For every incident, capture the literal Hebrew phrase, the speaker, the target, and the level.

## Stance vocabulary

For each participating speaker, classify their stance toward the topic as exactly one of: `support`, `oppose`, `neutral`, `ambivalent`. Use `ambivalent` when the speaker holds mixed or shifting positions; use `neutral` only for genuinely balanced/factual contributions.

## Reasoning (Chain-of-Thought)

Inside <thinking>...</thinking> first, do these steps in order:
1. Re-read the merged topic title and skim every chunk.
2. Sketch the *thematic flow*: how does the show approach this topic across its appearances? What is the framing, the disagreement, the conclusion (if any)?
3. List the entities (organizations, locations, public figures) and who mentioned each.
4. Scan for hate-speech / evaluative talk against the taxonomy above.
5. ONLY THEN, for each speaker, decide stance + write a 1-2 sentence Hebrew opinion summary that quotes or paraphrases what THEY said (not the show's overall view).

Keep the <thinking> block SHORT: at most ~120 words of terse notes (bullet fragments, no full prose, do not restate the transcript). After </thinking>, emit ONLY a fenced ```json``` block.

## JSON output

```json
{
  "topic_id": "t1",
  "merged_title_he": "...",
  "merged_title_en": "...",
  "category": "politics",
  "thematic_flow_he": "תיאור קצר של איך הנושא מתפתח לאורך התוכנית",
  "entities": [
    {
      "name_he": "בנימין נתניהו",
      "name_en": "Benjamin Netanyahu",
      "type": "figure",
      "mentioned_by": ["SPEAKER_00", "SPEAKER_02"]
    }
  ],
  "hate_speech_incidents": [
    {
      "speaker_label": "SPEAKER_01",
      "level": "hate_speech",
      "target": "מפגיני שמאל",
      "phrase_he": "פרזיטים",
      "context_he": "המשפט המלא בו הופיעה הבעת השנאה",
      "rationale_en": "Why this counts at this taxonomy level"
    }
  ],
  "speaker_insights": {
    "SPEAKER_00": {
      "stance": "support",
      "summary_of_opinion_he": "...",
      "summary_of_opinion_en": "...",
      "evidence_quotes_he": ["ציטוט קצר ראשון", "ציטוט קצר שני"]
    },
    "SPEAKER_01": {
      "stance": "oppose",
      "summary_of_opinion_he": "...",
      "summary_of_opinion_en": "...",
      "evidence_quotes_he": ["..."]
    }
  }
}
```

Rules:
- `entity.type` ∈ {organization, location, figure}.
- `mentioned_by` lists every distinct speaker who named the entity.
- `hate_speech_incidents` is `[]` when no incident occurs — never invent one.
- `speaker_insights` includes EVERY speaker who actually spoke on this topic, no others.
- All `*_he` fields must be Hebrew; all `*_en` fields must be English.
- Quotes must be verbatim from the transcript (no paraphrasing in `evidence_quotes_he`)."""


def format_chunks_for_joiner(chunks: list[dict]) -> str:
    """Format topic chunks (dicts with chunk_id/start/end/title/summary) for the joiner."""
    lines = []
    for c in chunks:
        lines.append(
            f"[{c['chunk_id']}] {_hhmmss(c['start'])} - {_hhmmss(c['end'])} | "
            f"speakers={','.join(c.get('speakers', []))}\n"
            f"  title: {c.get('tentative_title_he', '')}\n"
            f"  summary: {c.get('tentative_summary_he', '')}"
        )
    return "\n".join(lines)


def format_merged_topic_for_analysis(
    merged_title: str,
    category: str,
    chunks_with_text: list[dict],
) -> str:
    """Format a merged topic (title + each constituent chunk's full transcript)."""
    parts = [f"MERGED TOPIC: {merged_title}", f"CATEGORY: {category}", ""]
    for c in chunks_with_text:
        parts.append(
            f"--- CHUNK {c['chunk_id']} "
            f"({_hhmmss(c['start'])} - {_hhmmss(c['end'])}) ---"
        )
        parts.append(c["raw_text"])
        parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _hhmmss(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
