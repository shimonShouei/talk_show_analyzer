# Israeli Talk Show Analyzer Dashboard

A comprehensive Streamlit dashboard for analyzing and visualizing data from Israeli radio talk shows.

## Features

### 📊 Overview Page
- Quick metrics: Episodes, analyzed episodes, total hours, word count
- Segment type distribution
- Overall sentiment statistics
- Top guests by appearance frequency
- Trending topics
- Recent episodes list

### 📺 Episodes Page
- Filter episodes by station, status, and date range
- View detailed episode statistics:
  - Segment breakdown by type
  - Guest appearances count
  - Topic count
- Sort and search through episodes

### 👥 Guest Leaderboard
- Track guest appearances across all episodes
- Filter by station and date range
- View guest frequency distribution
- Display guest title and affiliation
- Guest statistics (total appearances, average, max)

### 🎯 Topics Page
- Identify trending topics over time
- Filter by station and date range
- View topic categories and counts
- Analyze average sentiment per topic
- Category distribution analysis
- Bilingual topic display (English + Hebrew)

### 💭 Sentiment Analysis
- Overall sentiment statistics (average, range, total results)
- Sentiment classification by emotional tone
- Tone distribution charts
- Average sentiment by tone
- Sentiment scale visualization

## Running the Dashboard

### Prerequisites

1. **Database**: PostgreSQL must be running with the talk_show_analyzer schema
2. **Environment**: Set up `.env` with `DATABASE_URL`
3. **Dependencies**: Install project with `pip install -e .`

### Start the Dashboard

```bash
# Option 1: Using the provided script
python run_dashboard.py

# Option 2: Direct streamlit command
streamlit run src/talk_show_analyzer/dashboard/app.py
```

The dashboard will open in your browser at `http://localhost:8501`

### Configuration

Edit `.streamlit/config.toml` to customize:
- Theme colors
- Font settings
- Logger level
- Browser settings

## Data Structure

The dashboard queries the following database tables:

### Core Tables
- **Episodes** — Recorded shows with transcription status
- **Stations** — Radio stations (Galatz, 103FM, Kan Reshet Bet)
- **Segments** — Content segments (interview, news, ads, etc.)
- **Topics** — Extracted topics with categories
- **Guests** — People appearing in shows
- **GuestAppearances** — Guest-segment relationships
- **SentimentResults** — Sentiment scores per speaker per topic
- **PipelineRuns** — Pipeline execution tracking

## Caching Strategy

The dashboard uses Streamlit's built-in caching to improve performance:

| Function | TTL | Purpose |
|----------|-----|---------|
| `get_stations()` | 1 hour | Rarely changes |
| `get_episodes()` | 5 minutes | Updates frequently |
| `get_episode_details()` | 10 minutes | Semi-stable data |
| `get_top_guests()` | 5 minutes | Updates frequently |
| `get_topic_trends()` | 5 minutes | Updates frequently |
| `get_sentiment_stats()` | 5 minutes | Updates frequently |
| `get_sentiment_by_tone()` | 5 minutes | Updates frequently |
| `get_segment_distribution()` | 5 minutes | Updates frequently |

### Clear Cache

To force refresh the dashboard data:
```python
# In the Streamlit sidebar (automatic "Clear cache" button)
# Or manually in code:
st.cache_data.clear()
```

## Navigation

The dashboard uses Streamlit's multi-page app system. Pages are automatically discovered from the `pages/` directory:

- `app.py` — Main landing page with overview
- `pages/overview.py` — Daily overview metrics
- `pages/episodes.py` — Episode list and filtering
- `pages/guests.py` — Guest leaderboard
- `pages/topics.py` — Topic trends
- `pages/sentiment.py` — Sentiment analysis

Switch between pages using the sidebar navigation.

## Performance Tips

1. **Use filters** — Narrow down date ranges and stations to reduce query time
2. **Check cache TTLs** — Adjust in `utils.py` if data updates very frequently
3. **Database indexes** — Ensure indexes exist on `recorded_at`, `station_id`, `type`, `category`

## Future Enhancements

- [ ] Political leaning analysis page
- [ ] Guest-to-guest co-occurrence network
- [ ] Word clouds for topics
- [ ] Time-series sentiment trends
- [ ] Export to CSV/PDF reports
- [ ] Real-time updates with websockets
- [ ] Advanced filtering with date pickers
- [ ] Guest comparison across shows
- [ ] Topic popularity trends
- [ ] Ad time analysis

## Troubleshooting

### Database Connection Issues
```bash
# Check DATABASE_URL in .env
export DATABASE_URL="postgresql://user:password@localhost:5432/talk_show"
# Then restart the dashboard
```

### Hebrew Text Not Displaying
- Ensure PostgreSQL is using UTF-8 encoding
- Check Streamlit font settings in `.streamlit/config.toml`

### Slow Performance
- Check database connection pool settings in `db.py`
- Reduce date range in filters
- Clear cache: `streamlit run app.py --logger.level=debug`

### No Data Showing
- Verify pipeline has run and populated the database
- Check episode status: `SELECT COUNT(*) FROM episodes WHERE status='analyzed';`
- Run a test analysis: `python test_full_pipeline.py`
