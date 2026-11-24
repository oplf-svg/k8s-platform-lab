"""Proves that the tests can fail. Each line is a mistake that is easy to make. One at a time is made in a copy, and the tests
have to notice it.

  python3 tests/wrong.py [words of a mistake]
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
COUNT, JUDGE, TALLY, APP, CLIENTS = "count/count.py", "count/judge.py", "front/tally.py", "standin/app.py", "clients/clients.py"
CONF, GATE, ROLLOUT, FRONT, PROMETHEUS = "front/nginx.conf", "k8s/base/gate.yaml", "k8s/base/rollout.yaml", "k8s/base/front.yaml", "k8s/base/prometheus.yaml"
IMAGES, KNOWN, NETWORK, WALLS = "k8s/walls/images.yaml", "k8s/walls/images.txt", "k8s/walls/network.yaml", ".github/scripts/walls.sh"
WALKER, RIGHT, POLICY = "k8s/walk/walker.py", "k8s/walk/walker.yaml", "k8s/walk/policy.yaml"
LIST, RELEASES, CANNOT, PARTS = ".github/scripts/list.sh", ".github/scripts/releases.sh", ".github/scripts/cannot.sh", ".github/parts.env"
MANY, BREAK, JOB = "count/many.py", ".github/scripts/break.sh", ".github/scripts/job.sh"
RECORD, HOLD = "count/record.py", ".github/scripts/tests.sh"

# These measure time, so nothing else may run beside them.
ALONE = {"chain"}
# What is wrong, where, what stands there, what stands there instead, and which tests have to notice it.
MISTAKES = [
    ("a number that is missing is nothing", COUNT, "        if missing:", "        if False:", "count"),
    ("a number that was never planned is nothing", COUNT, "        if strange:", "        if False:", "count"),
    ("a doubled number is nothing", COUNT, "if times > 1]", "if False]", "count"),
    ("an id that does not fit is nothing", COUNT, "if line[\"id\"] != f\"{run}-{line['number']:07d}\"]", "if False]", "count"),
    ("lines that cannot be read are nothing", COUNT, "    if unreadable:", "    if False:", "count"),
    ("a list without an end is nothing", COUNT, 'if len(ends) != 1 or ends[0]["end"] != run:', "if False:", "count"),
    ("clients that sent nothing are nothing", COUNT, "    if not sent:", "    if False:", "count"),
    ("marks are not looked for", COUNT, "        if len(found) != 1:", "        if False:", "count"),
    ("other runs are counted too", COUNT, 'part = front_lines[places["start"][0] + 1:places["end"][0]]', "part = front_lines", "count"),
    ("strangers are nothing", COUNT, "    if strangers and not strangers_allowed:", "    if False:", "count"),
    ("two answers to one request are nothing", COUNT, "        if event in front:", "        if False:", "count"),
    ("a repeated request is nothing", COUNT, 'if "," in upstream or ":" in upstream:', "if False:", "count"),
    ("an answer to nobody is nothing", COUNT, "for event in front if event not in known]", "for event in front if False]", "count"),
    ("other answers on both lists are nothing", COUNT, 'or str(there.get("status")) != str(status)', "or False", "count"),
    ("other releases on both lists are nothing", COUNT, 'if there.get("release", "") != line.get("release", ""):', "if False:", "count"),
    ("only 5xx is an error", COUNT, 'if status != line["expected"]:', "if status is not None and status >= 500:", "count judge"),
    ("no answer is not an error", COUNT, 'if status != line["expected"]:', 'if status is not None and status != line["expected"]:', "count"),
    ("the end is the whole run", COUNT, "LAST = 5.0", "LAST = 500.0", "count"),
    ("the share is of a whole minute", COUNT, "min(last, first + FIRST)", "first + FIRST", "count"),
    ("an answer is there when it is asked for", COUNT, 'return line.get("at", 0.0) + line.get("seconds", 0.0)', 'return line.get("at", 0.0)', "count"),
    ("nothing is slow", COUNT, 'slow[release] += line.get("seconds", 0.0) > SLOW_FROM', "pass", "count judge"),
    ("nobody is late", COUNT, 'line.get("late", 0.0) > LATE_FROM', "False", "judge"),
    ("numbers that cannot be believed are judged", JUDGE, '    if counted["problems"]:', "    if False:", "judge"),
    ("the controller is not asked", JUDGE, "    if said != [stays]:", "    if False:", "judge"),
    ("the end does not matter", JUDGE, "    if at_the_end != [new if kind == GOOD else old]:", "    if False:", "judge"),
    ("a release that nobody tried is judged", JUDGE, '    if reached < gate["at_least" if kind == GOOD else "early_at_least"] and scenario != "unasked":', "    if False:", "judge"),
    ("a good release needs as few requests as a bad one", JUDGE, '"at_least" if kind == GOOD else "early_at_least"', '"early_at_least"', "judge"),
    ("the share does not matter", JUDGE, '    if not SHARE[0] <= share <= SHARE[1] and scenario != "unasked":', "    if False:", "judge"),
    ("a good release may have errors", JUDGE, "        if errors:\n            wrong.append(f\"clients saw {errors} errors: {counted['seen errors by answer']}\")\n        # Two runs", "        if False:\n            pass\n        # Two runs", "judge"),
    ("any number of errors is acceptable", JUDGE, '    if errors > gate["seen_errors"]:', "    if False:", "judge"),
    ("any time is acceptable", JUDGE, '    if took > gate["rolled_back_seconds"]:', "    if False:", "judge"),
    ("what is never ready may answer", JUDGE, "        if others:", "        if False:", "judge"),
    ("a bad release need not be bad", JUDGE, "return wrong + was_it_bad(scenario, sent, counted, new)", "return wrong", "judge"),
    ("clients may be late", JUDGE, 'if counted["late requests"] * 100 > counted["sent"] * LATE:', "if False:", "judge"),
    ("why it went back does not matter", JUDGE, "    if not stopped & WHY[scenario] or not stopped <= WHY[scenario] | ALSO.get(scenario, set()):", "    if False:", "judge"),
    ("any look may have stopped it", JUDGE, "    if not stopped & WHY[scenario] or not stopped <= WHY[scenario] | ALSO.get(scenario, set()):", "    if not stopped:", "judge"),
    ("a look that may join may stop it alone", JUDGE, "    if not stopped & WHY[scenario] or", "    if not stopped or", "judge"),
    ("a look may join anywhere", JUDGE, "ALSO.get(scenario, set())", '{"wrong"}', "judge"),
    ("a look may join nowhere", JUDGE, "ALSO.get(scenario, set())", "set()", "judge"),
    ("a controller that was never away was away", JUDGE, '    if scenario == "interrupted" and took < AWAY:', "    if False:", "judge"),
    ("no look may have stopped it", JUDGE, "    if not stopped & WHY[scenario] or not stopped <=", "    if not stopped <=", "judge"),
    ("a look that could not be taken is nothing", JUDGE, 'if phase in ("Failed", "Error")}', 'if phase == "Failed"}', "judge"),
    ("a good release need not pass the looks", JUDGE, "        if len(runs) != 2 or passed != {(run, look) for run in runs for look in LOOKS}:", "        if False:", "judge"),
    ("a good release is looked at once", JUDGE, "        if len(runs) != 2 or passed !=", "        if passed !=", "judge"),
    ("the looks of other releases count too", JUDGE, 'if row.get("name", "").startswith(f"{name}-{release}-"))', "if True)", "judge"),
    ("the looks of a release that is called alike count too", JUDGE, 'startswith(f"{name}-{release}-")', 'startswith(f"{name}-{release}")', "judge"),
    ("nobody has to ask the controller", JUDGE, '    if not isinstance(status, dict) or set(status) != {"release", "gate"}:\n        return ["nobody asked the controller"]\n', "", "judge"),
    ("the tally does not say what it gives", TALLY, '            self.send_header("content-type", kind)\n', "", "tally"),
    ("the gate cannot be asked", CONF, "query=analysis_run_metric_phase==1;", "query=analysis_run_metric_phase;", "files"),
    ("something can be added to a question", CONF, "    location = /status/up {\n      if ($is_args) {\n        return 404;\n      }\n", "    location = /status/up {\n", "files"),
    ("a good release that was not let through is kept", WALKER, '        if name == GOOD and (note(get()) != name or phase(get()) == "Healthy"):', "        if name == GOOD:", "walker"),
    ("a good release is forgotten when the job starts again", WALKER, '(note(get()) != name or phase(get()) == "Healthy")', 'phase(get()) == "Healthy"', "walker"),
    ("two new releases are one", JUDGE, "    if len(others) != 1:", "    if not others:", "judge"),
    ("an answer of the controller is not compared by name", JUDGE, 'if one["metric"].get("name") == name)', "if True)", "judge"),
    ("no error is no number", TALLY, "                self.answers[release, feed, status] += 0", "                pass", "tally"),
    ("nothing slow is no number", TALLY, "            self.slow[release, feed] += 0", "            pass", "tally"),
    ("each feed is a number of its own", TALLY, 'feed = feed if feed in FEEDS else "other"', "feed = feed", "tally"),
    ("what no pod answered belongs to nobody", TALLY, 'str(line["release"]) or NOBODY', 'str(line["release"])', "tally"),
    ("the tally finds nothing slow", TALLY, "+= seconds > SLOW_FROM", "+= seconds > 100", "tally"),
    ("a list that became shorter is the list", TALLY, "if os.fstat(file.fileno()).st_size < file.tell():", "if False:", "tally"),
    ("half a line is lost", TALLY, "*whole, rest = (rest + part).split", "*whole, rest = part.split", "tally"),
    ("a line that cannot be read is not counted", TALLY, "                self.unreadable += 1", "                pass", "tally"),
    ("old numbers are given as new ones", TALLY, "200 if alive else 503", "200", "tally"),
    ("any number of marks is kept", TALLY, "len(self.marks) < 100", "True", "tally"),
    ("what is over begins again", TALLY, 'self.marks.setdefault(found[1], "started")', 'self.marks[found[1]] = "started"', "tally"),
    ("a run that never began can be over", TALLY, "            elif found[1] in self.marks:", "            else:", "tally"),
    ("a typo makes a good release", APP, "        if kind not in KINDS:", "        if False:", "standin"),
    ("it does not listen when it is told to end", APP, "    signal.signal(signal.SIGTERM, stop)", "    pass", "standin"),
    ("it is ready while it ends", APP, "        app.closing = True", "        pass", "standin"),
    ("any time is the right time", APP, "if abs(self.clock() - int(moment)) > CLOCK:", "if False:", "standin"),
    ("any size is right", APP, "        if length > LARGEST:", "        if False:", "standin"),
    ("any signature is right", APP, "if not any(hmac.compare_digest", "if False and not any(hmac.compare_digest", "standin"),
    ("a header may be there twice", APP, "if any(len(headers[name]) != 1 for name in HEADERS):", "if any(not headers[name] for name in HEADERS):", "standin"),
    ("an id may go on after what is right", APP, "EVENT.fullmatch(event)", "EVENT.match(event)", "standin"),
    ("a time may go on after what is right", APP, "MOMENT.fullmatch(moment)", "MOMENT.match(moment)", "standin"),
    ("what is too large is wrong in time first", APP, "        if length > LARGEST:\n            return 413\n        if abs(self.clock() - int(moment)) > CLOCK:\n            return 401\n", "        if abs(self.clock() - int(moment)) > CLOCK:\n            return 401\n        if length > LARGEST:\n            return 413\n", "standin"),
    ("the clients wait less than the front", CLIENTS, "PATIENCE = 8.0", "PATIENCE = 3.0", "files"),
    ("the controller is asked after the mark", CLIENTS, "        pathlib.Path(given.status).write_text(controller(front))\n        mark(front, given.run, \"end\")\n", "        mark(front, given.run, \"end\")\n        pathlib.Path(given.status).write_text(controller(front))\n", "chain"),
    ("the front repeats a request", CONF, "proxy_next_upstream off;", "proxy_next_upstream error timeout;", "files"),
    ("the front keeps connections", CONF, "proxy_http_version 1.0;", "proxy_http_version 1.1;", "files"),
    ("the front lists everything", CONF, "  access_log off;\n", "", "files"),
    ("the front forgets who goes away", CONF, "proxy_ignore_client_abort on;", "proxy_ignore_client_abort off;", "files"),
    ("a line of the front has no time", CONF, '"seconds":"$request_time",', "", "files"),
    ("a release that nobody asked is good", GATE, "    - name: wrong\n      initialDelay: 75s\n      consecutiveErrorLimit: 2\n      successCondition: len(result) == 1 && result[0] <= 2", "    - name: wrong\n      initialDelay: 75s\n      consecutiveErrorLimit: 2\n      successCondition: len(result) == 0 || result[0] <= 2", "files"),
    ("a slow release that nobody asked is good", GATE, "    - name: slow\n      initialDelay: 75s\n      consecutiveErrorLimit: 2\n      successCondition: len(result) == 1 && result[0] <= 2", "    - name: slow\n      initialDelay: 75s\n      consecutiveErrorLimit: 2\n      successCondition: len(result) == 0 || result[0] <= 2", "files"),
    ("the gate reads old and new together", GATE, 'sum(front_slow_answers_total{release="{{args.release}}",feed=~"good|forged"})\n            / (sum(front_answers_total{release="{{args.release}}",feed=~"good|forged"}) >= 300)', 'sum(front_slow_answers_total{feed=~"good|forged"})\n            / (sum(front_answers_total{feed=~"good|forged"}) >= 300)', "files"),
    ("what the front refuses itself counts", GATE, ',status=~"5.."', "", "files"),
    ("the early look is wide open", GATE, "    - name: clearly-wrong\n      interval: 5s\n      count: 15\n      consecutiveErrorLimit: 2\n      successCondition: len(result) == 0 || result[0] <= 10", "    - name: clearly-wrong\n      interval: 5s\n      count: 15\n      consecutiveErrorLimit: 2\n      successCondition: len(result) == 0 || result[0] <= 100", "files"),
    ("a release that is never ready stays", ROLLOUT, "progressDeadlineAbort: true", "progressDeadlineAbort: false", "files"),
    ("it begins with every second pod", ROLLOUT, "        - setWeight: 10\n", "        - setWeight: 50\n", "files"),
    ("the release names itself", ROLLOUT, "                  fieldPath: metadata.labels['rollouts-pod-template-hash']\n", "                  fieldPath: metadata.labels['app']\n", "files"),
    ("the settings stand elsewhere", ROLLOUT, "            - name: NOTE\n              value: one\n            - name: FAIL\n              value: \"\"\n", "            - name: FAIL\n              value: \"\"\n            - name: NOTE\n              value: one\n", "files"),
    ("an image without a fingerprint", PROMETHEUS, "@sha256:fa3302279710be2f21a8301ec17a8b4f2301fd829bd113839b3b6b02b6f191a2", "", "files"),
    ("a load balancer", FRONT, "  type: NodePort\n", "  type: LoadBalancer\n", "files"),
    ("the front has a token", FRONT, "      automountServiceAccountToken: false\n", "", "files"),
    ("the tally may write to the list", FRONT, "            - name: list\n              mountPath: /var/log/front\n              readOnly: true\n", "            - name: list\n              mountPath: /var/log/front\n", "files"),
    ("the walker may delete", RIGHT, "verbs: [get, patch]", "verbs: [get, patch, delete]", "files"),
    ("the walker may change every Rollout", RIGHT, "    resourceNames: [standin]\n", "", "files"),
    ("the walker may do it everywhere", RIGHT, "kind: Role\nmetadata", "kind: ClusterRole\nmetadata", "files"),
    ("the policy is open when it cannot look", POLICY, "failurePolicy: Fail", "failurePolicy: Ignore", "files"),
    ("the policy only writes it down", POLICY, "validationActions: [Deny]", "validationActions: [Audit]", "files"),
    ("the policy knows a release that is none", POLICY, '"unasked:",', '"unasked:", "other:other",', "files"),
    ("the policy lets a good release fail", POLICY, '"blind:",', '"blind:errors",', "files"),
    ("the policy forgets a release", POLICY, '"restarted:errors", ', "", "files"),
    ("the walker lets a good release fail", WALKER, '"blind": "",', '"blind": "errors",', "walker files"),
    ("the policy does not look at the gate", POLICY, "    - message: it may not change how the release is done\n", "    - message: it may do as it likes\n", "files"),
    ("the policy looks at somebody else", POLICY, "system:serviceaccount:shop:walker", "system:serviceaccount:shop:other", "files"),
    ("the old release is not seen alone first", WALKER, "                sleep(SETTLE)\n", "", "walker"),
    ("the next release does not wait until all is well", WALKER, '            wait(lambda: phase(get()) == "Healthy"', '            wait(lambda: True', "walker"),
    ("a job that starts again waits for a release that is tried", WALKER, "        if note(get()) == stable:\n", "        if True:\n", "walker"),
    ("a job that starts again ends what runs", WALKER, "        elif note(get()) == name:", "        else:", "walker"),
    ("a job that starts again begins what runs", WALKER, "            if note(get()) != name:", "            if True:", "walker"),
    ("a good release does not stay", WALKER, "            stable = name\n", "            pass\n", "walker"),
    ("the walker does not wait for the mark", WALKER, "        wait(lambda: name in marks()", "        wait(lambda: True", "walker"),
    ("the walker does not wait for the end", WALKER, 'wait(lambda: marks()[name] == "ended"', "wait(lambda: True", "walker"),
    ("any name is on the list", WALKER, "    if strange or not names", "    if not names", "walker"),
    ("an empty list is a list", WALKER, "or not names or", "or", "walker"),
    ("the token is read once", WALKER, "(account / 'token').read_text().strip()", "TOKEN.setdefault(0, (account / 'token').read_text().strip())", "walker"),
    ("a front that is away stops the walker", WALKER, "    except (OSError, ValueError):", "    except ZeroDivisionError:", "walker"),
    ("one release is not tried", LIST, '"dies drops"', '"drops"', "files"),
    ("what the walker cannot do is not tried", LIST, '"cannot good errors"', '"good errors"', "files"),
    ("two jobs have the same name", LIST, "run-$n $list", "run $list", "files"),
    ("a repetition leaves something out", LIST, 'seq -w "$repeat"', 'seq -w 2 "$repeat"', "files"),
    ("every pull request repeats everything", LIST, 'repeat="${1:-1}"', 'repeat="${1:-2}"', "files"),
    ("a repetition is anything", LIST, "^[1-9][0-9]?$ ]]", "^[1-9] ]]", "files"),
    ("the clients are slower than the numbers say", RELEASES, "  rate=50\n", "  rate=5\n", "files"),
    ("every release is asked for by hardly anybody", RELEASES, 'if [ "$name" = unasked ]; then rate=1; fi', "rate=1", "files"),
    ("something is taken away on every cluster", RELEASES, 'bash "$BREAK" "$name" & fi', 'bash .github/scripts/break.sh "$name" & fi', "files"),
    ("nothing is taken away", JOB, "BREAK=.github/scripts/break.sh bash", "bash", "files"),
    ("one thing is not taken away", BREAK, "  blind)\n", "  nothing)\n", "files"),
    ("Prometheus comes back while the release is there", BREAK, '    has_to_be "the release" "$(phase)" Degraded\n    shop scale', "    shop scale", "break"),
    ("the controller starts again while the release is there", BREAK, '    has_to_be "the release" "$(phase)" Degraded\n    who_leads', "    who_leads", "break"),
    ("the same controller is another one", BREAK, ' && [ "$now" != "$1" ]; }', "; }", "break"),
    ("nobody is somebody", BREAK, ' && [ -n "$now" ]', "", "break"),
    ("a controller that is still there is away", BREAK, '    wait_for 30 "the controller is away" nobody\n', "", "break"),
    ("the controller goes before the release is looked at", BREAK, '    wait_for 60 "the release is looked at" looked_at "$there"\n', "", "break"),
    ("a release that was looked at before is looked at", BREAK, '[ "$(runs)" -gt "$1" ]', '[ "$(runs)" -ge "$1" ]', "break"),
    ("the controller is away for a moment", BREAK, "    sleep 30\n", "    sleep 3\n", "break"),
    ("nobody looks whether it took over", BREAK, '    wait_for 60 "another controller leads" another "$before"\n', "", "break"),
    ("what never comes is not missed", BREAK, 'it was still not so: $what" >&2\n  exit 1', 'it was still not so: $what" >&2\n  return 0', "break"),
    ("what is not as it has to be is fine", BREAK, """and has to be '$3'." >&2; exit 1; }""", """and has to be '$3'." >&2; }""", "break"),
    ("a release that could not be measured need not go back for that", JUDGE, "        return wrong + was_it_unmeasured(scenario, errors, reached, results, gate)", "        return wrong", "judge"),
    ("a release that was asked was not asked", JUDGE, '        if reached >= gate["at_least"]:', "        if False:", "judge"),
    ("it does not matter why nobody could say so", JUDGE, '        if failed != {"wrong", "slow"} or broken:', "        if False:", "judge"),
    ("a look that failed was a look that could not be taken", JUDGE, "    elif failed or not broken:", "    elif not broken and not failed:", "judge"),
    ("errors of a release that could not be measured are nothing", JUDGE, 'wrong = [f"clients saw {errors} errors"] if errors else []', "wrong = []", "judge"),
    ("what is missing among many is nothing", MANY, "        if there != how_many:", "        if False:", "many"),
    ("one too many is nothing", MANY, "        if there != how_many:", "        if there < how_many:", "many"),
    ("many are not judged again", MANY, 'wrong = judge(name, counted, clients, json.loads(status.read_text()), gate) if name in SCENARIOS else ["it is not known"]', "wrong = []", "many"),
    ("the same run counts twice", MANY, "        if not wrong and print_of in seen:", "        if False:", "many"),
    ("a list that is missing is nothing", MANY, '[f"{path.name} is missing" for path in files.values() if not path.exists()]', "[]", "many"),
    ("it says to be surer than it is", MANY, "0.05 ** (1 / runs)", "0.5 ** (1 / runs)", "many"),
    ("problems among many do not matter", MANY, "        return 1\n    print(f", "        return 0\n    print(f", "many"),
    ("other files are the same files", MANY, "for job, its in said.items() if its != tree]", "for job, its in said.items() if False]", "many"),
    ("a job that does not say its files has the same ones", MANY, 'if (place / "tree.txt").exists() else "nothing"', 'if (place / "tree.txt").exists() else tree', "many"),
    ("a run that was started again is in a row", MANY, '    if env.get("GITHUB_RUN_ATTEMPT", "1") != "1":', "    if False:", "many"),
    ("the site hears yes when something was wrong", MANY, 'in a row": not problems}', 'in a row": True}', "many"),
    ("a row that was not tried was tried", MANY, 'was tried": len(table.get(name, [])) == how_many', 'was tried": True', "many"),
    ("a row with another number", MANY, '"blind": 9,', '"blind": 8,', "many"),
    ("an answer belongs to the second of its question", RECORD, 'line["at"] + line["seconds"] - zero', 'line["at"] - zero', "record"),
    ("answers of nobody are left out", RECORD, '"nobody": [line for line in sent if not line.get("release")]', '"nobody": []', "record"),
    ("only 5xx is wrong in the recording", RECORD, 'if line["status"] != line["expected"]]}', 'if (line["status"] or 0) >= 500]}', "record"),
    ("the looks at another release are its own", RECORD, 'if not run["metadata"]["name"].startswith(f"{name}-{release}-"):', "if False:", "record"),
    ("a look that read nothing was well", RECORD, '"well" if read_something else "nothing"', '"well"', "record"),
    ("a look that could not be taken was well", RECORD, 'elif any(phase == "Error"', 'elif any(phase == "None"', "record"),
    ("a bad look was well", RECORD, 'if phase == "Failed"]', 'if phase == "None"]', "record"),
    ("what is no number is a number", RECORD, " and math.isfinite(found[0])", "", "record"),
    ("a look that did not end has ended", RECORD, 'if not one.get("finishedAt"):', "if False:", "record"),
    ("two new releases are one", RECORD, "    if len(new) > 1:", "    if False:", "record"),
    ("a list that was cut off is drawn", RECORD, 'if unreadable or not any("end" in line for line in lines):', "if unreadable:", "record"),
    ("a list that cannot be read is drawn", RECORD, 'if unreadable or not any("end" in line for line in lines):', 'if not any("end" in line for line in lines):', "record"),
    ("a branch that has to wait need not wait", HOLD, "[ -e HOLD ] || [ -L HOLD ]", "false", "hold"),
    ("a link that leads nowhere does not hold", HOLD, "[ -e HOLD ] || [ -L HOLD ]", "[ -e HOLD ]", "hold"),
    ("it only says that it has to wait", HOLD, "; exit 1; fi", "; fi", "hold"),
    ("one thing that it cannot do is not tried", CANNOT, 'refused policy "a release without the gate"', '# policy "a release without the gate"', "files"),
    ("images are only written down", IMAGES, "validationActions: [Deny]", "validationActions: [Audit]", "files"),
    ("without a list everything starts", IMAGES, "parameterNotFoundAction: Deny", "parameterNotFoundAction: Allow", "files"),
    ("when it cannot be looked at, everything starts", IMAGES, "failurePolicy: Fail", "failurePolicy: Ignore", "files"),
    ("a container before the first is not looked at", IMAGES, "object.spec.initContainers.map(c, c.image)", "[]", "files"),
    ("a container that joins is not looked at", IMAGES, "resources: [pods, pods/ephemeralcontainers]", "resources: [pods]", "files"),
    ("a pod that runs is not looked at", IMAGES, "operations: [CREATE, UPDATE]", "operations: [CREATE]", "files"),
    ("an image too many on the list", KNOWN, "quay.io/argoproj", "docker.io/library/other@sha256:00\nquay.io/argoproj", "files"),
    ("an image is not on the list", KNOWN, "docker.io/prom/prometheus", "# docker.io/prom/prometheus", "files"),
    ("one place has no label", "k8s/base/namespace.yaml", "    images: known\n", "", "files"),
    ("the network is open by default", NETWORK, "metadata:\n  name: nothing\n  namespace: shop\nspec:\n  podSelector: {}\n  policyTypes: [Ingress, Egress]", "metadata:\n  name: nothing\n  namespace: shop\nspec:\n  podSelector: {}\n  policyTypes: [Ingress]", "files"),
    ("a way out to any address", NETWORK, "    - to:\n        - podSelector:\n            matchLabels:\n              app: standin\n", "    - to:\n        - ipBlock:\n            cidr: 0.0.0.0/0\n", "files"),
    ("a way that is not tried", WALLS, '  "closed|the program to the internet|standin standin 1.1.1.1 443"\n', "", "files"),
    ("only a part of the wall is put back", WALLS, "admin.conf apply --kustomize", "admin.conf --namespace shop apply --kustomize", "files"),
    ("the list is not put back", WALLS, "put_back\nsleep 5\n", "sleep 5\n", "files"),
    ("a way is only tried with the wall", WALLS, "try_all without\n", "", "files"),
    ("an image that is not tried", WALLS, 'refused "not on the list" "another image that joins a pod that runs"', 'true "not on the list" "another image that joins a pod that runs"', "files"),
    ("a Kubernetes that nobody tested", PARTS, "kindest/node:v1.35.8", "kindest/node:v1.37.0", "files"),
    ("the walker is not on a cloud", "k8s/clouds/azure/kustomization.yaml", "  - ../../walk\n", "", "files"),
    ("a cloud that nobody listed", "k8s/clouds/clouds.json", '  "gcp": "GKE"\n', '  "gcp": "GKE",\n  "oci": "OKE"\n', "files"),
    ("the base names a cloud", FRONT, "# One pod, and never two", "# On AKS one pod, and never two", "files"),
    ("nobody is named", "NOTICE", "Copyright 2026 ", "Copyright ", "files"),
    ("somebody else is named on top", "README.md", "Part of the public portfolio of ", "Part of the public portfolio of J. ", "files"),
    ("more is claimed for the owner", "README.md", "Code, tests and texts are written by Claude", "Texts are written by Claude", "files"),
    ("half a licence", "LICENSE", "   END OF TERMS AND CONDITIONS\n", "", "files"),
    ("other numbers than were decided", "gate.json", '"wrong_percent": 2', '"wrong_percent": 3', "files"),
]


