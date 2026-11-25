#!/usr/bin/env bash
# Which clusters CI starts, and which releases each of them tries. "cannot" tries first what the walker must not be able to do,
# and "walls" what the two walls have to refuse.
# It stands here and not in the workflow, so that the workflow never has to change. tests/test_files.py looks that every
# release is tried once in each repetition.
# One run shows that it works and not how often. A number after it repeats everything so many times.
set -euo pipefail

lists=(
  "cannot good errors"
  "walls few slow"
  "never-ready refuses"
  "dies drops"
  "unasked blind"
  "restarted interrupted"
)
repeat="${1:-20}"
[[ "$repeat" =~ ^[1-9][0-9]?$ ]] || { echo "How many times? Not $repeat." >&2; exit 2; }

words=()
for n in $(seq -w "$repeat"); do
  for list in "${lists[@]}"; do
    # No two jobs may have the same name.
    if [ "$repeat" = 1 ]; then words+=("\"$list\""); else words+=("\"run-$n $list\""); fi
  done
done
(IFS=, && echo "words=[${words[*]}]")
