"""Main Streamlit dashboard app for Israeli Talk Show Analyzer."""

import streamlit as st

st.set_page_config(
    page_title="Talk Show Analyzer",
    page_icon="📻",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    [data-testid="baseButton-primary"] {
        background-color: #1f77b4;
    }
    .metric-card {
        padding: 20px;
        border-radius: 10px;
        background-color: #f0f2f6;
    }
</style>
""", unsafe_allow_html=True)

st.title("📻 Israeli Talk Show Analyzer")
st.markdown("---")

st.info(
    """
    **Israeli Talk Show Analyzer** — Daily automated recording, transcription, and analysis
    of Israeli radio talk shows from Galatz, 103FM, and Kan Reshet Bet.

    Use the sidebar to navigate between different analysis views.
    """
)

st.markdown("""
## 📊 Dashboard Overview

### Available Pages

- **📊 Overview** — Daily summary with key metrics, top speakers, trending topics
- **📺 Episodes** — View all recorded episodes with detailed filtering and statistics
- **💬 Conversation** — Read the identified transcript: Name1: "..." Name2: "..."
- **👥 Speaker Leaderboard** — Track speaker appearances and frequency
- **🎯 Topics** — Analyze trending topics and their sentiment over time
- **💭 Sentiment** — Detailed sentiment analysis by speaker and tone

### Key Features

✅ **Multi-station analysis** — Compare Galatz, 103FM, and Kan Reshet Bet
✅ **Time-based filtering** — Analyze trends over different periods
✅ **Guest tracking** — See who appears most frequently
✅ **Topic trending** — Identify what's being discussed
✅ **Sentiment tracking** — Monitor emotional tone and sentiment patterns
✅ **Hebrew support** — Full support for Hebrew names and topics

### Data Sources

The dashboard pulls data from:
- Transcribed audio with speaker identification
- Automated segment classification (interview, news, ads, etc.)
- Guest identification and appearance tracking
- Topic extraction and categorization
- Sentiment analysis per speaker per topic

---

### 📈 Key Metrics

| Metric | Description |
|--------|-------------|
| **Episodes** | Number of recorded shows analyzed |
| **Guests** | Unique people appearing in shows |
| **Topics** | Distinct topics discussed |
| **Segments** | Content segments identified |
| **Sentiment** | Overall emotional tone (-1.0 to +1.0) |

Start exploring by selecting a page from the sidebar!
""")
