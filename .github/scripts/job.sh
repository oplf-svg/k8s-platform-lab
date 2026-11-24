#!/usr/bin/env bash
# One cluster, and the releases that the words name. What was counted is on the page of the run, also if it was not right.
set -euo pipefail
cd "$(dirname "$0")/../.."
trap 'cat build/public/summary.md >> "${GITHUB_STEP_SUMMARY:-/dev/null}" 2> /dev/null || true' EXIT
cannot=no
if [ "${1:-}" = cannot ]; then
  cannot=yes
  shift
fi
bash .github/scripts/cluster.sh "$@"
[ "$cannot" = no ] || bash .github/scripts/cannot.sh
bash .github/scripts/releases.sh "$@"
