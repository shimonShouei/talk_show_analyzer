"""Episodes page with detailed filtering."""

import streamlit as st
import pandas as pd
from talk_show_analyzer.dashboard.utils import (
    get_stations,
    get_episodes,
    get_episode_details,
)

st.title("📺 Episodes")
st.markdown("---")

col1, col2, col3 = st.columns(3)

stations = get_stations()
station_names = ["All"] + [s["name"] for s in stations]

with col1:
    selected_station = st.selectbox("Station", options=station_names)
    station_id = (
        next((s["id"] for s in stations if s["name"] == selected_station), None)
        if selected_station != "All"
        else None
    )

with col2:
    status_filter = st.selectbox(
        "Status",
        ["All", "pending", "analyzed", "failed"],
    )
    status = status_filter if status_filter != "All" else None

with col3:
    days = st.slider("Days to show", 7, 365, 30)

st.markdown("---")

episodes = get_episodes(station_id=station_id, status=status, days=days)

if episodes:
    episodes_df = pd.DataFrame(episodes)
    st.subheader(f"Found {len(episodes)} episodes")
    st.dataframe(episodes_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("📊 Episode Details")

    selected_episode = st.selectbox(
        "Select episode to view details",
        range(len(episodes)),
        format_func=lambda i: f"{episodes[i]['date']} - {episodes[i]['station']}",
    )

    if selected_episode is not None:
        episode_id = episodes[selected_episode]["id"]
        details = get_episode_details(episode_id)

        if details:
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Station", details.get("station", "N/A"))
                st.metric("Duration", f"{details.get('duration', 0) / 60:.1f} min")

            with col2:
                st.metric("Status", details.get("status", "N/A"))
                st.metric("Words", f"{details.get('word_count', 0):,}")

            with col3:
                st.metric("Segments", details.get("segment_count", 0))
                st.metric("Topics", details.get("topic_count", 0))

            st.markdown("---")

            col1, col2 = st.columns([1, 1])

            with col1:
                st.subheader("Segment Types")
                seg_types = details.get("segment_types", {})
                if seg_types:
                    seg_df = pd.DataFrame(
                        list(seg_types.items()),
                        columns=["Type", "Count"]
                    ).sort_values("Count", ascending=False)
                    st.bar_chart(seg_df.set_index("Type"))

            with col2:
                st.subheader("Guests")
                st.metric("Guest Appearances", details.get("guest_count", 0))
else:
    st.info("No episodes found for the selected filters")
