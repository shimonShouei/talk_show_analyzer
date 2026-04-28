"""Configuration for talk show analyzer."""

from pathlib import Path
from pydantic_settings import BaseSettings


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
    whisper_model: str = "base"  # base, small, medium, large
    whisper_device: str = "auto"  # cuda, cpu, auto
    whisper_compute_type: str = "float16"  # float16, float32, int8, etc
    diarization_enabled: bool = True

    # Pyannote config
    pyannote_device: str = "auto"  # cuda, cpu, auto
    pyannote_num_speakers: int | None = None  # Auto-detect if None

    # API
    anthropic_api_key: str = ""

    # Storage
    output_dir: Path = Path("./data")
    s3_bucket: str | None = None
    gcs_bucket: str | None = None

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
