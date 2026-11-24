"""The judge must accept what is right and refuse everything else. The runs here are made up, request by request."""

import copy
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
for part in ("standin", "count"):
    sys.path.insert(0, str(ROOT / part))
import count  # noqa: E402
import judge  # noqa: E402
from app import ONE_IN, picked  # noqa: E402

GATE = json.loads((ROOT / "gate.json").read_text())


def said(*phases):
    return {"status": "success", "data": {"resultType": "vector", "result": [{"metric": {"name": "standin", "phase": one}, "value": [0, "1"]} for one in phases]}}


def made(scenario, seconds=160, rate=50, first=20.0, last=45.0):
    """The two lists of a run in which the new release got 1 request of 10 between two moments, and all or none after them."""
    clients, front = [], [{"id": "", "path": f"/mark/{scenario}/start", "status": "204", "upstream": ""}]
    for n in range(1, seconds * rate + 1):
        at, event, feed = (n - 1) / rate, f"{scenario}-{n:07d}", "forged" if n % 10 == 0 else "good"
        expected = 401 if feed == "forged" else 202
        tenth = (n // 10) % 10 == n % 10
        if scenario in ("never-ready", "dies"):
            new = False
        else:
            new = (first <= at < last and tenth) or (scenario == "good" and at >= last)
        status, took = expected, 0.02
        release, pod = ("b2", "n1") if new else ("a1", f"o{n % 9}")
        if new and scenario in ONE_IN and feed == "good" and picked(event, ONE_IN[scenario]):
            status = 500
            if scenario == "drops":
                # Nobody can say whose it was. The front answers 502 itself.
                status, release, pod = 502, "", ""
        if new and scenario == "refuses":
            status = 401
        if new and scenario == "slow":
            took = 3.02
        clients.append({"id": event, "number": n, "feed": feed, "expected": expected, "at": at, "status": status, "release": release, "pod": pod, "seconds": took})
        front.append({"id": event, "path": f"/hooks/{feed}", "status": str(status), "upstream": str(status), "release": release, "pod": pod})
    clients.append({"end": scenario, "total": seconds * rate})
    front.append({"id": "", "path": f"/mark/{scenario}/end", "status": "204", "upstream": ""})
    return clients, front


def verdict(scenario, change=lambda clients, front: None, status=None, gate=GATE, **times):
    clients, front = copy.deepcopy(made(scenario, **times))
    change(clients, front)
    counted = count.compare(clients, front, scenario)
    return judge.judge(scenario, counted, clients, status or said("Completed" if scenario == "good" else "Abort"), gate)


class Right(unittest.TestCase):
    def test_every_release_as_it_has_to_be(self):
        for scenario, times in {"good": {"last": 110.0}, "errors": {}, "few": {"last": 98.0}, "drops": {}, "refuses": {"last": 38.0}, "slow": {}, "never-ready": {}, "dies": {}}.items():
            with self.subTest(scenario):
                self.assertEqual(verdict(scenario, **times), [])

    def test_what_the_controller_says_about_others_does_not_matter(self):
        status = said("Abort")
        status["data"]["result"].append({"metric": {"name": "other", "phase": "Completed"}, "value": [0, "1"]})
        self.assertEqual(verdict("errors", status=status), [])

    def test_there_is_a_run_for_each_release_that_can_fail(self):
        from app import KINDS
        self.assertEqual(set(judge.SCENARIOS) - {"good"}, set(KINDS) - {""})


class Wrong(unittest.TestCase):
    def refused(self, found, part):
        self.assertTrue(any(part in one for one in found), f"{part!r} is not in {found}")

    def test_a_bad_release_that_stays(self):
        def stays(clients, front):
            for line, there in zip(clients, front[1:]):
                if line.get("at", 0) > 150:
                    line.update(release="b2")
                    there.update(release="b2")
        self.refused(verdict("errors", stays), "at the end the answers came from")

    def test_the_controller_says_that_a_bad_release_is_done(self):
        self.refused(verdict("errors", status=said("Completed")), "and not Abort")

    def test_the_controller_calls_it_late_only(self):
        self.refused(verdict("never-ready", status=said("Timeout")), "and not Abort")

    def test_the_controller_says_nothing(self):
        for status in ({"status": "error"}, {"status": "success", "data": {"result": []}}, []):
            with self.subTest(status):
                self.refused(judge.judge("errors", count.compare(*made("errors"), "errors"), made("errors")[0], status, GATE), "nothing")

    def test_the_controller_says_two_things(self):
        self.refused(verdict("errors", status=said("Abort", "Completed")), "and not Abort")

    def test_too_many_errors(self):
        self.refused(verdict("refuses", last=80.0), "are acceptable")

    def test_too_long(self):
        self.refused(verdict("few", seconds=240, last=145.0), "seconds, and 120 are acceptable")

    def test_nothing_reached_the_new_release(self):
        self.refused(verdict("errors", last=21.0), "only 4 requests reached")
        self.refused(verdict("errors", first=500.0, last=501.0), "there are 0 new releases")

    def test_two_new_releases(self):
        def third(clients, front):
            clients[4000].update(release="c3")
            front[4001].update(release="c3")
        self.refused(verdict("errors", third), "there are 2 new releases")

    def test_a_good_release_that_hardly_anybody_tried(self):
        # More than a bad release needs, and fewer than a good one.
        self.refused(verdict("good", seconds=40, first=20.0, last=39.9), "nothing was tried")

    def test_not_one_pod_of_ten(self):
        def more(clients, front):
            for line, there in zip(clients, front[1:]):
                if 20 <= line.get("at", 0) < 45 and line["number"] % 2:
                    line.update(release="b2", status=500 if picked(line["id"], 5) else 202)
                    there.update(release="b2", status=str(line["status"]), upstream=str(line["status"]))
        self.refused(verdict("errors", more), "which is not 1 pod of 10")

    def test_an_error_in_a_good_release(self):
        def one(clients, front):
            clients[3].update(status=502, release="")
            front[4].update(status="502", upstream="502", release="")
        self.refused(verdict("good", one, last=110.0), "clients saw 1 errors")

    def test_a_request_without_an_answer_in_a_good_release(self):
        def one(clients, front):
            clients[3].update(status=None, release="")
            del front[4]
        self.refused(verdict("good", one, last=110.0), "clients saw 1 errors")

    def test_a_release_that_was_not_as_bad_as_planned(self):
        def better(clients, front):
            for line, there in zip(clients, front[1:]):
                if line.get("status") == 500:
                    line.update(status=202)
                    there.update(status="202", upstream="202")
        self.refused(verdict("errors", better), "not as planned")
        self.refused(verdict("refuses", lambda c, f: [(a.update(status=202), b.update(status="202", upstream="202")) for a, b in zip(c, f[1:]) if a.get("release") == "b2" and a["feed"] == "good"], last=38.0), "not refused")
        self.refused(verdict("slow", lambda c, f: [a.update(seconds=0.1) for a in c[:-1:2]]), "were slow")

    def test_a_release_that_did_not_drop_what_was_planned(self):
        def none(clients, front):
            for line, there in zip(clients, front[1:]):
                if line.get("status") == 502:
                    line.update(status=202, release="b2")
                    there.update(status="202", upstream="202", release="b2")

        def others(clients, front):
            for line, there in zip(clients, front[1:]):
                if line.get("release") == "b2" and line["feed"] == "good" and line["number"] % 3 == 0:
                    line.update(status=502, release="")
                    there.update(status="502", upstream="502", release="")
        self.refused(verdict("drops", none), "dropped nothing")
        self.refused(verdict("drops", none), "not as planned")
        self.refused(verdict("drops", others), "others were dropped")

    def test_what_was_never_ready_answered(self):
        def answered(clients, front):
            clients[500].update(release="b2")
            front[501].update(release="b2")
        self.refused(verdict("dies", answered), "should never have been asked")

    def test_numbers_that_cannot_be_believed(self):
        self.refused(verdict("errors", lambda c, f: f.__delitem__(slice(100, None))), "cannot be believed")

    def test_clients_that_could_not_keep_up(self):
        def late(how_many):
            return lambda clients, front: [line.update(late=0.9) for line in clients[:how_many]]
        self.assertEqual(verdict("errors", late(80)), [])
        self.refused(verdict("errors", late(81)), "could not keep up")

    def test_nobody_got_an_answer(self):
        def none(clients, front):
            for line in clients[:-1]:
                line.update(status=None, release="")
            del front[1:-1]
        self.refused(verdict("errors", none), "nobody got an answer")

    def test_the_new_release_was_there_before(self):
        self.refused(verdict("good", first=0.0, last=0.0), "there are 0 new releases")


if __name__ == "__main__":
    unittest.main()
