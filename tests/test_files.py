"""What has to stand in the files that only a cluster reads. Plain text is enough for it."""

import hashlib
import json
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
K8S = ROOT / "k8s"
GATE = json.loads((ROOT / "gate.json").read_text())
CLOUDS = json.loads((K8S / "clouds" / "clouds.json").read_text())


def text(*parts):
    return ROOT.joinpath(*parts).read_text()


def yaml_files(place):
    return sorted(place.rglob("*.y*ml"))


class Name(unittest.TestCase):
    def test_whose_portfolio_this_is_and_who_wrote_it(self):
        # Typed in NOTICE. Everywhere else it has to be the same.
        name = re.search(r"^Copyright 2026 (.+)$", text("NOTICE"), re.MULTILINE)[1]
        readme = text("README.md")
        self.assertEqual(readme.splitlines()[2:4], [f"Part of the public portfolio of {name}.", "[The other parts](https://github.com/oplf-svg)."])
        self.assertIn(f"\n## Who made this\n\nDirected and approved by {name}. Code, tests and texts are written by Claude, an AI agent that "
                      "proposes its changes under an identity of its own.\n", readme)

    def test_the_licence_is_the_whole_one(self):
        self.assertEqual(hashlib.sha256(ROOT.joinpath("LICENSE").read_bytes()).hexdigest(), "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4")


class Images(unittest.TestCase):
    def test_every_image_has_its_fingerprint(self):
        found = [line.strip() for path in yaml_files(K8S) for line in path.read_text().splitlines() if re.match(r"\s*(- )?image:", line)]
        self.assertGreaterEqual(len(found), 3)
        for line in found:
            self.assertRegex(line, r"^(- )?image: docker\.io/[a-z0-9/]+:[A-Za-z0-9.-]+@sha256:[0-9a-f]{64}$")

    def test_every_part_of_the_cluster_has_its_fingerprint(self):
        parts = dict(line.split("=", 1) for line in text(".github", "parts.env").splitlines() if line and not line.startswith("#"))
        for name in ("KIND_SHA256", "ROLLOUTS_SHA256"):
            self.assertRegex(parts[name], r"^[0-9a-f]{64}$")
        self.assertRegex(parts["NODE_IMAGE"], r"^kindest/node:v1\.35\.\d+@sha256:[0-9a-f]{64}$")
        self.assertRegex(parts["ROLLOUTS_DIGEST"], r"^sha256:[0-9a-f]{64}$")


class Neutral(unittest.TestCase):
    def test_no_cloud_is_named_in_what_is_the_same_everywhere(self):
        names = r"\b(aws|eks|amazon|azure|aks|microsoft|gcp|gke|google|oci|oke|oracle|ecr|acr)\b"
        for place in (K8S / "base", K8S / "walk", K8S / "walls", K8S / "list", ROOT / "standin", ROOT / "front", ROOT / "clients", ROOT / "count"):
            for path in place.rglob("*"):
                if path.is_file() and path.suffix in (".yaml", ".yml", ".py", ".conf"):
                    self.assertIsNone(re.search(names, path.read_text(), re.IGNORECASE), path)

    def test_every_cloud_has_its_folder_and_every_folder_is_on_the_list(self):
        folders = {path.name for path in (K8S / "clouds").iterdir() if path.is_dir()}
        self.assertEqual(folders, set(CLOUDS))
        for name in CLOUDS:
            parts = re.findall(r"- \.\./\.\./([a-z]+)", text("k8s", "clouds", name, "kustomization.yaml"))
            # In CI each cluster tries a part of the list, so the scripts make it there.
            # The walls need the way to the API of the cluster, which is different on each cloud. A cloud gets both together.
            self.assertEqual(parts, ["base", "walk", "walls"] if name == "kind" else ["base", "walk", "list"], name)
            self.assertEqual("walls" in parts, (K8S / "clouds" / name / "api.yaml").exists(), name)

    def test_nothing_that_a_cloud_makes_outside_of_our_code(self):
        # It would be in no state, and it would stay after the cluster is gone.
        for path in yaml_files(K8S):
            for word in ("LoadBalancer", "PersistentVolumeClaim", "volumeClaimTemplates", "kind: Ingress", "kind: Gateway"):
                self.assertNotIn(word, path.read_text(), path)


