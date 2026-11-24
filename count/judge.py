"""Says whether a run was what docs/contract.md asks for. Ends with 1 if not, and says why.

  judge.py --scenario errors --counted FILE --clients FILE --status FILE

The numbers stand in gate.json. What the controller says about itself is only one of the things that are looked at.
"""

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "standin"))
sys.path.insert(0, str(ROOT / "count"))
from app import ONE_IN, picked  # noqa: E402
from count import read  # noqa: E402

GOOD, BAD, NEVER_ANSWERS = "good", "bad", "bad, and never answers"
SCENARIOS = {"good": GOOD, "errors": BAD, "few": BAD, "drops": BAD, "refuses": BAD, "slow": BAD, "never-ready": NEVER_ANSWERS, "dies": NEVER_ANSWERS}
# 1 pod of 10 should get a tenth. Far from it means that the clients, the front or the cluster do not share as we think.
SHARE = (4.0, 20.0)
# How many requests in 100 may leave late. More, and the clients could not keep up, so the release got fewer than planned.
LATE = 1
# Which look has to stop it. A release that goes back because nothing could be measured was stopped by none of these.
WHY = {"errors": {"clearly-wrong"}, "refuses": {"clearly-wrong"}, "slow": {"clearly-slow"}, "drops": {"unanswered"}, "few": {"clearly-wrong", "wrong"}}
LOOKS = {"clearly-wrong", "clearly-slow", "unanswered", "wrong", "slow"}
# How the controller's metric calls it. Its status field has other names for the same: Healthy and Degraded.
DONE, ROLLED_BACK = "Completed", "Abort"


def phases(status, name="standin"):
    """What the controller says about the release. None, or more than one, is not an answer."""
    if not isinstance(status, dict) or status.get("status") != "success":
        return []
    return sorted(one["metric"].get("phase", "") for one in status["data"]["result"] if one["metric"].get("name") == name)


def looks(status, release, name="standin"):
    """What each look at this release came to: one line for each run of the gate and each of its five looks."""
    if not isinstance(status, dict) or status.get("status") != "success":
        return []
    rows = [one["metric"] for one in status["data"]["result"]]
    return sorted((row.get("name", ""), row.get("metric", ""), row.get("phase", "")) for row in rows if row.get("name", "").startswith(f"{name}-{release}-"))


def judge(scenario, counted, client_lines, status, gate):
    if not isinstance(status, dict) or set(status) != {"release", "gate"}:
        return ["nobody asked the controller"]
    if counted["problems"]:
        return ["the numbers cannot be believed", *counted["problems"][:20]]
    kind = SCENARIOS[scenario]
    sent = [line for line in client_lines if "end" not in line]
    answered = [line for line in sent if line["status"] is not None and line.get("release")]
    if not answered:
        return ["nobody got an answer"]
    # What answered first is the old release. The names are given by the cluster, so they say nothing else.
    old = min(answered, key=lambda line: line["at"])["release"]
    others = sorted(set(counted["answers by release"]) - {old})

    wrong = []
    errors, at_the_end = counted["seen errors"], counted["answers at the end"]
    if counted["late requests"] * 100 > counted["sent"] * LATE:
        wrong.append(f"the clients could not keep up: {counted['late requests']} of {counted['sent']} requests left late")
    said, stays = phases(status["release"]), DONE if kind == GOOD else ROLLED_BACK
    if said != [stays]:
        wrong.append(f"the controller says {said or 'nothing'} and not {stays}")

    if kind == NEVER_ANSWERS:
        if others:
            wrong.append(f"{others} answered, and should never have been asked")
        if errors:
            wrong.append(f"clients saw {errors} errors: {counted['seen errors by answer']}")
        if at_the_end != [old]:
            wrong.append(f"at the end the answers came from {at_the_end}")
        return wrong

    if len(others) != 1:
        return [*wrong, f"there are {len(others)} new releases, so nothing was tried"]
    new = others[0]
    reached, share = counted["answers by release"][new], counted["share in the first minute"][new]
    took = counted["seconds from first to last answer"][new]
    if at_the_end != [new if kind == GOOD else old]:
        wrong.append(f"at the end the answers came from {at_the_end}")
    # The early look needs fewer requests, and a bad release should not get more than it takes.
    if reached < gate["at_least" if kind == GOOD else "early_at_least"]:
        wrong.append(f"only {reached} requests reached the new release, so nothing was tried")
    if not SHARE[0] <= share <= SHARE[1]:
        wrong.append(f"the new release got {share}% of the requests in its first minute, which is not 1 pod of 10")
    results = looks(status["gate"], new)
    if kind == GOOD:
        if errors:
            wrong.append(f"clients saw {errors} errors: {counted['seen errors by answer']}")
        # Two runs of the gate, with five looks each.
        runs = {run for run, _, _ in results}
        passed = {(run, look) for run, look, phase in results if phase == "Successful"}
        if len(runs) != 2 or passed != {(run, look) for run in runs for look in LOOKS}:
            wrong.append(f"it did not pass every look twice: {results}")
        return wrong
    stopped = {look for _, look, phase in results if phase in ("Failed", "Error")}
    if not stopped or not stopped <= WHY[scenario]:
        wrong.append(f"it was stopped by {sorted(stopped) or 'no look'} and not by {sorted(WHY[scenario])}: {results}")
    if errors > gate["seen_errors"]:
        wrong.append(f"clients saw {errors} errors, and {gate['seen_errors']} are acceptable")
    if took > gate["rolled_back_seconds"]:
        wrong.append(f"it answered for {took} seconds, and {gate['rolled_back_seconds']} are acceptable")
    return wrong + was_it_bad(scenario, sent, counted, new)


