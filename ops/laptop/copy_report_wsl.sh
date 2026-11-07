#!/bin/bash
# Historical copy from the Windows profile into ~/tsa_data. Not a pipeline step.
set -euo pipefail
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$_d/../require_win_user.sh"
mkdir -p ~/tsa_data/repeats/spotcheck_2026-11-04
cp "/mnt/c/Users/${WIN_USER}/spotcheck_2026-11-04_report.md" ~/tsa_data/repeats/spotcheck_2026-11-04/report.md
ls -lah ~/tsa_data/repeats/spotcheck_2026-11-04/report.md
echo "clips:" $(find ~/tsa_data/repeats/spotcheck_2026-11-04 -name 'c*.mp3' | wc -l)
echo "txts:" $(find ~/tsa_data/repeats/spotcheck_2026-11-04 -name 'c*.txt' | wc -l)
