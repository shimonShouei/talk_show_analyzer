"""Conversation page — identified transcript view per episode."""

import streamlit as st
from talk_show_analyzer.dashboard.utils import get_stations, get_episodes, get_episode_conversation

# Colour palette for up to 8 distinct speakers
_SPEAKER_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
]

_SEGMENT_ICONS = {
    "interview": "🎙️",
    "panel": "👥",
    "news": "📰",
    "ad": "📣",
    "jingle": "🎵",
    "music": "🎶",
    "caller": "📞",
    "weather": "⛅",
    "commentary": "💬",
    "unknown": "❓",
}

st.title("💬 Conversation View")
st.markdown("Select an episode to see the transcript with identified speaker names.")
st.markdown("---")

# --- Filters ---
col1, col2, col3 = st.columns(3)

stations = get_stations()
station_names = ["All"] + [s["name"] for s in stations]

with col1:
    selected_station = st.selectbox("Station", options=station_names, key="conv_station")
    station_id = (
        next((s["id"] for s in stations if s["name"] == selected_station), None)
        if selected_station != "All"
        else None
    )

with col2:
    days = st.slider("Days to show", 7, 365, 30, key="conv_days")

with col3:
    hide_ads = st.checkbox("Hide ads / jingles / music", value=True)

episodes = get_episodes(station_id=station_id, status="analyzed", days=days)

if not episodes:
    st.info("No analyzed episodes found for the selected filters.")
    st.stop()

selected_idx = st.selectbox(
    "Episode",
    range(len(episodes)),
    format_func=lambda i: f"{episodes[i]['date']} — {episodes[i]['station']}",
    key="conv_episode",
)

episode_id = episodes[selected_idx]["id"]
data = get_episode_conversation(episode_id)

if not data["episode"]:
    st.error("Could not load episode.")
    st.stop()

ep = data["episode"]
st.markdown(f"**{ep['station']}** · {ep['date']} · {ep['duration'] / 60:.0f} min")
st.markdown("---")

# --- Speaker legend ---
speakers = data["speakers"]
if speakers:
    labels = sorted(speakers.keys())
    color_map = {label: _SPEAKER_COLORS[i % len(_SPEAKER_COLORS)] for i, label in enumerate(labels)}

    st.subheader("🎤 Identified Speakers")
    legend_cols = st.columns(min(len(labels), 4))
    for i, label in enumerate(labels):
        info = speakers[label]
        color = color_map[label]
        with legend_cols[i % len(legend_cols)]:
            st.markdown(
                f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;">'
                f'<b>{info["name"]}</b></span> <small>({info["role"]})</small>',
                unsafe_allow_html=True,
            )
    st.markdown("---")
else:
    color_map = {}
    st.info("No speakers were identified for this episode. Run the pipeline with the updated code to populate speaker identities.")

# --- Transcript timeline ---
st.subheader("📜 Transcript")

non_content_types = {"ad", "jingle", "music"}

for line in data["lines"]:
    seg_type = line["type"]
    if hide_ads and seg_type in non_content_types:
        continue

    icon = _SEGMENT_ICONS.get(seg_type, "❓")
    start_min = line["start"] / 60
    end_min = line["end"] / 60

    with st.expander(
        f"{icon} [{start_min:.1f}–{end_min:.1f} min] **{seg_type.upper()}** — {line['summary'][:80]}",
        expanded=(seg_type not in non_content_types),
    ):
        if line["speakers"]:
            speaker_tags = []
            for sp in line["speakers"]:
                color = color_map.get(sp["label"], "#888")
                name = sp["name"]
                speaker_tags.append(
                    f'<span style="background:{color};color:white;padding:1px 6px;'
                    f'border-radius:3px;font-size:0.85em;">{name}</span>'
                )
            st.markdown("**Speakers:** " + " ".join(speaker_tags), unsafe_allow_html=True)

        st.markdown(f"_{line['summary']}_")