def was_it_bad(scenario, sent, counted, new):
    """A release that was not as bad as planned proves nothing."""
    its_answers = [line for line in sent if line.get("release") == new]
    good = [line for line in its_answers if line["feed"] == "good"]
    if scenario == "drops":
        # What it dropped has no release on it, so it is known by its id. Nothing else may be unanswered.
        dropped = [line["id"] for line in sent if line["status"] == 502]
        other = [event for event in dropped if not picked(event, ONE_IN[scenario])]
        kept = [line["id"] for line in good if picked(line["id"], ONE_IN[scenario])]
        return [*([] if dropped else ["it dropped nothing"]),
                *([f"{len(other)} others were dropped, the first is {other[0]}"] if other else []),
                *([f"{len(kept)} answers were not as planned, the first is {kept[0]}"] if kept else [])]
    if scenario in ONE_IN:
        other = [line["id"] for line in good if line["status"] != (500 if picked(line["id"], ONE_IN[scenario]) else 202)]
        return [f"{len(other)} answers were not as planned, the first is {other[0]}"] if other else []
    if scenario == "refuses":
        other = [line["id"] for line in good if line["status"] != 401]
        return [f"{len(other)} good requests were not refused, the first is {other[0]}"] if other else []
    slow = counted["slow answers by release"].get(new, 0)
    return [] if slow == len(its_answers) else [f"only {slow} of {len(its_answers)} answers were slow"]


def main(argv=None):
    ask = argparse.ArgumentParser()
    ask.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    ask.add_argument("--counted", required=True)
    ask.add_argument("--clients", required=True)
    ask.add_argument("--status", required=True)
    given = ask.parse_args(argv)
    counted = json.loads(pathlib.Path(given.counted).read_text())
    status = json.loads(pathlib.Path(given.status).read_text())
    clients, unreadable = read(given.clients)
    gate = json.loads((ROOT / "gate.json").read_text())
    wrong = judge(given.scenario, counted, clients, status, gate)
    if unreadable:
        wrong.append(f"{unreadable} lines of the clients cannot be read")
    print(f"- **{given.scenario}**: {'as it has to be' if not wrong else 'NOT as it has to be'}. "
          f"{counted['sent']} requests, {counted['seen errors']} errors that clients saw. "
          f"Seconds from first to last answer: {counted['seconds from first to last answer']}")
    for one in wrong:
        print(f"  - {one}")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
