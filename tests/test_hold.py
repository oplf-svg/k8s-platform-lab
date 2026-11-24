"""A branch that must not be merged yet is red, whatever its tests say."""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / ".github" / "scripts" / "tests.sh"
RUN = "asked\nasked\n"


class Hold(unittest.TestCase):
    def tried(self, make=lambda place: None):
        """The real script in a folder of its own, and a python3 that only says that it was asked."""
        with tempfile.TemporaryDirectory() as folder:
            place = pathlib.Path(folder)
            (place / ".github" / "scripts").mkdir(parents=True)
            shutil.copy(SCRIPT, place / ".github" / "scripts" / "tests.sh")
            (place / "python3").write_text("#!/bin/sh\necho asked\n")
            (place / "python3").chmod(0o755)
            make(place)
            done = subprocess.run(["bash", str(place / ".github" / "scripts" / "tests.sh")], cwd="/", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                  env={**os.environ, "PATH": f"{place}:{os.environ['PATH']}"})
        return done.returncode, done.stdout

    def test_without_it_only_the_tests_count(self):
        self.assertEqual(self.tried(), (0, RUN))
        self.assertEqual(self.tried(lambda place: (place / "HOLDER").write_text("x")), (0, RUN))

        def deeper(place):
            (place / "a").mkdir()
            (place / "a" / "HOLD").write_text("x")
        self.assertEqual(self.tried(deeper), (0, RUN))

    def test_with_it_the_tests_are_run_and_it_is_red_and_says_why(self):
        for text, why in (("Waits for the first run, until 1 December.\nmore\n", "Waits for the first run, until 1 December."), ("", "")):
            self.assertEqual(self.tried(lambda place: (place / "HOLD").write_text(text)), (1, f"{RUN}Not to be merged yet: {why}\n"))

    def test_what_is_not_a_plain_file_is_red_and_nobody_reads_it(self):
        def link(place):
            (place / "other").write_text("not for the log")
            (place / "HOLD").symlink_to("other")
        for make in (link, lambda place: (place / "HOLD").symlink_to("nowhere"), lambda place: (place / "HOLD").mkdir()):
            self.assertEqual(self.tried(make), (1, f"{RUN}Not to be merged yet: HOLD is not a plain file.\n"))


if __name__ == "__main__":
    unittest.main()
