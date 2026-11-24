#!/usr/bin/env bash
# The tests that need no cluster, and then the proof that they can fail. A few minutes, and nothing but Python 3.12 or newer.
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -W error -m unittest discover --start-directory tests --verbose
python3 tests/wrong.py
