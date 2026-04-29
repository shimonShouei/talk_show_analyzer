#!/usr/bin/env python3
"""Command-line tool for managing backups and recovery.

Usage:
    python manage_backups.py backup <episode_id>          # Backup an episode
    python manage_backups.py list                          # List all backups
    python manage_backups.py restore <episode_id>         # Restore from backup
    python manage_backups.py recovery <episode_id>        # Backup + retry analysis
    python manage_backups.py failed                       # Show failed episodes
    python manage_backups.py stats                        # Show backup storage stats
    python manage_backups.py cleanup [days]               # Delete old backups
"""

import sys
import json
from pathlib import Path
from loguru import logger

from talk_show_analyzer.backup import BackupManager, RecoveryManager

# Setup logging
logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {message}",
)


def cmd_backup(episode_id: int) -> int:
    """Backup an episode."""
    logger.info(f"\n{'='*70}")
    logger.info(f"BACKUP EPISODE {episode_id}")
    logger.info(f"{'='*70}\n")

    try:
        backup_mgr = BackupManager()
        info = backup_mgr.backup_episode(episode_id)
        logger.info(f"Files backed up:")
        for file_type, path in info["files"].items():
            logger.info(f"  • {file_type}: {path}")
        return 0
    except Exception as e:
        logger.error(f"Backup failed: {e}\n")
        return 1


def cmd_list() -> int:
    """List all backups."""
    logger.info(f"\n{'='*70}")
    logger.info("AVAILABLE BACKUPS")
    logger.info(f"{'='*70}\n")

    backup_mgr = BackupManager()
    backups = backup_mgr.list_backups()

    if not backups:
        logger.info("No backups found\n")
        return 0

    for i, backup in enumerate(backups, 1):
        logger.info(
            f"{i}. Episode {backup['episode_id']} ({backup['station'].upper()})"
        )
        logger.info(f"   Recorded: {backup['recorded_at']}")
        logger.info(f"   Backed up: {backup['backup_time']}")
        logger.info(f"   Duration: {backup['duration']:.1f}s")
        logger.info(f"   Files: {', '.join(backup['files'].keys())}\n")

    return 0


def cmd_restore(episode_id: int) -> int:
    """Restore an episode from backup."""
    logger.info(f"\n{'='*70}")
    logger.info(f"RESTORE EPISODE {episode_id}")
    logger.info(f"{'='*70}\n")

    try:
        backup_mgr = BackupManager()
        restored = backup_mgr.restore_episode(episode_id)
        logger.info(f"Restored files:")
        for file_type, path in restored["files"].items():
            logger.info(f"  • {file_type}: {path}")
        return 0
    except Exception as e:
        logger.error(f"Restore failed: {e}\n")
        return 1


def cmd_recovery(episode_id: int) -> int:
    """Backup and attempt recovery of a failed episode."""
    logger.info(f"\n{'='*70}")
    logger.info(f"BACKUP + RECOVERY FOR EPISODE {episode_id}")
    logger.info(f"{'='*70}\n")

    try:
        recovery_mgr = RecoveryManager()
        result = recovery_mgr.backup_and_recover(episode_id)

        logger.info(f"Results:")
        logger.info(f"  Backup: {'✓' if result['backup_successful'] else '✗'}")
        logger.info(f"  Recovery: {'✓' if result['recovery_successful'] else '✗'}\n")

        return 0 if result["recovery_successful"] else 1
    except Exception as e:
        logger.error(f"Recovery failed: {e}\n")
        return 1


def cmd_failed() -> int:
    """List failed episodes."""
    logger.info(f"\n{'='*70}")
    logger.info("FAILED EPISODES")
    logger.info(f"{'='*70}\n")

    recovery_mgr = RecoveryManager()
    failed = recovery_mgr.get_failed_episodes()

    if not failed:
        logger.info("No failed episodes\n")
        return 0

    for ep in failed:
        logger.info(f"Episode {ep['id']} ({ep['station'].upper()})")
        logger.info(f"  Status: {ep['status']}")
        logger.info(f"  Recorded: {ep['recorded_at']}\n")

    logger.info(f"Total: {len(failed)} failed episodes\n")
    logger.info("Recovery options:")
    logger.info("  1. python manage_backups.py recovery <episode_id>")
    logger.info("  2. Check logs for root cause")
    logger.info("  3. Fix issue, then retry\n")

    return 0


def cmd_stats() -> int:
    """Show backup storage statistics."""
    logger.info(f"\n{'='*70}")
    logger.info("BACKUP STORAGE STATISTICS")
    logger.info(f"{'='*70}\n")

    backup_mgr = BackupManager()
    stats = backup_mgr.get_backup_stats()

    logger.info(f"Total backups: {stats['total_backups']}")
    logger.info(f"Total files: {stats['total_files']}")
    logger.info(f"Storage used: {stats['total_size_mb']:.1f} MB")
    logger.info(f"Location: {stats['backup_dir']}\n")

    if stats["total_size_mb"] > 1000:
        logger.warning(f"Storage is {stats['total_size_mb'] / 1024:.1f} GB")
        logger.warning("Consider running: python manage_backups.py cleanup\n")

    return 0


def cmd_cleanup(days: int = 30) -> int:
    """Clean up old backups."""
    logger.info(f"\n{'='*70}")
    logger.info(f"CLEANUP: DELETE BACKUPS OLDER THAN {days} DAYS")
    logger.info(f"{'='*70}\n")

    backup_mgr = BackupManager()

    # Show what will be deleted
    logger.info("Old backups to delete:")
    stats_before = backup_mgr.get_backup_stats()

    deleted = backup_mgr.cleanup_old_backups(keep_days=days)

    stats_after = backup_mgr.get_backup_stats()
    freed_mb = stats_before["total_size_mb"] - stats_after["total_size_mb"]

    logger.info(f"Deleted: {deleted} backups")
    logger.info(f"Freed: {freed_mb:.1f} MB\n")

    return 0


def main():
    """Main CLI handler."""
    if len(sys.argv) < 2:
        logger.info(__doc__)
        return 1

    command = sys.argv[1].lower()

    try:
        if command == "backup":
            if len(sys.argv) < 3:
                logger.error("Usage: python manage_backups.py backup <episode_id>\n")
                return 1
            return cmd_backup(int(sys.argv[2]))

        elif command == "list":
            return cmd_list()

        elif command == "restore":
            if len(sys.argv) < 3:
                logger.error("Usage: python manage_backups.py restore <episode_id>\n")
                return 1
            return cmd_restore(int(sys.argv[2]))

        elif command == "recovery":
            if len(sys.argv) < 3:
                logger.error("Usage: python manage_backups.py recovery <episode_id>\n")
                return 1
            return cmd_recovery(int(sys.argv[2]))

        elif command == "failed":
            return cmd_failed()

        elif command == "stats":
            return cmd_stats()

        elif command == "cleanup":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            return cmd_cleanup(days)

        else:
            logger.error(f"Unknown command: {command}\n")
            logger.info(__doc__)
            return 1

    except Exception as e:
        logger.error(f"Error: {e}\n")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
