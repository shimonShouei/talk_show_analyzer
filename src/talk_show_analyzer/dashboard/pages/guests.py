"""Guest Leaderboard page."""

import streamlit as st
import pandas as pd
from talk_show_analyzer.dashboard.utils import (
    get_stations,
    get_top_guests,
)

st.title("👥 Guest Leaderboard")
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
    limit = st.number_input("Show top N guests", 5, 50, 20)

st.markdown("---")

guests = get_top_guests(station_id=station_id, days=days, limit=limit)

if guests:
    guests_df = pd.DataFrame(guests)

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader(f"Top {len(guests)} Guests")
        guests_df_display = guests_df[["name", "title", "appearances"]].rename(
            columns={
                "name": "Guest",
                "title": "Title",
                "appearances": "Appearances",
            }
        )
        st.dataframe(guests_df_display, use_container_width=True, hide_index=True)

    with col2:
        st.subheader("Statistics")
        col1a, col1b = st.columns(1)
        with col1a:
            st.metric("Total Guests", len(guests))
            st.metric(
                "Average Appearances",
                f"{guests_df['appearances'].mean():.1f}"
            )
            st.metric(
                "Max Appearances",
                guests_df['appearances'].max()
            )

    st.markdown("---")

    st.subheader("📊 Guest Appearance Distribution")
    st.bar_chart(
        guests_df.set_index("name")["appearances"].sort_values(ascending=False)
    )

    st.markdown("---")

    st.subheader("Guest Details")
    selected_guest = st.selectbox(
        "Select guest",
        options=range(len(guests)),
        format_func=lambda i: f"{guests[i]['name']} ({guests[i]['title']})",
    )

    if selected_guest is not None:
        guest = guests[selected_guest]
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Name", guest["name"])
            st.metric("Hebrew", guest["name_he"])

        with col2:
            st.metric("Title", guest["title"])

        with col3:
            st.metric("Total Appearances", guest["appearances"])

else:
    st.info("No guest data found")
