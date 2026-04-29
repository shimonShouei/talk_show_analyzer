"""Daily Overview page."""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from talk_show_analyzer.dashboard.utils import (
    get_stations,
    get_episodes,
    get_top_guests,
    get_topic_trends,
    get_sentiment_stats,
    get_segment_distribution,
)

st.title("📊 Daily Overview")
st.markdown("---")

col1, col2 = st.columns([1, 4])

with col1:
    stations = get_stations()
    station_names = [s["name"] for s in stations]
    selected_station = st.selectbox(
        "Station",
        options=station_names,
        index=0,
    )
    station_id = next(s["id"] for s in stations if s["name"] == selected_station)

with col2:
    days = st.slider("Days to analyze", 7, 90, 30)

st.markdown("---")

episodes = get_episodes(station_id=station_id, days=days)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Episodes", len(episodes))

with col2:
    completed = sum(1 for e in episodes if e["status"] == "analyzed")
    st.metric("Analyzed", completed)

with col3:
    total_hours = sum(
        float(e["duration"].split()[0]) / 60 for e in episodes
    )
    st.metric("Hours", f"{total_hours:.1f}h")

with col4:
    total_words = sum(e["word_count"] for e in episodes)
    st.metric("Words", f"{total_words:,}")

st.markdown("---")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📈 Segment Types")
    seg_dist = get_segment_distribution(station_id=station_id, days=days)
    if seg_dist:
        df = pd.DataFrame(
            list(seg_dist.items()),
            columns=["Type", "Count"]
        ).sort_values("Count", ascending=False)
        st.bar_chart(df.set_index("Type"))
    else:
        st.info("No data available")

with col2:
    st.subheader("💭 Sentiment Overview")
    sentiment_stats = get_sentiment_stats(station_id=station_id, days=days)
    if sentiment_stats["total"] > 0:
        col1a, col1b, col1c = st.columns(3)
        with col1a:
            st.metric("Average", f"{sentiment_stats['avg']:.2f}")
        with col1b:
            st.metric("Range", f"{sentiment_stats['min']:.1f} to {sentiment_stats['max']:.1f}")
        with col1c:
            st.metric("Results", sentiment_stats["total"])
    else:
        st.info("No sentiment data yet")

st.markdown("---")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("👥 Top Guests")
    guests = get_top_guests(station_id=station_id, days=days, limit=10)
    if guests:
        guest_df = pd.DataFrame(guests)
        guest_df = guest_df[["name", "title", "appearances"]].rename(
            columns={"name": "Guest", "title": "Title", "appearances": "Appearances"}
        )
        st.dataframe(guest_df, use_container_width=True, hide_index=True)
    else:
        st.info("No guest data yet")

with col2:
    st.subheader("🎯 Top Topics")
    topics = get_topic_trends(station_id=station_id, days=days)
    if topics:
        topic_df = pd.DataFrame(topics[:10])
        topic_df = topic_df[["topic", "category", "count", "avg_sentiment"]].rename(
            columns={
                "topic": "Topic",
                "category": "Category",
                "count": "Count",
                "avg_sentiment": "Sentiment",
            }
        )
        topic_df["Sentiment"] = topic_df["Sentiment"].round(2)
        st.dataframe(topic_df, use_container_width=True, hide_index=True)
    else:
        st.info("No topic data yet")

st.markdown("---")

st.subheader("📅 Recent Episodes")
if episodes:
    episodes_df = pd.DataFrame(episodes)
    episodes_df = episodes_df[["date", "duration", "word_count", "status"]].rename(
        columns={
            "date": "Date",
            "duration": "Duration",
            "word_count": "Words",
            "status": "Status",
        }
    )
    st.dataframe(episodes_df, use_container_width=True, hide_index=True)
else:
    st.info("No episodes found for this period")
