"""Archive download and DVR rewind utilities for missed recordings."""

import subprocess
from pathlib import Path
from datetime import datetime
from loguru import logger

from talk_show_analyzer.recorder.capture import record_station
from talk_show_analyzer.recorder.streams import get_stream


def download_from_url(url: str, output_path: Path = Path("data")) -> Path | None:
    """
    Download episode from station website URL using yt-dlp.

    Converts to same format as live recording: 128k MP3, mono, 16kHz.

    Args:
        url: Episode URL from station website
        output_path: Directory to save MP3 file

    Returns:
        Path to downloaded file, or None if failed
    """
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"\n{'='*70}")
    logger.info("DOWNLOADING EPISODE FROM URL")
    logger.info(f"{'='*70}\n")
    logger.info(f"URL: {url}\n")

    # Use yt-dlp to extract audio
    output_template = str(output_path / "%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "-x",  # Extract audio only
        "--audio-format", "mp3",  # Convert to MP3
        "--audio-quality", "128",  # 128k bitrate
        "-o", output_template,
        url,
    ]

    logger.info(f"Command: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes
        )

        if result.returncode != 0:
            logger.error(f"yt-dlp failed: {result.stderr}")
            return None

        # Find the downloaded file
        mp3_files = list(output_path.glob("*.mp3"))
        if not mp3_files:
            logger.error("No MP3 file found after download")
            return None

        # Get the most recent file (in case multiple exist)
        downloaded_file = max(mp3_files, key=lambda p: p.stat().st_mtime)

        # Standardize filename
        station_match = url.split("/")[2]  # Extract domain
        timestamp = datetime.now().isoformat().replace(":", "-")
        final_name = f"archive_{station_match}_{timestamp}.mp3"
        final_path = output_path / final_name

        downloaded_file.rename(final_path)

        logger.info(f"✓ Downloaded: {final_path}")
        logger.info(f"  Size: {final_path.stat().st_size / (1024*1024):.1f} MB\n")

        return final_path

    except subprocess.TimeoutExpired:
        logger.error("Download timed out (10 minutes)")
        return None
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return None


def rewind_stream(
    station: str,
    minutes_ago: int,
    duration: int,
    output_path: Path = Path("data"),
) -> Path | None:
    """
    Attempt HLS DVR rewind for time-shifted streams (Kan Bet, 103FM).

    Rewinds the HLS playlist URL by appending a DVR offset and records it.
    Works only if CDN supports time-shifting (typically 1-4 hours window).

    Args:
        station: Station name (kan_bet or 103fm)
        minutes_ago: How many minutes in the past to rewind
        duration: Recording duration in seconds
        output_path: Directory to save MP3 file

    Returns:
        Path to recorded file, or None if failed
    """
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"\n{'='*70}")
    logger.info(f"ATTEMPTING HLS DVR REWIND ({station.upper()})")
    logger.info(f"{'='*70}\n")
    logger.info(f"Rewind: {minutes_ago} minutes ago")
    logger.info(f"Duration: {duration} seconds\n")

    # Get stream
    stream = get_stream(station)
    if not stream:
        logger.error(f"Stream not found: {station}")
        return None

    # Only works for HLS streams
    if "m3u8" not in stream.url and "playlist" not in stream.url:
        logger.warning(f"{station} does not use HLS (DVR not supported)")
        logger.info("Use --url option instead to download from archive website\n")
        return None

    # Append DVR offset to playlist URL
    # Format: #EXT-X-START:TIME-OFFSET=-Nseonds
    dvr_url = f"{stream.url}?start_offset=-{minutes_ago * 60}"

    logger.info(f"DVR URL: {dvr_url}\n")
    logger.info("Note: This works only if CDN supports DVR (typically 1-4 hour window)\n")

    # Try to record from DVR URL
    timestamp = datetime.now().isoformat().replace(":", "-")
    output_file = output_path / f"{station}_dvr_{timestamp}.mp3"

    try:
        # Use ffmpeg directly with DVR URL
        cmd = [
            "ffmpeg",
            "-headers", f"Referer: {stream.referer}\r\nUser-Agent: {stream.user_agent or 'Mozilla/5.0'}\r\n",
            "-t", str(duration),
            "-i", dvr_url,
            "-acodec", "libmp3lame",
            "-ab", "128k",
            "-ar", "16000",
            "-ac", "1",
            str(output_file),
        ]

        logger.info("Recording from DVR...\n")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=duration + 60,
        )

        if result.returncode != 0:
            logger.warning(f"DVR rewind failed (CDN may not support DVR):")
            logger.warning(f"  {result.stderr[:200]}\n")
            # Clean up incomplete file
            if output_file.exists():
                output_file.unlink()
            return None

        if not output_file.exists() or output_file.stat().st_size == 0:
            logger.warning("DVR rewind failed (no data received)\n")
            return None

        logger.info(f"✓ Recorded from DVR: {output_file}")
        logger.info(f"  Size: {output_file.stat().st_size / (1024*1024):.1f} MB\n")

        return output_file

    except subprocess.TimeoutExpired:
        logger.error(f"Recording timed out after {duration} seconds")
        if output_file.exists():
            output_file.unlink()
        return None
    except Exception as e:
        logger.error(f"DVR rewind failed: {e}\n")
        if output_file.exists():
            output_file.unlink()
        return None
