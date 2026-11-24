"""The walker without a cluster: what it does, in which order, and what it sends."""

import http.server
import json
import pathlib
import sys
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "k8s" / "walk"))
import walker  # noqa: E402


class Pretended:
    """A cluster and a front in which time passes only when the walker waits."""

    def __init__(self, plan, note="one"):
        # When each run begins and is over, and which release the Rollout has.
        self.plan, self.note, self.now, self.said, self.changed = plan, note, 0.0, [], 0.0
        self.broken = False
        # A release that the gate does not let through.
        self.refused = None

    def sleep(self, seconds):
        self.now += seconds

    def marks(self):
        known = {}
        for name, (begins, ends) in self.plan.items():
            if self.now >= begins:
                known[name] = "ended" if self.now >= ends else "started"
        return known

    def get(self):
        # While a bad release is there, it is never well.
        well = self.note in ("one", "good") and self.note != self.refused and not self.broken and self.now >= self.changed + 20
        phase = "Healthy" if well else "Degraded"
        return {"spec": {"template": {"spec": {"containers": [{"env": [{"name": "NOTE", "value": self.note}, {"name": "FAIL"}]}]}}}, "status": {"phase": phase}}

    def patch(self, body):
        self.note, self.changed = body[0]["value"], self.now
        self.said.append((round(self.now), body[0]["value"], body[1]["value"]))

    def walk(self, *names):
        walker.walk(list(names), self.get, self.patch, self.marks, self.sleep, lambda text: None)
        return self.said


class Walk(unittest.TestCase):
    def test_each_release_begins_after_its_mark_and_goes_back_after_the_other(self):
        said = Pretended({"errors": (100, 200), "few": (300, 400)}).walk("errors", "few")
        self.assertEqual(said, [(110, "errors", "errors"), (200, "one", ""), (310, "few", "few"), (400, "one", "")])

    def test_a_good_release_stays_and_is_what_the_next_goes_back_to(self):
        said = Pretended({"good": (10, 300), "slow": (400, 500)}).walk("good", "slow")
        self.assertEqual(said, [(20, "good", ""), (410, "slow", "slow"), (500, "good", "")])

    def test_a_good_release_that_was_not_let_through_is_not_kept(self):
        there = Pretended({"good": (10, 300), "slow": (400, 500)})
        there.refused = "good"
        self.assertEqual(there.walk("good", "slow"), [(20, "good", ""), (300, "one", ""), (410, "slow", "slow"), (500, "one", "")])

    def test_the_order_of_the_list_decides_and_not_the_order_of_the_marks(self):
        said = Pretended({"few": (0, 1000), "errors": (500, 600)}).walk("errors", "few")
        self.assertEqual([what for _, what, _ in said], ["errors", "one", "few", "one"])
        self.assertGreater(said[0][0], 500)

    def test_a_run_that_is_not_on_the_list_changes_nothing(self):
        said = Pretended({"dies": (0, 50), "errors": (100, 200)}).walk("errors")
        self.assertEqual([what for _, what, _ in said], ["errors", "one"])

    def test_it_waits_until_all_is_well(self):
        there = Pretended({"errors": (0, 100), "few": (100, 200)})
        said = there.walk("errors", "few")
        # 20 seconds until it is well again, and then the 10 in which the old release is seen alone.
        self.assertEqual(said[1][0], 100)
        self.assertGreaterEqual(said[2][0], 130)

    def test_it_gives_up_when_it_never_becomes_well(self):
        there = Pretended({"errors": (0, 100), "few": (100, 200)})
        there.broken = True
        with self.assertRaises(walker.Gone):
            there.walk("errors", "few")
        self.assertEqual([what for _, what, _ in there.said], ["errors", "one"])

    def test_it_gives_up_when_nobody_comes(self):
        with self.assertRaises(walker.Gone):
            Pretended({}).walk("errors")

    def test_started_again_in_the_middle_of_a_run_it_does_not_begin_it_again(self):
        there = Pretended({"errors": (0, 100)}, note="errors")
        there.now = 60
        self.assertEqual(there.walk("errors"), [(100, "one", "")])

    def test_started_again_it_does_not_end_the_run_of_a_later_release(self):
        there = Pretended({"errors": (0, 100), "few": (200, 300)}, note="few")
        there.now = 250
        self.assertEqual(there.walk("errors", "few"), [(300, "one", "")])

    def test_started_again_between_the_end_of_a_run_and_the_way_back(self):
        there = Pretended({"errors": (0, 100)}, note="errors")
        there.now = 150
        self.assertEqual(there.walk("errors"), [(150, "one", "")])

    def test_started_again_after_a_good_release_it_knows_what_to_go_back_to(self):
        there = Pretended({"good": (0, 100), "errors": (200, 300)}, note="errors")
        there.now = 250
        self.assertEqual(there.walk("good", "errors"), [(300, "good", "")])


class List(unittest.TestCase):
    def test_the_merged_list_can_be_read_and_has_every_release(self):
        names = walker.read_list((ROOT / "k8s" / "list" / "releases.txt").read_text())
        # Where nobody outside has a right, nothing can be taken away meanwhile.
        self.assertEqual(sorted(names), sorted(set(walker.FAILS) - {"blind", "restarted", "interrupted"}))

    def test_what_is_not_a_list_of_known_releases_stops_it(self):
        for text in ("", "# only words\n", "errors\nother\n", "errors\nerrors\n", "one\n", "errors few\n"):
            with self.assertRaises(ValueError, msg=repr(text)):
                walker.read_list(text)


class Sent(unittest.TestCase):
    def test_only_two_settings_are_in_it(self):
        self.assertEqual(walker.patch_for("errors"), [
            {"op": "add", "path": "/spec/template/spec/containers/0/env/0/value", "value": "errors"},
            {"op": "add", "path": "/spec/template/spec/containers/0/env/1/value", "value": "errors"}])
        for name, fails in {"one": "", "good": "", "unasked": "", "blind": "", "restarted": "errors", "interrupted": "errors", "few": "few"}.items():
            self.assertEqual([one["value"] for one in walker.patch_for(name)], [name, fails])

    def test_it_asks_with_the_token_that_is_there_now(self):
        seen = []

        class Cluster(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_PATCH(self):
                body = self.rfile.read(int(self.headers.get("content-length", "0")))
                seen.append((self.command, self.headers["authorization"], self.headers["content-type"], json.loads(body) if body else None))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"answer": true}')

            do_GET = do_PATCH

        server = http.server.HTTPServer(("127.0.0.1", 0), Cluster)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as place:
            account, address = pathlib.Path(place), f"http://127.0.0.1:{server.server_address[1]}/"
            for token in ("first", "second"):
                (account / "token").write_text(token + "\n")
                self.assertEqual(walker.rollout_call("PATCH", walker.patch_for("few"), address, account), {"answer": True})
            walker.rollout_call(address=address, account=account)
        self.assertEqual([(method, token) for method, token, _, _ in seen], [("PATCH", "Bearer first"), ("PATCH", "Bearer second"), ("GET", "Bearer second")])
        self.assertEqual(seen[0][2:], ("application/json-patch+json", walker.patch_for("few")))

    def test_a_front_that_does_not_answer_changes_nothing(self):
        known = {"errors": "started"}
        self.assertEqual(walker.read_marks("http://127.0.0.1:9/marks", known), {"errors": "started"})


if __name__ == "__main__":
    unittest.main()
