#!/usr/bin/env python3
"""Test the full analysis pipeline: segmentation → topics → guests → sentiment → ads."""

from pathlib import Path
from loguru import logger

from conftest import load_transcript_from_json
from talk_show_analyzer.analysis import (
    Segmenter,
    TopicExtractor,
    GuestIdentifier,
    SentimentAnalyzer,
    aggregate_ads,
)

# Setup logging
logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {message}",
)


def main():
    """Run full analysis pipeline."""

    # Load transcript
    transcript_file = Path("test_output/galatz_transcript.json")
    if not transcript_file.exists():
        logger.error(f"Transcript not found: {transcript_file}")
        return

    logger.info(f"Loading transcript from: {transcript_file}\n")
    transcript = load_transcript_from_json(transcript_file)

    # ======================
    # STEP 1: SEGMENTATION
    # ======================
    logger.info("\n" + "=" * 60)
    logger.info("STEP 1: SEGMENTATION")
    logger.info("=" * 60 + "\n")

    segmenter = Segmenter()
    segments_list = segmenter.segment(transcript)

    logger.info(f"\nSegmented into {len(segments_list)} segments")

    # ======================
    # STEP 2: TOPIC EXTRACTION
    # ======================
    logger.info("\n" + "=" * 60)
    logger.info("STEP 2: TOPIC EXTRACTION")
    logger.info("=" * 60 + "\n")

    topic_extractor = TopicExtractor()
    topic_analyses = topic_extractor.extract_topics(segments_list)

    logger.info(f"\nExtracted topics for {len(topic_analyses)} segments")

    # ======================
    # STEP 3: GUEST IDENTIFICATION
    # ======================
    logger.info("\n" + "=" * 60)
    logger.info("STEP 3: GUEST IDENTIFICATION")
    logger.info("=" * 60 + "\n")

    guest_identifier = GuestIdentifier()
    guest_analyses = guest_identifier.identify_guests(segments_list)

    total_guests = sum(len(g.guests) for g in guest_analyses)
    logger.info(f"\nIdentified {total_guests} guests across {len(guest_analyses)} segments")

    # ======================
    # STEP 4: SENTIMENT ANALYSIS
    # ======================
    logger.info("\n" + "=" * 60)
    logger.info("STEP 4: SENTIMENT ANALYSIS")
    logger.info("=" * 60 + "\n")

    sentiment_analyzer = SentimentAnalyzer()
    sentiment_analyses = sentiment_analyzer.analyze_sentiments(topic_analyses)

    total_sentiments = sum(len(s.sentiments) for s in sentiment_analyses)
    logger.info(f"\nAnalyzed sentiment for {total_sentiments} speaker-topic combinations")

    # ======================
    # STEP 5: ADS AGGREGATION
    # ======================
    logger.info("\n" + "=" * 60)
    logger.info("STEP 5: ADS AGGREGATION")
    logger.info("=" * 60 + "\n")

    ads_report = aggregate_ads(segments_list, transcript.duration)

    # ======================
    # PRINT RESULTS
    # ======================
    logger.info("\n\n" + "=" * 60)
    logger.info("ANALYSIS RESULTS SUMMARY")
    logger.info("=" * 60)

    logger.info(f"\n📊 SEGMENTATION:")
    for i, seg in enumerate(segments_list, 1):
        duration = seg.end - seg.start
        logger.info(
            f"  {i}. [{seg.type:12s}] {seg.start:6.0f}s - {seg.end:6.0f}s "
            f"({duration:5.0f}s): {seg.summary}"
        )

    logger.info(f"\n🎯 TOPICS ({len(topic_analyses)} segments analyzed):")
    for analysis in topic_analyses:
        logger.info(f"  • {analysis.main_topic.name_en} ({analysis.main_topic.category})")
        logger.info(f"    {analysis.main_topic.summary_en}")
        if analysis.subtopics:
            for sub in analysis.subtopics:
                logger.info(f"    └─ {sub.name_en} ({sub.category})")

    logger.info(f"\n👥 GUESTS ({total_guests} identified):")
    for analysis in guest_analyses:
        for guest in analysis.guests:
            logger.info(
                f"  • {guest.name_en} ({guest.title}), {guest.affiliation} "
                f"[confidence: {guest.confidence:.0%}]"
            )

    logger.info(f"\n💭 SENTIMENT ({total_sentiments} analyzed):")
    for analysis in sentiment_analyses:
        for sentiment in analysis.sentiments:
            score_str = f"{sentiment.score:+.2f}"
            logger.info(
                f"  • {sentiment.topic}: {score_str} ({sentiment.tone}), "
                f"speaker {sentiment.speaker_label}"
            )

    logger.info(f"\n📺 ADS:")
    logger.info(f"  Total duration: {ads_report.total_duration:.0f}s ({ads_report.total_duration/60:.1f} min)")
    logger.info(f"  Ad duration: {ads_report.ad_duration:.0f}s ({ads_report.ad_duration/60:.1f} min)")
    logger.info(f"  Ad percentage: {ads_report.ad_percentage:.1f}%")
    logger.info(f"  Ad segments: {ads_report.ad_count}")

    # ======================
    # SAVE TO JSON
    # ======================
    output_file = Path("test_output/galatz_analysis.json")

    analysis_output = {
        "transcript": {
            "duration": transcript.duration,
            "language": transcript.language,
            "word_count": transcript.word_count,
        },
        "segmentation": [
            {
                "type": seg.type,
                "start": seg.start,
                "end": seg.end,
                "duration": seg.end - seg.start,
                "summary": seg.summary,
            }
            for seg in segments_list
        ],
        "topics": [
            {
                "segment_type": analysis.segment.type,
                "main_topic": {
                    "name_he": analysis.main_topic.name_he,
                    "name_en": analysis.main_topic.name_en,
                    "category": analysis.main_topic.category,
                    "summary_he": analysis.main_topic.summary_he,
                    "summary_en": analysis.main_topic.summary_en,
                },
                "subtopics": [
                    {
                        "name_he": t.name_he,
                        "name_en": t.name_en,
                        "category": t.category,
                        "summary_en": t.summary_en,
                    }
                    for t in analysis.subtopics
                ],
            }
            for analysis in topic_analyses
        ],
        "guests": [
            {
                "name_he": guest.name_he,
                "name_en": guest.name_en,
                "title": guest.title,
                "affiliation": guest.affiliation,
                "speaker_label": guest.speaker_label,
                "confidence": guest.confidence,
            }
            for analysis in guest_analyses
            for guest in analysis.guests
        ],
        "sentiment": [
            {
                "topic": sentiment.topic,
                "speaker": sentiment.speaker_label,
                "score": sentiment.score,
                "tone": sentiment.tone,
                "quotes": sentiment.quotes,
            }
            for analysis in sentiment_analyses
            for sentiment in analysis.sentiments
        ],
        "ads": {
            "total_duration": ads_report.total_duration,
            "ad_duration": ads_report.ad_duration,
            "ad_percentage": ads_report.ad_percentage,
            "ad_count": ads_report.ad_count,
        },
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(analysis_output, f, ensure_ascii=False, indent=2)

    logger.info(f"\n\n✓ Full analysis saved to: {output_file}\n")


if __name__ == "__main__":
    main()
