"""What one release was like for the clients, second by second. Numbers only and as small as possible, so that a page can draw it.

  record.py --scenario refuses --clients FILE [--analysis FILE]

One line of JSON. Second 0 begins with the first request. An answer belongs to the second in which the client had it. What the
looks came to is there where somebody could ask the cluster; their moments are whole seconds.
"""

import argparse
import datetime
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "count"))
from count import read  # noqa: E402

EARLY, LONG = ("clearly-wrong", "clearly-slow", "unanswered"), ("wrong", "slow")


def moment(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def number(value):
    """What a look read, "[14.1]", or None if it read nothing that is a number."""
    found = json.loads(value) if value else []
    return round(float(found[0]), 1) if found and math.isfinite(found[0]) else None


def looks(analysis, release, zero, name="standin"):
    """Each look at the release: its second, which look it was, and what it came to. A look that says no says also why."""
    found = {}
    for run in analysis["items"] if analysis else []:
        if not run["metadata"]["name"].startswith(f"{name}-{release}-"):
            continue
        for metric in run["status"].get("metricResults", []):
            for one in metric.get("measurements", []):
                if not one.get("finishedAt"):
                    continue
                second = int(moment(one["finishedAt"]) - zero)
                kind = "early" if metric["name"] in EARLY else "long"
                found.setdefault((second, kind), {})[metric["name"]] = (one["phase"], number(one.get("value")))
    said = []
    for (second, kind), metrics in sorted(found.items()):
        failed = [(metric, value) for metric, (phase, value) in sorted(metrics.items()) if phase == "Failed"]
        # Whether it could say anything is said by those that count the requests of the release.
        read_something = any(metrics.get(metric, ("", None))[1] is not None for metric in ("clearly-wrong", "clearly-slow", *LONG))
        if failed:
            said.append([second, kind, "bad", *failed[0]])
        elif any(phase == "Error" for phase, _ in metrics.values()):
            said.append([second, kind, "error"])
        else:
            said.append([second, kind, "well" if read_something else "nothing"])
    return said


def record(scenario, lines, analysis=None):
    sent = [line for line in lines if "end" not in line]
    zero = min(line["at"] for line in sent)
    had = lambda line: line["at"] + line["seconds"] - zero  # noqa: E731
    answered = [line for line in sent if line.get("release")]
    old = min(answered, key=lambda line: line["at"])["release"]
    new = sorted({line["release"] for line in answered} - {old})
    if len(new) > 1:
        raise ValueError(f"there are {len(new)} new releases")
    whose = {"old": [line for line in answered if line["release"] == old], "new": [line for line in answered if line["release"] != old],
             "nobody": [line for line in sent if not line.get("release")], "wrong": [line for line in sent if line["status"] != line["expected"]]}
    long = int(max(had(line) for line in sent)) + 1
    a_second = {}
    for name, part in whose.items():
        if part or name in ("old", "new", "wrong"):
            counts = [0] * long
            for line in part:
                counts[int(had(line))] += 1
            a_second[name] = counts
    return {
        "release": scenario,
        "seconds": long,
        "sent": len(sent),
        "counts": {name: len(part) for name, part in whose.items()},
        "first": {name: round(min(had(line) for line in whose[name]), 1) for name in ("old", "new") if whose[name]},
        "last": {name: round(max(had(line) for line in whose[name]), 1) for name in ("old", "new") if whose[name]},
        # From the first to the last answer, as the judge counts it.
        "took": {name: round(max(map(had, whose[name])) - min(map(had, whose[name])), 1) for name in ("old", "new") if whose[name]},
        "looks": looks(analysis, new[0], zero) if new else [],
        "a second": a_second,
    }


def main(argv=None):
    ask = argparse.ArgumentParser()
    ask.add_argument("--scenario", required=True)
    ask.add_argument("--clients", required=True)
    ask.add_argument("--analysis")
    given = ask.parse_args(argv)
    lines, unreadable = read(given.clients)
    if unreadable or not any("end" in line for line in lines):
        print("The list of the clients cannot be read to its end.", file=sys.stderr)
        return 1
    analysis = json.loads(pathlib.Path(given.analysis).read_text()) if given.analysis and pathlib.Path(given.analysis).exists() else None
    print(json.dumps(record(given.scenario, lines, analysis), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
