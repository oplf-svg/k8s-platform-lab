"""The rules that the two workflow files have to keep. Agents may not change them, and the list of clusters comes from a script that a
pull request can change. That they are the files that were looked at at all is said in test_files.py."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
OFTEN = (ROOT / ".github" / "workflows" / "often.yml").read_text()
BOTH = {"ci.yml": CI, "often.yml": OFTEN}


def jobs(text):
    """Each job with its lines. A name that nobody expects is a job too."""
    parts = re.split(r"(?m)^  (\S+):\n", text.split("\njobs:\n")[1])
    return dict(zip(parts[1::2], parts[2::2]))


def lines(text, *starts):
    return [line for line in text.splitlines() if line.strip().startswith(starts)]


class Both(unittest.TestCase):
    def test_no_job_may_write_anything(self):
        for name, text in BOTH.items():
            with self.subTest(name):
                self.assertEqual(set(lines(text, "permissions")), {"permissions: {}", "    permissions:"})
                # What stands under it is only this, and a job without it gets what stands at the top: nothing.
                under = re.findall(r"(?m)^    permissions:\n((?:      .*\n)+)", text)
                self.assertEqual(len(under), text.count("\n    permissions:\n"))
                self.assertLessEqual({line for part in under for line in part.splitlines()}, {"      contents: read", "      pull-requests: read"})
                self.assertEqual(re.findall(r"\bwrite-all\b|: write\b", text), [])

    def test_every_job_is_on_the_same_machine_and_has_no_sign_in_anywhere(self):
        for name, text in BOTH.items():
            with self.subTest(name):
                self.assertEqual(set(lines(text, "runs-on")), {"    runs-on: ubuntu-24.04"})
                self.assertEqual(len(lines(text, "runs-on")), len(jobs(text)))
                for word in ("environment:", "container:", "services:", "id-token", "pull_request_target", "workflow_run", "workflow_call", "toJSON(secrets", "inherit"):
                    self.assertNotIn(word, text)

    def test_only_actions_of_github_at_a_commit(self):
        for name, text in BOTH.items():
            with self.subTest(name):
                for action in re.findall(r"uses: (.*)", text):
                    self.assertRegex(action, r"^actions/(checkout|upload-artifact|download-artifact)@[0-9a-f]{40} # v[\d.]+$")

    def test_what_is_red_is_red_and_nothing_is_left_out(self):
        for text, whens in ((CI, ["${{ always() }}"] * 2), (OFTEN, ["${{ github.ref == 'refs/heads/main' }}", "${{ always() }}", "${{ !cancelled() && needs.list.result == 'success' }}"])):
            # With this word a step that fails counts as passed, and a job that fails does not make the run red.
            self.assertNotIn("continue-on-error", text)
            self.assertNotIn("||", text)
            self.assertEqual(re.findall(r"\bif: (.*)", text), whens)
            self.assertNotIn("shell:", text)

    def test_the_sign_in_of_git_is_not_kept(self):
        for name, text in BOTH.items():
            with self.subTest(name):
                self.assertEqual(text.count("uses: actions/checkout@"), text.count("          persist-credentials: false\n"))

    def test_a_long_list_cannot_take_all_machines(self):
        for name, text in BOTH.items():
            with self.subTest(name):
                self.assertEqual(lines(text, "max-parallel", "fail-fast", "words: ${{ fromJSON"),
                                 ["      fail-fast: false", "      max-parallel: 5", "        words: ${{ fromJSON(needs.list.outputs.words) }}"])

    def test_the_words_of_the_list_reach_nothing_but_a_name_and_a_setting(self):
        for name, text in BOTH.items():
            with self.subTest(name):
                self.assertEqual(text.count("matrix.words"), 2)
                self.assertIn("    name: cluster (${{ matrix.words }})\n", text)
                self.assertIn("          WORDS: ${{ matrix.words }}\n", text)
                self.assertIn("run: bash .github/scripts/job.sh $WORDS\n", text)


class Ci(unittest.TestCase):
    def test_only_the_private_terms_are_a_secret(self):
        self.assertEqual(re.findall(r"secrets\b.*", CI), ["secrets.BLOCKED_TERMS }}"])
        self.assertIn("secrets.BLOCKED_TERMS", jobs(CI)["blocked-terms"])

    def test_each_job_does_what_it_is_there_for(self):
        self.assertEqual(list(jobs(CI)), ["tests", "list", "clusters", "blocked-terms", "ci"])
        for name, run in (("tests", "- run: bash .github/scripts/tests.sh"), ("list", 'run: bash .github/scripts/list.sh >> "$GITHUB_OUTPUT"'),
                          ("clusters", "- run: bash .github/scripts/job.sh $WORDS"), ("blocked-terms", 'run: python3 -I "$RUNNER_TEMP/blocked_terms.py"')):
            self.assertEqual([line.strip() for line in jobs(CI)[name].splitlines()].count(run), 1, run)
        # The others can print lines of the code, so they wait.
        for name in ("tests", "list", "clusters"):
            self.assertRegex(jobs(CI)[name], r"(?m)^    needs: (blocked-terms|\[blocked-terms, list\])$")

    def test_it_runs_for_every_pull_request(self):
        self.assertIn("\non:\n  pull_request:\n    types: [opened, synchronize, reopened, edited]\n\n", CI)

    def test_the_required_check_is_one_job_and_waits_for_every_other(self):
        self.assertEqual([line.strip() for line in lines(CI, "name: ") if line.startswith("    name:")], ["name: cluster (${{ matrix.words }})"])
        check = jobs(CI)["ci"]
        others = [name for name in jobs(CI) if name != "ci"]
        self.assertEqual(sorted(re.findall(r"needs: \[(.*)\]", check)[0].split(", ")), sorted(others))
        # Every word of it, because one that is missing makes it green.
        self.assertTrue(check.endswith(f"""        run: |
          jq --raw-output 'to_entries[] | "\\(.key): \\(.value.result)"' <<< "$RESULTS"
          jq --exit-status --arg attempt "$ATTEMPT" '
            length == {len(others)}
            and all(.[]; .result == "success")
            and ."blocked-terms".outputs.attempt == $attempt
          ' <<< "$RESULTS" > /dev/null
