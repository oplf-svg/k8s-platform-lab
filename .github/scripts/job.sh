#!/usr/bin/env bash
# One cluster, and the releases that the words name. What was counted is on the page of the run, also if it was not right.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p build/public
# Which files these are, so that runs can be put together only if they are the same.
git rev-parse 'HEAD^{tree}' > build/public/tree.txt
trap 'cat build/public/summary.md >> "${GITHUB_STEP_SUMMARY:-/dev/null}" 2> /dev/null || true' EXIT
# Which repetition it is says nothing but that.
if [[ "${1:-}" =~ ^run-[0-9]+$ ]]; then shift; fi
tries=()
while [ "${1:-}" = cannot ] || [ "${1:-}" = walls ]; do
  tries+=("$1")
  shift
done
bash .github/scripts/cluster.sh "$@"
for one in "${tries[@]}"; do bash ".github/scripts/$one.sh"; done
# Some releases are tried while a part of the cluster is away. Only here, where the cluster is thrown away afterwards.
BREAK=.github/scripts/break.sh bash .github/scripts/releases.sh "$@"
