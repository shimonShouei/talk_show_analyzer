"""Sentiment Analysis page."""

import streamlit as st
import pandas as pd
from talk_show_analyzer.dashboard.utils import (
    get_stations,
    get_sentiment_stats,
    get_sentiment_by_tone,
)

st.title("💭 Sentiment Analysis")
st.markdown("---")

col1, col2 = st.columns(2)

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

st.markdown("---")

sentiment_stats = get_sentiment_stats(station_id=station_id, days=days)

if sentiment_stats["total"] > 0:
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Results", sentiment_stats["total"])

    with col2:
        st.metric(
            "Average Sentiment",
            f"{sentiment_stats['avg']:.2f}",
            delta=f"Range: {sentiment_stats['min']:.1f} to {sentiment_stats['max']:.1f}"
        )

    with col3:
        if sentiment_stats["avg"] > 0.2:
            sentiment_label = "📈 Positive"
        elif sentiment_stats["avg"] < -0.2:
            sentiment_label = "📉 Negative"
        else:
            sentiment_label = "➡️ Neutral"
        st.metric("Overall", sentiment_label)

    with col4:
        st.metric(
            "Sentiment Range",
            f"{sentiment_stats['max'] - sentiment_stats['min']:.2f}"
        )

    st.markdown("---")

    sentiment_by_tone = get_sentiment_by_tone(station_id=station_id, days=days)

    if sentiment_by_tone:
        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("📊 Results by Tone")
            tone_df = pd.DataFrame(sentiment_by_tone)
            tone_df_display = tone_df[["tone", "count", "avg_score"]].rename(
                columns={
                    "tone": "Tone",
                    "count": "Count",
                    "avg_score": "Avg Score",
                }
            )
            tone_df_display["Avg Score"] = tone_df_display["Avg Score"].round(2)
            st.dataframe(tone_df_display, use_container_width=True, hide_index=True)

        with col2:
            st.subheader("Distribution by Tone")
            st.bar_chart(
                tone_df.set_index("tone")["count"].sort_values(ascending=False)
            )

        st.markdown("---")

        st.subheader("Average Score by Tone")
        score_data = tone_df[["tone", "avg_score"]].set_index("tone").sort_values("avg_score")
        st.bar_chart(score_data)

        st.markdown("---")

        st.subheader("Tone Breakdown")
        for _, row in tone_df.iterrows():
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**{row['tone'].upper()}**")
            with col2:
                st.metric("Count", row["count"])
            with col3:
                st.metric("Avg", f"{row['avg_score']:.2f}")

    else:
        st.info("No sentiment by tone data found")

else:
    st.info("No sentiment data found for the selected period")

st.markdown("---")

st.subheader("📈 Sentiment Scale")
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.write("😠")
    st.caption("Very Negative\n-1.0")

with col2:
    st.write("😔")
    st.caption("Negative\n-0.5")

with col3:
    st.write("😐")
    st.caption("Neutral\n0.0")

with col4:
    st.write("🙂")
    st.caption("Positive\n+0.5")

with col5:
    st.write("😄")
    st.caption("Very Positive\n+1.0")
