"""Download recorded talk show episodes from a direct URL using ffmpeg or HTTP."""

import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from loguru import logger


def download_episode(
    url: str,
    output_path: str | Path,
    user_agent: str = "Mozilla/5.0",
    referer: str | None = None,
    use_ffmpeg: bool = True,
    timeout: int = 300,
) -> bool:
    """
    Download a recorded talk show episode from a URL.

    Uses ffmpeg for streaming/media URLs (HLS, RTMP, direct audio) and falls
    back to plain HTTP download for regular file links.

    Args:
        url: Direct URL to the audio file or stream.
        output_path: Destination path (e.g. "episode.mp3").
        user_agent: HTTP User-Agent header.
        referer: Optional HTTP Referer header.
        use_ffmpeg: Prefer ffmpeg (handles HLS/RTMP and re-encodes to MP3).
            Set False to use a plain HTTP download instead.
        timeout: Max seconds to wait (ffmpeg) or socket timeout (HTTP).

    Returns:
        True on success, False on failure.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Downloading episode from {url} → {output_path}")

    if use_ffmpeg:
        return _download_ffmpeg(url, output_path, user_agent, referer, timeout)
    else:
        return _download_http(url, output_path, user_agent, referer, timeout)


def _download_ffmpeg(
    url: str,
    output_path: Path,
    user_agent: str,
    referer: str | None,
    timeout: int,
) -> bool:
    headers = [f"User-Agent: {user_agent}"]
    if referer:
        headers.append(f"Referer: {referer}")
    headers_str = "\\r\\n".join(headers) + "\\r\\n"

    cmd = [
        "ffmpeg",
        "-headers", headers_str,
        "-i", url,
        "-acodec", "libmp3lame",
        "-ab", "128k",
        "-ar", "16000",
        "-ac", "1",
        "-y",
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"Download complete: {size_mb:.1f} MB")
            return True
        else:
            logger.error(f"ffmpeg failed (rc={result.returncode}): {result.stderr[-500:]}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"Download timed out after {timeout}s")
        return False
    except FileNotFoundError:
        logger.error("ffmpeg not found. Install with: conda install -c conda-forge ffmpeg")
        return False
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False


def _download_http(
    url: str,
    output_path: Path,
    user_agent: str,
    referer: str | None,
    timeout: int,
) -> bool:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", user_agent)
    if referer:
        req.add_header("Referer", referer)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
        output_path.write_bytes(data)
        size_mb = len(data) / (1024 * 1024)
        logger.info(f"Download complete: {size_mb:.1f} MB")
        return True
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP {e.code}: {e.reason}")
        return False
    except urllib.error.URLError as e:
        logger.error(f"URL error: {e.reason}")
        return False
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False
