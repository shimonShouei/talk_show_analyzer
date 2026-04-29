"""Configuration for talk show analyzer."""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    """App configuration from environment variables."""

    # Database
    database_url: str = "postgresql://localhost/talk_show_analyzer"

    # Audio
    audio_format: str = "mp3"
    audio_bitrate: str = "128k"
    audio_sample_rate: int = 16000
    audio_channels: int = 1

    # Transcription
    whisper_model: str = "large-v3"  # tiny, base, small, medium, large, large-v3
    whisper_device: str = "auto"  # cuda, cpu, auto
    whisper_compute_type: str = "float16"  # float16, float32, int8, etc
    whisper_beam_size: int = 5  # Higher = better quality, slower
    whisper_vad_min_silence_ms: int = 500  # Silence duration for VAD (tuned for radio)
    diarization_enabled: bool = True

    # Pyannote config
    pyannote_device: str = "auto"  # cuda, cpu, auto
    pyannote_num_speakers: Optional[int] = None  # Auto-detect if None

    # HuggingFace token for Pyannote models
    hf_token: str = ""

    # API
    anthropic_api_key: str = ""

    # Storage
    output_dir: Path = Path("./data")
    s3_bucket: Optional[str] = None
    gcs_bucket: Optional[str] = None

    # Logging
    log_level: str = "INFO"

    @field_validator("pyannote_num_speakers", mode="before")
    @classmethod
    def validate_num_speakers(cls, v):
        """Convert empty string to None."""
        if v == "" or v is None:
            return None
        return int(v) if v else None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
