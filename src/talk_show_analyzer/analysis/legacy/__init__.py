"""Legacy analysis modules — superseded by ThematicAnalyzer.

These modules are kept for reference and backward compatibility but are no longer
part of the active pipeline. Use ThematicAnalyzer for new analysis work.

Deprecated modules:
- segmenter.py — Window-based show segmentation. Moved to ThematicAnalyzer.
- topics.py — Topic extraction per segment. Superseded by ThematicAnalyzer stages 1-2.
- sentiment.py — Per-topic sentiment analysis. Replaced by speaker_insights in ThematicAnalyzer.
- guests.py — Guest identification. Replaced by UnifiedSpeakerIdentifier.
- ads.py — Ad aggregation. Not yet integrated into new pipeline.
"""
