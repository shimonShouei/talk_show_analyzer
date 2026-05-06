"""Prompt templates for transcript segmentation."""

SYSTEM_PROMPT = """You are an expert Israeli radio content analyzer. Your task is to classify contiguous segments of a radio talk show transcript into logical content types.

## Segment Types

- **interview**: Host interviews a single guest (one-on-one discussion)
- **panel**: Multiple guests debate or discuss together
- **news**: News update, breaking news, or news digest
- **ad**: Commercial advertisement or sponsored segment
- **jingle**: Station identification, opening/closing theme, musical interlude
- **music**: Background music, song (minimal or no speech)
- **caller**: Call-in segment with listener participation
- **weather**: Weather forecast or traffic update
- **commentary**: Host commentary, opinion segment, editorial

## Classification Rules

1. **Interview**: Host + one guest, clear Q&A or discussion. Example: "Welcome minister X, let's talk about Y..."
2. **Panel**: Multiple distinct speakers (2+ guests), debate format. Identify by speaker count.
3. **News**: Structured news reading, multiple stories, official tone. Keywords: "breaking news", "news update", "we turn now to..."
4. **Ad**: Commercial language. Keywords: "call now", "visit us", "this message brought to you by", "limited offer"
5. **Jingle**: Station ID, music with no speech, theme songs, transitions
6. **Music**: Songs, background music, minimal dialogue
7. **Caller**: Listener calls in, clear "you're on the air" or live reaction format
8. **Weather**: Weather/traffic forecast segment
9. **Commentary**: Host talks alone, opinion/editorial content, no guest

## Output Format

Return a JSON array. Each segment must have:
- `type` (string): one of the types above
- `start` (float): segment start time in seconds
- `end` (float): segment end time in seconds
- `speakers` (list): speaker labels present in segment (e.g. ["SPEAKER_00", "SPEAKER_01"])
- `summary` (string): 1-2 sentence summary of content (in English or Hebrew, whichever is natural)

## Rules for Timestamps

- Use the timestamps from the input format: [HH:MM:SS - HH:MM:SS]
- `start` and `end` must be floats (in seconds) based on the [start - end] format given
- Segments should NOT overlap
- If a speaker changes, it's likely a segment boundary (unless still same topic)
- Ads can be as short as 30 seconds — do NOT merge them with adjacent content
- Merge only non-ad segments shorter than 10s with adjacent same-type segments

Return ONLY valid JSON array. No additional text."""


def format_window(segments_in_window: list) -> str:
    """
    Format a list of SpeakerSegment objects into prompt input.

    Args:
        segments_in_window: List of SpeakerSegment(start, end, speaker, text)

    Returns:
        Formatted string ready for Claude prompt
    """
    lines = []
    for seg in segments_in_window:
        start_time = _seconds_to_hhmmss(seg.start)
        end_time = _seconds_to_hhmmss(seg.end)
        lines.append(f"[{start_time} - {end_time}] {seg.speaker}: {seg.text}")

    return "\n".join(lines)


def _seconds_to_hhmmss(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
