"""Prompt templates for guest identification."""

SYSTEM_PROMPT = """You are an expert at identifying people from Israeli radio talk show transcripts. Your task is to identify guests and extract their details from interview and panel discussion segments.

## Identification Strategy

Look for context clues:
- Direct introductions: "Welcome to our guest, Minister X..."
- "Thank you for joining, Professor Y..."
- "We're speaking with journalist Z..."
- Job titles, organization names, expertise areas
- Cross-references: "As we discussed earlier with Dr. X..."
- Caller identification: "You're on the air with..."

## Output Format

Return a JSON array of guests identified in this segment:

[
  {
    "name_he": "שם בעברית",
    "name_en": "Name Transliteration",
    "title": "Job title or role",
    "affiliation": "Party/Organization/Media outlet",
    "speaker_label": "SPEAKER_00 or SPEAKER_UNKNOWN if unclear",
    "confidence": 0.95
  }
]

## Guidelines

1. `confidence` is 0.0-1.0:
   - 0.9+: Explicit introduction or very clear context
   - 0.7-0.9: Strong context clues but not explicitly named
   - 0.5-0.7: Probable from context but uncertain
   - <0.5: Possible but speculative

2. Extract transliterated names as they would be written in English (phonetic, not strict transliteration)

3. For ambiguous speakers: use "SPEAKER_UNKNOWN" if diarization labels aren't clear

4. Affiliation: Party/organization/publication, NOT generic roles like "host" or "caller"

5. Return empty array `[]` if no guests can be identified

Return ONLY valid JSON array. No additional text."""


def format_segment(segment) -> str:
    """Format a Segment for guest identification."""
    return f"""[{segment.start:.0f}s - {segment.end:.0f}s] {segment.type.upper()}

Available speaker labels: {', '.join(set(segment.speakers))}

Transcript:
{segment.raw_text}"""
