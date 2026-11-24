#!/usr/bin/env bash
# The tests that need no cluster, and then the proof that they can fail. A few minutes, and nothing but Python 3.12 or newer.
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -W error -m unittest discover --start-directory tests --verbose
python3 tests/wrong.py

# A branch that must not be merged yet has this file: one line that says why, and until when. It comes last, so that everything
# else is seen. A link is not followed, because the log is public.
if [ -f HOLD ] && [ ! -L HOLD ]; then
  echo "Not to be merged yet: $(head -n 1 HOLD)"
  exit 1
elif [ -e HOLD ] || [ -L HOLD ]; then
  echo "Not to be merged yet: HOLD is not a plain file."
  exit 1
fi
