# Backup and Recovery Guide

Complete guide for downloading shows, backing up data, and recovering from failures.

## Overview

The backup and recovery system provides:
- ✅ **Automatic episode backups** — Audio + transcripts + metadata
- ✅ **Failed episode recovery** — Retry analysis from checkpoints
- ✅ **Storage management** — Clean up old backups automatically
- ✅ **Easy CLI commands** — Simple commands for all operations

## Quick Start

### Backup an Episode
```bash
python manage_backups.py backup <episode_id>
```

### View All Backups
```bash
python manage_backups.py list
```

### Restore from Backup
```bash
python manage_backups.py restore <episode_id>
```

### Check Failed Episodes
```bash
python manage_backups.py failed
```

### Recover a Failed Episode
```bash
python manage_backups.py recovery <episode_id>
```

## Commands Reference

### backup
**Backup an episode's audio and transcript**

```bash
python manage_backups.py backup 1
```

Saves:
- Audio file (MP3)
- Transcript (JSON with speaker labels)
- Metadata (episode info, backup timestamp)

Location: `backups/episode_<id>_<timestamp>/`

### list
**Show all available backups**

```bash
python manage_backups.py list
```

Output:
```
1. Episode 1 (GALATZ)
   Recorded: 2026-04-29T14:30:00
   Backed up: 2026-04-29T14:45:00
   Duration: 300.0s
   Files: audio, transcript

2. Episode 2 (103FM)
   ...
```

### restore
**Restore an episode from backup**

```bash
python manage_backups.py restore 1
```

Restores files to `data/` directory:
- `data/galatz_*.mp3` (audio)
- `data/galatz_*_transcript.json` (transcript)

### recovery
**Backup + attempt to recover a failed episode**

```bash
python manage_backups.py recovery 1
```

Does:
1. Backs up current state
2. Attempts to resume analysis from last checkpoint
3. Reports success/failure

Use when:
- Pipeline crashed mid-analysis
- Want to save current state before retrying
- Need to recover without re-recording

### failed
**List all failed episodes**

```bash
python manage_backups.py failed
```

Shows:
- Episode ID and station
- Current status (failed, analyzing)
- When it was recorded

Next steps suggestions:
```
Recovery options:
  1. python manage_backups.py recovery <episode_id>
  2. Check logs for root cause
  3. Fix issue, then retry
```

### stats
**Show backup storage statistics**

```bash
python manage_backups.py stats
```

Output:
```
Total backups: 10
Total files: 30
Storage used: 1250.5 MB
Location: /path/to/backups/
```

Warns if storage exceeds 1GB.

### cleanup
**Delete old backups**

```bash
# Delete backups older than 30 days (default)
python manage_backups.py cleanup

# Delete backups older than 7 days
python manage_backups.py cleanup 7
```

Output:
```
Deleted: 5 backups
Freed: 450.2 MB
```

## Recovery Scenarios

### Scenario 1: Pipeline Crashed During Analysis

**Problem:** Job failed at step 5 (sentiment analysis)

**Solution:**
```bash
# 1. Check failed episodes
python manage_backups.py failed

# 2. Recover from checkpoint
python manage_backups.py recovery 1

# 3. Monitor logs
tail -f slurm_logs/job_*.out
```

The pipeline will:
1. Resume from the last completed step
2. Skip steps 1-4 (already done)
3. Retry step 5 and continue

### Scenario 2: Network/API Error During Recording

**Problem:** Recording failed mid-stream, partial MP3 saved

**Solution:**
```bash
# 1. Backup partial file
python manage_backups.py backup 1

# 2. Re-record (will overwrite)
python test_e2e.py

# 3. Analyze as normal
```

### Scenario 3: Database Connection Lost

**Problem:** Analysis completed but couldn't save to database

**Solution:**
```bash
# 1. Restore from backup
python manage_backups.py restore 1

# 2. Verify database is running
psql $DATABASE_URL -c "SELECT 1;"

# 3. Re-run analysis from transcript
python manage_backups.py recovery 1
```

### Scenario 4: Need to Download All Shows

**Problem:** Want to download all episodes for offline analysis

**Solution:**
```bash
# 1. List all backups
python manage_backups.py list

# 2. Backup all episodes (batch)
for episode_id in $(seq 1 100); do
    python manage_backups.py backup $episode_id 2>/dev/null
done

# 3. Copy to external drive
cp -r backups/ /mnt/external_drive/
```

## Backup Structure

```
backups/
├── episode_1_2026-04-29T14:45:00
│   ├── galatz_2026-04-29T14:30:00.mp3       (audio file)
│   ├── galatz_2026-04-29T14:30:00_transcript.json
│   └── backup_info.json                      (metadata)
├── episode_2_2026-04-29T14:50:00
│   ├── 103fm_2026-04-29T14:35:00.mp3
│   ├── 103fm_2026-04-29T14:35:00_transcript.json
│   └── backup_info.json
└── episode_3_2026-04-29T15:05:00
    └── ...
```