"""), check)


class Often(unittest.TestCase):
    """The same clusters, several times, and then all of them judged together. Started by hand."""

    def test_it_is_started_by_hand_and_only_on_what_was_approved(self):
        self.assertEqual(re.findall(r"(?m)^  (\S+):", OFTEN.split("\non:\n")[1].split("\npermissions:")[0]), ["workflow_dispatch"])
        self.assertIn("    if: ${{ github.ref == 'refs/heads/main' }}\n", jobs(OFTEN)["list"])
        self.assertIn('        required: true\n        type: choice\n        options: ["20", "2"]\n', OFTEN)
        # Every other job waits for that one, and each takes the files of the run.
        self.assertIn("    needs: list\n", jobs(OFTEN)["clusters"])
        self.assertNotIn(" ref:", OFTEN)

    def test_it_can_never_stand_in_for_the_required_check(self):
        self.assertEqual(list(jobs(OFTEN)), ["list", "clusters", "together"])
        self.assertEqual([line for line in lines(OFTEN, "name: ") if line.startswith("    name:")], ["    name: cluster (${{ matrix.words }})"])

    def test_one_run_does_not_end_another(self):
        self.assertIn("\nconcurrency:\n  group: often\n  cancel-in-progress: false\n", OFTEN)

    def test_a_cluster_is_the_same_as_in_a_pull_request(self):
        def without_what_it_waits_for(job):
            return re.sub(r"    needs: .*\n", "", job).split("\n\n  #")[0].rstrip()
        self.assertEqual(without_what_it_waits_for(jobs(OFTEN)["clusters"]), without_what_it_waits_for(jobs(CI)["clusters"]))

    def test_what_somebody_chose_reaches_nothing_but_a_setting(self):
        self.assertEqual(lines(OFTEN, "TIMES:"), ["          TIMES: ${{ inputs.times }}"] * 2)
        self.assertEqual(OFTEN.count("inputs"), 3)
        self.assertIn('run: bash .github/scripts/list.sh "$TIMES" >> "$GITHUB_OUTPUT"\n', jobs(OFTEN)["list"])

    def test_it_sees_no_secret(self):
        self.assertNotIn("secrets", OFTEN)

    def test_it_judges_also_when_something_was_red(self):
        sum_of_all = jobs(OFTEN)["together"]
        self.assertIn("    needs: [list, clusters]\n    if: ${{ !cancelled() && needs.list.result == 'success' }}\n", sum_of_all)
        # Only what this run left behind, and then the judging, with nothing between.
        self.assertTrue(sum_of_all.endswith("""        with:
          pattern: counted *
          path: build/all
      - run: bash .github/scripts/together.sh "$TIMES"
        env:
          TIMES: ${{ inputs.times }}
"""), sum_of_all)


if __name__ == "__main__":
    unittest.main()
