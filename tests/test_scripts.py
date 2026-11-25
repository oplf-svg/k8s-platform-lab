"""A script that a workflow starts is red when one of its parts is red, whatever comes after it."""

import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / ".github" / "scripts"
# It writes down that it was asked, and the one that FAIL names by its number fails.
ASKED = """#!/bin/sh
echo "$(basename "$0")${*:+ }$*${BREAK:+ while $BREAK}${GITHUB_RUN_ATTEMPT:+ at try $GITHUB_RUN_ATTEMPT}" >> "$LOG"
if [ "$(basename "$0")" = git ]; then echo the-tree; fi
[ "$(grep -c . "$LOG")" -ne "$FAIL" ]
"""


class Red(unittest.TestCase):
    def asked(self, script, *words, fail=0, others=()):
        """The real script in a folder of its own. All that it asks for only writes down that it was asked."""
        with tempfile.TemporaryDirectory() as folder:
            place = pathlib.Path(folder)
            (place / ".github" / "scripts").mkdir(parents=True)
            (place / "bin").mkdir()
            (place / "build" / "public").mkdir(parents=True)
            (place / "build" / "public" / "summary.md").write_text("what was seen\n")
            shutil.copy(SCRIPTS / script, place / ".github" / "scripts" / script)
            for file in [place / "bin" / name for name in ("python3", "git")] + [place / ".github" / "scripts" / name for name in others]:
                file.write_text(ASKED)
                file.chmod(0o755)
            done = subprocess.run(["bash", str(place / ".github" / "scripts" / script), *words], cwd="/", capture_output=True, text=True,
                                  env={**os.environ, "PATH": f"{place / 'bin'}:{os.environ['PATH']}", "LOG": str(place / "log"), "FAIL": str(fail),
                                       "GITHUB_STEP_SUMMARY": str(place / "page"), "GITHUB_RUN_ATTEMPT": "2"})
            # Every part is told which try it is, because the sum has to know it.
            log = (place / "log").read_text().splitlines()
            self.assertEqual([line for line in log if not line.endswith(" at try 2")], [])
            log = [line.removesuffix(" at try 2") for line in log]
            self.tree = place / "build" / "public" / "tree.txt"
            self.tree = self.tree.read_text() if self.tree.exists() else ""
            page = (place / "page").read_text() if (place / "page").exists() else ""
        return done.returncode, log, page

    def red_at_each(self, script, *words, others=(), all_of_it):
        code, log, page = self.asked(script, *words, others=others)
        self.assertEqual((code, log), (0, all_of_it))
        for number in range(1, len(all_of_it) + 1):
            with self.subTest(all_of_it[number - 1]):
                code, log, page = self.asked(script, *words, fail=number, others=others)
                self.assertNotEqual(code, 0)
                # Nothing after it is done.
                self.assertEqual(log, all_of_it[:number])
        return page

    def test_the_tests(self):
        self.red_at_each("tests.sh", all_of_it=["python3 -W error -m unittest discover --start-directory tests --verbose", "python3 tests/wrong.py"])

    def test_a_job(self):
        others = ("cluster.sh", "cannot.sh", "walls.sh", "releases.sh")
        tree = "git rev-parse HEAD^{tree}"
        page = self.red_at_each("job.sh", "cannot", "walls", "good", "errors", others=others, all_of_it=[
            tree, "cluster.sh good errors", "cannot.sh", "walls.sh", "releases.sh good errors while .github/scripts/break.sh"])
        # What was counted is on the page also then.
        self.assertEqual(page, "what was seen\n")
        self.red_at_each("job.sh", "run-07", "few", others=others, all_of_it=[tree, "cluster.sh few", "releases.sh few while .github/scripts/break.sh"])
        # Which files these are stands beside what is left behind, and a repetition tries the same things.
        self.assertEqual(self.tree, "the-tree\n")
        code, log, page = self.asked("job.sh", "run-07", "cannot", "walls", "few", "slow", others=others)
        self.assertEqual(log, [tree, "cluster.sh few slow", "cannot.sh", "walls.sh", "releases.sh few slow while .github/scripts/break.sh"])

    def test_the_sum(self):
        self.red_at_each("together.sh", "20", all_of_it=["git rev-parse HEAD^{tree}", "python3 count/many.py build/all 20 the-tree"])
        self.assertEqual(self.asked("together.sh")[1][1], "python3 count/many.py build/all 1 the-tree")
        # An empty word is not one time.
        self.assertEqual(self.asked("together.sh", "")[1][1], "python3 count/many.py build/all  the-tree")


class Text(unittest.TestCase):
    def test_every_script_begins_with_the_same_line(self):
        for script in sorted(SCRIPTS.glob("*.sh")):
            lines = [line for line in script.read_text().splitlines() if line and not line.startswith("#")]
            self.assertEqual(lines[0], "set -euo pipefail", script.name)
            self.assertEqual([line for line in lines if re.match(r"\s*set ", line)], ["set -euo pipefail"], script.name)

    def test_only_these_are_followed_by_or_true(self):
        there = {script.name: len(re.findall(r"\|\| (?:true|:)", script.read_text())) for script in SCRIPTS.glob("*.sh")}
        self.assertEqual({name: times for name, times in there.items() if times}, {"cluster.sh": 2, "job.sh": 1, "releases.sh": 6})


if __name__ == "__main__":
    unittest.main()
