#!/usr/bin/env python
"""Run the Streamlit dashboard."""

import subprocess
import sys
from pathlib import Path

# Add src to Python path
repo_root = Path(__file__).parent.parent
src_path = repo_root / "src"
sys.path.insert(0, str(src_path))

# Run Streamlit
subprocess.run(
    [
        "streamlit",
        "run",
        str(repo_root / "src/talk_show_analyzer/dashboard/app.py"),
    ],
    check=False,
)
