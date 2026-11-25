#!/usr/bin/env bash
# Takes a part of the cluster away while a release is tried, and puts it back. Only for a cluster that is thrown away.
# It begins with the mark of the run, and the walker changes the release 10 seconds later. Whatever it waits for has to come: a
# release that was tried while nothing was away says nothing about what happens then.
set -euo pipefail
kube() { docker exec lab-control-plane kubectl --kubeconfig /etc/kubernetes/admin.conf "$@"; }
shop() { kube --namespace shop "$@"; }
controller() { kube --namespace argo-rollouts "$@"; }

phase() { shop get rollout standin --output 'jsonpath={.status.phase}'; }
leader() { controller get lease --output 'jsonpath={.items[*].spec.holderIdentity}'; }
runs() { shop get analysisrun --output name | wc -l; }
looked_at() { [ "$(runs)" -gt "$1" ]; }
nobody() { [ -z "$(controller get pod --output name)" ]; }
another() { local now; now="$(leader)" && [ -n "$now" ] && [ "$now" != "$1" ]; }
who_leads() { wait_for 10 "a controller leads" another "" && before="$(leader)"; }
has_to_be() { # what, as it is, as it has to be
  [ "$2" = "$3" ] || { echo "$1 is '$2' and has to be '$3'." >&2; exit 1; }
}
wait_for() { # seconds at most, what is waited for, the test
  local long="$1" what="$2"
  shift 2
  for _ in $(seq "$long"); do
    if "$@"; then echo "$(date -u +%T) $what"; return 0; fi
    sleep 1
  done
  echo "After $long seconds it was still not so: $what" >&2
  exit 1
}

case "${1:-}" in
  blind)
    # Prometheus is gone before the release begins, and comes back when it has gone back.
    shop scale deployment/prometheus --replicas 0
    sleep 75
    has_to_be "the release" "$(phase)" Degraded
    shop scale deployment/prometheus --replicas 1
    shop rollout status deployment/prometheus --timeout 60s
    ;;
  restarted)
    # The bad release has gone back, and then another controller takes over.
    sleep 75
    has_to_be "the release" "$(phase)" Degraded
    who_leads
    controller rollout restart deployment/argo-rollouts
    wait_for 90 "another controller leads" another "$before"
    ;;
  interrupted)
    # The controller goes as soon as it looks at a bad release. It cannot say anything before 50 requests, and they take 10 seconds.
    who_leads
    there="$(runs)"
    wait_for 60 "the release is looked at" looked_at "$there"
    controller scale deployment/argo-rollouts --replicas 0
    wait_for 30 "the controller is away" nobody
    sleep 30
    controller scale deployment/argo-rollouts --replicas 1
    wait_for 60 "another controller leads" another "$before"
    ;;
  *) ;;
esac
