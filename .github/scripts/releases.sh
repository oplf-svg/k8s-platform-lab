#!/usr/bin/env bash
# Counts from outside while one release after the other is tried. It changes nothing: the walker in the cluster does, when a
# run is marked as begun. So this is the same for a cluster in CI and for one in a cloud, and needs no right in either.
# Words after it name the releases, in the order of the list. FRONT is where the front is.
set -euo pipefail
cd "$(dirname "$0")/../.."

front="${FRONT:-127.0.0.1:30080}"
out=build/public
mkdir -p "$out"
said() {
  curl --fail --silent --max-time 10 "http://$front/status/release" \
    | jq --raw-output '[.data.result[] | select(.metric.name == "standin") | .metric.phase] | join(",")'
}
well() { # waits until the old release, or the new good one, is alone
  for _ in $(seq 120); do
    if [ "$(said || true)" = Completed ]; then return 0; fi
    sleep 5
  done
  echo "It never became well: $(said || true)"
  return 1
}
# Long enough for what has to happen, and a minute more to see that it stays so.
seconds() {
  case "$1" in
    good) echo 300 ;;
    errors | refuses | drops) echo 130 ;;
    slow) echo 140 ;;
    few) echo 190 ;;
    never-ready | dies) echo 220 ;;
    *) echo "There is no release called $1." >&2 && return 1 ;;
  esac
}

[ $# -gt 0 ] || { echo "Which releases?"; exit 2; }
failed=()
for name in "$@"; do
  echo "::group::$name"
  long="$(seconds "$name")"
  well
  python3 clients/clients.py --front "$front" --run "$name" --seconds "$long" --rate 50 \
    --out "$out/$name.clients.jsonl" --status "$out/$name.status.json"
  curl --fail --silent --show-error --max-time 60 --output "$out/$name.front.jsonl" "http://$front/lists/answers"
  # What is wrong in the numbers is said by the judge.
  python3 count/count.py --clients "$out/$name.clients.jsonl" --front "$out/$name.front.jsonl" --run "$name" > "$out/$name.counted.json" || true
  # Only to look at afterwards, and only where the cluster is on this machine.
  if docker inspect lab-control-plane > /dev/null 2>&1; then
    docker exec lab-control-plane kubectl --kubeconfig /etc/kubernetes/admin.conf --namespace shop \
      get rollout,analysisrun,pod,job --output wide > "$out/$name.cluster.txt" || true
    docker exec lab-control-plane kubectl --kubeconfig /etc/kubernetes/admin.conf --namespace shop \
      logs job/walker --tail 50 >> "$out/$name.cluster.txt" 2>&1 || true
  fi
  python3 count/judge.py --scenario "$name" --counted "$out/$name.counted.json" --clients "$out/$name.clients.jsonl" \
    --status "$out/$name.status.json" | tee -a "$out/summary.md" || failed+=("$name")
  echo "::endgroup::"
done
[ ${#failed[@]} -eq 0 ] || { echo "Not as it has to be: ${failed[*]}"; exit 1; }