**backup_info.json contents:**
```json
{
  "episode_id": 1,
  "station": "galatz",
  "recorded_at": "2026-04-29T14:30:00",
  "duration": 300.0,
  "backup_time": "2026-04-29T14:45:00",
  "files": {
    "audio": "backups/episode_1_2026-04-29T14:45:00/galatz_2026-04-29T14:30:00.mp3",
    "transcript": "backups/episode_1_2026-04-29T14:45:00/galatz_2026-04-29T14:30:00_transcript.json"
  }
}
```

## Integrating with Pipeline

The orchestrator can automatically backup episodes on failure:

```python
from talk_show_analyzer.pipeline import PipelineOrchestrator
from talk_show_analyzer.backup import BackupManager

orchestrator = PipelineOrchestrator()
backup_mgr = BackupManager()

try:
    episode = orchestrator.run("galatz", duration_seconds=300)
except Exception as e:
    # Automatically backup on failure
    backup_mgr.backup_episode(episode.id)
    raise
```

Or add to the orchestrator:

```python
# In pipeline/orchestrator.py
except Exception as e:
    from talk_show_analyzer.backup import BackupManager
    BackupManager().backup_episode(episode_id)
    logger.error(f"Pipeline failed: {e}")
    raise
```

## Storage Management

### Monitor Backup Size
```bash
du -sh backups/
```

### Estimate Storage Needed
- Per episode: ~150-300 MB (audio + transcript)
- Per station per day: ~7-14 GB (48 episodes)
- Per month: ~200-400 GB

### Automatic Cleanup Strategy

**Option 1: Monthly cleanup**
```bash
# Run once a month, keep 30 days
python manage_backups.py cleanup 30
```

**Option 2: Scheduled cleanup (cron)**
```bash
# Add to crontab (runs on 1st of month at 2am)
0 2 1 * * cd /home/shouei/talk_show_analyzer && python manage_backups.py cleanup 30
```

**Option 3: Keep only recent backups**
```bash
# Keep only last 7 days
python manage_backups.py cleanup 7
```

## Best Practices

1. **Backup before major changes**
   ```bash
   python manage_backups.py backup 1
   ```

2. **Regular cleanup to save storage**
   ```bash
   # Weekly
   python manage_backups.py cleanup 14
   ```

3. **Monitor storage usage**
   ```bash
   python manage_backups.py stats
   ```

4. **External backup for important episodes**
   ```bash
   # Copy critical backups to external storage
   cp -r backups/episode_1_* /mnt/external/
   ```

5. **Verify restoration works**
   ```bash
   # Test restore before deleting original
   python manage_backups.py restore 1
   ls -lah data/
   ```

## Troubleshooting

### "No backup found for episode X"
- Backup hasn't been created yet
- Solution: `python manage_backups.py backup X`

### "Restore failed: Permission denied"
- Backup directory not writable
- Solution: `chmod -R u+w backups/`

### "Recovery failed: Database connection"
- PostgreSQL not running
- Solution: Verify database is running, check `$DATABASE_URL`

### "Cleanup found no old backups"
- All backups are newer than specified days
- Solution: Use smaller `days` value

## Advanced Usage

### Manual Backup in Python

```python
from talk_show_analyzer.backup import BackupManager
from pathlib import Path

backup_mgr = BackupManager(backup_dir=Path("my_backups"))

# Backup specific files
info = backup_mgr.backup_episode(
    episode_id=1,
    audio_path=Path("my_audio.mp3"),
    transcript_path=Path("my_transcript.json")
)

print(f"Backed up to: {info['files']}")
```

### Manual Recovery in Python

```python
from talk_show_analyzer.backup import RecoveryManager

recovery_mgr = RecoveryManager()

# Get failed episodes
failed = recovery_mgr.get_failed_episodes()
for ep in failed:
    print(f"Retry episode {ep['id']}")
    success = recovery_mgr.retry_analysis(ep['id'])
```

### Storage Analysis

```python
import json
from pathlib import Path

backups_dir = Path("backups")
total_by_station = {}

for backup in backups_dir.glob("episode_*"):
    metadata = backup / "backup_info.json"
    if metadata.exists():
        with open(metadata) as f:
            info = json.load(f)
            station = info['station']
            size = sum(f.stat().st_size for f in backup.rglob('*') if f.is_file())
            total_by_station[station] = total_by_station.get(station, 0) + size

for station, size in total_by_station.items():
    print(f"{station}: {size / (1024**2):.1f} MB")
```

## Summary

| Command | Purpose | Output |
|---------|---------|--------|
| `backup <id>` | Save episode files | Backed up files |
| `list` | View all backups | Backup list |
| `restore <id>` | Get files from backup | Restored paths |
| `recovery <id>` | Retry analysis | Success/failure |
| `failed` | See broken episodes | Failed episodes list |
| `stats` | Storage usage | Disk space used |
| `cleanup [days]` | Remove old backups | Freed space |

**For production use:** Set up automatic cleanup on cron, monitor storage monthly, and always test restore before deleting originals.
