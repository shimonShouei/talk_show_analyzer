#!/bin/bash
# usage: rec_station.sh <name> <url> <referer> <end HH:MM>
NAME=$1; URL=$2; REF=$3; END=$4
DAY=$(date +%F)
OUT=~/tsa_data/recordings/$DAY/$NAME; mkdir -p "$OUT"
END_TS=$(date -d "$DAY $END" +%s)
n=0
while [ $(date +%s) -lt $END_TS ]; do
  left=$(( END_TS - $(date +%s) ))
  n=$((n+1)); f="$OUT/part$(printf %02d $n)_$(date +%H%M%S).mp3"
  echo "$(date -Is) start part $n ($left s left) -> $f" >> "$OUT/rec.log"
  ffmpeg -nostdin -loglevel warning -headers "Referer: $REF"$'\r\n' \
    -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30 \
    -i "$URL" -t "$left" -c copy "$f" >> "$OUT/rec.log" 2>&1
  echo "$(date -Is) ffmpeg exit $?" >> "$OUT/rec.log"
  [ $(date +%s) -lt $END_TS ] && sleep 5
done
echo "$(date -Is) REC_DONE" >> "$OUT/rec.log"
