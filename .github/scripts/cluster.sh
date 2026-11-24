#!/usr/bin/env bash
# Starts a cluster in this machine and puts in what the releases need. Meant for CI: it wants Linux on x86, and Docker.
# Words after it are the list of releases that the walker of this cluster walks through.
set -euo pipefail
cd "$(dirname "$0")/../.."
source .github/parts.env
[ $# -gt 0 ] || { echo "Which releases?"; exit 2; }
mkdir -p build

get() { # address, fingerprint, file
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --retry 3 --max-time 180 --output "$3" "$1"
  echo "$2  $3" | sha256sum --check --strict --quiet
}
kube() { docker exec --interactive lab-control-plane kubectl --kubeconfig /etc/kubernetes/admin.conf "$@"; }

get "https://github.com/kubernetes-sigs/kind/releases/download/$KIND_VERSION/kind-linux-amd64" "$KIND_SHA256" build/kind
get "https://github.com/argoproj/argo-rollouts/releases/download/$ROLLOUTS_VERSION/install.yaml" "$ROLLOUTS_SHA256" build/rollouts.yaml
chmod +x build/kind

# kubectl is the one inside of the machine image. The one of the CI machine is too new for this cluster.
build/kind create cluster --image "$NODE_IMAGE" --config k8s/clouds/kind/cluster.yaml --wait 180s
kube version

# The file names its image by tag. What runs here is named by its fingerprint.
image=quay.io/argoproj/argo-rollouts
sed "s|$image:$ROLLOUTS_VERSION|$image@$ROLLOUTS_DIGEST|" build/rollouts.yaml > build/rollouts-pinned.yaml
[ "$(grep --count "image: $image@$ROLLOUTS_DIGEST" build/rollouts-pinned.yaml)" = 1 ] || { echo "The image of Argo Rollouts was not found once."; exit 1; }
kube create namespace argo-rollouts
# From the side of the server, because the definitions are too long for the note that kubectl would add to them.
kube apply --server-side --namespace argo-rollouts --filename - < build/rollouts-pinned.yaml > build/rollouts.log
kube --namespace argo-rollouts rollout status deployment/argo-rollouts --timeout 180s

docker exec lab-control-plane mkdir -p /repo
for part in k8s standin front; do docker cp --quiet "$part" "lab-control-plane:/repo/$part"; done
# First the list, so that the walker finds it. On a cloud the merged one is there.
kube apply --filename /repo/k8s/base/namespace.yaml
printf '%s\n' "$@" | kube --namespace shop create configmap releases --from-file releases.txt=/dev/stdin
kube apply --kustomize /repo/k8s/clouds/kind
for part in front prometheus; do kube --namespace shop rollout status "deployment/$part" --timeout 240s; done
kube --namespace shop wait --for=jsonpath='{.status.phase}'=Healthy --timeout=240s rollout/standin

# The gate decides by what Prometheus reads, and nothing read looks like a bad release. So first it has to read both.
read_by_prometheus() {
  curl --fail --silent --max-time 10 http://127.0.0.1:30080/status/up \
    | jq --raw-output '[.data.result[] | select(.value[1] == "1") | .metric.job] | sort | join(" ")'
}
for _ in $(seq 45); do
  if [ "$(read_by_prometheus || true)" = "front rollouts" ]; then exit 0; fi
  sleep 2
done
echo "Prometheus does not read both: $(read_by_prometheus || true)"
kube --namespace shop logs deployment/prometheus --tail 30
exit 1
