"""Puts many runs together. Ends with 1 if one of them was not as it has to be, or if some are missing.

  many.py FOLDER HOW_MANY TREE

FOLDER has a folder for each job, with what it left behind. A run counts only with everything that belongs to it, and it is
judged again here, so a summary that says otherwise changes nothing. TREE is the fingerprint of all files; a job with other
files does not count. "In a row" also means at the first try: GitHub can start a job again that failed.
"""

import hashlib
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "count"))
from count import compare, read  # noqa: E402
from judge import SCENARIOS, judge  # noqa: E402

# The rows of docs/contract.md that a single release stands for. The site counts these by their numbers.
ROWS = {"unasked": 8, "blind": 9, "restarted": 14, "interrupted": 15}


def sure(runs):
    """95% sure that it fails in less than so many of a hundred runs, when none of these failed."""
    return round(100 * (1 - 0.05 ** (1 / runs)), 1)


def look_at(folder, gate):
    """One line for each release that a job tried: which job, which release, its list, the errors, its seconds, what is wrong."""
    for status in sorted(folder.glob("*/*.status.json")):
        name, place = status.name.removesuffix(".status.json"), status.parent
        files = {what: place / f"{name}.{what}" for what in ("clients.jsonl", "front.jsonl")}
        wrong, print_of, errors, seconds = [f"{path.name} is missing" for path in files.values() if not path.exists()], "", 0, 0.0
        if not wrong:
            print_of = hashlib.sha256(files["clients.jsonl"].read_bytes()).hexdigest()
            clients, bad_clients = read(files["clients.jsonl"])
            front, bad_front = read(files["front.jsonl"])
            counted = compare(clients, front, name, bad_clients + bad_front)
            try:
                wrong = judge(name, counted, clients, json.loads(status.read_text()), gate) if name in SCENARIOS else ["it is not known"]
            except json.JSONDecodeError:
                wrong = ["what the controller said cannot be read"]
            first = min((line for line in clients if line.get("release")), key=lambda line: line["at"], default={})
            errors = counted["seen errors"]
            seconds = max((took for release, took in counted["seconds from first to last answer"].items() if release != first.get("release")), default=0.0)
        yield place.name, name, print_of, errors, seconds, wrong


def other_files(folder, tree):
    """The jobs that did not run exactly these files, or do not say which."""
    jobs = [place for place in sorted(folder.iterdir()) if place.is_dir()]
    said = {place.name: (place / "tree.txt").read_text().strip() if (place / "tree.txt").exists() else "nothing" for place in jobs}
    return [f"{job} ran {its}, and not {tree}" for job, its in said.items() if its != tree]


def for_the_site(how_many, table, problems):
    """Sentences that the site knows word for word. It says nothing if one of them is missing or not right."""
    said = {f"right {how_many} times in a row": not problems}
    said.update({f"row {row} was tried": len(table.get(name, [])) == how_many for name, row in ROWS.items()})
    return ["site: " + json.dumps({"lane": "ci", "what": what, "got": "yes" if ok else "no", "ok": ok}, separators=(",", ":")) for what, ok in said.items()]


def put_together(lines, how_many):
    problems, table, seen = [], {}, set()
    for job, name, print_of, errors, seconds, wrong in lines:
        if not wrong and print_of in seen:
            wrong = ["the same list stands there twice"]
        seen.add(print_of)
        if wrong:
            problems.append(f"{job}, {name}: {'; '.join(wrong)}")
        else:
            table.setdefault(name, []).append((errors, seconds))
    for name in SCENARIOS:
        there = len(table.get(name, []))
        if there != how_many:
            problems.append(f"{name}: {there} good runs, and {how_many} have to be there")
    return table, problems


def main(argv, env=os.environ):
    folder, how_many, tree = pathlib.Path(argv[0]), int(argv[1]), argv[2]
    gate = json.loads((ROOT / "gate.json").read_text())
    if not folder.is_dir():
        print("No job left anything behind.")
        return 1
    table, problems = put_together(look_at(folder, gate), how_many)
    problems += other_files(folder, tree)
    if env.get("GITHUB_RUN_ATTEMPT", "1") != "1":
        problems.append(f"this is try {env['GITHUB_RUN_ATTEMPT']} of the run, so it is not in a row")
    print("| Release | Runs | Errors that clients saw: fewest, middle, most | Seconds of the release: shortest, longest |")
    print("|---|---|---|---|")
    for name, rows in table.items():
        errors, seconds = sorted(row[0] for row in rows), sorted(row[1] for row in rows)
        print(f"| {name} | {len(rows)} | {errors[0]}, {errors[len(errors) // 2]}, {errors[-1]} | {seconds[0]}, {seconds[-1]} |")
    print()
    for one in for_the_site(how_many, table, problems):
        print(one)
    if problems:
        print(f"\n{len(problems)} problems:")
        for one in problems:
            print(f"- {one}")
        return 1
    print(f"\n{how_many} in a row, and none failed: it fails in less than {sure(how_many)}% of the runs, 95% sure.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
