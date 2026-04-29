"""Link per-chunk speaker labels into a single global identity space.

Pyannote diarization runs independently on each chunk, so SPEAKER_00 in chunk 0
is unrelated to SPEAKER_00 in chunk 1. This module remaps each chunk's local
labels to canonical global IDs (GLOBAL_00, GLOBAL_01, ...) using two signals:

1. Overlap-anchored matching — chunks share an overlap window (default 60s).
   A speaker active in both the tail of chunk N and the head of chunk N+1 must
   be the same person; we match by speech-time overlap inside that window.
2. Embedding cosine similarity — for speakers absent from the overlap window,
   compare pyannote's per-speaker embedding centroid against a registry of
   already-seen global speakers.

Speakers matching neither signal are registered as new global IDs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from loguru import logger

from talk_show_analyzer.transcription.transcriber import (
    SpeakerSegment,
    TranscriptionResult,
)


@dataclass
class ChunkInput:
    """A transcribed chunk plus its absolute-time offset in the source audio."""

    result: TranscriptionResult
    offset_seconds: float  # where this chunk starts in the original recording


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _clipped_intervals(
    segments: list[SpeakerSegment],
    offset: float,
    window_start: float,
    window_end: float,
) -> list[tuple[float, float, str]]:
    """Return (abs_start, abs_end, label) clipped to an absolute-time window."""
    out: list[tuple[float, float, str]] = []
    for seg in segments:
        st = max(seg.start + offset, window_start)
        en = min(seg.end + offset, window_end)
        if en > st:
            out.append((st, en, seg.speaker))
    return out


def _cooccurrence(
    a: list[tuple[float, float, str]],
    b: list[tuple[float, float, str]],
) -> dict[tuple[str, str], float]:
    """Sum overlap durations per (label_a, label_b) pair across two timelines."""
    co: dict[tuple[str, str], float] = {}
    for ast, aen, alab in a:
        for bst, ben, blab in b:
            ovl = min(aen, ben) - max(ast, bst)
            if ovl > 0:
                co[(alab, blab)] = co.get((alab, blab), 0.0) + ovl
    return co


def link_chunks(
    chunks: list[ChunkInput],
    overlap_seconds: float = 60.0,
    similarity_threshold: float = 0.7,
    min_overlap_speech: float = 1.0,
) -> list[TranscriptionResult]:
    """Remap each chunk's speaker labels to a shared global ID space.

    Args:
        chunks: Per-chunk transcription results in chronological order, each
            with its absolute offset_seconds in the source recording.
        overlap_seconds: Length of overlap between consecutive chunks. Must
            match the chunker's overlap (default 60s).
        similarity_threshold: Cosine similarity above which two embeddings are
            considered the same speaker. 0.7 is a reasonable default for the
            pyannote community-1 embedder.
        min_overlap_speech: Minimum speech seconds in the overlap window to
            trust an overlap-based pairing. Below this we fall back to
            embeddings — too little overlap is unreliable.

    Returns:
        New TranscriptionResult instances (one per input chunk) with
        `segments[*].speaker` rewritten to global IDs ("GLOBAL_00", ...) and
        `speaker_embeddings` re-keyed under those IDs (centroid across chunks).
    """
    if not chunks:
        return []

    # Global registry: global_id -> (centroid_embedding, count_of_chunks_seen)
    registry: dict[str, tuple[np.ndarray, int]] = {}
    next_global = 0

    def _new_global() -> str:
        nonlocal next_global
        gid = f"GLOBAL_{next_global:02d}"
        next_global += 1
        return gid

    def _register(gid: str, emb: np.ndarray | None) -> None:
        if emb is None:
            return
        if gid in registry:
            prev, n = registry[gid]
            registry[gid] = ((prev * n + emb) / (n + 1), n + 1)
        else:
            registry[gid] = (emb, 1)

    # Per-chunk: local_label -> global_id
    chunk_maps: list[dict[str, str]] = []

    for i, chunk in enumerate(chunks):
        local_labels = {seg.speaker for seg in chunk.result.segments}
        local_to_global: dict[str, str] = {}

        # --- Step 1: overlap-anchored matching against previous chunk ---
        if i > 0:
            prev = chunks[i - 1]
            prev_map = chunk_maps[i - 1]

            # Absolute time window that both chunks share
            win_start = chunk.offset_seconds
            win_end = chunk.offset_seconds + overlap_seconds

            this_iv = _clipped_intervals(
                chunk.result.segments, chunk.offset_seconds, win_start, win_end
            )
            prev_iv = _clipped_intervals(
                prev.result.segments, prev.offset_seconds, win_start, win_end
            )
            # co[(this_label, prev_label)] = duration both are speaking simultaneously
            co = _cooccurrence(this_iv, prev_iv)

            # Greedy match by descending temporal co-occurrence
            candidates = sorted(
                ((dur, tl, pl) for (tl, pl), dur in co.items()),
                reverse=True,
            )
            used_prev: set[str] = set()
            for dur, tl, pl in candidates:
                if dur < min_overlap_speech:
                    break
                if tl in local_to_global or pl in used_prev:
                    continue
                if pl in prev_map:
                    local_to_global[tl] = prev_map[pl]
                    used_prev.add(pl)

        # --- Step 2: embedding similarity for unmatched labels ---
        for label in local_labels:
            if label in local_to_global:
                continue
            emb = chunk.result.speaker_embeddings.get(label)
            best_gid: str | None = None
            best_sim = similarity_threshold
            if emb is not None and registry:
                for gid, (centroid, _) in registry.items():
                    sim = _cosine(emb, centroid)
                    if sim > best_sim:
                        best_sim = sim
                        best_gid = gid
            if best_gid is None:
                best_gid = _new_global()
                logger.debug(
                    f"chunk={i} {label} → {best_gid} (new; "
                    f"max_sim={best_sim:.2f} < {similarity_threshold})"
                )
            else:
                logger.debug(
                    f"chunk={i} {label} → {best_gid} (embedding sim={best_sim:.2f})"
                )
            local_to_global[label] = best_gid

        # Update registry centroids with this chunk's embeddings
        for local, gid in local_to_global.items():
            _register(gid, chunk.result.speaker_embeddings.get(local))

        chunk_maps.append(local_to_global)

    # --- Build new TranscriptionResults with rewritten speaker labels ---
    out: list[TranscriptionResult] = []
    for chunk, lmap in zip(chunks, chunk_maps):
        new_segments = [
            SpeakerSegment(
                start=seg.start,
                end=seg.end,
                speaker=lmap.get(seg.speaker, seg.speaker),
                text=seg.text,
            )
            for seg in chunk.result.segments
        ]
        new_embeddings = {
            lmap[local]: registry[lmap[local]][0]
            for local in chunk.result.speaker_embeddings
            if local in lmap
        }
        out.append(
            TranscriptionResult(
                raw_text=chunk.result.raw_text,
                language=chunk.result.language,
                duration=chunk.result.duration,
                word_count=chunk.result.word_count,
                segments=new_segments,
                speaker_embeddings=new_embeddings,
            )
        )

    logger.info(
        f"link_chunks: {len(chunks)} chunks → {next_global} global speakers"
    )
    return out
