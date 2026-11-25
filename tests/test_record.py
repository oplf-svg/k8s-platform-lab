"""One release, second by second: everything is counted once, and in the second in which the client had it."""

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
for part in ("standin", "count", "tests"):
    sys.path.insert(0, str(ROOT / part))
import count  # noqa: E402
import record  # noqa: E402
import test_judge  # noqa: E402


def stamp(second):
    """A moment as Kubernetes writes it: whole seconds."""
    return f"2026-11-24T22:{second // 60:02d}:{second % 60:02d}Z"


def analysis(*looks, release="b2", name="standin"):
    """Looks of one run of the gate: second, metric, phase and what was read."""
    metrics = {}
    for second, metric, phase, value in looks:
        metrics.setdefault(metric, []).append({"finishedAt": stamp(second), "phase": phase, "value": value})
    return {"items": [{"metadata": {"name": f"{name}-{release}-4-1"}, "status": {"metricResults": [{"name": metric, "measurements": some} for metric, some in metrics.items()]}}]}


class Record(unittest.TestCase):
    def test_everything_is_counted_once(self):
        for scenario, times in {"errors": {}, "drops": {}, "refuses": {"last": 38.0}, "good": {"last": 110.0}, "dies": {}, "slow": {}}.items():
            clients, front = test_judge.made(scenario, **times)
            one, counted = record.record(scenario, clients), count.compare(clients, front, scenario, 0)
            self.assertEqual((one["sent"], one["counts"]["wrong"]), (counted["sent"], counted["seen errors"]), scenario)
            self.assertEqual({one["counts"][name] for name in ("old", "new") if one["counts"][name]}, set(counted["answers by release"].values()), scenario)
            self.assertEqual(sorted(one["took"].values()), sorted(counted["seconds from first to last answer"].values()), scenario)
            for name, seconds in one["a second"].items():
                self.assertEqual((sum(seconds), len(seconds)), (one["counts"][name], one["seconds"]), (scenario, name))
            self.assertEqual(one["sent"], one["counts"]["old"] + one["counts"]["new"] + one["counts"]["nobody"], scenario)
            self.assertEqual("nobody" in one["a second"], scenario == "drops", scenario)

    def test_the_second_is_the_one_of_the_answer(self):
        lines = [{"at": 100.0, "seconds": 0.5, "status": 202, "expected": 202, "release": "a"}, {"at": 100.9, "seconds": 0.2, "status": 401, "expected": 202, "release": "b"},
                 {"at": 102.0, "seconds": 0.1, "status": 202, "expected": 202, "release": "a"}, {"end": "x", "total": 3}]
        one = record.record("errors", lines)
        self.assertEqual(one["a second"], {"old": [1, 0, 1], "new": [0, 1, 0], "wrong": [0, 1, 0]})
        self.assertEqual((one["first"], one["last"], one["took"]), ({"old": 0.5, "new": 1.1}, {"old": 2.1, "new": 1.1}, {"old": 1.6, "new": 0.0}))

    def test_what_the_looks_came_to(self):
        zero = record.moment(stamp(0))
        looks = record.looks(analysis(
            (15, "clearly-wrong", "Successful", "[]"), (15, "clearly-slow", "Successful", "[]"), (15, "unanswered", "Successful", "[0]"),
            (20, "clearly-wrong", "Successful", "[1.25]"), (20, "clearly-slow", "Successful", "[0]"), (20, "unanswered", "Successful", "[0]"),
            (25, "clearly-wrong", "Failed", "[98.21428]"), (25, "clearly-slow", "Successful", "[0]"),
            (30, "unanswered", "Error", ""), (90, "wrong", "Failed", "[]"), (90, "slow", "Failed", "[]"), (95, "wrong", "Successful", "[0]"), (95, "slow", "Successful", "[0.5]")), "b2", zero)
        self.assertEqual(looks, [[15, "early", "nothing"], [20, "early", "well"], [25, "early", "bad", "clearly-wrong", 98.2], [30, "early", "error"],
                                 [90, "long", "bad", "slow", None], [95, "long", "well"]])

    def test_what_is_no_number_and_a_look_that_did_not_end(self):
        one = analysis((15, "clearly-wrong", "Successful", "[NaN]"), (20, "clearly-wrong", "Successful", "[2]"))
        one["items"][0]["status"]["metricResults"][0]["measurements"].append({"startedAt": stamp(25), "phase": "Running"})
        self.assertEqual(record.looks(one, "b2", record.moment(stamp(0))), [[15, "early", "nothing"], [20, "early", "well"]])

    def test_the_looks_at_another_release_are_not_its_own(self):
        both = analysis((15, "wrong", "Failed", "[50]"), release="a1")["items"] + analysis((15, "wrong", "Failed", "[50]"), release="b2", name="other")["items"]
        self.assertEqual(record.looks({"items": both}, "b2", record.moment(stamp(0))), [])
        self.assertEqual(record.looks(None, "b2", 0), [])

    def test_two_new_releases_are_not_one(self):
        with self.assertRaises(ValueError):
            record.record("good", [{"at": float(n), "seconds": 0.1, "status": 202, "expected": 202, "release": name} for n, name in enumerate("abc")])

    def test_the_program(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "c.jsonl"
            clients, _ = test_judge.made("refuses", last=38.0)
            path.write_text("".join(json.dumps(line) + "\n" for line in clients))
            with contextlib.redirect_stdout(io.StringIO()) as said:
                self.assertEqual(record.main(["--scenario", "refuses", "--clients", str(path), "--analysis", str(path.with_name("not-there"))]), 0)
            one = json.loads(said.getvalue())
            self.assertEqual((one["release"], one["looks"], len(said.getvalue().splitlines())), ("refuses", [], 1))
            for broken in ("".join(json.dumps(line) + "\n" for line in clients[:-1]), path.read_text() + "{\n"):
                path.write_text(broken)
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()) as said:
                    self.assertEqual((record.main(["--scenario", "refuses", "--clients", str(path)]), said.getvalue()), (1, ""))


if __name__ == "__main__":
    unittest.main()