class Gate(unittest.TestCase):
    gate = text("k8s", "base", "gate.yaml")

    def numbers(self, metric):
        part = self.gate.split(f"- name: {metric}\n")[1].split("\n    - name: ")[0]
        return part, int(re.search(r"result\[0\] <= (\d+)", part)[1]), int(re.search(r">= (\d+)\)", part)[1])

    def test_the_long_look_has_the_numbers_that_were_decided(self):
        for metric, percent in (("wrong", "wrong_percent"), ("slow", "slow_percent")):
            part, limit, least = self.numbers(metric)
            self.assertEqual((limit, least), (GATE[percent], GATE["at_least"]))
            self.assertIn(f"initialDelay: {GATE['measure_seconds']}s", part)
            # Without the first half a release that nobody asked would pass.
            self.assertIn("successCondition: len(result) == 1 && result[0] <= ", part)

    def test_the_early_look_has_them_too(self):
        for metric in ("clearly-wrong", "clearly-slow"):
            part, limit, least = self.numbers(metric)
            self.assertEqual((limit, least), (GATE["early_percent"], GATE["early_at_least"]))
            self.assertIn(f"interval: {GATE['early_every_seconds']}s", part)
            self.assertIn(f"count: {GATE['measure_seconds'] // GATE['early_every_seconds']}", part)

    def test_only_the_new_release_is_read(self):
        def counters(part):
            return re.findall(r"front_[a-z_]+\{([^}]*(?:\}\}[^}]*)*)\}", part)
        self.assertEqual(len(counters(self.gate)), 12)
        for metric, how_many in (("clearly-wrong", 3), ("clearly-slow", 2), ("wrong", 3), ("slow", 2)):
            found = counters(self.numbers(metric)[0])
            self.assertEqual(len(found), how_many)
            for labels in found:
                self.assertIn('release="{{args.release}}"', labels)

    def test_what_no_pod_answered_is_looked_at_too(self):
        part, limit, _ = self.numbers("unanswered")
        self.assertEqual(limit, GATE["unanswered_percent"])
        self.assertIn('release="front",feed=~"good|forged",status=~"5.."', part)
        self.assertIn(f"interval: {GATE['early_every_seconds']}s", part)

    def test_the_feeds_are_the_same_everywhere(self):
        names = {name: expected for name, expected in re.findall(r'"(good|forged)": (\d+)', text("clients", "clients.py"))}
        self.assertEqual(names, {"good": "202", "forged": "401"})
        self.assertIn('FEEDS = ("good", "forged")', text("front", "tally.py"))
        for name, expected in names.items():
            self.assertEqual(self.gate.count(f'feed="{name}",status!="{expected}"'), 2)

    def test_the_judge_knows_the_looks_of_the_gate(self):
        looks = set(re.findall(r"^    - name: ([a-z-]+)$", self.gate.split("  metrics:\n")[1], re.MULTILINE))
        self.assertEqual(set(re.findall(r'"([a-z-]+)"', re.search(r"^LOOKS = \{(.*)\}$", text("count", "judge.py"), re.MULTILINE)[1])), looks)

    def test_the_cluster_waits_until_the_numbers_are_read(self):
        script = text(".github", "scripts", "cluster.sh")
        jobs = sorted(re.findall(r"job_name: ([a-z]+)", text("k8s", "base", "prometheus-config.yml")))
        self.assertIn(f'= "{" ".join(jobs)}" ]; then exit 0; fi', script)
        self.assertTrue(script.rstrip().endswith("exit 1"))

    def test_a_failure_condition_alone_would_let_nothing_pass_as_good(self):
        self.assertNotIn("failureCondition", self.gate)
        self.assertNotIn("vector(0)", self.gate)

    def test_the_limit_for_slow_is_the_one_of_the_program(self):
        for path, name in (("front/tally.py", "SLOW_FROM"), ("count/count.py", "SLOW_FROM")):
            self.assertEqual(float(re.search(rf"^{name} = ([\d.]+)$", text(path), re.MULTILINE)[1]), GATE["slow_seconds"])