def noticed(place, tests):
    for name in tests.split():
        done = subprocess.run([sys.executable, "-m", "unittest", "discover", "--start-directory", "tests", "--pattern", f"test_{name}.py"],
                              cwd=place, capture_output=True, text=True, timeout=300)
        if done.returncode:
            return name
    return None


def make(mistake):
    """Makes one mistake in a copy, or none, and returns what came of it."""
    what, where, old, new, tests = mistake
    with tempfile.TemporaryDirectory() as folder:
        place = pathlib.Path(folder) / "copy"
        shutil.copytree(ROOT, place, ignore=shutil.ignore_patterns(".git", "build", "__pycache__"))
        if where:
            text = (place / where).read_text()
            if text.count(old) != 1:
                return what, f"what it changes stands there {text.count(old)} times, and not once"
            (place / where).write_text(text.replace(old, new))
        by = noticed(place, tests)
    if where:
        return what, f"noticed by {by}" if by else "NOT NOTICED"
    return what, f"NOT RIGHT, test_{by}.py failed without a mistake" if by else "right"


def with_controls(wanted):
    """The mistakes, and between them the same tests without a mistake. They have to be right while the others run: a test that
    fails because the machine is busy would notice every mistake."""
    names, mixed = sorted({name for one in wanted for name in one[4].split()}), []
    for number, one in enumerate(wanted):
        mixed.append(one)
        if number % 5 == 4:
            name = names[number // 5 % len(names)]
            mixed.append((f"no mistake, for test_{name}.py", "", "", "", name))
    return mixed


def made(wanted):
    """Some at once, but not as many as there are processors. Those that measure time come last, one after the other."""
    together = [one for one in wanted if not ALONE & set(one[4].split())]
    with ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) * 3 // 4)) as pool:
        yield from pool.map(make, with_controls(together))
    yield from map(make, [one for one in wanted if one not in together])


def main(words):
    wanted = [one for one in MISTAKES if not words or words in one[0]]
    # Tests that fail without a mistake would notice every mistake.
    for name in sorted({name for one in wanted for name in one[4].split()}):
        if noticed(ROOT, name):
            print(f"test_{name}.py is not right without a mistake, so nothing can be said.")
            return 1
    missed, busy = [], []
    for what, said in made(wanted):
        print(f"{said}: {what}", flush=True)
        if said.startswith("NOT RIGHT"):
            busy.append(what)
        elif said != "right" and not said.startswith("noticed by "):
            missed.append(what)
    print(f"{len(wanted) - len(missed)} of {len(wanted)} mistakes were noticed.")
    if busy:
        print(f"Some tests were not right without a mistake while others ran, so nothing can be said: {busy}")
    return 1 if missed or busy or not wanted else 0


if __name__ == "__main__":
    sys.exit(main(" ".join(sys.argv[1:])))
