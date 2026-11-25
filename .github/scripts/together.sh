#!/usr/bin/env bash
# Judges everything that the clusters of one run left behind again, and all of it together. The word after it says how many times
# each release had to be tried.
set -euo pipefail
cd "$(dirname "$0")/../.."
tree="$(git rev-parse 'HEAD^{tree}')"
python3 count/many.py build/all "${1-1}" "$tree" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
