#!/usr/bin/env bash
# Tries what the walker must not be able to do, as the walker. Each has to be refused, and for the reason that is written in
# docs/walker.md. The one thing that it may do has to work, because a door that nobody can open proves nothing either.
set -euo pipefail
cd "$(dirname "$0")/../.."

kube() { docker exec --interactive lab-control-plane kubectl --kubeconfig /etc/kubernetes/admin.conf --namespace shop "$@"; }
as_walker() {
  kube --as system:serviceaccount:shop:walker --as-group system:serviceaccounts --as-group system:serviceaccounts:shop \
    --as-group system:authenticated "$@"
}
change() { as_walker patch rollout standin --type json --patch "$1"; }
container=/spec/template/spec/containers/0
tried=0

# A mistake in a command would look like a refusal, and so would a policy that breaks. So the answer has to be the right one.
refused() { # by what, what is tried, the command
  local by="$1" what="$2" answer wanted
  shift 2
  if [ "$by" = policy ]; then wanted='denied request: it may'; else wanted='is forbidden: User "system:serviceaccount:shop:walker" cannot'; fi
  if answer="$("$@" 2>&1)"; then
    echo "NOT REFUSED: $what"
    echo "$answer"
    exit 1
  fi
  if ! grep --quiet --fixed-strings "$wanted" <<< "$answer" || grep --quiet 'resulted in error' <<< "$answer"; then
    echo "Refused for another reason than $by: $what"
    echo "$answer"
    exit 1
  fi
  tried=$((tried + 1))
  echo "refused by the $by: $what"
}

# Its rights, compared with those of an account that nobody gave any. A kubectl that looks before it changes would be refused
# at the look, so the list is asked for as well.
rights() {
  kube --as "system:serviceaccount:shop:$1" --as-group system:serviceaccounts --as-group system:serviceaccounts:shop \
    --as-group system:authenticated auth can-i --list --no-headers | tr --squeeze-repeats ' ' | sed 's/ *$//' | sort
}
more="$(comm -13 <(rights default) <(rights walker))"
[ "$more" = "rollouts.argoproj.io [] [standin] [get patch]" ] || { echo "The walker has other rights than it should:"; echo "$more"; exit 1; }

spec() { kube get rollout standin --output json | jq --sort-keys .spec; }
before="$(spec)"

refused policy "another image" change "[{\"op\":\"replace\",\"path\":\"$container/image\",\"value\":\"docker.io/library/busybox\"}]"
refused policy "other words for the program" change "[{\"op\":\"replace\",\"path\":\"$container/args\",\"value\":[\"sleep\",\"1\"]}]"
refused policy "a second container" change '[{"op":"add","path":"/spec/template/spec/containers/-","value":{"name":"two","image":"docker.io/library/busybox"}}]'
refused policy "a container before the first" change '[{"op":"add","path":"/spec/template/spec/initContainers","value":[{"name":"two","image":"docker.io/library/busybox"}]}]'
refused policy "a Secret as a file" change '[{"op":"add","path":"/spec/template/spec/volumes/-","value":{"name":"s","secret":{"secretName":"x"}}}]'
refused policy "another account for the pods" change '[{"op":"add","path":"/spec/template/spec/serviceAccountName","value":"walker"}]'
refused policy "the network of the machine" change '[{"op":"add","path":"/spec/template/spec/hostNetwork","value":true}]'
refused policy "one setting more" change "[{\"op\":\"add\",\"path\":\"$container/env/-\",\"value\":{\"name\":\"X\",\"value\":\"1\"}}]"
refused policy "a setting that reads a Secret" change "[{\"op\":\"replace\",\"path\":\"$container/env/1\",\"value\":{\"name\":\"FAIL\",\"valueFrom\":{\"secretKeyRef\":{\"name\":\"x\",\"key\":\"y\"}}}}]"
refused policy "the name that the cluster gives" change "[{\"op\":\"replace\",\"path\":\"$container/env/2\",\"value\":{\"name\":\"RELEASE\",\"value\":\"other\"}}]"
refused policy "a release that is not known" change "[{\"op\":\"add\",\"path\":\"$container/env/0/value\",\"value\":\"other\"}]"
refused policy "a failure that is not known" change "[{\"op\":\"add\",\"path\":\"$container/env/1/value\",\"value\":\"other\"}]"
refused policy "a good release that fails" change "[{\"op\":\"add\",\"path\":\"$container/env/0/value\",\"value\":\"good\"},{\"op\":\"add\",\"path\":\"$container/env/1/value\",\"value\":\"errors\"}]"
refused policy "a release without the gate" change '[{"op":"replace","path":"/spec/strategy/canary/steps","value":[]}]'
refused policy "more time to become ready" change '[{"op":"replace","path":"/spec/progressDeadlineSeconds","value":9999}]'
refused policy "fewer pods" change '[{"op":"replace","path":"/spec/replicas","value":1}]'
refused policy "another label on the pods" change '[{"op":"add","path":"/spec/template/metadata/labels/other","value":"x"}]'
refused policy "a note on the Rollout" change '[{"op":"add","path":"/metadata/annotations","value":{"other":"x"}}]'

refused right "waving a release through" as_walker patch rollout standin --subresource status --type merge --patch '{"status":{"promoteFull":true}}'
refused right "deleting the Rollout" as_walker delete rollout standin
refused right "another Rollout" as_walker patch rollout other --type merge --patch '{"spec":{"replicas":1}}'
refused right "changing the gate" as_walker patch analysistemplate gate --type merge --patch '{"spec":{"metrics":[]}}'
refused right "changing the program" as_walker patch configmap standin --type merge --patch '{"data":{"app.py":""}}'
refused right "changing the list" as_walker patch configmap releases --type merge --patch '{"data":{"releases.txt":""}}'
refused right "reading Secrets" as_walker get secrets
refused right "seeing pods" as_walker get pods
refused right "going into a pod" as_walker exec deployment/front -- true
refused right "a pod of its own" as_walker run other --image docker.io/library/busybox
refused right "a token" as_walker create token walker
refused right "more rights" as_walker create rolebinding other --clusterrole admin --serviceaccount shop:walker
refused right "the policy that binds it" as_walker delete validatingadmissionpolicybinding walker-changes-two-settings
refused right "another place" as_walker get configmaps --namespace kube-system

[ "$(spec)" = "$before" ] || { echo "Something was refused, and changed nevertheless."; exit 1; }

settings() { change "[{\"op\":\"add\",\"path\":\"$container/env/0/value\",\"value\":\"$1\"},{\"op\":\"add\",\"path\":\"$container/env/1/value\",\"value\":\"$2\"}]" > /dev/null; }
settings errors errors
[ "$(kube get rollout standin --output json | jq --raw-output '[.spec.template.spec.containers[0].env[0:2][].value] | join(" ")')" = "errors errors" ] || { echo "What it may do does not work."; exit 1; }
settings one ""
kube wait --for=jsonpath='{.status.phase}'=Healthy --timeout=300s rollout/standin
echo "$tried things were refused, and the one that is allowed works."
mkdir -p build/public
echo "- **cannot**: $tried things that the walker tried were refused, and the one that is allowed works." >> build/public/summary.md
