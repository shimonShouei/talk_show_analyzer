#!/usr/bin/env python3
"""Quick validation of GPU setup and dependencies."""

import sys
from pathlib import Path

print("=" * 60)
print("GPU SETUP VALIDATION")
print("=" * 60)

# Check Python version
import platform
print(f"\n✓ Python {platform.python_version()}")

# Check GPU availability
try:
    import torch
    has_cuda = torch.cuda.is_available()
    print(f"{'✓' if has_cuda else '✗'} CUDA available: {has_cuda}")
    if has_cuda:
        print(f"  GPU count: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
except ImportError:
    print("✗ PyTorch not installed (needed for GPU detection)")

# Check key dependencies
packages = {
    "faster_whisper": "Speech-to-text",
    "pyannote": "Speaker diarization",
    "anthropic": "Claude API",
    "sqlalchemy": "Database ORM",
    "streamlit": "Dashboard",
    "pydantic": "Configuration",
}

print("\n" + "=" * 60)
print("DEPENDENCIES")
print("=" * 60)

missing = []
for pkg, desc in packages.items():
    try:
        __import__(pkg.replace("-", "_"))
        print(f"✓ {pkg:20} {desc}")
    except ImportError:
        print(f"✗ {pkg:20} {desc}")
        missing.append(pkg)

if missing:
    print(f"\n⚠ Missing packages: {', '.join(missing)}")
    sys.exit(1)

# Check project structure
print("\n" + "=" * 60)
print("PROJECT STRUCTURE")
print("=" * 60)

repo_root = Path(__file__).parent
required_dirs = [
    "src/talk_show_analyzer",
    "src/talk_show_analyzer/transcription",
    "src/talk_show_analyzer/recorder",
]

all_exist = True
for dir_path in required_dirs:
    full_path = repo_root / dir_path
    exists = full_path.exists()
    print(f"{'✓' if exists else '✗'} {dir_path}")
    if not exists:
        all_exist = False

# Check environment variables
print("\n" + "=" * 60)
print("ENVIRONMENT")
print("=" * 60)

import os
env_vars = {
    "HF_TOKEN": "HuggingFace token (for Pyannote)",
    "ANTHROPIC_API_KEY": "Claude API key",
    "DATABASE_URL": "PostgreSQL connection",
}

for var, desc in env_vars.items():
    value = os.getenv(var)
    if value:
        masked = value[:5] + "..." if len(value) > 8 else "***"
        print(f"✓ {var:20} {masked}")
    else:
        print(f"⚠ {var:20} NOT SET ({desc})")

# Test imports
print("\n" + "=" * 60)
print("IMPORT TEST")
print("=" * 60)

try:
    from talk_show_analyzer.transcription import Transcriber
    print("✓ Transcriber imports successfully")
except Exception as e:
    print(f"✗ Failed to import Transcriber: {e}")
    sys.exit(1)

try:
    from talk_show_analyzer.recorder import record_station, check_all_streams
    print("✓ Recorder imports successfully")
except Exception as e:
    print(f"✗ Failed to import recorder: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
if all_exist and not missing:
    print("✓ ALL CHECKS PASSED - Ready to run!")
    sys.exit(0)
else:
    print("✗ Some checks failed")
    sys.exit(1)