class Release(unittest.TestCase):
    rollout = text("k8s", "base", "rollout.yaml")

    def test_a_release_that_is_never_ready_goes_away(self):
        self.assertIn("progressDeadlineAbort: true", self.rollout)
        self.assertIn(f"progressDeadlineSeconds: {GATE['ready_seconds']}\n", self.rollout)

    def test_it_begins_with_one_pod_of_ten_and_is_looked_at_each_time(self):
        self.assertIn("replicas: 10\n", self.rollout)
        steps = re.findall(r"- (setWeight: \d+|analysis:)", self.rollout)
        self.assertEqual(steps[:2], ["setWeight: 10", "analysis:"])
        self.assertEqual(steps[1::2], ["analysis:"] * (len(steps) // 2))
        self.assertEqual(self.rollout.count("podTemplateHashValue: Latest"), steps.count("analysis:"))

    def test_the_two_settings_stand_where_the_scripts_change_them(self):
        env = self.rollout.split("          env:\n")[1]
        self.assertEqual(re.findall(r"- name: ([A-Z]+)", env), ["NOTE", "FAIL", "RELEASE"])
        self.assertIn("fieldPath: metadata.labels['rollouts-pod-template-hash']", env)

    def test_the_counting_has_no_right_in_the_cluster(self):
        # What looks at the cluster afterwards only reads, and only where the cluster is on the same machine.
        script = text(".github", "scripts", "releases.sh")
        for word in ("patch", "apply", "delete", "create", "edit", "scale", "replace", "annotate"):
            self.assertNotIn(f"kubectl {word}", script)
            self.assertIsNone(re.search(rf"--namespace shop[^\n]*\n? +{word} ", script), word)

    def test_every_release_is_tried_once(self):
        def lists(*words, code=0):
            done = subprocess.run(["bash", str(ROOT / ".github" / "scripts" / "list.sh"), *words], capture_output=True, text=True)
            self.assertEqual(done.returncode, code, (words, done.stdout, done.stderr))
            return json.loads(re.fullmatch(r"words=(\[.*\])\n", done.stdout)[1]) if code == 0 else done.stdout
        scenarios = re.search(r"^SCENARIOS = \{(.*?)\}$", text("count", "judge.py"), re.MULTILINE | re.DOTALL)[1]
        once = lists()
        # A pull request asks for one of each. More is only asked for by hand.
        self.assertIn('run: bash .github/scripts/list.sh >> "$GITHUB_OUTPUT"\n', WORKFLOW.read_text())
        self.assertEqual(lists("1"), once)
        for nonsense in ("0", "x", "-1", "100", "2; id", "2 3", "02"):
            self.assertEqual(lists(nonsense, code=2), "", nonsense)
        tried = [word for words in once for word in words.split()]
        refused = {"cannot", "walls"}
        for repeat in (2, 20):
            many = lists(str(repeat))
            # No two jobs with the same name, and each repetition has all of them.
            self.assertEqual((len(set(many)), len(many)), (len(once) * repeat, len(once) * repeat))
            numbers = {words.split(" ", 1)[0] for words in many}
            self.assertEqual(numbers, {f"run-{n:0{len(str(repeat))}d}" for n in range(1, repeat + 1)})
            for number in numbers:
                self.assertEqual([words.split(" ", 1)[1] for words in many if words.startswith(f"{number} ")], once)
        # These are no releases. They try what has to be refused, and once is enough.
        self.assertEqual([tried.count(one) for one in sorted(refused)], [1, 1])
        self.assertEqual(sorted(word for word in tried if word not in refused), sorted(re.findall(r'"([a-z-]+)":', scenarios)))
        known = set(re.findall(r"^    ([a-z| -]+)\) echo \d+ ;;$", text(".github", "scripts", "releases.sh"), re.MULTILINE))
        self.assertEqual({word for words in known for word in words.split(" | ")}, set(tried) - refused)

    def test_the_clients_send_as_fast_as_the_numbers_say(self):
        script = text(".github", "scripts", "releases.sh")
        self.assertRegex(script, rf'  rate={GATE["rate"]}\n  if \[ "\$name" = unasked \]; then rate=\d; fi\n')
        self.assertIn('--seconds "$long" --rate "$rate" ', script)

    def test_the_release_that_hardly_anybody_asks_is_asked_by_somebody(self):
        # Until the long look. One request of ten reaches the one new pod of ten, by chance.
        asked = int(re.search(r"= unasked \]; then rate=(\d+); fi", text(".github", "scripts", "releases.sh"))[1]) * GATE["measure_seconds"]
        # That none reaches it happens less than once in a million runs. With twice its share it still cannot be measured.
        self.assertLess(0.9 ** asked, 1e-6)
        self.assertLess(0.2 * asked, GATE["early_at_least"])

    def test_only_three_releases_take_a_part_away_and_only_in_ci(self):
        self.assertEqual(re.findall(r"^  ([a-z]+)\)$", text(".github", "scripts", "break.sh"), re.MULTILINE), ["blind", "restarted", "interrupted"])
        self.assertIn("BREAK=.github/scripts/break.sh bash .github/scripts/releases.sh", text(".github", "scripts", "job.sh"))
        self.assertNotIn("break.sh", text(".github", "scripts", "releases.sh"))

    def test_every_pod_gives_up_its_rights(self):
        for path in (K8S / "base" / name for name in ("rollout.yaml", "front.yaml", "prometheus.yaml")):
            for word in ("runAsNonRoot: true", "type: RuntimeDefault", "allowPrivilegeEscalation: false", "readOnlyRootFilesystem: true", "drop: [ALL]"):
                self.assertIn(word, path.read_text(), path)
            self.assertIn("automountServiceAccountToken: false", path.read_text(), path)

    def test_nothing_of_ours_has_a_right_in_the_cluster(self):
        for path in yaml_files(K8S / "base"):
            for word in ("kind: Role", "kind: ClusterRole", "kind: ServiceAccount", "serviceAccountName"):
                self.assertNotIn(word, path.read_text(), path)


class Walls(unittest.TestCase):
    policy, network = text("k8s", "walls", "images.yaml"), text("k8s", "walls", "network.yaml")

    def test_the_list_has_exactly_the_images_that_are_used(self):
        known = {line for line in text("k8s", "walls", "images.txt").splitlines() if line and not line.startswith("#")}
        used = {line.split("image: ")[1].strip() for path in yaml_files(K8S) for line in path.read_text().splitlines() if re.match(r"\s*(- )?image:", line)}
        parts = dict(line.split("=", 1) for line in text(".github", "parts.env").splitlines() if line and not line.startswith("#"))
        self.assertEqual(known, used | {f"quay.io/argoproj/argo-rollouts@{parts['ROLLOUTS_DIGEST']}"})

    def test_nothing_starts_when_it_cannot_be_looked_at(self):
        for word in ("failurePolicy: Fail\n", "parameterNotFoundAction: Deny\n", "validationActions: [Deny]\n", "resources: [pods, pods/ephemeralcontainers]\n",
                     "operations: [CREATE, UPDATE]\n"):
            self.assertEqual(self.policy.count(word), 1, word)
        for kind in ("containers", "initContainers", "ephemeralContainers"):
            self.assertIn(f"object.spec.{kind}.map(c, c.image)", self.policy)

    def test_both_places_carry_the_label(self):
        self.assertIn("    images: known\n", text("k8s", "base", "namespace.yaml"))
        self.assertIn("kube label namespace argo-rollouts images=known\n", text(".github", "scripts", "cluster.sh"))
        self.assertIn("      matchLabels:\n        images: known\n", self.policy)

    def test_nothing_is_open_that_is_not_named(self):
        parts = self.network.split("\n---\n")
        closed = [part for part in parts if "  name: nothing\n" in part]
        self.assertEqual([re.search(r"namespace: (.*)", part)[1] for part in closed], ["shop", "argo-rollouts"])
        for part in closed:
            self.assertRegex(part, r"  podSelector: \{\}\n  policyTypes: \[Ingress, Egress\](\n|$)")
        # Only the way in comes from anywhere, and nothing goes out to an address.
        self.assertNotIn("ipBlock", self.network)
        self.assertEqual(len(re.findall(r"^    - ports:$", self.network, re.MULTILINE)), 1)
        # Each rule names its ports, apart from the two that close everything.
        rules = len(re.findall(r"^    - (?:from|to|ports):", self.network, re.MULTILINE))
        self.assertEqual(len(re.findall(r"ports:$", self.network, re.MULTILINE)), rules)

    def test_everything_that_is_said_is_tried(self):
        said = re.findall(r"^\| (.+) \| (let through|refused|closed|open) \|$", text("docs", "walls.md"), re.MULTILINE)
        script = text(".github", "scripts", "walls.sh")
        tried = []
        for kind, what in re.findall(r'^(started|refused "[a-z ]+") "([^"]+)"', script, re.MULTILINE):
            tried.append((what, "let through" if kind == "started" else "refused"))
        tried += [(what, wanted) for wanted, what in re.findall(r'^  "(closed|open)\|([^|]+)\|', script, re.MULTILINE)]
        self.assertGreaterEqual(len(said), 21)
        self.assertEqual(said, tried)
        # Without the wall first, then with it.
        self.assertLess(script.index("try_all without\n"), script.index("try_all with\n"))
        self.assertIn('else echo "open without the wall: $what"; fi', script)
        # What was taken away is put back, and not only where the releases are.
        self.assertEqual(len(re.findall(r"^put_back$", script, re.MULTILINE)), 2)
        self.assertNotRegex(script, r"kube apply|put_back\(\).*--namespace")


class Walker(unittest.TestCase):
    def test_it_has_one_right_on_one_object(self):
        files = text("k8s", "walk", "walker.yaml")
        self.assertEqual(re.findall(r"^kind: (.*)$", files, re.MULTILINE), ["ServiceAccount", "Role", "RoleBinding", "Job"])
        rules = files.split("rules:\n")[1].split("---")[0]
        self.assertEqual(rules, "  - apiGroups: [argoproj.io]\n    resources: [rollouts]\n    resourceNames: [standin]\n    verbs: [get, patch]\n")

    def test_nobody_else_has_a_right(self):
        for path in yaml_files(K8S):
            if path != K8S / "walk" / "walker.yaml":
                self.assertIsNone(re.search(r"kind: (Cluster)?Role|kind: ServiceAccount$|serviceAccountName", path.read_text(), re.MULTILINE), path)

    def test_the_policy_is_closed_when_it_cannot_look(self):
        policy = text("k8s", "walk", "policy.yaml")
        self.assertIn("failurePolicy: Fail\n", policy)
        self.assertIn("validationActions: [Deny]\n", policy)
        self.assertIn('request.userInfo.username == "system:serviceaccount:shop:walker"', policy)
        self.assertIn('resources: ["*/*"]', policy)

    def test_the_policy_looks_at_everything(self):
        self.assertEqual(re.findall(r"- message: (.*)$", text("k8s", "walk", "policy.yaml"), re.MULTILINE), [
            "it may only change the Rollout standin", "it may not change names, labels, notes or owners",
            "it may not change how the release is done", "it may not change the labels of the pods", "it may not change the pod",
            "it may not change the container", "it may only change the two settings", "it may only set what is known"])

    def test_the_same_releases_are_known_everywhere(self):
        scenarios = set(re.findall(r'"([a-z-]+)":', re.search(r"^SCENARIOS = \{(.*?)\}$", text("count", "judge.py"), re.MULTILINE | re.DOTALL)[1]))
        walks = re.search(r"^FAILS = \{GOOD: \"\"(.*?)\}$", text("k8s", "walk", "walker.py"), re.MULTILINE | re.DOTALL)[1]
        pairs = {("good", ""), *re.findall(r'"([a-z-]+)": "([a-z-]*)"', walks)}
        self.assertEqual({name for name, _ in pairs}, scenarios)
        # The same pairs in the policy, and the one that is there at first.
        allowed = re.findall(r'"([a-z-]+):([a-z-]*)"', text("k8s", "walk", "policy.yaml").split("it may only set what is known")[1])
        self.assertEqual(set(allowed), pairs | {("one", "")})
        self.assertEqual(len(allowed), len(set(allowed)))
        kinds = re.findall(r'"([a-z-]*)"', re.search(r"^KINDS = \((.*)\)$", text("standin", "app.py"), re.MULTILINE)[1])
        self.assertEqual({fails for _, fails in pairs}, set(kinds))

    def test_everything_that_it_cannot_do_is_tried(self):
        said = re.findall(r"^\| (.+) \| (policy|right) \|$", text("docs", "walker.md"), re.MULTILINE)
        tried = re.findall(r'^refused (policy|right) "([^"]+)"', text(".github", "scripts", "cannot.sh"), re.MULTILINE)
        self.assertGreaterEqual(len(said), 30)
        self.assertEqual(said, [(what, by) for by, what in tried])

    def test_its_place_in_the_release_is_the_one_of_the_settings(self):
        self.assertIn('place = "/spec/template/spec/containers/0/env/{}/value"', text("k8s", "walk", "walker.py"))

    def test_it_gives_up_what_it_does_not_need(self):
        files = text("k8s", "walk", "walker.yaml")
        for word in ("runAsNonRoot: true", "type: RuntimeDefault", "allowPrivilegeEscalation: false", "readOnlyRootFilesystem: true", "drop: [ALL]"):
            self.assertIn(word, files)


WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
OFTEN = WORKFLOW.with_name("often.yml")


@unittest.skipUnless(WORKFLOW.exists(), "the owner pushes the workflow first")
class Workflow(unittest.TestCase):
    """Agents may not change the workflow. These are the rules that it has to keep, because its list of clusters comes from a
    script that a pull request can change. That each release is tried once is looked at above."""

    def setUp(self):
        self.text = WORKFLOW.read_text()
        self.jobs = re.findall(r"^  ([a-z-]+):$", self.text.split("\njobs:\n")[1], re.MULTILINE)

    def test_the_words_of_the_list_reach_nothing_but_a_name_and_a_setting(self):
        self.assertEqual(self.text.count("matrix.words"), 2)
        self.assertIn("    name: cluster (${{ matrix.words }})\n", self.text)
        self.assertIn("          WORDS: ${{ matrix.words }}\n", self.text)
        self.assertIn("run: bash .github/scripts/job.sh $WORDS\n", self.text)

    def test_a_long_list_cannot_take_all_machines(self):
        self.assertIn("      max-parallel: 5\n", self.text)

    def test_every_job_is_on_the_same_machine_and_has_no_rights_to_give_away(self):
        self.assertEqual(set(re.findall(r"runs-on: (.*)", self.text)), {"ubuntu-24.04"})
        self.assertIn("\npermissions: {}\n", self.text)
        self.assertEqual(set(re.findall(r"^      [a-z-]+: (read|write|none)$", self.text, re.MULTILINE)), {"read"})
        for word in ("environment:", "container:", "services:", "id-token", "pull_request_target", "workflow_run", "workflow_dispatch"):
            self.assertNotIn(word, self.text)
        self.assertEqual(set(re.findall(r"secrets\.([A-Z_]+)", self.text)), {"BLOCKED_TERMS"})

    def test_only_two_actions_of_github_at_a_commit(self):
        for action in re.findall(r"uses: (.*)", self.text):
            self.assertRegex(action, r"^actions/(checkout|upload-artifact)@[0-9a-f]{40} # v[\d.]+$")

    def test_the_required_check_waits_for_every_job(self):
        self.assertEqual(self.jobs[-1], "ci")
        waits = re.findall(r"needs: \[(.*)\]", self.text.split("\n  ci:\n")[1])[0].split(", ")
        self.assertEqual(sorted(waits), sorted(self.jobs[:-1]))
        self.assertIn(f"length == {len(waits)}\n", self.text)


@unittest.skipUnless(OFTEN.exists(), "The owner pushes it.")
class Often(unittest.TestCase):
    """The same clusters, several times, and then all of them judged together. Started by hand."""

    def setUp(self):
        self.text = OFTEN.read_text()
        self.parts = dict(re.findall(r"^  ([a-z-]+):\n((?:    .*\n|\n)+)", self.text.split("\njobs:\n")[1], re.MULTILINE))

    def test_it_is_started_by_hand_and_only_on_what_was_approved(self):
        self.assertEqual(re.findall(r"^  ([a-z_]+):", self.text.split("\non:\n")[1].split("\npermissions:")[0], re.MULTILINE), ["workflow_dispatch"])
        self.assertIn("    if: ${{ github.ref == 'refs/heads/main' }}\n", self.parts["list"])
        self.assertIn("        type: choice\n", self.text)

    def test_it_can_never_stand_in_for_the_required_check(self):
        self.assertEqual(list(self.parts), ["list", "clusters", "together"])
        self.assertNotIn("name: ci\n", self.text)

    def test_a_cluster_is_the_same_as_in_a_pull_request(self):
        def steps(part):
            return part.split("    steps:\n")[1].strip()
        there = WORKFLOW.read_text().split("\n  clusters:\n")[1].split("\n\n  ")[0]
        self.assertEqual(steps(self.parts["clusters"]), steps(there))
        for same in ("    name: cluster (${{ matrix.words }})\n", "      max-parallel: 5\n", "      fail-fast: false\n", "    timeout-minutes: 30\n"):
            self.assertIn(same, self.parts["clusters"])
            self.assertIn(same, there + "\n")

    def test_what_somebody_chose_reaches_nothing_but_a_setting(self):
        self.assertEqual(set(re.findall(r"^ *(\w+): \$\{\{ inputs\.times \}\}$", self.text, re.MULTILINE)), {"TIMES"})
        self.assertEqual(self.text.count("inputs."), 2)
        self.assertIn('run: bash .github/scripts/list.sh "$TIMES" >> "$GITHUB_OUTPUT"\n', self.parts["list"])
        self.assertIn('run: bash .github/scripts/together.sh "$TIMES"\n', self.parts["together"])

    def test_it_judges_also_when_something_was_red(self):
        self.assertIn("    needs: [list, clusters]\n    if: ${{ !cancelled() && needs.list.result == 'success' }}\n", self.parts["together"])

    def test_no_rights_and_only_actions_of_github_at_a_commit(self):
        self.assertIn("\npermissions: {}\n", self.text)
        self.assertEqual(set(re.findall(r"^      [a-z-]+: (read|write|none)$", self.text, re.MULTILINE)), {"read"})
        self.assertEqual(set(re.findall(r"runs-on: (.*)", self.text)), {"ubuntu-24.04"})
        for word in ("environment:", "container:", "services:", "id-token", "secrets.", "pull_request"):
            self.assertNotIn(word, self.text)
        for action in re.findall(r"uses: (.*)", self.text):
            self.assertRegex(action, r"^actions/(checkout|upload-artifact|download-artifact)@[0-9a-f]{40} # v[\d.]+$")


class Front(unittest.TestCase):
    conf = text("front", "nginx.conf")

    def test_it_hides_nothing(self):
        hooks = self.conf.split("location /hooks/ {")[1].split("location /mark/")[0]
        for word in ("proxy_next_upstream off;", "proxy_http_version 1.0;", "proxy_set_header Connection close;", "proxy_intercept_errors off;", "proxy_ignore_client_abort on;"):
            self.assertIn(word, hooks)

    def test_only_requests_and_marks_are_in_the_list(self):
        self.assertIn("\n  access_log off;\n", self.conf)
        self.assertEqual(self.conf.count("access_log /var/log/front/answers.jsonl answers;"), 2)

    def test_a_line_has_all_that_is_read_from_it(self):
        line = self.conf.split("log_format answers")[1].split(";\n")[0]
        self.assertEqual(re.findall(r'"([a-z]+)":"\$', line), ["id", "path", "status", "upstream", "release", "pod", "seconds", "at"])

    def test_nothing_can_be_added_to_the_question(self):
        asked = re.findall(r"location = /status/([a-z]+) \{", self.conf)
        self.assertEqual(asked, ["release", "gate", "up"])
        for name, question in zip(asked, ("rollout_info", "analysis_run_metric_phase==1", "up")):
            part = self.conf.split(f"location = /status/{name} {{")[1].split("\n    }\n")[0]
            self.assertIn("if ($is_args) {\n        return 404;", part)
            self.assertIn("limit_except GET {\n        deny all;", part)
            self.assertIn(f"proxy_pass http://prometheus:9090/api/v1/query?query={question};", part)
        self.assertEqual(self.conf.count("prometheus:9090"), 3)

    def test_the_tally_only_reads_the_list(self):
        self.assertIn("mountPath: /var/log/front\n              readOnly: true\n", text("k8s", "base", "front.yaml").split("- name: tally\n          image")[1])

    def test_the_clients_wait_longer_than_the_front(self):
        # Otherwise the front could write an answer after the run was marked as over.
        patience = float(re.search(r"^PATIENCE = ([\d.]+)$", text("clients", "clients.py"), re.MULTILINE)[1])
        waits = sum(int(re.search(rf"{name} (\d+)s;", self.conf)[1]) for name in ("proxy_connect_timeout", "proxy_read_timeout"))
        self.assertGreater(patience, waits)


if __name__ == "__main__":
    unittest.main()
