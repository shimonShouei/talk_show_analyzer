"""Thematic Intelligence pipeline.

A unified analyzer that replaces the old Segmenter + TopicExtractor +
SentimentAnalyzer trio with a single, topic-first pass:

    Stage 1 — Local segmentation:    transcript → topic chunks
    Stage 2 — Global merging:        chunks → merged topics across the show
    Stage 3 — Deep analysis:         per merged topic, extract entities,
                                     hate-speech incidents, and per-speaker
                                     stance + opinion.

Output is a list of `TopicAnalysis` Pydantic V2 models — the canonical data
contract for everything downstream (DB persistence, dashboard, exports).
"""

from __future__ import annotations

import json
from typing import Literal

import anthropic
import numpy as np
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from talk_show_analyzer.config import settings
from talk_show_analyzer.transcription.transcriber import (
    SpeakerSegment,
    TranscriptionResult,
)
from talk_show_analyzer.analysis.prompts.thematic import (
    LOCAL_SEGMENT_PROMPT,
    THEMATIC_JOINER_PROMPT,
    TOPIC_ANALYSIS_PROMPT,
    format_chunks_for_joiner,
    format_local_window,
    format_merged_topic_for_analysis,
)
from talk_show_analyzer.analysis.utils import (
    create_sliding_windows,
    extract_fenced_json,
    safe_response_text,
)


# =============================================================================
# Data contracts (Pydantic V2)
# =============================================================================

EntityType = Literal["organization", "location", "figure"]

HateSpeechLevel = Literal[
    "none",
    "offensive_language",
    "discrediting",
    "insulting",
    "hate_speech",
    "threat",
]

Stance = Literal["support", "oppose", "neutral", "ambivalent"]

TopicCategory = Literal[
    "politics",
    "security",
    "economy",
    "social",
    "legal",
    "international",
    "sports",
    "culture",
    "other",
]


class Entity(BaseModel):
    """A named entity mentioned within a merged topic."""

    model_config = ConfigDict(extra="forbid")

    name_he: str
    name_en: str
    type: EntityType
    mentioned_by: list[str] = Field(default_factory=list)


class HateSpeechIncident(BaseModel):
    """A single hate-speech / evaluative-talk event inside a merged topic."""

    model_config = ConfigDict(extra="forbid")

    speaker_label: str
    level: HateSpeechLevel
    target: str
    phrase_he: str
    context_he: str
    rationale_en: str


class SpeakerInsight(BaseModel):
    """One speaker's stance + opinion on one merged topic."""

    model_config = ConfigDict(extra="forbid")

    stance: Stance
    summary_of_opinion_he: str
    summary_of_opinion_en: str
    evidence_quotes_he: list[str] = Field(default_factory=list)


class TopicAnalysis(BaseModel):
    """Full thematic record for a merged topic across the show."""

    model_config = ConfigDict(extra="forbid")

    topic_id: str
    merged_title_he: str
    merged_title_en: str
    category: TopicCategory
    thematic_flow_he: str
    time_spans: list[tuple[float, float]] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    hate_speech_incidents: list[HateSpeechIncident] = Field(default_factory=list)
    speaker_insights: dict[str, SpeakerInsight] = Field(default_factory=dict)
    part_idx: int | None = None


# =============================================================================
# Internal helpers
# =============================================================================


class _UnionFind:
    """Tiny union-find for single-linkage clustering of similar chunks."""

    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


# =============================================================================
# ThematicAnalyzer
# =============================================================================


