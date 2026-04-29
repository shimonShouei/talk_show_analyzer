# Download Missed Shows Guide

If a recording fails or a SLURM job doesn't run, use this guide to fetch the episode after the fact.

## Quick Start

### Option 1: Download from Station Website (Recommended)

1. **Find the episode** on the station's website:
   - **Kan Reshet Bet**: https://www.kan.org.il/
   - **103FM**: https://103fm.maariv.co.il/
   - **Galatz**: https://www.glz.co.il/

2. **Copy the episode URL** and run:

```bash
python download_show.py --url "https://www.kan.org.il/Episode/12345"

# Output: data/archive_www.kan.org.il_2026-04-29T14-30-00.mp3
```

3. **Analyze the downloaded file**:

```bash
# Verify it downloaded correctly
ffprobe data/archive_*.mp3

# Run analysis pipeline
python test_full_pipeline.py
```

### Option 2: DVR Rewind (HLS Streams Only)

For Kan Bet or 103FM, try to rewind the live stream if it's within the CDN's buffer window (usually 1-4 hours):

```bash
# Rewind 120 minutes (2 hours) from now, record 4 hours
python download_show.py --station kan_bet --rewind 120 --duration 14400

# Output: data/kan_bet_dvr_2026-04-29T14-30-00.mp3
```

**Note**: This only works if the CDN supports DVR. If it fails, use Option 1 instead.

## Complete Commands Reference

### Download from URL
```bash
# Basic usage
python download_show.py --url "https://www.kan.org.il/Episode/..."

# Specify output directory
python download_show.py --url "https://..." --output ~/downloads/

# Download multiple episodes
for url in "url1" "url2" "url3"; do
  python download_show.py --url "$url"
done
```

**URL examples:**
- Kan: `https://www.kan.org.il/Episode/123456`
- 103FM: `https://103fm.maariv.co.il/episode/123456`
- Galatz: `https://www.glz.co.il/podcast/episode/123456`

### DVR Rewind (Kan Bet / 103FM only)
```bash
# Rewind 1 hour, record 4 hours
python download_show.py --station kan_bet --rewind 60 --duration 14400

# Rewind 3 hours, record 1 hour
python download_show.py --station 103fm --rewind 180 --duration 3600

# Note: Galatz doesn't support HLS DVR rewind
python download_show.py --station galatz --rewind 120 --duration 14400
# → ERROR: Galatz does not use HLS (DVR not supported)
# → Use --url option instead
```

## Workflow Examples

### Scenario 1: Recording Failed, Need to Fetch Episode

```bash
# 1. Go to station website and find the episode
# 2. Copy the URL
# 3. Download it
python download_show.py --url "https://www.kan.org.il/Episode/9999"
# → data/archive_www.kan.org.il_2026-04-29T15-00-00.mp3

# 4. Analyze it
python test_full_pipeline.py
# Pipeline will find the MP3 and process it
```

### Scenario 2: Job Completed But Doesn't Include Latest Show

```bash
# 1. Check what the SLURM job recorded
ls -la data/

# 2. If the latest show is missing, fetch from archive
python download_show.py --url "https://103fm.maariv.co.il/episode/2026-04-29-morning"

# 3. Run analysis on the new file
python test_full_pipeline.py

# 4. Verify in database
psql $DATABASE_URL -c "SELECT COUNT(*) FROM episodes;"
```

### Scenario 3: Multiple Episodes Missed

```bash
#!/bin/bash
# Download multiple episodes at once

URLS=(
  "https://www.kan.org.il/Episode/123"
  "https://www.kan.org.il/Episode/124"
  "https://www.kan.org.il/Episode/125"
)

for url in "${URLS[@]}"; do
  python download_show.py --url "$url"
done

# Analyze all downloaded files
python test_full_pipeline.py
```

## File Output

Downloaded files are saved to `data/` directory by default:

```
data/
├── archive_www.kan.org.il_2026-04-29T14-30-00.mp3
├── archive_103fm.maariv.co.il_2026-04-29T15-00-00.mp3
├── galatz_dvr_2026-04-29T14-25-00.mp3
└── ... (other recordings)
```

**Filename format:**
- From URL: `archive_<domain>_<timestamp>.mp3`
- From DVR: `<station>_dvr_<timestamp>.mp3`

## Troubleshooting

### "yt-dlp not found"
```bash
pip install yt-dlp

# Or with conda
conda install -c conda-forge yt-dlp
```

### Download fails with "Access Denied"
- Station website may have geo-blocking or require authentication
- Try accessing the URL in a browser to verify it's public
- Some episodes may require a subscription

### DVR rewind fails (404 or no audio)
- CDN may not support time-shifting
- Check if more than 4 hours have passed (DVR buffer is limited)
- Use URL download from website instead

### Downloaded file has no audio
```bash
# Check file
ffprobe archive_*.mp3

# Try different station website
# Some stations may have better archive quality
```

## How It Works

### URL Download (yt-dlp)
1. Takes episode URL from station website
2. Uses `yt-dlp` to extract audio stream
3. Converts to MP3 (128k, 16kHz mono) — same format as live recordings
4. Saves to `data/` directory
5. Ready for pipeline analysis

### DVR Rewind (HLS only)
1. Attempts to rewind HLS playlist URL
2. Appends DVR offset (`?start_offset=-Nseconds`)
3. Records from the rewind position using ffmpeg
4. Works only if CDN supports time-shifting (usually 1-4 hour window)
5. Gracefully fails if DVR not supported

## Integration with Pipeline

The pipeline automatically detects MP3 files in `data/`:

```bash
# Download episode
python download_show.py --url "https://..."

# Run analysis (will find the new file)
python test_full_pipeline.py

# File is transcribed, analyzed, and stored in database
# Then visible in dashboard
```

No need to manually move files or update database — the pipeline handles everything.

## Best Practices

1. **Verify before analyzing** — Check file size and duration
   ```bash
   ffprobe data/archive_*.mp3 | grep Duration
   ```

2. **Save important episodes** — Copy to external backup
   ```bash
   cp data/archive_*.mp3 /mnt/backup/
   ```

3. **Update dashboard** — After analyzing, view results
   ```bash
   python run_dashboard.py
   # http://localhost:8501 → Overview page
   ```

4. **Check for duplicates** — Don't process the same episode twice
   ```bash
   # List all analyzed episodes
   psql $DATABASE_URL -c "SELECT id, recorded_at FROM episodes ORDER BY recorded_at DESC LIMIT 10;"
   ```

## Summary

| Task | Command |
|------|---------|
| Download from website | `python download_show.py --url "..."` |
| DVR rewind (Kan/103) | `python download_show.py --station kan_bet --rewind 120` |
| Verify download | `ffprobe data/archive_*.mp3` |
| Analyze | `python test_full_pipeline.py` |
| View results | `python run_dashboard.py` |

**Key point**: If a show isn't recorded, download it from the station's website and let the pipeline process it normally. Everything else works the same!
