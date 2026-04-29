"""Backup, download, and recovery utilities for talk show recordings."""

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
from loguru import logger

from talk_show_analyzer.db import get_session
from talk_show_analyzer.models import Episode


class BackupManager:
    """Manage recording backups and recovery."""

    def __init__(self, backup_dir: Path = Path("backups")):
        """Initialize backup manager.

        Args:
            backup_dir: Directory to store backups
        """
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Backup directory: {self.backup_dir}")

    def backup_episode(
        self,
        episode_id: int,
        audio_path: Optional[Path] = None,
        transcript_path: Optional[Path] = None,
    ) -> dict:
        """
        Backup an episode's audio and transcript.

        Args:
            episode_id: Episode ID from database
            audio_path: Path to audio file (optional)
            transcript_path: Path to transcript JSON (optional)

        Returns:
            Backup info with paths and status
        """
        with get_session() as session:
            episode = session.query(Episode).filter_by(id=episode_id).first()
            if not episode:
                raise ValueError(f"Episode {episode_id} not found")

            # Use provided paths or get from episode
            audio = audio_path or Path(episode.audio_path)
            transcript = transcript_path or audio.parent / f"{audio.stem}_transcript.json"

            # Create backup directory for this episode
            episode_backup = self.backup_dir / f"episode_{episode_id}_{datetime.now().isoformat()}"
            episode_backup.mkdir(parents=True, exist_ok=True)

            backup_info = {
                "episode_id": episode_id,
                "station": episode.station.name,
                "recorded_at": episode.recorded_at.isoformat(),
                "duration": episode.duration,
                "backup_time": datetime.now().isoformat(),
                "files": {},
            }

            # Backup audio
            if audio.exists():
                backup_audio = episode_backup / audio.name
                shutil.copy2(audio, backup_audio)
                backup_info["files"]["audio"] = str(backup_audio)
                logger.info(f"✓ Backed up audio: {backup_audio.name}")
            else:
                logger.warning(f"Audio file not found: {audio}")

            # Backup transcript
            if transcript.exists():
                backup_transcript = episode_backup / transcript.name
                shutil.copy2(transcript, backup_transcript)
                backup_info["files"]["transcript"] = str(backup_transcript)
                logger.info(f"✓ Backed up transcript: {backup_transcript.name}")
            else:
                logger.warning(f"Transcript not found: {transcript}")

            # Save backup metadata
            metadata_file = episode_backup / "backup_info.json"
            with open(metadata_file, "w") as f:
                json.dump(backup_info, f, indent=2)

            logger.info(f"✓ Backup complete: {episode_backup}\n")
            return backup_info

    def list_backups(self) -> list[dict]:
        """List all available backups.

        Returns:
            List of backup info dictionaries
        """
        backups = []
        for backup_dir in sorted(self.backup_dir.iterdir()):
            if backup_dir.is_dir():
                metadata = backup_dir / "backup_info.json"
                if metadata.exists():
                    with open(metadata) as f:
                        info = json.load(f)
                        info["backup_dir"] = str(backup_dir)
                        backups.append(info)

        return sorted(backups, key=lambda x: x["backup_time"], reverse=True)

    def restore_episode(self, episode_id: int, target_dir: Path = Path("data")) -> dict:
        """
        Restore an episode from backup.

        Args:
            episode_id: Episode ID to restore
            target_dir: Directory to restore files to

        Returns:
            Restored file paths
        """
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        # Find latest backup for this episode
        latest_backup = None
        for backup_dir in self.backup_dir.iterdir():
            if backup_dir.is_dir() and f"episode_{episode_id}_" in backup_dir.name:
                metadata = backup_dir / "backup_info.json"
                if metadata.exists():
                    latest_backup = backup_dir
                    break

        if not latest_backup:
            raise ValueError(f"No backup found for episode {episode_id}")

        restored = {"episode_id": episode_id, "files": {}}

        # Restore files
        for file_path in latest_backup.iterdir():
            if file_path.name == "backup_info.json":
                continue

            target_path = target_dir / file_path.name
            shutil.copy2(file_path, target_path)
            restored["files"][file_path.suffix.lstrip(".")] = str(target_path)
            logger.info(f"✓ Restored {file_path.name} → {target_path}")

        logger.info(f"\n✓ Episode {episode_id} restored from {latest_backup}\n")
        return restored

    def cleanup_old_backups(self, keep_days: int = 30) -> int:
        """
        Delete old backups older than keep_days.

        Args:
            keep_days: Keep backups newer than this many days

        Returns:
            Number of backups deleted
        """
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=keep_days)
        deleted_count = 0

        for backup_dir in self.backup_dir.iterdir():
            if not backup_dir.is_dir():
                continue

            # Parse backup date from directory name
            try:
                date_str = "_".join(backup_dir.name.split("_")[2:])
                backup_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

                if backup_date < cutoff_date:
                    shutil.rmtree(backup_dir)
                    deleted_count += 1
                    logger.info(f"✓ Deleted old backup: {backup_dir.name}")
            except (ValueError, IndexError):
                logger.warning(f"Could not parse backup date from {backup_dir.name}")

        logger.info(f"\nDeleted {deleted_count} old backups\n")
        return deleted_count

    def get_backup_stats(self) -> dict:
        """Get backup storage statistics.

        Returns:
            Storage usage statistics
        """
        total_size = 0
        backup_count = 0

        for backup_dir in self.backup_dir.rglob("*"):
            if backup_dir.is_file():
                total_size += backup_dir.stat().st_size
                backup_count += 1

        return {
            "total_backups": len(list(self.backup_dir.glob("episode_*"))),
            "total_files": backup_count,
            "total_size_mb": total_size / (1024 * 1024),
            "backup_dir": str(self.backup_dir),
        }


