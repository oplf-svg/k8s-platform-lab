"""Many runs put together: everything has to be there, and everything is judged again."""

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
for part in ("standin", "count", "tests"):
    sys.path.insert(0, str(ROOT / part))
import judge  # noqa: E402
import many  # noqa: E402
import test_judge  # noqa: E402

TIMES = {"good": {"last": 110.0}, "few": {"last": 98.0}, "refuses": {"last": 38.0}, "interrupted": {"last": 80.0}, "unasked": {"rate": 1, "seconds": 170, "last": 98.0}}


TREE = "0123456789abcdef0123456789abcdef01234567"


def job(folder, name, number):
    """What one job leaves behind about one release. The times differ a little, as they do."""
    place = folder / f"job-{number}-{name}"
    place.mkdir()
    (place / "tree.txt").write_text(TREE + "\n")
    clients, front = test_judge.made(name, **TIMES.get(name, {}))
    for line in clients[:-1]:
        line["at"] += number / 1000
    for what, lines in (("clients", clients), ("front", front)):
        (place / f"{name}.{what}.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines))
    (place / f"{name}.status.json").write_text(json.dumps(test_judge.said("Completed" if name == "good" else "Abort", gate=test_judge.GATES[name])))
    return place


# All of them are made once. The other tests do with these, because making and judging all of them takes a second each time.
SOME = ("good", "errors", "few", "slow", "unasked", "blind", "restarted", "interrupted")


class Place(unittest.TestCase):
    names = SOME

    def setUp(self):
        place = tempfile.TemporaryDirectory()
        self.addCleanup(place.cleanup)
        self.folder = pathlib.Path(place.name)
        only = mock.patch.object(many, "SCENARIOS", {name: judge.SCENARIOS[name] for name in self.names})
        only.start()
        self.addCleanup(only.stop)

    def result(self, how_many, **env):
        with contextlib.redirect_stdout(io.StringIO()) as said:
            code = many.main([str(self.folder), str(how_many), TREE], env=env)
        return code, said.getvalue()

    def for_the_site(self, said):
        return [line for line in said.splitlines() if line.startswith("site: ")]

    def all_of(self, how_many):
        return [job(self.folder, name, number) for number in range(how_many) for name in self.names]


class Many(Place):
    def test_a_job_with_other_files(self):
        places = self.all_of(1)
        (places[3] / "tree.txt").write_text("f" * 40)
        code, said = self.result(1)
        self.assertEqual(code, 1)
        self.assertIn(f"{places[3].name} ran {'f' * 40}, and not {TREE}", said)
        self.assertEqual(self.for_the_site(said)[0], 'site: {"lane":"ci","what":"right 1 times in a row","got":"no","ok":false}')
        (places[3] / "tree.txt").unlink()
        self.assertIn(f"{places[3].name} ran nothing, and not {TREE}", self.result(1)[1])

    def test_a_run_that_was_started_again(self):
        self.all_of(1)
        self.assertEqual(self.result(1, GITHUB_RUN_ATTEMPT="1")[0], 0)
        code, said = self.result(1, GITHUB_RUN_ATTEMPT="2")
        self.assertEqual(code, 1)
        self.assertIn("this is try 2 of the run, so it is not in a row", said)
        self.assertIn('"right 1 times in a row","got":"no","ok":false', said)

    def test_a_row_that_was_not_tried(self):
        places = self.all_of(1)
        (places[self.names.index("blind")] / "blind.status.json").unlink()
        code, said = self.result(1)
        self.assertEqual(code, 1)
        self.assertEqual([json.loads(line[6:])["ok"] for line in self.for_the_site(said)], [False, True, False, True, True])

    def test_one_is_missing_or_one_too_many(self):
        places = self.all_of(1)
        self.assertEqual(self.result(1)[0], 0)
        job(self.folder, "slow", 7)
        self.assertIn("slow: 2 good runs, and 1 have to be there", self.result(1)[1])
        self.assertEqual(self.result(1)[0], 1)
        (places[0] / "good.status.json").unlink()
        self.assertIn("good: 0 good runs, and 1 have to be there", self.result(1)[1])
        self.assertEqual(self.result(1)[0], 1)
        self.assertEqual(self.result(2)[0], 1)

    def test_one_was_not_as_it_has_to_be(self):
        place = [one for one in self.all_of(1) if one.name.endswith("-errors")][0]
        (place / "errors.status.json").write_text(json.dumps(test_judge.said("Completed", gate=test_judge.GATES["errors"])))
        code, said = self.result(1)
        self.assertEqual(code, 1)
        self.assertIn("and not Abort", said)

    def test_a_summary_that_says_otherwise_changes_nothing(self):
        place = [one for one in self.all_of(1) if one.name.endswith("-few")][0]
        (place / "few.counted.json").write_text('{"problems": []}')
        (place / "summary.md").write_text("- **few**: as it has to be.")
        lines = (place / "few.front.jsonl").read_text().splitlines(keepends=True)
        (place / "few.front.jsonl").write_text("".join(lines[:100]))
        self.assertIn("the numbers cannot be believed", self.result(1)[1])

    def test_a_list_is_missing(self):
        place = [one for one in self.all_of(1) if one.name.endswith("-slow")][0]
        (place / "slow.front.jsonl").unlink()
        self.assertIn("slow.front.jsonl is missing", self.result(1)[1])

    def test_the_same_run_twice(self):
        places = self.all_of(1)
        for place in places:
            again = self.folder / f"again-{place.name}"
            again.mkdir()
            for file in place.iterdir():
                (again / file.name).write_bytes(file.read_bytes())
        self.assertIn("the same list stands there twice", self.result(2)[1])

    def test_a_release_that_nobody_knows(self):
        self.all_of(1)
        place = self.folder / "other"
        place.mkdir()
        clients, front = test_judge.made("errors")
        for what, lines in (("clients", clients), ("front", front)):
            (place / f"other.{what}.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines))
        (place / "other.status.json").write_text("{}")
        self.assertIn("other, other: it is not known", self.result(1)[1])

    def test_how_sure_it_is(self):
        self.assertEqual([many.sure(runs) for runs in (1, 3, 20, 59, 299)], [95.0, 63.2, 13.9, 5.0, 1.0])


class All(Place):
    """Once with every release that there is."""
    names = tuple(judge.SCENARIOS)

    def test_everything_is_there_and_right(self):
        self.all_of(2)
        code, said = self.result(2)
        self.assertEqual(code, 0, said)
        self.assertIn("2 in a row, and none failed: it fails in less than 77.6% of the runs, 95% sure.", said)
        self.assertRegex(said, r"\| errors \| 2 \| ([1-9]\d), \1, \1 \| 24\.7, 24\.7 \|")
        self.assertIn("| dies | 2 | 0, 0, 0 | 0.0, 0.0 |", said)
        # Word for word, because the site counts them.
        self.assertEqual(self.for_the_site(said), [
            'site: {"lane":"ci","what":"right 2 times in a row","got":"yes","ok":true}',
            *(f'site: {{"lane":"ci","what":"row {row} was tried","got":"yes","ok":true}}' for row in (8, 9, 14, 15))])


if __name__ == "__main__":
    unittest.main()
