"""Topic Trends page."""

import streamlit as st
import pandas as pd
from talk_show_analyzer.dashboard.utils import (
    get_stations,
    get_topic_trends,
)

st.title("🎯 Topic Trends")
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
    days = st.slider("Days", 7, 365, 30)

with col3:
    limit = st.number_input("Show top N topics", 5, 50, 20)

st.markdown("---")

topics = get_topic_trends(station_id=station_id, days=days)

if topics:
    topics = topics[:limit]
    topics_df = pd.DataFrame(topics)

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader(f"Top {len(topics)} Topics")
        topics_df_display = topics_df[["topic", "category", "count", "avg_sentiment"]].rename(
            columns={
                "topic": "Topic",
                "category": "Category",
                "count": "Mentions",
                "avg_sentiment": "Avg Sentiment",
            }
        )
        topics_df_display["Avg Sentiment"] = topics_df_display["Avg Sentiment"].round(2)
        st.dataframe(topics_df_display, use_container_width=True, hide_index=True)

    with col2:
        st.subheader("Statistics")
        st.metric("Total Topics", len(topics))
        st.metric(
            "Average Mentions",
            f"{topics_df['count'].mean():.1f}"
        )
        st.metric(
            "Avg Sentiment",
            f"{topics_df['avg_sentiment'].mean():.2f}"
        )

    st.markdown("---")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📊 Topic Frequency")
        freq_data = topics_df[["topic", "count"]].set_index("topic").sort_values("count", ascending=False)
        st.bar_chart(freq_data)

    with col2:
        st.subheader("💭 Average Sentiment by Topic")
        sentiment_data = topics_df[["topic", "avg_sentiment"]].set_index("topic").sort_values("avg_sentiment")
        st.bar_chart(sentiment_data)

    st.markdown("---")

    st.subheader("📋 Category Distribution")
    category_counts = topics_df["category"].value_counts()
    col1, col2 = st.columns([1, 2])

    with col1:
        st.metric("Categories", len(category_counts))
        for cat, count in category_counts.items():
            st.write(f"• {cat}: {count}")

    with col2:
        st.bar_chart(category_counts)

    st.markdown("---")

    st.subheader("Topic Details")
    selected_topic_idx = st.selectbox(
        "Select topic",
        options=range(len(topics)),
        format_func=lambda i: f"{topics[i]['topic']} ({topics[i]['count']} mentions)",
    )

    if selected_topic_idx is not None:
        topic = topics[selected_topic_idx]
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Topic", topic["topic"])
            st.metric("Hebrew", topic["topic_he"])

        with col2:
            st.metric("Category", topic["category"])

        with col3:
            st.metric("Mentions", topic["count"])
            st.metric("Avg Sentiment", f"{topic['avg_sentiment']:.2f}")

else:
    st.info("No topic data found")