class RecoveryManager:
    """Handle pipeline recovery and re-analysis."""

    def __init__(self, backup_dir: Path = Path("backups")):
        """Initialize recovery manager.

        Args:
            backup_dir: Directory with backups
        """
        self.backup_mgr = BackupManager(backup_dir)

    def get_failed_episodes(self) -> list[dict]:
        """Get list of failed episodes from database.

        Returns:
            List of episodes with failed status
        """
        with get_session() as session:
            failed = session.query(Episode).filter(
                Episode.status.in_(["failed", "analyzing"])
            ).all()

            return [
                {
                    "id": ep.id,
                    "station": ep.station.name,
                    "recorded_at": ep.recorded_at.isoformat(),
                    "status": ep.status,
                }
                for ep in failed
            ]

    def retry_analysis(self, episode_id: int, from_transcript: bool = True) -> bool:
        """
        Retry analysis for a failed episode.

        Args:
            episode_id: Episode ID to retry
            from_transcript: Use existing transcript if available

        Returns:
            Success status
        """
        from talk_show_analyzer.pipeline import PipelineOrchestrator

        logger.info(f"\nRetrying analysis for episode {episode_id}...")

        try:
            orchestrator = PipelineOrchestrator()

            if from_transcript:
                # Resume from last successful step
                episode = orchestrator.resume(episode_id)
                logger.info(f"✓ Resumed from checkpoint\n")
            else:
                # Full re-run from backup
                restored = self.backup_mgr.restore_episode(episode_id)
                # Would need to re-transcribe here
                logger.warning("Full re-run requires manual transcription first")
                return False

            return episode.status == "analyzed"

        except Exception as e:
            logger.error(f"✗ Retry failed: {e}\n")
            return False

    def backup_and_recover(self, episode_id: int) -> dict:
        """
        Backup current state and attempt recovery.

        Args:
            episode_id: Episode to backup and recover

        Returns:
            Recovery status and details
        """
        result = {
            "episode_id": episode_id,
            "backup_successful": False,
            "recovery_attempted": False,
            "recovery_successful": False,
        }

        # Backup current state
        try:
            with get_session() as session:
                episode = session.query(Episode).filter_by(id=episode_id).first()
                if episode:
                    self.backup_mgr.backup_episode(episode_id)
                    result["backup_successful"] = True
        except Exception as e:
            logger.error(f"Backup failed: {e}")

        # Attempt recovery
        try:
            result["recovery_attempted"] = True
            success = self.retry_analysis(episode_id)
            result["recovery_successful"] = success
        except Exception as e:
            logger.error(f"Recovery failed: {e}")

        return result
