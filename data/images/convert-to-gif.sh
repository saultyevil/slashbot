#!/bin/bash

for input in "$@"; do
    [[ "$input" == *.mp4 ]] || { echo "Skipping (not mp4): $input"; continue; }
    [[ -f "$input" ]] || { echo "Skipping (not found): $input"; continue; }

    output="${input%.mp4}.gif"

    echo "Converting: $input → $output"

    ffmpeg -i "$input" -vf "fps=15,scale=640:-1:flags=lanczos" -loop 0 "$output"

    echo "Saved: $output"
done
