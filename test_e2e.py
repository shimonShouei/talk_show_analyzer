#!/usr/bin/env python3
"""End-to-end test: Record from Israeli radio stream, then transcribe."""

import sys
from pathlib import Path
from loguru import logger

from talk_show_analyzer.recorder import check_all_streams, record_station
from talk_show_analyzer.transcription import Transcriber

# Setup logging
logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {message}",
)


def main():
    """Run E2E test: record → transcribe."""

    # Create output directory
    test_dir = Path("test_output")
    test_dir.mkdir(exist_ok=True)

    # Step 1: Check stream health
    logger.info("\n=== CHECKING STREAM HEALTH ===\n")
    health = check_all_streams()

    healthy_stations = [s for s, h in health.items() if h]
    if not healthy_stations:
        logger.error("No streams are healthy. Check network/geo-blocking.")
        sys.exit(1)

    logger.info(f"\n✓ {len(healthy_stations)} stream(s) available\n")

    # Step 2: Record from first healthy station
    station = healthy_stations[0]
    audio_file = test_dir / f"{station}_sample.mp3"

    logger.info(f"\n=== RECORDING 5 MINUTES FROM {station.upper()} ===\n")
    success = record_station(station, audio_file, duration_seconds=300)

    if not success:
        logger.error(f"Failed to record from {station}")
        sys.exit(1)

    # Step 3: Transcribe
    logger.info("\n=== INITIALIZING TRANSCRIBER ===\n")
    logger.info("Loading Faster-Whisper (base model)...")
    logger.info("Loading Pyannote diarization pipeline...")
    logger.info("(This may take a minute on first run)\n")

    try:
        transcriber = Transcriber(
            model_size="base",
            device="auto",
            compute_type="float16",
            enable_diarization=True,
        )
    except Exception as e:
        logger.error(f"Failed to initialize transcriber: {e}")
        logger.info(
            "\nTroubleshooting:\n"
            "  - Install ffmpeg: apt-get install ffmpeg\n"
            "  - Set HF_TOKEN: https://huggingface.co/settings/tokens\n"
            "  - For GPU: CUDA toolkit 11.0+ required\n"
        )
        sys.exit(1)

    logger.info(f"\n=== TRANSCRIBING {audio_file.name} ===\n")
    result = transcriber.transcribe_file(
        audio_file,
        output_json=test_dir / f"{station}_transcript.json",
        language="he",
    )

    # Step 4: Show results
    logger.info("\n" + "=" * 60)
    logger.info("TRANSCRIPTION RESULTS")
    logger.info("=" * 60 + "\n")

    logger.info(f"Language:        {result.language}")
    logger.info(f"Duration:        {result.duration:.1f}s ({result.duration / 60:.1f} min)")
    logger.info(f"Word count:      {result.word_count}")
    logger.info(f"Speaker segments: {len(result.segments)}\n")

    # Show unique speakers
    speakers = set(seg.speaker for seg in result.segments)
    logger.info(f"Speakers detected: {', '.join(sorted(speakers))}\n")

    # Show first 5 segments
    logger.info("First 5 segments:")
    for i, seg in enumerate(result.segments[:5], 1):
        logger.info(
            f"  {i}. [{seg.start:.1f}s - {seg.end:.1f}s] {seg.speaker}\n"
            f"     {seg.text[:70]}..."
        )

    logger.info(f"\n✓ Transcript saved to: {test_dir / f'{station}_transcript.json'}\n")


if __name__ == "__main__":
    main()
