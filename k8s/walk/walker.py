"""Walks through the list of releases that was merged, inside of the cluster. It may change two settings of one Rollout, and
nothing else: docs/walker.md.

A release begins some seconds after its run was marked as begun at the front, and goes back when the run was marked as over. So
whoever counts from outside says when, the merged list says what, and nobody outside needs a right in here.
"""

import json
import pathlib
import ssl
import sys
import time
import urllib.error
import urllib.request

LIST = "/walk/releases.txt"
ACCOUNT = pathlib.Path("/var/run/secrets/kubernetes.io/serviceaccount")
ROLLOUT = "https://kubernetes.default.svc/apis/argoproj.io/v1alpha1/namespaces/shop/rollouts/standin"
MARKS = "http://tally:9100/marks"
FIRST, GOOD = "one", "good"
# Each release that may be tried, and how it fails. The policy knows the same pairs.
FAILS = {GOOD: "", "errors": "errors", "few": "few", "drops": "drops", "refuses": "refuses", "slow": "slow", "never-ready": "never-ready", "dies": "dies",
         "unasked": "", "blind": "", "restarted": "errors", "interrupted": "errors"}
SETTLE = 10.0
PATIENCE = 3600.0


def read_list(text):
    names = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    strange = [name for name in names if name not in FAILS]
    if strange or not names or len(set(names)) != len(names):
        raise ValueError(f"the list is not a list of different known releases: {names}")
    return names


def settings(name):
    return name, FAILS.get(name, "")


def patch_for(name):
    # "add" and not "replace": an empty setting may be gone when the controller has written the object.
    place = "/spec/template/spec/containers/0/env/{}/value"
    return [{"op": "add", "path": place.format(n), "value": value} for n, value in enumerate(settings(name))]


def note(rollout):
    return rollout["spec"]["template"]["spec"]["containers"][0]["env"][0].get("value", "")


def phase(rollout):
    return rollout.get("status", {}).get("phase", "")


class Gone(Exception):
    """It took too long. The job starts again and goes on where the marks say that it was."""


def wait(until, what, sleep, patience=PATIENCE, every=1.0):
    for _ in range(int(patience / every)):
        if until():
            return
        sleep(every)
    raise Gone(what)


def walk(names, get, patch, marks, sleep=time.sleep, say=print):
    stable = FIRST
    for name in names:
        wait(lambda: name in marks(), f"{name} never began", sleep)
        if marks()[name] == "started":
            # Already changed: the job was started again in the middle of this one.
            if note(get()) != name:
                sleep(SETTLE)
                say(f"release {name}")
                patch(patch_for(name))
            wait(lambda: marks()[name] == "ended", f"{name} never ended", sleep)
        # Kept only if it is well. When the job was started again and something else runs, it was kept.
        if name == GOOD and (note(get()) != name or phase(get()) == "Healthy"):
            stable = name
        elif note(get()) == name:
            say(f"back to {stable}")
            patch(patch_for(stable))
        # Not while a later release is there: then the job was started again, and that one is not well because it is tried.
        if note(get()) == stable:
            wait(lambda: phase(get()) == "Healthy", f"it never became well after {name}", sleep, patience=600.0)
    say("the list is at its end")


def rollout_call(method="GET", body=None, address=ROLLOUT, account=ACCOUNT):
    """The token is read again each time, because it is changed while the job runs."""
    request = urllib.request.Request(address, method=method, data=None if body is None else json.dumps(body).encode())
    request.add_header("authorization", f"Bearer {(account / 'token').read_text().strip()}")
    request.add_header("content-type", "application/json-patch+json")
    context = ssl.create_default_context(cafile=str(account / "ca.crt")) if address.startswith("https:") else None
    with urllib.request.urlopen(request, timeout=10, context=context) as answer:
        return json.load(answer)


def read_marks(address=MARKS, last={}):
    """A front that does not answer for a moment changes nothing. What was known stays known."""
    try:
        with urllib.request.urlopen(address, timeout=5) as answer:
            last.update(json.load(answer))
    except (OSError, ValueError):
        pass
    return last


def main():
    names = read_list(pathlib.Path(LIST).read_text())
    walk(names, rollout_call, lambda body: rollout_call("PATCH", body), read_marks, say=lambda text: print(text, flush=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
