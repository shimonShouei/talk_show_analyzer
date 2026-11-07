"""Lightweight checks for the integrated local MVP notes.

No audio, no model download, no systemd, no recording.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WIN_USER_SCRIPTS = [
    ROOT / "ops/require_win_user.sh",
    ROOT / "tools/ads/install_ad_tools.sh",
    ROOT / "ops/laptop/install_ad_tools.sh",
    ROOT / "ops/laptop/copy_report_wsl.sh",
    ROOT / "ops/laptop/refine_and_pull.sh",
    ROOT / "ops/laptop/start_rec.sh",
]


def _run(script: Path, env: dict) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    merged.pop("WIN_USER", None)
    merged.pop("TSA_WIN_USER_CHECKED", None)
    merged.update(env)
    return subprocess.run(
        ["bash", str(script)],
        cwd=ROOT,
        env=merged,
        text=True,
        capture_output=True,
        timeout=15,
    )


class WinUserGuardTests(unittest.TestCase):
    def test_unset_is_refused(self):
        for script in WIN_USER_SCRIPTS:
            with self.subTest(script=script.name):
                result = _run(script, {})
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("WIN_USER", result.stderr)

    def test_path_is_refused(self):
        result = _run(ROOT / "ops/require_win_user.sh", {"WIN_USER": "../Administrator"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("WIN_USER", result.stderr)

    def test_explicit_folder_name_is_accepted(self):
        result = _run(ROOT / "ops/require_win_user.sh", {"WIN_USER": "YourName"})
        self.assertEqual(result.returncode, 0, result.stderr)


class CaveatTests(unittest.TestCase):
    def test_dependency_pin_and_documented_limits(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('av==15.1.0', pyproject)
        report = (ROOT / "docs/reports/spotcheck_2026-11-04_report.md").read_text(encoding="utf-8")
        self.assertIn("74×", report)
        self.assertIn("120×", report)
        self.assertIn("not commercial ad minutes", report)
        style = (ROOT / "experiments/audio_style_2026-11-07/README.md").read_text(encoding="utf-8")
        self.assertIn("948", style)
        self.assertIn("music versus speech", style)
        self.assertIn("not a proven ad classifier", style)
        gold = (ROOT / "data/ads/PROVENANCE.md").read_text(encoding="utf-8")
        self.assertIn("103FM", gold)
        self.assertIn("not in the repo", gold.lower())
        nov8 = (ROOT / "ops/systemd_20261108/README.md").read_text(encoding="utf-8")
        self.assertIn("2026-11-08", nov8)
        self.assertIn("not a daily schedule", nov8)

    def test_extract_refuses_missing_paths_without_importing_models(self):
        env = os.environ.copy()
        for key in ("TSA_HOUR1_MP3", "TSA_RECORDINGS_ROOT", "TSA_GOLD_CSV"):
            env.pop(key, None)
        result = subprocess.run(
            ["python3", str(ROOT / "experiments/audio_style_2026-11-07/extract.py")],
            cwd=ROOT / "experiments/audio_style_2026-11-07",
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("TSA_HOUR1_MP3", result.stderr)
        self.assertNotIn("panns", result.stderr.lower())

    def test_build_labels_refuses_missing_data_root(self):
        env = os.environ.copy()
        env.pop("TSA_DATA_ROOT", None)
        result = subprocess.run(
            ["python3", str(ROOT / "tools/ads/build_labels.py")],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("TSA_DATA_ROOT", result.stderr)


if __name__ == "__main__":
    unittest.main()
