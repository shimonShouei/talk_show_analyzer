#!/usr/bin/env bash
# record_loop.sh NAME URL OUTROOT [UNTIL_HHMM]  - records a stream into OUTROOT/YYYY-MM-DD/NAME/partNN_HHMMSS.mp3,
# starting a new part after any stall/disconnect (rw_timeout 20 s).
name=$1; url=$2; root=$3; until=${4:-2359}
while [ "$(date +%H%M)" -lt "$until" ]; do
  d=$(date +%F); dir="$root/$d/$name"; mkdir -p "$dir"
  n=$(printf "%02d" $(( $(ls "$dir"/part*.mp3 2>/dev/null | wc -l) + 1 )))
  ffmpeg -nostdin -v error -rw_timeout 20000000 -i "$url" -c copy -t $(( 86400 - $(date +%s) % 86400 )) "$dir/part${n}_$(date +%H%M%S).mp3" 2>>"$dir/ff.log"
  sleep 3
done
