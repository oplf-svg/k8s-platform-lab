"""What takes a part of the cluster away, with a cluster that is only pretended. It has to end badly when something did not happen."""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "count"))
from judge import AWAY  # noqa: E402

# Time goes on only when somebody sleeps. Every question is written down with its moment.
SLEEP = """#!/bin/sh
place=$(dirname "$0")
echo $(($(cat "$place/now") + $1)) > "$place/now"
"""
DOCKER = """#!/bin/sh
place=$(dirname "$0")
. "$place/settings"
now=$(cat "$place/now")
shift 5
echo "$now $*" >> "$place/asked"
since() { if [ -f "$place/$1" ]; then echo $((now - $(cat "$place/$1"))); else echo -1; fi; }
case "$*" in
  *"get rollout standin "*) if [ "$now" -ge "$BACK" ]; then printf Degraded; else printf Progressing; fi ;;
  *"get analysisrun "*) echo one; if [ "$now" -ge "$LOOKED" ]; then echo two; fi ;;
  *"get lease "*) if [ "$(since up)" -ge "$LEADS" ]; then printf "$NEW"; else printf "$LEADER"; fi ;;
  *"get pod "*) if [ "$(since down)" -lt "$GONE" ]; then echo pod/argo-rollouts-1; fi ;;
  *"deployment/argo-rollouts --replicas 0") echo "$now" > "$place/down" ;;
  *"deployment/argo-rollouts --replicas 1" | *"restart deployment/argo-rollouts") echo "$now" > "$place/up" ;;
esac
"""
AS_IT_IS = {"BACK": 28, "LOOKED": 4, "GONE": 2, "LEADS": 5, "LEADER": "old_1", "NEW": "new_2"}
NEVER = 9999


class Break(unittest.TestCase):
    def taken(self, name, **instead):
        """Returns how it ended, what it said, and what it asked the cluster: the moment and the words of each question."""
        with tempfile.TemporaryDirectory() as folder:
            place = pathlib.Path(folder)
            for program, text in (("sleep", SLEEP), ("docker", DOCKER)):
                (place / program).write_text(text)
                (place / program).chmod(0o755)
            (place / "now").write_text("0")
            (place / "asked").write_text("")
            (place / "settings").write_text("".join(f"{key}={value}\n" for key, value in {**AS_IT_IS, **instead}.items()))
            done = subprocess.run(["bash", str(ROOT / ".github" / "scripts" / "break.sh"), name], capture_output=True, text=True, timeout=60,
                                  env={**os.environ, "PATH": f"{place}:{os.environ['PATH']}"})
            asked = [line.split(" ", 1) for line in (place / "asked").read_text().splitlines()]
        return done.returncode, done.stdout + done.stderr, [(int(moment), words) for moment, words in asked]

    def when(self, asked, words):
        moments = [moment for moment, all_words in asked if words in all_words]
        self.assertEqual(len(moments), 1, (words, asked))
        return moments[0]

    def refused(self, name, words, **instead):
        code, said, asked = self.taken(name, **instead)
        self.assertEqual(code, 1, said)
        self.assertIn(words, said)
        return asked

    def test_nothing_is_taken_away_from_the_others(self):
        for name in ("good", "errors", "unasked", ""):
            self.assertEqual(self.taken(name), (0, "", []), name)

    def test_prometheus_is_away_until_the_release_has_gone_back(self):
        code, said, asked = self.taken("blind")
        self.assertEqual(code, 0, said)
        self.assertEqual(self.when(asked, "scale deployment/prometheus --replicas 0"), 0)
        self.assertEqual(self.when(asked, "scale deployment/prometheus --replicas 1"), 75)
        self.when(asked, "rollout status deployment/prometheus")

    def test_a_release_that_did_not_go_back_while_prometheus_was_away(self):
        asked = self.refused("blind", "the release is 'Progressing' and has to be 'Degraded'", BACK=NEVER)
        self.assertEqual([words for _, words in asked if "replicas 1" in words], [])

    def test_another_controller_takes_over(self):
        code, said, asked = self.taken("restarted")
        self.assertEqual(code, 0, said)
        self.assertEqual(self.when(asked, "rollout restart deployment/argo-rollouts"), 75)
        self.assertEqual(asked[-1][0], 80)
        self.assertIn("another controller leads", said)

    def test_a_controller_that_starts_again_before_the_release_went_back(self):
        asked = self.refused("restarted", "the release is 'Progressing' and has to be 'Degraded'", BACK=NEVER)
        self.assertEqual([words for _, words in asked if "restart" in words], [])

    def test_no_other_controller_takes_over(self):
        self.refused("restarted", "still not so: another controller leads", LEADS=NEVER)
        self.refused("interrupted", "still not so: another controller leads", LEADS=NEVER)

    def test_nobody_is_no_other_controller(self):
        self.refused("restarted", "still not so: another controller leads", NEW="")
        self.refused("interrupted", "still not so: another controller leads", NEW="")

    def test_nobody_leads_at_all(self):
        for name in ("restarted", "interrupted"):
            asked = self.refused(name, "still not so: a controller leads", LEADER="", LEADS=NEVER)
            self.assertEqual([words for _, words in asked if "restart" in words or "replicas" in words], [])

    def test_the_controller_goes_in_the_middle_and_stays_away(self):
        code, said, asked = self.taken("interrupted")
        self.assertEqual(code, 0, said)
        # At once when the release is looked at, which is before anything can be said about it.
        self.assertEqual(self.when(asked, "--replicas 0"), AS_IT_IS["LOOKED"])
        gone = AS_IT_IS["LOOKED"] + AS_IT_IS["GONE"]
        self.assertGreaterEqual(self.when(asked, "--replicas 1"), gone + AWAY)
        self.assertEqual(asked[-1][0], self.when(asked, "--replicas 1") + AS_IT_IS["LEADS"])

    def test_the_release_was_never_looked_at(self):
        asked = self.refused("interrupted", "still not so: the release is looked at", LOOKED=NEVER)
        self.assertEqual([words for _, words in asked if "replicas" in words], [])

    def test_the_controller_did_not_go(self):
        asked = self.refused("interrupted", "still not so: the controller is away", GONE=NEVER)
        self.assertEqual([words for _, words in asked if "replicas 1" in words], [])


if __name__ == "__main__":
    unittest.main()
