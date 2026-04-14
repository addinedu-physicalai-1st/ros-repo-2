#!/bin/bash
# Usage: ./remove_audio.sh input.mp4 [output.mp4]

INPUT="$1"
OUTPUT="${2:-${INPUT%.*}_muted.${INPUT##*.}}"

if [ -z "$INPUT" ]; then
  echo "Usage: $0 input.mp4 [output.mp4]"
  exit 1
fi

if [ ! -f "$INPUT" ]; then
  echo "Error: File not found — $INPUT"
  exit 1
fi

ffmpeg -i "$INPUT" -an -c:v copy "$OUTPUT"
echo "Done: $OUTPUT"
