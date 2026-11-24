#!/usr/bin/env bash
# Which clusters CI starts, and which releases each of them tries. "cannot" tries first what the walker must not be able to do.
# It stands here and not in the workflow, so that the workflow never has to change. tests/test_files.py looks that every
# release is tried once.
set -euo pipefail
echo 'words=["cannot good errors", "few slow", "never-ready refuses", "dies drops"]'
