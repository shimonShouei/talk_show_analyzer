"""Parts Timeline dashboard page.

Shows a horizontal timeline of episode structural parts and a
speaker × topic hate-proxy heatmap.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from loguru import logger
from sqlalchemy.orm import Session

from talk_show_analyzer.db import get_session
from talk_show_analyzer.models import (
    Episode,
    HateSpeechIncidentORM,
    MergedTopic,
    PartORM,
    Station,
)

# ── colour palette for part types ────────────────────────────────────────────
PART_COLORS: dict[str, str] = {
    "interview": "#2196F3",
    "host_talk": "#4CAF50",
    "news": "#FF9800",
    "jingle": "#9C27B0",
    "commercial": "#F44336",
    "unknown": "#9E9E9E",
}
DEFAULT_COLOR = "#9E9E9E"

# hate-level ordinal map
HATE_LEVELS: dict[str, int] = {
    "none": 0,
    "offensive_language": 1,
    "discrediting": 2,
    "insulting": 3,
    "hate_speech": 4,
    "threat": 5,
}


# ─────────────────────────────── data helpers ────────────────────────────────

def load_all_episodes(db_url: str | None = None) -> list[dict[str, Any]]:
    """Return all episodes newest-first for the selector dropdown."""
    rows: list[dict[str, Any]] = []
    try:
        with get_session(db_url) as session:
            eps = (
                session.query(Episode, Station)
                .join(Station, Episode.station_id == Station.id)
                .order_by(Episode.recorded_at.desc())
                .all()
            )
            for ep, st in eps:
                rows.append(
                    {
                        "id": ep.id,
                        "station": st.name,
                        "recorded_at": ep.recorded_at,
                        "duration": ep.duration,
                        "label": (
                            f"{st.name} — "
                            f"{ep.recorded_at.strftime('%Y-%m-%d %H:%M')} "
                            f"(id={ep.id})"
                        ),
                    }
                )
    except Exception as exc:
        logger.error(f"load_all_episodes error: {exc}")
    return rows


def load_parts(episode_id: int, db_url: str | None = None) -> list[dict[str, Any]]:
    """Return PartORM rows for *episode_id* as plain dicts, topic count included."""
    result: list[dict[str, Any]] = []
    try:
        with get_session(db_url) as session:
            parts = (
                session.query(PartORM)
                .filter(PartORM.episode_id == episode_id)
                .order_by(PartORM.idx)
                .all()
            )
            topics = (
                session.query(MergedTopic)
                .filter(MergedTopic.episode_id == episode_id)
                .all()
            )
            # pre-flatten all time-spans once
            topic_spans: list[tuple[float, float]] = []
            for t in topics:
                for span in t.time_spans or []:
                    if isinstance(span, (list, tuple)) and len(span) >= 2:
                        topic_spans.append((float(span[0]), float(span[1])))

            for p in parts:
                n_topics = sum(
                    1
                    for s, e in topic_spans
                    if s < p.end_seconds and e > p.start_seconds
                )
                result.append(
                    {
                        "id": p.id,
                        "idx": p.idx,
                        "type": p.type,
                        "start_seconds": p.start_seconds,
                        "end_seconds": p.end_seconds,
                        "duration": p.end_seconds - p.start_seconds,
                        "host_labels": p.host_labels or [],
                        "guest_labels": p.guest_labels or [],
                        "unknown_labels": p.unknown_labels or [],
                        "n_topics": n_topics,
                        "speaker_analyses": p.speaker_analyses or [],
                        "qa_pairs": p.qa_pairs or [],
                    }
                )
    except Exception as exc:
        logger.error(f"load_parts error: {exc}")
    return result


def load_hate_heatmap(
    episode_id: int, db_url: str | None = None
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Return (heatmap_df, speakers, topics) for the hate-proxy heatmap.

    Cell value = MAX hate level (ordinal) over all incidents for that
    (speaker, topic) pair.  Empty cells = 0.
    """
    try:
        with get_session(db_url) as session:
            # gather merged topics for this episode
            topics = (
                session.query(MergedTopic)
                .filter(MergedTopic.episode_id == episode_id)
                .all()
            )
            if not topics:
                return pd.DataFrame(), [], []

            topic_map: dict[int, str] = {}
            for t in topics:
                label = (t.merged_title_he or t.merged_title_en or str(t.topic_id))[:40]
                topic_map[t.id] = label

            # collect all incidents for those topics
            topic_ids = list(topic_map.keys())
            incidents = (
                session.query(HateSpeechIncidentORM)
                .filter(HateSpeechIncidentORM.merged_topic_id.in_(topic_ids))
                .all()
            )

            # collect all speakers from parts
            parts = (
                session.query(PartORM)
                .filter(PartORM.episode_id == episode_id)
                .all()
            )
            speaker_set: set[str] = set()
            for p in parts:
                speaker_set.update(p.host_labels or [])
                speaker_set.update(p.guest_labels or [])

            # also add speakers from incidents even if not in parts
            for inc in incidents:
                speaker_set.add(inc.speaker_label)

            speakers = sorted(speaker_set)
            topic_labels = [topic_map[tid] for tid in topic_ids]

            # build matrix: rows=speakers, cols=topics
            # value = max ordinal hate level
            matrix: dict[tuple[str, int], int] = {}
            for inc in incidents:
                key = (inc.speaker_label, inc.merged_topic_id)
                level_val = HATE_LEVELS.get(inc.level.lower(), 0)
                matrix[key] = max(matrix.get(key, 0), level_val)

            data = {
                tlabel: [
                    matrix.get((sp, tid), 0)
                    for sp in speakers
                ]
                for tid, tlabel in topic_map.items()
            }
            df = pd.DataFrame(data, index=speakers)
            return df, speakers, topic_labels
    except Exception as exc:
        logger.error(f"load_hate_heatmap error: {exc}")
        return pd.DataFrame(), [], []


