"""Compares the two lists, request by request. Ends with 1 if anything is not explained.

  count.py --clients FILE --front FILE --run NAME [--strangers-allowed]

It does not say whether a release was good. It says whether the numbers can be believed, and what the clients saw.
"""

import argparse
import json
import sys
from collections import Counter

CUT_OFF = "499"
SLOW_FROM = 1.0
# A request that left so much later than planned, in seconds. Then the clients were the slow ones.
LATE_FROM = 0.5
# What counts as the end of a run, and as the beginning of a release, in seconds.
LAST = 5.0
FIRST = 60.0


def read(path):
    """A line that cannot be read is a problem, not something to skip."""
    good, bad = [], 0
    with open(path, encoding="utf-8") as lines:
        for line in lines:
            try:
                one = json.loads(line)
                if not isinstance(one, dict):
                    raise ValueError
                good.append(one)
            except ValueError:
                bad += 1
    return good, bad


def is_mark(line):
    return str(line.get("path", "")).startswith("/mark/")


def between_marks(front_lines, run, problems):
    """What the front wrote in this run. Other runs may stand before and after it, but not in it."""
    places = {which: [n for n, line in enumerate(front_lines) if line.get("path") == f"/mark/{run}/{which}"] for which in ("start", "end")}
    for which, found in places.items():
        if len(found) != 1:
            problems.append(f"the list of the front has no single mark for the {which}")
    part = front_lines
    if all(len(found) == 1 for found in places.values()):
        part = front_lines[places["start"][0] + 1:places["end"][0]]
        problems += [f"another run stands in the middle of this one: {line['path']}" for line in part if is_mark(line)]
    return [line for line in part if not is_mark(line)]


def moment(line):
    """When the answer was there, not when it was asked for."""
    return line.get("at", 0.0) + line.get("seconds", 0.0)


def look_at_times(answered):
    """When each release answered, what answered at the end, and which share a release had when it was new."""
    if not answered:
        return {}, [], {}
    times = {}
    for line in answered:
        if line.get("release"):
            first, last = times.get(line["release"], (moment(line), moment(line)))
            times[line["release"]] = (min(first, moment(line)), max(last, moment(line)))
    end = max(moment(line) for line in answered)
    at_the_end = sorted({line.get("release") or "the front itself" for line in answered if moment(line) > end - LAST})
    share = {}
    for release, (first, last) in times.items():
        # A release that is stopped after 20 seconds has no first minute, so only the time that it was there counts.
        window = [line.get("release") for line in answered if first <= moment(line) <= min(last, first + FIRST)]
        share[release] = round(100 * window.count(release) / len(window), 1)
    return times, at_the_end, share


def compare(client_lines, front_lines, run, unreadable=0, strangers_allowed=False):
    problems = []
    if unreadable:
        problems.append(f"{unreadable} lines cannot be read")

    ends = [line for line in client_lines if "end" in line]
    sent = [line for line in client_lines if "end" not in line]
    if len(ends) != 1 or ends[0]["end"] != run:
        problems.append("the list of the clients has no end")
    total = ends[0].get("total") if len(ends) == 1 else None

    # Every number from 1 to the total, exactly once.
    numbers = Counter(line["number"] for line in sent)
    if not sent:
        problems.append("the clients sent nothing")
    if total is not None:
        missing = [n for n in range(1, total + 1) if n not in numbers]
        strange = [n for n in numbers if not 1 <= n <= total]
        if missing:
            problems.append(f"{len(missing)} numbers are missing in the list of the clients, the first is {missing[0]}")
        if strange:
            problems.append(f"{len(strange)} numbers in the list of the clients were never planned")
    problems += [f"the clients have number {n} more than once" for n, times in numbers.items() if times > 1]
    problems += [f"{line['id']} does not fit its number" for line in sent if line["id"] != f"{run}-{line['number']:07d}"]

    front, strangers = {}, 0
    for line in between_marks(front_lines, run, problems):
        event = line.get("id") or ""
        if not event.startswith(f"{run}-"):
            strangers += 1
            continue
        if event in front:
            problems.append(f"the front answered {event} more than once")
        front[event] = line
        # "500, 202" means that it asked twice and hid the first answer.
        upstream = str(line.get("upstream", ""))
        if "," in upstream or ":" in upstream:
            problems.append(f"the front repeated {event}: {upstream}")
    if strangers and not strangers_allowed:
        problems.append(f"{strangers} requests in the list of the front are from somebody else")

    known = {line["id"] for line in sent}
    problems += [f"the front answered {event}, which no client sent" for event in front if event not in known]

    seen, slow = Counter(), Counter()
    releases, pods, kinds = Counter(), {}, Counter()
    for line in sent:
        event, status = line["id"], line["status"]
        there = front.get(event)
        if status is None:
            kinds["only the client knows" if there is None else "cut off"] += 1
        elif there is None:
            problems.append(f"{event} was answered with {status}, and the front does not know of it")
        elif str(there.get("status")) == CUT_OFF or str(there.get("status")) != str(status):
            problems.append(f"{event}: the client got {status}, the front says {there.get('status')}")
        else:
            kinds["both agree"] += 1
            if there.get("release", "") != line.get("release", ""):
                problems.append(f"{event}: both lists name another release")
        if status != line["expected"]:
            seen[str(status) if status is not None else "no answer"] += 1
        release = line.get("release") or ""
        if release:
            releases[release] += 1
            pods.setdefault(release, set()).add(line.get("pod", ""))
            slow[release] += line.get("seconds", 0.0) > SLOW_FROM

    times, at_the_end, share = look_at_times([line for line in sent if line["status"] is not None])
    return {
        "run": run,
        "sent": len(sent),
        "seen errors": sum(seen.values()),
        "seen errors by answer": dict(sorted(seen.items())),
        "requests": dict(sorted(kinds.items())),
        "strangers": strangers,
        "late requests": sum(line.get("late", 0.0) > LATE_FROM for line in sent),
        "answers by release": dict(sorted(releases.items())),
        "slow answers by release": {name: n for name, n in sorted(slow.items()) if n},
        "pods by release": {name: len(found) for name, found in sorted(pods.items())},
        "seconds from first to last answer": {name: round(last - first, 1) for name, (first, last) in sorted(times.items())},
        "share in the first minute": dict(sorted(share.items())),
        "answers at the end": at_the_end,
        "problems": problems,
    }


def main(argv=None):
    ask = argparse.ArgumentParser()
    ask.add_argument("--clients", required=True)
    ask.add_argument("--front", required=True)
    ask.add_argument("--run", required=True)
    ask.add_argument("--strangers-allowed", action="store_true")
    given = ask.parse_args(argv)
    clients, bad_clients = read(given.clients)
    front, bad_front = read(given.front)
    result = compare(clients, front, given.run, bad_clients + bad_front, given.strangers_allowed)
    print(json.dumps(result, indent=2))
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
