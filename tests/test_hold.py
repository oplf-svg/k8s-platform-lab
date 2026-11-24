"""A branch that must not be merged yet is red, whatever its tests say."""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / ".github" / "scripts" / "tests.sh"


class Hold(unittest.TestCase):
    def tried(self, **files):
        """The script in a folder of its own, and a python3 that only says that it was asked."""
        with tempfile.TemporaryDirectory() as folder:
            place = pathlib.Path(folder)
            (place / ".github" / "scripts").mkdir(parents=True)
            shutil.copy(SCRIPT, place / ".github" / "scripts" / "tests.sh")
            (place / "python3").write_text("#!/bin/sh\necho asked\n")
            (place / "python3").chmod(0o755)
            for name, text in files.items():
                (place / name).symlink_to(text[2:]) if text.startswith("->") else (place / name).write_text(text)
            done = subprocess.run(["bash", str(place / ".github" / "scripts" / "tests.sh")], cwd="/", capture_output=True, text=True, env={**os.environ, "PATH": f"{place}:{os.environ['PATH']}"})
        return done.returncode, done.stdout

    def test_without_it_the_tests_are_run(self):
        self.assertEqual(self.tried(), (0, "asked\nasked\n"))
        self.assertEqual(self.tried(HOLDER="x"), (0, "asked\nasked\n"))

    def test_with_it_nothing_is_run_and_it_says_why(self):
        self.assertEqual(self.tried(HOLD="Waits for the first run, until 1 December.\nmore\n"), (1, "Not to be merged yet: Waits for the first run, until 1 December.\n"))
        self.assertEqual(self.tried(HOLD=""), (1, "Not to be merged yet: \n"))
        self.assertEqual(self.tried(HOLD="->nowhere")[0], 1)


if __name__ == "__main__":
    unittest.main()
