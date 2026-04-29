#!/usr/bin/env python3
"""Test the segmentation module on recorded transcript."""

import json
from pathlib import Path
from loguru import logger

from talk_show_analyzer.transcription.transcriber import (
    TranscriptionResult,
    SpeakerSegment,
)
from talk_show_analyzer.analysis import Segmenter

# Setup logging
logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {message}",
)


def main():
    """Load transcript and segment it."""

    # Load the recorded transcript
    transcript_file = Path("test_output/galatz_transcript.json")
    if not transcript_file.exists():
        logger.error(f"Transcript not found: {transcript_file}")
        return

    logger.info(f"Loading transcript from: {transcript_file}\n")
    with open(transcript_file) as f:
        data = json.load(f)

    # Reconstruct TranscriptionResult
    segments = [
        SpeakerSegment(
            start=seg["start"],
            end=seg["end"],
            speaker=seg["speaker"],
            text=seg["text"],
        )
        for seg in data["segments"]
    ]

    transcript = TranscriptionResult(
        raw_text=data["raw_text"],
        language=data["language"],
        duration=data["duration"],
        word_count=data["word_count"],
        segments=segments,
    )

    logger.info(f"Transcript: {transcript.duration:.0f}s, {len(segments)} segments\n")

    # Segment with Claude
    logger.info("=== SEGMENTING TRANSCRIPT ===\n")
    segmenter = Segmenter()
    result_segments = segmenter.segment(transcript)

    # Print results
    logger.info("\n=== SEGMENTATION RESULTS ===\n")
    for i, seg in enumerate(result_segments, 1):
        duration = seg.end - seg.start
        logger.info(
            f"{i}. [{seg.type:12s}] {seg.start:6.0f}s - {seg.end:6.0f}s ({duration:5.0f}s)"
        )
        logger.info(f"   Speakers: {', '.join(seg.speakers)}")
        logger.info(f"   Summary:  {seg.summary}\n")

    logger.info(f"\n✓ Segmented into {len(result_segments)} segments")

    # Save results to JSON
    output_file = Path("test_output/galatz_segments.json")
    output_data = {
        "transcript": {
            "duration": transcript.duration,
            "language": transcript.language,
            "word_count": transcript.word_count,
        },
        "segments": [
            {
                "type": seg.type,
                "start": seg.start,
                "end": seg.end,
                "duration": seg.end - seg.start,
                "speakers": seg.speakers,
                "summary": seg.summary,
            }
            for seg in result_segments
        ],
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    logger.info(f"\n✓ Results saved to: {output_file}")


if __name__ == "__main__":
    main()