# ─────────────────────────────── chart builders ──────────────────────────────

def build_timeline_figure(parts: list[dict[str, Any]]) -> go.Figure:
    """Build a Plotly horizontal timeline (Gantt-style) from parts list."""
    fig = go.Figure()

    for p in parts:
        dur_s = int(p["duration"])
        mm, ss = divmod(dur_s, 60)
        hosts = ", ".join(p["host_labels"]) or "—"
        guests = ", ".join(p["guest_labels"]) or "—"
        hover = (
            f"<b>Part {p['idx']} — {p['type']}</b><br>"
            f"Duration: {mm:02d}:{ss:02d}<br>"
            f"Hosts: {hosts}<br>"
            f"Guests: {guests}<br>"
            f"Merged topics overlapping: {p['n_topics']}"
        )
        color = PART_COLORS.get(p["type"], DEFAULT_COLOR)
        fig.add_trace(
            go.Bar(
                x=[p["duration"]],
                y=["Parts"],
                base=[p["start_seconds"]],
                orientation="h",
                marker_color=color,
                hovertemplate=hover + "<extra></extra>",
                name=p["type"],
                showlegend=False,
            )
        )

    # Legend items (one per distinct type)
    seen: set[str] = set()
    for p in parts:
        t = p["type"]
        if t not in seen:
            seen.add(t)
            fig.add_trace(
                go.Bar(
                    x=[0],
                    y=["_legend"],
                    orientation="h",
                    marker_color=PART_COLORS.get(t, DEFAULT_COLOR),
                    name=t,
                    showlegend=True,
                    hoverinfo="skip",
                )
            )

    total = max((p["end_seconds"] for p in parts), default=1)
    fig.update_layout(
        barmode="stack",
        height=180,
        margin=dict(l=20, r=20, t=10, b=40),
        xaxis=dict(title="Seconds", range=[0, total]),
        yaxis=dict(showticklabels=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


def build_heatmap_figure(df: pd.DataFrame) -> go.Figure:
    """Build a speaker × topic heatmap."""
    fig = go.Figure(
        go.Heatmap(
            z=df.values.tolist(),
            x=list(df.columns),
            y=list(df.index),
            colorscale="Reds",
            zmin=0,
            zmax=5,
            colorbar=dict(
                title="Hate level",
                tickvals=list(HATE_LEVELS.values()),
                ticktext=list(HATE_LEVELS.keys()),
            ),
            hovertemplate="Speaker: %{y}<br>Topic: %{x}<br>Level: %{z}<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(200, 40 * len(df.index) + 80),
        margin=dict(l=20, r=20, t=20, b=120),
        xaxis=dict(tickangle=-40),
    )
    return fig


# ─────────────────────────────── Streamlit render ────────────────────────────

st.title("🗂️ Parts Timeline")
st.markdown("---")

all_episodes = load_all_episodes()

if not all_episodes:
    st.warning("No episodes found in the database.")
    st.stop()

episode_labels = [e["label"] for e in all_episodes]
selected_idx = st.selectbox(
    "Select episode",
    range(len(all_episodes)),
    format_func=lambda i: episode_labels[i],
)
ep_meta = all_episodes[selected_idx]
episode_id = ep_meta["id"]

# ── header metadata ──────────────────────────────────────────────────────────
parts = load_parts(episode_id)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Station", ep_meta["station"])
with col2:
    st.metric("Recorded at", ep_meta["recorded_at"].strftime("%Y-%m-%d %H:%M"))
with col3:
    dur_min = int(ep_meta["duration"] // 60)
    st.metric("Duration", f"{dur_min} min")
with col4:
    st.metric("Parts", len(parts))

st.markdown("---")

# ── timeline ─────────────────────────────────────────────────────────────────
if parts:
    st.subheader("Timeline")
    fig_tl = build_timeline_figure(parts)
    st.plotly_chart(fig_tl, use_container_width=True)

    # parts table
    with st.expander("Parts detail table"):
        df_parts = pd.DataFrame(
            [
                {
                    "idx": p["idx"],
                    "type": p["type"],
                    "start": f"{int(p['start_seconds'] // 60):02d}:{int(p['start_seconds'] % 60):02d}",
                    "end": f"{int(p['end_seconds'] // 60):02d}:{int(p['end_seconds'] % 60):02d}",
                    "duration": f"{int(p['duration'] // 60):02d}:{int(p['duration'] % 60):02d}",
                    "hosts": ", ".join(p["host_labels"]),
                    "guests": ", ".join(p["guest_labels"]),
                    "topics_overlap": p["n_topics"],
                }
                for p in parts
            ]
        )
        st.dataframe(df_parts, use_container_width=True, hide_index=True)
else:
    st.info("No parts found for this episode.")

st.markdown("---")

# ── per-part stance & tone ────────────────────────────────────────────────────
content_parts = [p for p in parts if p["type"] not in ("jingle", "commercial", "news")]
if content_parts and any(p["speaker_analyses"] for p in content_parts):
    st.subheader("Per-Part Speaker Stance & Tone")

    TONE_COLORS: dict[str, str] = {
        "aggressive": "#F44336",
        "defensive": "#FF9800",
        "calm": "#4CAF50",
        "sarcastic": "#9C27B0",
        "emotional": "#E91E63",
        "factual": "#2196F3",
        "evasive": "#795548",
        "enthusiastic": "#00BCD4",
        "dismissive": "#FF5722",
        "uncertain": "#9E9E9E",
    }

    for p in content_parts:
        analyses = p["speaker_analyses"]
        if not analyses:
            continue
        mm_s = int(p["start_seconds"] // 60)
        ss_s = int(p["start_seconds"] % 60)
        mm_e = int(p["end_seconds"] // 60)
        ss_e = int(p["end_seconds"] % 60)
        header = f"**Part {p['idx']} — {p['type']}** ({mm_s:02d}:{ss_s:02d} – {mm_e:02d}:{ss_e:02d})"
        with st.expander(header, expanded=False):
            for sa in analyses:
                tone = sa.get("tone", "calm")
                tone_color = TONE_COLORS.get(tone, "#9E9E9E")
                hate_score = sa.get("hate_score", 0.0)
                hate_level = sa.get("hate_level_max", "none")
                stance = sa.get("stance_summary_he", "")
                topics_he = sa.get("topics_he", [])

                cols = st.columns([2, 1, 1, 3])
                with cols[0]:
                    st.markdown(f"**{sa['speaker_label']}**")
                with cols[1]:
                    st.markdown(
                        f"<span style='background:{tone_color};color:white;padding:2px 8px;"
                        f"border-radius:4px;font-size:0.8em'>{tone}</span>",
                        unsafe_allow_html=True,
                    )
                with cols[2]:
                    if hate_score > 0.1:
                        st.markdown(
                            f"<span style='color:#F44336;font-size:0.85em'>"
                            f"⚠ {hate_level} ({hate_score:.2f})</span>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            "<span style='color:#9E9E9E;font-size:0.85em'>✓ civil</span>",
                            unsafe_allow_html=True,
                        )
                with cols[3]:
                    if stance:
                        st.caption(stance)
                    if topics_he:
                        st.markdown(
                            " · ".join(
                                f"<span style='background:#E3F2FD;padding:1px 6px;"
                                f"border-radius:3px;font-size:0.8em'>{t}</span>"
                                for t in topics_he
                            ),
                            unsafe_allow_html=True,
                        )

    st.markdown("---")

# ── per-interview Q&A pairs ───────────────────────────────────────────────────
interview_parts = [p for p in parts if p["type"] == "interview" and p["qa_pairs"]]
if interview_parts:
    st.subheader("Interview Q&A Pairs")
    for p in interview_parts:
        mm_s = int(p["start_seconds"] // 60)
        ss_s = int(p["start_seconds"] % 60)
        guests = ", ".join(p["guest_labels"]) or "unknown guest"
        header = f"**Interview {p['idx']}** — {guests} ({mm_s:02d}:{ss_s:02d})"
        with st.expander(header, expanded=False):
            for i, qa in enumerate(p["qa_pairs"], 1):
                q_text = qa.get("question_text_he", "")
                a_text = qa.get("answer_text_he", "")
                topic = qa.get("topic_label_he", "")
                t_start = int(qa.get("start_seconds", 0))
                mm_q, ss_q = divmod(t_start, 60)
                st.markdown(
                    f"**Q{i}** <span style='color:#9E9E9E;font-size:0.8em'>"
                    f"{mm_q:02d}:{ss_q:02d}  ·  {topic}</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='background:#F5F5F5;padding:8px 12px;border-radius:4px;"
                    f"margin-bottom:4px;direction:rtl'>{q_text}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='background:#E8F5E9;padding:8px 12px;border-radius:4px;"
                    f"margin-bottom:12px;direction:rtl'>{a_text}</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")

# ── hate heatmap ─────────────────────────────────────────────────────────────
st.subheader("Speaker × Topic Hate-Proxy Heatmap")
df_hate, speakers, topic_labels = load_hate_heatmap(episode_id)

if df_hate.empty:
    st.info("No hate-speech incidents recorded for this episode.")
else:
    fig_hm = build_heatmap_figure(df_hate)
    st.plotly_chart(fig_hm, use_container_width=True)
    st.caption(
        "Cell value = max hate-level ordinal "
        "(none=0 … threat=5) across all incidents for that speaker/topic pair."
    )
