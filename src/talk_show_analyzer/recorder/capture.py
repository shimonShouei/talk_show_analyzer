"""Capture audio from streaming sources using ffmpeg."""

import subprocess
from pathlib import Path
from typing import Optional
from loguru import logger

from talk_show_analyzer.recorder.streams import get_stream, StreamInfo


def record_stream(
    stream: StreamInfo,
    output_path: str | Path,
    duration_seconds: int = 300,
    bitrate: str = "128k",
    sample_rate: int = 16000,
    channels: int = 1,
) -> bool:
    """
    Record audio from a stream using ffmpeg.

    Args:
        stream: StreamInfo object with URL and headers
        output_path: Where to save the MP3
        duration_seconds: How long to record (default 5 min for testing)
        bitrate: Audio bitrate (e.g., 128k)
        sample_rate: Sample rate in Hz
        channels: Mono (1) or stereo (2)

    Returns:
        True if recording succeeded, False otherwise
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build ffmpeg headers string
    headers = [
        f"Referer: {stream.referer}",
        f"User-Agent: {stream.user_agent or 'Mozilla/5.0'}",
    ]
    headers_str = "\\r\\n".join(headers) + "\\r\\n"

    logger.info(f"Recording {stream.name} for {duration_seconds}s → {output_path}")
    logger.debug(f"Stream URL: {stream.url}")

    cmd = [
        "ffmpeg",
        "-headers",
        headers_str,
        "-i",
        stream.url,
        "-t",
        str(duration_seconds),
        "-acodec",
        "libmp3lame",
        "-ab",
        bitrate,
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        "-y",  # Overwrite output file
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=duration_seconds + 30,  # Allow some buffer
        )

        if result.returncode == 0:
            file_size = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"✓ Recording complete: {file_size:.1f} MB")
            return True
        else:
            logger.error(f"ffmpeg failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("Recording timed out")
        return False
    except FileNotFoundError:
        logger.error("ffmpeg not found. Install with: apt-get install ffmpeg")
        return False
    except Exception as e:
        logger.error(f"Recording failed: {e}")
        return False


def record_station(
    station: str,
    output_path: str | Path,
    duration_seconds: int = 300,
) -> bool:
    """
    Convenience function: record from a named station.

    Args:
        station: Station key (galatz, kan_bet, 103fm)
        output_path: Where to save the MP3
        duration_seconds: How long to record

    Returns:
        True if successful
    """
    stream = get_stream(station)
    if not stream:
        logger.error(f"Unknown station: {station}")
        return False

    return record_stream(stream, output_path, duration_seconds=duration_seconds)
