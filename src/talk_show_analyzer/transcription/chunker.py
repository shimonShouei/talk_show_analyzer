"""Split audio into chunks for transcription."""

from pathlib import Path
import librosa
import soundfile as sf
from loguru import logger


def chunk_audio(
    audio_path: str | Path,
    chunk_duration_seconds: int = 1500,  # 25 minutes
    overlap_seconds: int = 60,  # 1 minute overlap
    output_dir: str | Path = "./chunks",
) -> list[str]:
    """
    Split an audio file into overlapping chunks.

    Args:
        audio_path: Path to input audio file
        chunk_duration_seconds: Chunk length (default 25 min for Whisper's context)
        overlap_seconds: Overlap between consecutive chunks
        output_dir: Directory to save chunks

    Returns:
        List of chunk file paths
    """
    audio_path = Path(audio_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load audio
    logger.info(f"Loading audio: {audio_path}")
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)
    logger.info(f"Audio duration: {duration:.1f}s ({duration/60:.1f} min)")

    chunks = []
    step_seconds = chunk_duration_seconds - overlap_seconds
    start_sec = 0

    chunk_num = 0
    while start_sec < duration:
        end_sec = min(start_sec + chunk_duration_seconds, duration)
        start_sample = int(start_sec * sr)
        end_sample = int(end_sec * sr)

        chunk_audio = y[start_sample:end_sample]
        chunk_path = output_dir / f"{audio_path.stem}_chunk_{chunk_num:03d}.wav"

        sf.write(str(chunk_path), chunk_audio, sr)
        chunks.append(str(chunk_path))

        logger.info(
            f"Chunk {chunk_num}: {start_sec:.1f}s - {end_sec:.1f}s "
            f"({chunk_audio.shape[0] / sr:.1f}s) → {chunk_path.name}"
        )

        chunk_num += 1
        start_sec += step_seconds

    logger.info(f"Created {len(chunks)} chunks")
    return chunks
