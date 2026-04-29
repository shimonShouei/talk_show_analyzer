#!/usr/bin/env python
"""Run the Streamlit dashboard."""

import subprocess
import sys
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Run Streamlit
subprocess.run(
    [
        "streamlit",
        "run",
        str(Path(__file__).parent / "src/talk_show_analyzer/dashboard/app.py"),
    ],
    check=False,
)
