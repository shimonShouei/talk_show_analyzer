"""Registry of Israeli radio station streams with health checks."""

from dataclasses import dataclass
from typing import Optional
import requests
from loguru import logger


@dataclass
class StreamInfo:
    """Information about a radio stream."""

    name: str
    url: str
    referer: str
    format: str  # mp3, hls, etc
    user_agent: Optional[str] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


STREAMS = {
    "galatz": StreamInfo(
        name="Galatz (תחנת גלץ)",
        url="https://glzwizzlv.bynetcdn.com/glz_mp3",
        referer="https://glfrp.glz.co.il/",
        format="mp3",
    ),
    "kan_bet": StreamInfo(
        name="Kan Reshet Bet (ערוץ בית)",
        url="https://kanlivep2event-i.akamaihd.net/hls/live/749624/749624/kanbet_mp3/chunklist.m3u8",
        referer="https://www.kan.org.il/",
        format="hls",
    ),
    "103fm": StreamInfo(
        name="103FM (103 FM)",
        url="https://stream.103fm.maariv.co.il/103fm/playlist.m3u8",
        referer="https://103fm.maariv.co.il/",
        format="hls",
    ),
}


def check_stream_health(station: str) -> bool:
    """
    Check if a stream is accessible.

    Args:
        station: Station key (galatz, kan_bet, 103fm)

    Returns:
        True if stream is reachable
    """
    if station not in STREAMS:
        logger.error(f"Unknown station: {station}")
        return False

    stream = STREAMS[station]
    headers = {
        "Referer": stream.referer,
        "User-Agent": stream.user_agent or "Mozilla/5.0",
    }

    try:
        response = requests.head(stream.url, headers=headers, timeout=5, allow_redirects=True)
        is_healthy = response.status_code in (200, 206)  # 206 = partial content (streaming)
        status = "✓" if is_healthy else "✗"
        logger.info(f"{status} {stream.name}: {response.status_code}")
        return is_healthy
    except Exception as e:
        logger.error(f"✗ {stream.name}: {e}")
        return False


def check_all_streams() -> dict[str, bool]:
    """Check health of all streams."""
    results = {}
    for station in STREAMS.keys():
        results[station] = check_stream_health(station)
    return results


def get_stream(station: str) -> Optional[StreamInfo]:
    """Get stream info by station key."""
    return STREAMS.get(station)
