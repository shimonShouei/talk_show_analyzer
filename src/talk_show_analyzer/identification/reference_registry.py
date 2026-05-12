"""Reference speaker registry for known hosts/guests.

Stores pre-computed voice embeddings for known people so we can match
episode speaker labels against them by cosine similarity — before or
instead of LLM-based name extraction.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from loguru import logger


@dataclass
class ReferenceEntry:
    name_he: str
    name_en: str
    role: str
    embedding: np.ndarray  # L2-normalised 256-d vector


def load_registry(registry_path: str | Path) -> list[ReferenceEntry]:
    """Load reference embeddings from a JSON registry file."""
    registry_path = Path(registry_path)
    if not registry_path.exists():
        logger.debug(f"No reference registry found at {registry_path}")
        return []

    with open(registry_path) as f:
        data = json.load(f)

    entries: list[ReferenceEntry] = []
    for item in data.get("speakers", []):
        emb_path = Path(item["embedding_path"])
        if not emb_path.exists():
            logger.warning(f"Reference embedding not found: {emb_path} — skipping {item['name_en']}")
            continue
        emb = np.load(emb_path).astype(np.float32).flatten()
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        entries.append(ReferenceEntry(
            name_he=item["name_he"],
            name_en=item["name_en"],
            role=item.get("role", "host"),
            embedding=emb,
        ))
        logger.debug(f"Loaded reference: {item['name_en']} (dim={emb.shape[0]})")

    logger.info(f"Reference registry: {len(entries)} known speakers loaded")
    return entries


def match_to_references(
    episode_embeddings: dict[str, np.ndarray],
    references: list[ReferenceEntry],
    threshold: float = 0.75,
) -> dict[str, ReferenceEntry]:
    """Match episode speaker labels to reference speakers by cosine similarity.

    Returns a dict of speaker_label → best matching ReferenceEntry,
    only for matches above `threshold`. Labels not matched are omitted.
    """
    if not references or not episode_embeddings:
        return {}

    matches: dict[str, ReferenceEntry] = {}
    for label, emb in episode_embeddings.items():
        emb = np.array(emb, dtype=np.float32).flatten()
        norm = np.linalg.norm(emb)
        if norm == 0:
            continue
        emb = emb / norm

        best_sim = -1.0
        best_ref = None
        for ref in references:
            sim = float(np.dot(emb, ref.embedding))
            if sim > best_sim:
                best_sim = sim
                best_ref = ref

        if best_ref is not None and best_sim >= threshold:
            matches[label] = best_ref
            logger.info(
                f"  {label} matched → {best_ref.name_en} "
                f"(cosine={best_sim:.3f}, role={best_ref.role})"
            )
        else:
            logger.debug(
                f"  {label} no match (best={best_ref.name_en if best_ref else 'none'}, "
                f"sim={best_sim:.3f})"
            )

    return matches