class ThematicAnalyzer:
    """Three-stage topic-first analyzer for Israeli talk shows."""

    WINDOW_SIZE_SECONDS = 5 * 60
    OVERLAP_SECONDS = 60
    OVERLAP_DEDUP_RATIO = 0.5  # drop chunks that overlap a kept chunk by ≥ 50%

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        deep_model: str = "claude-sonnet-4-6",
        embedder: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        similarity_threshold: float = 0.65,
    ):
        self.model = model
        self.deep_model = deep_model
        self.embedder_name = embedder
        self.similarity_threshold = similarity_threshold

        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._embedder = None  # lazy-loaded on first use

    # ---------------------------------------------------------------- public

    def analyze(self, transcript: TranscriptionResult) -> list[TopicAnalysis]:
        """Run all three stages over a transcript and return the topic records."""
        logger.info(
            f"ThematicAnalyzer: {transcript.duration:.0f}s, "
            f"{len(transcript.segments)} speaker segments"
        )

        chunks = self._local_segment(transcript)
        logger.info(f"Stage 1: produced {len(chunks)} topic chunks")
        if not chunks:
            return []

        merged = self._global_merge(chunks)
        logger.info(f"Stage 2: merged to {len(merged)} cross-show topics")

        analyses: list[TopicAnalysis] = []
        for i, m in enumerate(merged):
            logger.info(
                f"Stage 3: deep analysis {i+1}/{len(merged)} — {m['merged_title_he']}"
            )
            ta = self._analyze_topic(m, chunks)
            if ta is not None:
                analyses.append(ta)

        logger.info(f"ThematicAnalyzer: completed {len(analyses)} topic analyses")
        return analyses

    def analyze_part(self, part) -> list[TopicAnalysis]:
        """Run the 3-stage pipeline on a single structural Part.

        Returns [] if the part is too short (<60s) or has <3 segments.
        The Part type (interview, host_talk, etc.) is NOT a filter — all
        substantive parts are analyzed.
        """
        # Import here to avoid circular imports at module load time.
        from talk_show_analyzer.analysis.structural_segmenter import Part  # noqa: F401

        if part.duration < 60 or len(part.segments) < 3:
            logger.info(
                f"analyze_part: skipping {part.type.value} part "
                f"({part.duration:.0f}s, {len(part.segments)} segs) — too short"
            )
            return []

        synthetic = self._part_to_transcript(part)
        logger.info(
            f"analyze_part: {part.type.value} {part.start:.0f}-{part.end:.0f}s "
            f"({len(part.segments)} segs)"
        )
        return self.analyze(synthetic)

    @staticmethod
    def _part_to_transcript(part) -> TranscriptionResult:
        """Build a synthetic TranscriptionResult from a Part's segments."""
        raw_text = " ".join(s.text for s in part.segments if s.text)
        word_count = len(raw_text.split())
        return TranscriptionResult(
            raw_text=raw_text,
            language="he",
            duration=part.end - part.start,
            word_count=word_count,
            segments=part.segments,
            speaker_embeddings={},
        )

    # ----------------------------------------------------- Stage 1: local seg

    def _local_segment(self, transcript: TranscriptionResult) -> list[dict]:
        """Window the transcript and ask the LLM for topic-coherent chunks.

        Returns chunks with: chunk_id, start, end, speakers, raw_text,
        tentative_title_he, tentative_summary_he.
        """
        windows = create_sliding_windows(
            transcript, self.WINDOW_SIZE_SECONDS, self.OVERLAP_SECONDS
        )
        logger.info(f"Stage 1: {len(windows)} windows")

        all_chunks: list[dict] = []
        next_id = 0
        for i, window in enumerate(windows):
            logger.info(
                f"Stage 1: window {i+1}/{len(windows)} "
                f"({window[0].start:.0f}s-{window[-1].end:.0f}s)"
            )
            window_chunks = self._segment_window(window)
            for c in window_chunks:
                c["chunk_id"] = f"c{next_id}"
                next_id += 1
                c["raw_text"] = self._gather_chunk_text(transcript, c["start"], c["end"])
            all_chunks.extend(window_chunks)

        return self._dedup_overlapping_chunks(all_chunks)


    def _segment_window(self, window: list[SpeakerSegment]) -> list[dict]:
        """LLM call for one window. Returns list of chunk dicts (no chunk_id yet)."""
        prompt_input = format_local_window(window)
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2500,
                temperature=0,
                system=[
                    {
                        "type": "text",
                        "text": LOCAL_SEGMENT_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": f"Segment this window by topic:\n\n{prompt_input}",
                    }
                ],
            )
            data = extract_fenced_json(safe_response_text(response))
        except (json.JSONDecodeError, anthropic.APIError, ValueError) as e:
            logger.warning(f"Local segmentation failed for window: {e}")
            return []

        chunks = []
        for item in data:
            try:
                chunks.append(
                    {
                        "start": float(item["start"]),
                        "end": float(item["end"]),
                        "speakers": list(item.get("speakers", [])),
                        "tentative_title_he": str(item.get("tentative_title_he", "")),
                        "tentative_summary_he": str(
                            item.get("tentative_summary_he", "")
                        ),
                    }
                )
            except (KeyError, TypeError, ValueError) as e:
                logger.warning(f"Skipping malformed chunk {item}: {e}")
        return chunks

    def _gather_chunk_text(
        self, transcript: TranscriptionResult, start: float, end: float
    ) -> str:
        """Concatenate speaker segments within [start, end] into a transcript block."""
        lines = []
        for seg in transcript.segments:
            if seg.end <= start or seg.start >= end:
                continue
            lines.append(f"[{seg.start:.0f}-{seg.end:.0f}] {seg.speaker}: {seg.text}")
        return "\n".join(lines)

    def _dedup_overlapping_chunks(self, chunks: list[dict]) -> list[dict]:
        """When two chunks overlap by ≥ OVERLAP_DEDUP_RATIO, keep the longer one."""
        if not chunks:
            return []
        chunks = sorted(chunks, key=lambda c: (c["start"], -c["end"]))
        kept: list[dict] = []
        for c in chunks:
            duplicate = False
            for k in kept:
                overlap = max(0.0, min(c["end"], k["end"]) - max(c["start"], k["start"]))
                shorter = min(c["end"] - c["start"], k["end"] - k["start"])
                if shorter > 0 and overlap / shorter >= self.OVERLAP_DEDUP_RATIO:
                    duplicate = True
                    # if the new one is meaningfully longer, replace
                    if (c["end"] - c["start"]) > (k["end"] - k["start"]) * 1.2:
                        kept[kept.index(k)] = c
                    break
            if not duplicate:
                kept.append(c)
        # re-sort and re-id
        kept.sort(key=lambda c: c["start"])
        for i, c in enumerate(kept):
            c["chunk_id"] = f"c{i}"
        return kept

    # ------------------------------------------------- Stage 2: global merge

    def _global_merge(self, chunks: list[dict]) -> list[dict]:
        """Cluster chunks by semantic similarity, then verify with the LLM joiner.

        Returns merged topics: dicts with topic_id, merged_title_he/en, category,
        chunk_ids.
        """
        if len(chunks) == 1:
            c = chunks[0]
            return [
                {
                    "topic_id": "t0",
                    "merged_title_he": c["tentative_title_he"],
                    "merged_title_en": "",
                    "category": "other",
                    "chunk_ids": [c["chunk_id"]],
                }
            ]

        candidate_groups = self._cluster_by_embedding(chunks)
        logger.info(f"Stage 2: {len(candidate_groups)} candidate groups from embeddings")

        # Send candidate groups + all chunks to the LLM for verification.
        # The joiner is allowed to split or re-merge groups.
        merged = self._verify_with_llm(chunks, candidate_groups)
        return merged

    def _cluster_by_embedding(self, chunks: list[dict]) -> list[list[str]]:
        """Single-linkage cluster on cosine similarity of chunk embeddings."""
        embedder = self._get_embedder()
        if embedder is None:
            # Fallback: every chunk is its own group
            return [[c["chunk_id"]] for c in chunks]

        texts = [
            f"{c['tentative_title_he']} {c['tentative_summary_he']}".strip()
            for c in chunks
        ]
        embeddings = embedder.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        sims = np.asarray(embeddings) @ np.asarray(embeddings).T

        n = len(chunks)
        uf = _UnionFind(n)
        for i in range(n):
            for j in range(i + 1, n):
                if sims[i][j] >= self.similarity_threshold:
                    uf.union(i, j)

        groups: dict[int, list[str]] = {}
        for i, c in enumerate(chunks):
            groups.setdefault(uf.find(i), []).append(c["chunk_id"])
        return list(groups.values())

    def _get_embedder(self):
        if self._embedder is not None:
            return self._embedder
        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading sentence-transformer: {self.embedder_name}")
            self._embedder = SentenceTransformer(self.embedder_name)
            return self._embedder
        except Exception as e:
            logger.warning(
                f"sentence-transformers unavailable ({e}); "
                "falling back to LLM-only joiner with one chunk per group"
            )
            return None

    def _verify_with_llm(
        self, chunks: list[dict], candidate_groups: list[list[str]]
    ) -> list[dict]:
        """LLM joiner refines the embedding clusters into final merged topics."""
        # Build a context message that shows the chunks AND the embedding-suggested
        # groups, then let the model decide the final partition.
        chunk_listing = format_chunks_for_joiner(chunks)
        groups_repr = "\n".join(
            f"  group {i}: {', '.join(g)}" for i, g in enumerate(candidate_groups)
        )
        user_msg = (
            f"All topic chunks discovered in the show:\n\n{chunk_listing}\n\n"
            f"Embedding-based candidate groups (you may split or re-merge these):\n"
            f"{groups_repr}\n\n"
            "Produce the final merged-topic partition."
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=3000,
                temperature=0,
                system=[
                    {
                        "type": "text",
                        "text": THEMATIC_JOINER_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_msg}],
            )
            data = extract_fenced_json(safe_response_text(response))
        except (json.JSONDecodeError, anthropic.APIError, ValueError) as e:
            logger.warning(
                f"LLM joiner failed ({e}); falling back to embedding groups"
            )
            return [
                {
                    "topic_id": f"t{i}",
                    "merged_title_he": "",
                    "merged_title_en": "",
                    "category": "other",
                    "chunk_ids": g,
                }
                for i, g in enumerate(candidate_groups)
            ]

        merged: list[dict] = []
        for i, item in enumerate(data):
            try:
                merged.append(
                    {
                        "topic_id": str(item.get("topic_id", f"t{i}")),
                        "merged_title_he": str(item.get("merged_title_he", "")),
                        "merged_title_en": str(item.get("merged_title_en", "")),
                        "category": str(item.get("category", "other")),
                        "chunk_ids": list(item.get("chunk_ids", [])),
                    }
                )
            except (KeyError, TypeError) as e:
                logger.warning(f"Skipping malformed merged topic {item}: {e}")

        # Safety net: ensure every chunk_id is partitioned exactly once
        seen = {cid for m in merged for cid in m["chunk_ids"]}
        leftovers = [c["chunk_id"] for c in chunks if c["chunk_id"] not in seen]
        if leftovers:
            logger.warning(
                f"Joiner dropped {len(leftovers)} chunks; bucketing them as 'misc'"
            )
            merged.append(
                {
                    "topic_id": f"t{len(merged)}",
                    "merged_title_he": "שונות",
                    "merged_title_en": "Miscellaneous",
                    "category": "other",
                    "chunk_ids": leftovers,
                }
            )
        return merged

    # ----------------------------------------------- Stage 3: deep analysis

    def _analyze_topic(
        self, merged: dict, all_chunks: list[dict]
    ) -> TopicAnalysis | None:
        """Per merged topic: extract entities, hate-speech, speaker insights."""
        chunks_in_topic = [c for c in all_chunks if c["chunk_id"] in merged["chunk_ids"]]
        if not chunks_in_topic:
            return None

        prompt_body = format_merged_topic_for_analysis(
            merged_title=merged["merged_title_he"] or merged["merged_title_en"],
            category=merged["category"],
            chunks_with_text=chunks_in_topic,
        )

        time_spans = [(c["start"], c["end"]) for c in chunks_in_topic]

        return self._call_topic_analysis(
            user_msg=f"Analyze this merged topic:\n\n{prompt_body}",
            merged=merged,
            time_spans=time_spans,
            retry_with_error=None,
        )

    def _call_topic_analysis(
        self,
        user_msg: str,
        merged: dict,
        time_spans: list[tuple[float, float]],
        retry_with_error: str | None,
    ) -> TopicAnalysis | None:
        """Single Claude call + Pydantic validation; retries once on validation error."""
        messages = [{"role": "user", "content": user_msg}]
        if retry_with_error:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous response failed schema validation:\n"
                        f"{retry_with_error}\n\n"
                        "Re-emit the JSON, conforming exactly to the schema."
                    ),
                }
            )
        try:
            response = self.client.messages.create(
                model=self.deep_model,
                max_tokens=4000,
                temperature=0,
                system=[
                    {
                        "type": "text",
                        "text": TOPIC_ANALYSIS_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=messages,
            )
            data = extract_fenced_json(safe_response_text(response))
        except (json.JSONDecodeError, anthropic.APIError, ValueError) as e:
            logger.error(f"Deep analysis call failed for {merged['topic_id']}: {e}")
            return None

        # Inject fields the LLM doesn't own
        data["topic_id"] = merged["topic_id"]
        data["chunk_ids"] = merged["chunk_ids"]
        data["time_spans"] = [list(span) for span in time_spans]
        # Backfill defaults if the model omitted them
        data.setdefault("merged_title_he", merged.get("merged_title_he", ""))
        data.setdefault("merged_title_en", merged.get("merged_title_en", ""))
        data.setdefault("category", merged.get("category", "other"))
        data.setdefault("entities", [])
        data.setdefault("hate_speech_incidents", [])
        data.setdefault("speaker_insights", {})
        data.setdefault("thematic_flow_he", "")

        try:
            return TopicAnalysis.model_validate(data)
        except ValidationError as e:
            if retry_with_error is None:
                logger.warning(
                    f"Validation error on {merged['topic_id']}; retrying once: {e}"
                )
                return self._call_topic_analysis(
                    user_msg=user_msg,
                    merged=merged,
                    time_spans=time_spans,
                    retry_with_error=str(e),
                )
            logger.error(
                f"Validation failed twice on {merged['topic_id']}; dropping: {e}"
            )
            return None
