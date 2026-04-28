#!/usr/bin/env python3
"""Example: Transcribe and diarize a single audio file."""

from pathlib import Path
import json
from talk_show_analyzer.transcription import Transcriber

# Initialize transcriber with Faster-Whisper + Pyannote
transcriber = Transcriber(
    model_size="base",  # Try "tiny" for faster results
    device="auto",      # Use GPU if available
    compute_type="float16",
    enable_diarization=True,
)

# Transcribe an audio file (Hebrew)
audio_file = Path("sample_radio.mp3")

if not audio_file.exists():
    print(f"Error: {audio_file} not found")
    print("Please provide a sample Hebrew audio file to transcribe")
    exit(1)

result = transcriber.transcribe_file(
    audio_file,
    output_json="transcript.json",
    language="he",
)

# Print summary
print("\n" + "="*60)
print("TRANSCRIPTION SUMMARY")
print("="*60)
print(f"Language: {result.language}")
print(f"Duration: {result.duration:.1f}s ({result.duration/60:.1f} min)")
print(f"Word count: {result.word_count}")
print(f"Speaker segments: {len(result.segments)}")
print()

# Print first 3 segments
print("First 3 segments:")
for i, seg in enumerate(result.segments[:3]):
    print(f"  [{seg.start:.1f}s - {seg.end:.1f}s] {seg.speaker}")
    print(f"    {seg.text[:80]}...")

print()
print(f"Full transcript saved to: transcript.json")
print(f"Raw text length: {len(result.raw_text)} chars")
