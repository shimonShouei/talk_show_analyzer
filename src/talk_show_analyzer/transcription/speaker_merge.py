"""Post-diarization speaker merging by voice similarity.

pyannote over-splits long radio audio (and chunked transcription can fail to
link a speaker across chunks), so one person often ends up under several
labels. This module computes one voice embedding per label straight from the
audio (pyannote's own embedding model, no re-diarization) and merges labels
whose embeddings are close, with a turn-taking guard: two labels that answer
each other back and forth are a conversation between different people and are
never merged.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

import numpy as np
from loguru import logger

from talk_show_analyzer.transcription.transcriber import SpeakerSegment, TranscriptionResult

EMBEDDING_CHECKPOINT = "pyannote/speaker-diarization-community-1"
SAMPLE_RATE = 16000


def _load_audio(audio_path: str | Path):
    """Decode to 16 kHz mono float tensor via ffmpeg (tolerates corrupt MP3 frames,
    e.g. at the joins of a resumed live recording, which torchaudio rejects)."""
    import subprocess

    import torch

    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(audio_path), "-f", "s16le", "-ac", "1",
         "-ar", str(SAMPLE_RATE), "-"],
        capture_output=True, check=False,
    ).stdout
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if audio.size == 0:
        raise RuntimeError(f"could not decode audio: {audio_path}")
    return torch.from_numpy(audio.copy()).unsqueeze(0)


def _load_model():
    import torch
    from pyannote.audio import Model

    from talk_show_analyzer.config import settings

    model = Model.from_pretrained(
        EMBEDDING_CHECKPOINT, subfolder="embedding", token=settings.hf_token or None
    )
    model.eval()
    return model.to(torch.device("cpu"))


def compute_label_embeddings(
    audio_path: str | Path,
    segments: list[SpeakerSegment],
    min_segment_s: float = 1.5,
    max_crop_s: float = 10.0,
    max_total_s: float = 60.0,
    model=None,
) -> dict[str, np.ndarray]:
    """One L2-normalised voice embedding per speaker label (mean of crops)."""
    import torch

    waveform = _load_audio(audio_path)
    model = model or _load_model()
    by_label: dict[str, list[SpeakerSegment]] = defaultdict(list)
    for s in segments:
        if s.speaker and s.speaker != "SPEAKER_UNKNOWN" and s.end - s.start >= min_segment_s:
            by_label[s.speaker].append(s)

    out: dict[str, np.ndarray] = {}
    with torch.inference_mode():
        for label, segs in by_label.items():
            segs = sorted(segs, key=lambda s: s.end - s.start, reverse=True)
            vecs, total = [], 0.0
            for s in segs:
                if total >= max_total_s:
                    break
                dur = min(s.end - s.start, max_crop_s)
                mid = (s.start + s.end) / 2
                a = int(max(0.0, mid - dur / 2) * SAMPLE_RATE)
                b = int(min(waveform.shape[1], a + dur * SAMPLE_RATE))
                if b - a < SAMPLE_RATE:  # <1s of audio
                    continue
                emb = model(waveform[:, a:b].unsqueeze(0)).squeeze(0).cpu().numpy()
                n = np.linalg.norm(emb)
                if n > 0 and np.isfinite(n):
                    vecs.append(emb / n)
                    total += dur
            if vecs:
                m = np.mean(vecs, axis=0)
                out[label] = m / (np.linalg.norm(m) or 1.0)
    return out


def _turn_transitions(segments: list[SpeakerSegment]) -> Counter:
    """Count direct A→B speaker changes (unordered pairs)."""
    c: Counter = Counter()
    prev = None
    for s in segments:
        if prev and s.speaker != prev:
            c[frozenset((prev, s.speaker))] += 1
        prev = s.speaker
    return c


def plan_merges(
    embeddings: dict[str, np.ndarray],
    segments: list[SpeakerSegment],
    threshold: float = 0.75,
    max_turns: int = 2,
) -> dict[str, str]:
    """Average-linkage agglomerative merge. Returns {old_label: canonical_label}.

    Two clusters merge only if their average cosine similarity >= ``threshold``
    and no pair across them has more than ``max_turns`` direct turn changes
    (speakers who talk *to each other* are different people).
    """
    speech = Counter()
    for s in segments:
        speech[s.speaker] += s.end - s.start
    turns = _turn_transitions(segments)
    clusters: list[list[str]] = [[lab] for lab in embeddings]

    def sim(a: list[str], b: list[str]) -> float:
        return float(np.mean([embeddings[x] @ embeddings[y] for x in a for y in b]))

    def conversing(a: list[str], b: list[str]) -> bool:
        return any(turns[frozenset((x, y))] > max_turns for x in a for y in b)

    while True:
        best = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                s = sim(clusters[i], clusters[j])
                if s >= threshold and (best is None or s > best[0]) and not conversing(
                    clusters[i], clusters[j]
                ):
                    best = (s, i, j)
        if best is None:
            break
        s, i, j = best
        logger.info(f"voice merge: {clusters[i]} + {clusters[j]} (sim={s:.2f})")
        clusters[i] = clusters[i] + clusters[j]
        del clusters[j]

    mapping: dict[str, str] = {}
    for cl in clusters:
        canon = max(cl, key=lambda lab: speech[lab])
        for lab in cl:
            if lab != canon:
                mapping[lab] = canon
    return mapping


def merge_speakers_by_voice(
    transcript: TranscriptionResult,
    audio_path: str | Path,
    threshold: float = 0.75,
    embeddings: dict[str, np.ndarray] | None = None,
) -> tuple[TranscriptionResult, dict[str, str]]:
    """Relabel ``transcript`` so voice-identical labels share one label."""
    if embeddings is None:
        embeddings = compute_label_embeddings(audio_path, transcript.segments)
    mapping = plan_merges(embeddings, transcript.segments, threshold=threshold)
    before = len({s.speaker for s in transcript.segments})
    new_segments = [replace(s, speaker=mapping.get(s.speaker, s.speaker)) for s in transcript.segments]
    after = len({s.speaker for s in new_segments})
    logger.info(f"voice merge: {before} → {after} speaker labels (threshold={threshold})")
    new_emb = {k: v for k, v in (transcript.speaker_embeddings or {}).items() if k not in mapping}
    return replace(transcript, segments=new_segments, speaker_embeddings=new_emb), mapping
