"""The proof that the tests can fail has to be able to fail too."""

import contextlib
import io
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import wrong  # noqa: E402

LEFT_OUT = {".git", "build", "__pycache__"}


def is_changed(place):
    """Whether one of the files is not as it is here."""
    files = [file.relative_to(ROOT) for file in ROOT.rglob("*") if file.is_file() and not LEFT_OUT & set(file.relative_to(ROOT).parts)]
    return any((place / file).read_bytes() != (ROOT / file).read_bytes() for file in files)


class Proof(unittest.TestCase):
    def result(self, noticed, words=""):
        with mock.patch.object(wrong, "noticed", noticed), contextlib.redirect_stdout(io.StringIO()) as said:
            code = wrong.main(words)
        return code, said.getvalue()

    def test_each_mistake_changes_something_and_nothing_else_is_one(self):
        code, said = self.result(lambda place, tests: tests.split()[0] if is_changed(place) else None)
        self.assertEqual(code, 0, said)
        self.assertIn(f"{len(wrong.MISTAKES)} of {len(wrong.MISTAKES)} mistakes were noticed.", said)
        # Every file of tests is tried without a mistake too, while the others run, apart from those that run alone.
        for name in {name for one in wrong.MISTAKES for name in one[4].split()} - wrong.ALONE:
            self.assertIn(f"right: no mistake, for test_{name}.py\n", said)

    def test_a_mistake_that_nobody_notices(self):
        code, said = self.result(lambda place, tests: None, "walker")
        self.assertEqual(code, 1)
        self.assertIn("NOT NOTICED: ", said)
        self.assertIn("\n0 of ", said)

    def test_a_machine_that_is_too_busy(self):
        # Right when it is alone, and then everything fails.
        code, said = self.result(lambda place, tests: None if place == ROOT else tests.split()[0], "walker")
        self.assertEqual(code, 1)
        self.assertIn("so nothing can be said: ['no mistake, for test_", said)

    def test_tests_that_are_not_right_from_the_start(self):
        code, said = self.result(lambda place, tests: tests.split()[0], "walker")
        self.assertEqual(code, 1)
        self.assertIn("is not right without a mistake, so nothing can be said.", said)

    def test_a_mistake_that_is_not_there(self):
        code, said = self.result(lambda place, tests: None, "no such mistake")
        self.assertEqual((code, said), (1, "0 of 0 mistakes were noticed.\n"))


if __name__ == "__main__":
    unittest.main()
