"""Transcription + diarization using Faster-Whisper + Pyannote."""

import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import torch
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline
from huggingface_hub import login
from loguru import logger

from talk_show_analyzer.config import settings
from talk_show_analyzer.transcription.chunker import chunk_audio


@dataclass
class SpeakerSegment:
    """A speaker segment in the transcript."""

    start: float
    end: float
    speaker: str
    text: str


@dataclass
class TranscriptionResult:
    """Result of transcription + diarization."""

    raw_text: str
    language: str
    duration: float
    word_count: int
    segments: list[SpeakerSegment]  # Diarized segments with speaker labels

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "raw_text": self.raw_text,
            "language": self.language,
            "duration": self.duration,
            "word_count": self.word_count,
            "segments": [
                {
                    "start": seg.start,
                    "end": seg.end,
                    "speaker": seg.speaker,
                    "text": seg.text,
                }
                for seg in self.segments
            ],
        }


class Transcriber:
    """Transcribe + diarize audio using Faster-Whisper + Pyannote."""

    def __init__(
        self,
        model_size: str | None = None,
        device: str = "auto",
        compute_type: str = "float16",
        enable_diarization: bool = True,
        beam_size: int | None = None,
        vad_min_silence_ms: int | None = None,
    ):
        """
        Initialize transcriber.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large, large-v3).
                        If None, uses settings.whisper_model
            device: Device to use (cuda, cpu, auto)
            compute_type: Computation type (float16, float32, int8, etc)
            enable_diarization: Whether to perform speaker diarization
            beam_size: Beam search width. If None, uses settings.whisper_beam_size
            vad_min_silence_ms: Silence duration for VAD. If None, uses settings.whisper_vad_min_silence_ms
        """
        if model_size is None:
            model_size = settings.whisper_model
        if beam_size is None:
            beam_size = settings.whisper_beam_size
        if vad_min_silence_ms is None:
            vad_min_silence_ms = settings.whisper_vad_min_silence_ms

        self.beam_size = beam_size
        self.vad_min_silence_ms = vad_min_silence_ms

        logger.info(f"Loading Whisper model: {model_size}")
        self.whisper_model = WhisperModel(
            model_size, device=device, compute_type=compute_type
        )

        self.enable_diarization = enable_diarization
        self.diarization_pipeline = None

        if enable_diarization:
            logger.info("Loading Pyannote diarization pipeline")
            # Requires HuggingFace token for authentication
            try:
                if settings.hf_token:
                    login(token=settings.hf_token, add_to_git_credential=False)
                self.diarization_pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-community-1"
                )
                # Convert device string to torch.device for Pyannote v3.0
                if device == "auto":
                    device_obj = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                else:
                    device_obj = torch.device(device)
                self.diarization_pipeline = self.diarization_pipeline.to(device_obj)
            except Exception as e:
                logger.warning(f"Failed to load diarization pipeline: {e}")
                logger.warning("Continuing without diarization")
                self.diarization_pipeline = None
                self.enable_diarization = False

    def transcribe(
        self,
        audio_path: str | Path,
        language: str = "he",
        num_speakers: Optional[int] = None,
    ) -> TranscriptionResult:
        """
        Transcribe and diarize an audio file.

        Args:
            audio_path: Path to audio file
            language: Language code (he for Hebrew)
            num_speakers: Expected number of speakers (optional, for diarization)

        Returns:
            TranscriptionResult with transcript and speaker segments
        """
        audio_path = Path(audio_path)
        logger.info(f"Transcribing: {audio_path}")

        # Transcribe with Faster-Whisper
        logger.info(f"Running Whisper transcription (language={language})")
        segments, info = self.whisper_model.transcribe(
            str(audio_path),
            language=language,
            beam_size=self.beam_size,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": self.vad_min_silence_ms},
        )

        # Collect full transcript
        segments_list = list(segments)
        raw_text = " ".join(seg.text.strip() for seg in segments_list)
        word_count = len(raw_text.split())

        logger.info(
            f"Transcription complete: {len(segments_list)} segments, "
            f"{word_count} words, duration={info.duration:.1f}s"
        )

        # Apply diarization if enabled
        if self.enable_diarization and self.diarization_pipeline:
            diarized_segments = self._apply_diarization(
                audio_path, segments_list, num_speakers
            )
        else:
            # Fallback: create speaker segments without diarization
            diarized_segments = [
                SpeakerSegment(
                    start=seg.start,
                    end=seg.end,
                    speaker="SPEAKER_00",  # Unknown speaker
                    text=seg.text,
                )
                for seg in segments_list
            ]

        return TranscriptionResult(
            raw_text=raw_text,
            language=language,
            duration=info.duration,
            word_count=word_count,
            segments=diarized_segments,
        )

    def _apply_diarization(
        self,
        audio_path: Path,
        whisper_segments,
        num_speakers: Optional[int] = None,
    ) -> list[SpeakerSegment]:
        """
        Apply speaker diarization to transcript segments.

        Args:
            audio_path: Path to audio
            whisper_segments: Transcription segments from Whisper
            num_speakers: Optional expected speaker count

        Returns:
            List of SpeakerSegment with speaker labels assigned
        """
        logger.info("Running speaker diarization...")

        try:
            # Pre-decode to a 16kHz mono tensor and pass the in-memory dict form.
            # Feeding MP3 paths directly causes pyannote sample-count mismatches
            # (MP3 decoders return ~158895 samples for a 10s @16kHz chunk vs the
            # expected 160000); the dict form skips pyannote's internal decode.
            import torchaudio

            waveform, sr = torchaudio.load(str(audio_path))
            if waveform.shape[0] > 1:
                waveform = waveform.mean(dim=0, keepdim=True)
            target_sr = 16000
            if sr != target_sr:
                waveform = torchaudio.functional.resample(waveform, sr, target_sr)
            audio_input = {"waveform": waveform, "sample_rate": target_sr}

            diarization_kwargs = {"num_speakers": num_speakers} if num_speakers else {}
            diarization_output = self.diarization_pipeline(
                audio_input,
                **diarization_kwargs,
            )

            # pyannote v4 returns DiarizeOutput; use exclusive_speaker_diarization
            # (no overlapping turns) for cleaner whisper-segment → speaker mapping.
            annotation = diarization_output.exclusive_speaker_diarization

            # Map Whisper segments to speakers based on timestamp overlap.
            # Labels from pyannote are already formatted like "SPEAKER_00".
            diarized_segments = []
            for seg in whisper_segments:
                seg_mid = (seg.start + seg.end) / 2
                speaker = "SPEAKER_UNKNOWN"
                for turn, _, speaker_obj in annotation.itertracks(yield_label=True):
                    if turn.start <= seg_mid < turn.end:
                        speaker = str(speaker_obj)
                        break

                diarized_segments.append(
                    SpeakerSegment(
                        start=seg.start,
                        end=seg.end,
                        speaker=speaker,
                        text=seg.text,
                    )
                )

            logger.info(f"Diarization complete: {len(diarized_segments)} speaker segments")
            return diarized_segments

        except Exception as e:
            logger.error(f"Diarization failed: {e}")
            logger.warning("Falling back to no diarization")
            return [
                SpeakerSegment(
                    start=seg.start,
                    end=seg.end,
                    speaker="SPEAKER_00",
                    text=seg.text,
                )
                for seg in whisper_segments
            ]

    def transcribe_file(
        self,
        audio_path: str | Path,
        output_json: Optional[str | Path] = None,
        language: str = "he",
    ) -> TranscriptionResult:
        """
        Transcribe a file and optionally save result as JSON.

        Args:
            audio_path: Path to audio file
            output_json: Optional path to save result as JSON
            language: Language code

        Returns:
            TranscriptionResult
        """
        result = self.transcribe(audio_path, language=language)

        if output_json:
            output_json = Path(output_json)
            output_json.parent.mkdir(parents=True, exist_ok=True)
            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info(f"Saved transcript to: {output_json}")

        return result
