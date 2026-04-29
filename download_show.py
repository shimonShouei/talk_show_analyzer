#!/usr/bin/env python3
"""Download missed episodes from archives or via DVR rewind.

Usage:
    # Download from station website URL
    python download_show.py --url "https://www.kan.org.il/Episode/..."

    # Attempt DVR rewind (Kan Bet / 103FM only)
    python download_show.py --station kan_bet --rewind 120 --duration 14400

    # Specify output directory
    python download_show.py --url "..." --output /path/to/save/
"""

import sys
import argparse
from pathlib import Path
from loguru import logger

from talk_show_analyzer.recorder.archive import download_from_url, rewind_stream

# Setup logging
logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {message}",
)


def main():
    """Main CLI handler."""
    parser = argparse.ArgumentParser(
        description="Download missed episodes from archives or DVR.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download from URL
  python download_show.py --url "https://www.kan.org.il/Episode/12345"

  # DVR rewind (try to fetch from last N minutes)
  python download_show.py --station kan_bet --rewind 120 --duration 14400

  # Save to specific directory
  python download_show.py --url "..." --output ~/downloads/
        """,
    )

    # URL-based download
    parser.add_argument(
        "--url",
        type=str,
        help="Episode URL from station website (Kan, Galatz, 103FM)",
    )

    # DVR rewind options
    parser.add_argument(
        "--station",
        type=str,
        choices=["galatz", "kan_bet", "103fm"],
        help="Station name (for DVR rewind)",
    )
    parser.add_argument(
        "--rewind",
        type=int,
        default=120,
        help="Minutes to rewind from current time (default: 120)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=14400,
        help="Recording duration in seconds (default: 14400 = 4 hours)",
    )

    # Common options
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data"),
        help="Output directory (default: data/)",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.url and not args.station:
        parser.print_help()
        logger.error("\nError: Specify either --url or --station\n")
        return 1

    if args.url and args.station:
        logger.error("Error: Specify only --url or --station, not both\n")
        return 1

    # Execute download
    try:
        if args.url:
            # Download from URL
            result = download_from_url(args.url, output_path=args.output)
            if not result:
                logger.error("✗ Download failed\n")
                return 1

            logger.info(f"✓ Episode saved to: {result}")
            logger.info(f"\nNext steps:")
            logger.info(f"  1. Verify file: ffprobe {result}")
            logger.info(f"  2. Analyze: python test_full_pipeline.py\n")
            return 0

        else:
            # DVR rewind
            result = rewind_stream(
                station=args.station,
                minutes_ago=args.rewind,
                duration=args.duration,
                output_path=args.output,
            )

            if not result:
                logger.error("✗ DVR rewind failed\n")
                logger.error("Note: DVR only works if CDN supports time-shifting (usually 1-4 hours window)")
                logger.error("Try downloading from the station's website instead:\n")
                logger.error(f"  python download_show.py --url <episode_url>\n")
                return 1

            logger.info(f"✓ Episode saved to: {result}")
            logger.info(f"\nNext steps:")
            logger.info(f"  1. Verify file: ffprobe {result}")
            logger.info(f"  2. Analyze: python test_full_pipeline.py\n")
            return 0

    except Exception as e:
        logger.error(f"Error: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
