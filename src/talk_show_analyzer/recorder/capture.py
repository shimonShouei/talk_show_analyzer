"""Capture audio from streaming sources using ffmpeg."""

import subprocess
import time
from pathlib import Path
from typing import Optional
from loguru import logger

from talk_show_analyzer.recorder.streams import get_stream, StreamInfo


def _probe_duration(path: Path) -> float:
    """Audio duration in seconds via ffprobe (0.0 if unreadable)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return float(out.stdout.strip() or 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def record_stream(
    stream: StreamInfo,
    output_path: str | Path,
    duration_seconds: int = 300,
    bitrate: str = "128k",
    sample_rate: int = 16000,
    channels: int = 1,
    grace_seconds: int = 300,
) -> bool:
    """Record ``duration_seconds`` of audio, resuming after stream drops.

    Live icecast streams sometimes end or stall mid-recording while ffmpeg
    still exits 0, which silently produced short files. We check the real
    duration, keep recording the remainder into part files until the target
    (or wall-clock deadline = duration + grace) is reached, then concatenate.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + duration_seconds + grace_seconds
    parts: list[Path] = []
    recorded = 0.0
    while recorded < duration_seconds - 5 and time.time() < deadline:
        remaining = int(min(duration_seconds - recorded, deadline - time.time()))
        if remaining <= 5:
            break
        part = output_path.with_name(f"{output_path.stem}.part{len(parts)}{output_path.suffix}")
        _record_once(stream, part, remaining, bitrate, sample_rate, channels)
        got = _probe_duration(part) if part.exists() else 0.0
        if got > 1.0:
            parts.append(part)
            recorded += got
            if recorded < duration_seconds - 5:
                logger.warning(
                    f"Stream ended early: {recorded:.0f}/{duration_seconds}s recorded; reconnecting"
                )
        else:
            part.unlink(missing_ok=True)
            time.sleep(5)
    if not parts:
        logger.error("Recording failed: no audio captured")
        return False
    if len(parts) == 1:
        parts[0].replace(output_path)
    else:
        listing = output_path.with_suffix(".concat.txt")
        listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-c", "copy", "-y", str(output_path)],
            check=False, capture_output=True,
        )
        listing.unlink(missing_ok=True)
        for p in parts:
            p.unlink(missing_ok=True)
    final = _probe_duration(output_path)
    if final < duration_seconds - 5:
        logger.warning(f"Recording short: {final:.0f}s of {duration_seconds}s requested")
    else:
        logger.info(f"✓ Recording complete: {final:.0f}s in {len(parts)} piece(s)")
    return final > 0


def _record_once(
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
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "30",
        "-rw_timeout", "30000000",  # 30s: fail instead of hanging on a stalled stream
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
