"""Wrong lists must be noticed. Every test but the first two takes a right pair of lists and spoils it once."""

import copy
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "count"))
import count  # noqa: E402


def lists(total=20, errors=(7, 13), unanswered=(), run="r"):
    clients, front = [], [{"id": "", "path": f"/mark/{run}/start", "status": "204", "upstream": ""}]
    for n in range(1, total + 1):
        status = 500 if n in errors else 202
        event = f"{run}-{n:07d}"
        if n in unanswered:
            clients.append({"id": event, "number": n, "expected": 202, "status": None, "release": "", "pod": ""})
            continue
        clients.append({"id": event, "number": n, "expected": 202, "status": status, "release": "new", "pod": "a"})
        front.append({"id": event, "path": "/hooks/good", "status": str(status), "upstream": str(status), "release": "new", "pod": "a"})
    clients.append({"end": run, "total": total})
    front.append({"id": "", "path": f"/mark/{run}/end", "status": "204", "upstream": ""})
    return clients, front


class Right(unittest.TestCase):
    def test_what_is_right_is_accepted(self):
        result = count.compare(*lists(), "r")
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["seen errors"], 2)
        self.assertEqual(result["seen errors by answer"], {"500": 2})
        self.assertEqual(result["sent"], 20)

    def test_no_answer_is_an_error_that_was_seen(self):
        result = count.compare(*lists(unanswered=(3, 4)), "r")
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["seen errors"], 4)
        self.assertEqual(result["requests"]["only the client knows"], 2)

    def test_other_runs_before_and_after_do_not_matter(self):
        clients, front = lists()
        front = lists(run="before")[1] + front + lists(run="after")[1]
        self.assertEqual(count.compare(clients, front, "r")["problems"], [])

    def test_strangers_are_counted_where_anybody_can_come(self):
        clients, front = lists()
        front.insert(4, {"id": "", "path": "/hooks/good", "status": "401", "upstream": "401"})
        result = count.compare(clients, front, "r", strangers_allowed=True)
        self.assertEqual((result["problems"], result["strangers"]), ([], 1))

    def test_times_shares_and_slow_answers(self):
        clients, front = lists(total=100, errors=())
        for line, there in zip(clients[:100], front[1:101]):
            new = 30 <= line["number"] < 50
            line.update(at=float(line["number"]), seconds=2.0 if new else 0.1, release="new" if new else "old")
            there.update(release=line["release"])
        result = count.compare(clients, front, "r")
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["seconds from first to last answer"], {"new": 19.0, "old": 99.0})
        self.assertEqual(result["slow answers by release"], {"new": 20})
        self.assertEqual(result["answers at the end"], ["old"])
        # 20 of its own and one of the old release, between its first and its last answer.
        self.assertEqual(result["share in the first minute"]["new"], 95.2)


class Wrong(unittest.TestCase):
    def spoil(self, change, *parts):
        clients, front = copy.deepcopy(lists())
        change(clients, front)
        found = count.compare(clients, front, "r")["problems"]
        for part in parts:
            self.assertTrue(any(part in one for one in found), f"{part!r} is not in {found}")

    def test_front_cut_off_at_the_end(self):
        self.spoil(lambda c, f: f.__delitem__(slice(10, None)), "mark for the end", "does not know of it")

    def test_front_cut_off_at_the_start(self):
        self.spoil(lambda c, f: f.__delitem__(slice(0, 5)), "mark for the start", "does not know of it")

    def test_client_list_without_end(self):
        self.spoil(lambda c, f: c.pop(), "no end")

    def test_a_client_line_is_lost(self):
        self.spoil(lambda c, f: c.pop(4), "missing in the list of the clients", "which no client sent")

    def test_a_number_that_was_never_planned(self):
        def more(clients, front):
            clients.insert(20, {**clients[3], "id": "r-0000021", "number": 21})
            front.insert(21, {**front[4], "id": "r-0000021"})
        self.spoil(more, "never planned")

    def test_a_client_line_is_doubled(self):
        self.spoil(lambda c, f: c.insert(0, dict(c[2])), "more than once")

    def test_a_front_line_is_doubled(self):
        self.spoil(lambda c, f: f.insert(2, dict(f[2])), "more than once")

    def test_the_answers_differ(self):
        self.spoil(lambda c, f: f[3].update(status="503"), "the front says 503")

    def test_a_retry_hides_an_error(self):
        self.spoil(lambda c, f: f[3].update(upstream="500, 202"), "repeated")

    def test_somebody_else_sent_something(self):
        self.spoil(lambda c, f: f.insert(3, {"id": "x-0000001", "path": "/hooks/good", "status": "202", "upstream": "202"}), "from somebody else")

    def test_somebody_else_took_an_id_of_this_run(self):
        self.spoil(lambda c, f: f.insert(3, {"id": "r-0000021", "path": "/hooks/good", "status": "202", "upstream": "202"}), "which no client sent")

    def test_a_request_without_an_id(self):
        self.spoil(lambda c, f: f.insert(3, {"id": "", "path": "/hooks/good", "status": "202", "upstream": "202"}), "from somebody else")

    def test_another_run_in_the_middle(self):
        self.spoil(lambda c, f: f.insert(5, {"id": "", "path": "/mark/other/start", "status": "204", "upstream": ""}), "in the middle of this one")

    def test_the_releases_differ(self):
        self.spoil(lambda c, f: f[3].update(release="old"), "another release")

    def test_an_id_that_does_not_fit(self):
        self.spoil(lambda c, f: c[3].update(id="r-9999999"), "does not fit its number")

    def test_nothing_was_sent(self):
        self.spoil(lambda c, f: c.__delitem__(slice(0, 20)), "sent nothing")

    def test_a_line_that_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as place:
            path = pathlib.Path(place) / "list"
            path.write_text('{"id": "a"}\nnot json\n[]\n')
            lines, bad = count.read(path)
        self.assertEqual((len(lines), bad), (1, 2))
        self.assertIn("1 lines cannot be read", count.compare(*lists(), "r", 1)["problems"])


if __name__ == "__main__":
    unittest.main()
