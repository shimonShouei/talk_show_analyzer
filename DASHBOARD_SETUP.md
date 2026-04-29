# Dashboard Setup & Running Guide

## Quick Start

### 1. Install Dependencies

The dashboard requires Streamlit and other dependencies. Install them using:

```bash
# Using conda (recommended, see CLAUDE.md)
conda activate talk_show
pip install -e . --no-cache-dir

# Or with pip directly
pip install streamlit plotly pandas sqlalchemy
```

### 2. Set Up Database

Ensure PostgreSQL is running and your `.env` file has the correct `DATABASE_URL`:

```bash
cp .env.example .env
# Edit .env with your database URL
export $(cat .env | xargs)
```

### 3. Run the Dashboard

```bash
# Option 1: Using the provided script
python run_dashboard.py

# Option 2: Direct Streamlit command
streamlit run src/talk_show_analyzer/dashboard/app.py

# Option 3: With debug logging
streamlit run src/talk_show_analyzer/dashboard/app.py --logger.level=debug
```

The dashboard will open at `http://localhost:8501`

## Dashboard Structure

```
src/talk_show_analyzer/dashboard/
├── app.py                 # Main page (home/overview)
├── pages/
│   ├── overview.py       # Daily metrics & summary
│   ├── episodes.py       # Episode list with filtering
│   ├── guests.py         # Guest leaderboard
│   ├── topics.py         # Topic trends & analysis
│   └── sentiment.py      # Sentiment analysis
├── utils.py              # Database query utilities
└── README.md             # Full documentation
```

## Pages Overview

### 🏠 Home (app.py)
- Project overview
- Links to all analysis pages
- Feature summary

### 📊 Overview
- Episode count, analyzed count, total hours
- Segment type distribution
- Overall sentiment statistics
- Top guests and trending topics
- Recent episodes list

**Filters**: Station, Date range (7-90 days)

### 📺 Episodes
- View all episodes with detailed information
- Filter by: Station, Status (all/pending/analyzed/failed), Date range
- Per-episode breakdown:
  - Segment types and counts
  - Guest appearances
  - Topics extracted

**Features**: Sortable table, episode detail view

### 👥 Guest Leaderboard
- Top guests by appearance count
- Guest information: name (English + Hebrew), title, affiliation
- Guest statistics: total appearances, average, max
- Appearance frequency visualization

**Filters**: Station, Date range (7-365 days), Top N guests

### 🎯 Topics
- Trending topics with frequency counts
- Category distribution (politics, security, economy, etc.)
- Average sentiment per topic
- Bilingual display (English + Hebrew)

**Filters**: Station, Date range, Topic limit

### 💭 Sentiment
- Overall sentiment statistics (average, range, count)
- Results grouped by emotional tone
- Tone distribution charts
- Average score per tone

**Sentiment Scale**: -1.0 (very negative) to +1.0 (very positive)

**Tones**: angry, calm, enthusiastic, dismissive, neutral, etc.

## Configuration

### Streamlit Settings (.streamlit/config.toml)

```toml
[theme]
primaryColor = "#1f77b4"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#31333F"
font = "sans serif"

[client]
showErrorDetails = true
showWarningOnDirectExecution = false

[browser]
gatherUsageStats = false

[logger]
level = "info"
```

### Cache Settings (utils.py)

Adjust TTLs (time-to-live) for different data freshness needs:

```python
@st.cache_data(ttl=300)  # 5 minutes
def get_episodes(...):
    ...
```

**Current TTLs**:
- `get_stations()` — 1 hour (rarely changes)
- `get_episodes()` — 5 minutes
- `get_episode_details()` — 10 minutes
- `get_top_guests()` — 5 minutes
- `get_topic_trends()` — 5 minutes
- `get_sentiment_stats()` — 5 minutes

## Performance Tips

1. **Narrow filters** — Reduce date range to improve query speed
2. **Station-specific** — Filtering by station reduces data volume
3. **Clear cache** — If data seems stale, use Streamlit's cache clear button
4. **Database indexes** — Ensure these indexes exist:
   ```sql
   CREATE INDEX idx_episode_recorded ON episodes(recorded_at);
   CREATE INDEX idx_segment_type ON segments(type);
   CREATE INDEX idx_topic_category ON topics(category);
   ```

## Troubleshooting

### "No module named 'streamlit'"
```bash
pip install streamlit
# Or with conda:
conda install streamlit
```

### "Database connection failed"
```bash
# Check DATABASE_URL
echo $DATABASE_URL

# Verify PostgreSQL is running
psql $DATABASE_URL -c "SELECT 1"

# Update .env if needed
export DATABASE_URL="postgresql://user:pass@localhost:5432/talk_show"
```

### "No data found"
Ensure:
1. The pipeline has run (`python test_full_pipeline.py`)
2. Episodes have been analyzed (check `episodes.status = 'analyzed'`)
3. Database has data:
   ```bash
   psql $DATABASE_URL
   # In psql:
   SELECT COUNT(*) FROM episodes;
   SELECT COUNT(*) FROM guests;
   ```

### "Hebrew text not displaying"
- Ensure PostgreSQL uses UTF-8 encoding
- Check terminal supports UTF-8
- Verify Streamlit font settings

### Slow performance
- Check network/database latency
- Reduce date range in filters
- Increase cache TTLs
- Check database query plans:
  ```sql
  EXPLAIN ANALYZE
  SELECT * FROM episodes
  WHERE recorded_at > NOW() - INTERVAL '30 days'
  LIMIT 100;
  ```

## Testing

Run the dashboard validation test:

```bash
python test_dashboard.py
```

This checks:
✓ All modules import correctly
✓ Database connection works
✓ Query functions execute
✓ All page files exist

## Next Steps

### Enhancements to Consider

1. **Political Leaning** — Add political analysis page (needs political.py implementation)
2. **Guest Network** — Show co-guest relationships
3. **Word Clouds** — Visualize topic keywords
4. **Time Series** — Sentiment trends over time
5. **Export** — CSV/PDF report generation
6. **Real-time Updates** — WebSocket updates
7. **Advanced Filters** — Date pickers, multi-select
8. **Alerts** — Notify on specific topics or guests

### For Development

```bash
# Run with debug logging
streamlit run src/talk_show_analyzer/dashboard/app.py --logger.level=debug

# Run with code reloading
streamlit run src/talk_show_analyzer/dashboard/app.py --client.runOnSave=true

# Run on specific host/port
streamlit run src/talk_show_analyzer/dashboard/app.py --server.port=8502 --server.address=0.0.0.0
```

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -e .

EXPOSE 8501

CMD ["streamlit", "run", "src/talk_show_analyzer/dashboard/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]
```

### Cloud (AWS, GCP, Azure)

Use managed container services:
- **AWS ECS/App Runner**
- **GCP Cloud Run**
- **Azure Container Instances**
- **Heroku** (free tier deprecated)

Ensure DATABASE_URL is set as environment variable.

## Support

- **Issues**: Check this guide and the dashboard README
- **Logs**: Check `~/.streamlit/logs/`
- **Database**: Use PostgreSQL admin tools
- **Code**: See `dashboard/README.md` for architecture details
