#!/usr/bin/env bash
# Tries what the two walls have to refuse (docs/walls.md), and what they have to let through. Each way is first tried without the
# wall, because a way that was never open proves nothing when it is closed. Only for a cluster that is thrown away.
set -euo pipefail
cd "$(dirname "$0")/../.."

kube() { docker exec --interactive lab-control-plane kubectl --kubeconfig /etc/kubernetes/admin.conf --namespace shop "$@"; }
name_of() { kube get pod --selector "app=$1" --field-selector status.phase=Running --output name | head -1; }
known="$(grep -m1 '/python:' k8s/walls/images.txt)"
other="docker.io/library/other:1@sha256:$(printf '0%.0s' $(seq 64))"
tried=0

# ---- images. Nothing is started: the cluster only says whether it would.
pod() { # image, and the image of a container before it
  jq --null-input --arg image "$1" --arg before "${2:-}" '
    {allowPrivilegeEscalation: false, capabilities: {drop: ["ALL"]}} as $little
    | {apiVersion: "v1", kind: "Pod", metadata: {name: "tried", namespace: "shop"},
       spec: ({restartPolicy: "Never", automountServiceAccountToken: false,
               securityContext: {runAsNonRoot: true, runAsUser: 10009, seccompProfile: {type: "RuntimeDefault"}},
               containers: [{name: "c", image: $image, securityContext: $little}]}
              + (if $before == "" then {} else {initContainers: [{name: "b", image: $before, securityContext: $little}]} end))}'
}
start() { pod "$@" | kube create --dry-run=server --filename -; }
change_image() { kube patch "$(name_of front)" --dry-run=server --type json --patch "[{\"op\":\"replace\",\"path\":\"/spec/containers/0/image\",\"value\":\"$1\"}]"; }
join_pod() {
  local pod
  pod="$(name_of front)"
  kube get "$pod" --output json \
    | jq --arg image "$1" '.spec.ephemeralContainers = [{name: "late", image: $image, securityContext: {allowPrivilegeEscalation: false, capabilities: {drop: ["ALL"]}}}]' \
    | kube replace --raw "/api/v1/namespaces/shop/pods/${pod#pod/}/ephemeralcontainers?dryRun=All" --filename -
}
refused() { # the words that have to be in the answer, what is tried, the command
  local wanted="$1" what="$2" answer
  shift 2
  if answer="$("$@" 2>&1)"; then echo "NOT REFUSED: $what"; echo "$answer"; exit 1; fi
  if ! grep --quiet --fixed-strings "$wanted" <<< "$answer" || grep --quiet 'resulted in error' <<< "$answer"; then
    echo "Refused for another reason: $what"
    echo "$answer"
    exit 1
  fi
  tried=$((tried + 1))
  echo "refused: $what"
}
started() { # what is tried, the command
  local what="$1" answer
  shift
  answer="$("$@" 2>&1)" || { echo "NOT LET THROUGH: $what"; echo "$answer"; exit 1; }
  tried=$((tried + 1))
  echo "let through: $what"
}
started "an image from the list" start "$known"
refused "not on the list" "an image that is not on the list" start "$other"
refused "not on the list" "an image from the list without its fingerprint" start "${known%@*}"
refused "not on the list" "an image from the list with another fingerprint" start "${known%@*}@${other#*@}"
refused "not on the list" "another image before the first one" start "$known" "$other"
refused "not on the list" "another image in a pod that runs" change_image "$other"
refused "not on the list" "another image that joins a pod that runs" join_pod "$other"
kube --namespace walls delete configmap known-images > /dev/null
sleep 5
refused "no params found" "an image from the list, when there is no list" start "$known"
kube apply --kustomize /repo/k8s/clouds/kind > /dev/null
sleep 5
started "an image from the list, when the list is there again" start "$known"

# ---- connections
reach() { # app, container, host, port: says open or closed
  kube exec "$(name_of "$1")" --container "$2" -- python3 -c '
import socket, sys
try:
    socket.create_connection((sys.argv[1], int(sys.argv[2])), 4).close()
    print("open")
except OSError:
    print("closed")' "$3" "$4"
}
ways=(
  "closed|the program to Prometheus|standin standin prometheus 9090"
  "closed|the program to the numbers of the front|standin standin tally 9100"
  "closed|the program to the front|standin standin front 80"
  "closed|the program to the internet|standin standin 1.1.1.1 443"
  "closed|the front to the internet|front tally 1.1.1.1 443"
  "closed|the walker to the program|walker walker standin 80"
  "closed|the walker to Prometheus|walker walker prometheus 9090"
  "closed|the walker to the internet|walker walker 1.1.1.1 443"
  "open|the front to the program|front tally standin 80"
  "open|the front to Prometheus|front tally prometheus 9090"
  "open|the walker to the numbers of the front|walker walker tally 9100"
  "open|the walker to the cluster|walker walker kubernetes.default.svc 443"
)
try_all() { # with the wall, or without it
  local way wanted what words is
  # The cluster needs a moment to hear of it, and the first way says when it has. Then each is tried once.
  for _ in $(seq 15); do
    if [ "$(reach standin standin prometheus 9090)" = "$([ "$1" = without ] && echo open || echo closed)" ]; then break; fi
    sleep 2
  done
  for way in "${ways[@]}"; do
    IFS='|' read -r wanted what words <<< "$way"
    if [ "$1" = without ]; then wanted=open; fi
    # shellcheck disable=SC2086
    is="$(reach $words)"
    [ "$is" = "$wanted" ] || { echo "$1 the wall, $what is $is, and has to be $wanted"; exit 1; }
    if [ "$1" = with ]; then tried=$((tried + 1)) && echo "$is: $what"; fi
  done
}
kube delete networkpolicy --all > /dev/null
try_all without
kube apply --kustomize /repo/k8s/clouds/kind > /dev/null
try_all with

echo "$tried things were tried at the two walls, and each was as it has to be."
mkdir -p build/public
echo "- **walls**: $tried things were tried at the two walls, and each was as it has to be." >> build/public/summary.md
