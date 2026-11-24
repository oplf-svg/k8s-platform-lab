"""The numbers of the front: they are what the gate decides by."""

import http.client
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "front"))
import tally  # noqa: E402


def line(release="r1", feed="good", status="202", seconds="0.004", **more):
    return json.dumps({"id": "x", "path": f"/hooks/{feed}", "status": status, "upstream": status, "release": release, "pod": "p",
                       "seconds": seconds, "at": "1.0", **more})


class Numbers(unittest.TestCase):
    def of(self, *lines):
        one = tally.Tally()
        for each in lines:
            one.add(each)
        return one.text()

    def test_each_answer_once(self):
        text = self.of(line(), line(), line(status="500"), line(feed="forged", status="401"), line(release="r2"))
        for part in ('{release="r1",feed="good",status="202"} 2', '{release="r1",feed="good",status="500"} 1',
                     '{release="r1",feed="forged",status="401"} 1', '{release="r2",feed="good",status="202"} 1'):
            self.assertIn(f"front_answers_total{part}", text)
        self.assertIn("front_lines_total 5", text)

    def test_no_error_is_a_number_from_the_first_answer(self):
        text = self.of(line())
        for part in ('answers_total{release="r1",feed="good",status="500"} 0', 'answers_total{release="r1",feed="forged",status="202"} 0',
                     'slow_answers_total{release="r1",feed="good"} 0', 'slow_answers_total{release="r1",feed="forged"} 0', 'answers_total{release="front",feed="good",status="502"} 0'):
            self.assertIn(f"front_{part}", text)

    def test_what_no_pod_answered_belongs_to_the_front(self):
        self.assertIn('front_answers_total{release="front",feed="good",status="502"} 1', self.of(line(release="", status="502")))

    def test_slow(self):
        text = self.of(line(seconds="1.001"), line(seconds="1.000"), line(seconds="0.2"))
        self.assertIn('front_slow_answers_total{release="r1",feed="good"} 1', text)

    def test_marks_and_other_paths_are_not_answers(self):
        before = self.of()
        after = self.of(line(path="/mark/r/start"), line(path="/elsewhere"))
        self.assertEqual(before.replace("front_lines_total 0", "front_lines_total 2"), after)

    def test_marks_say_which_runs_have_begun_and_are_over(self):
        one = tally.Tally()

        def after(*paths):
            for path in paths:
                one.add(line(path=path))
            return json.loads(one.runs())
        self.assertEqual(after(), {})
        self.assertEqual(after("/mark/errors/end"), {})
        self.assertEqual(after("/mark/errors/start"), {"errors": "started"})
        self.assertEqual(after("/mark/never-ready/start", "/mark/errors/end"), {"errors": "ended", "never-ready": "started"})
        # What is over does not begin again.
        self.assertEqual(after("/mark/errors/start")["errors"], "ended")
        for path in ("/mark/errors/other", "/mark/a/b/start", "/mark//start", "/mark/UPPER/start", "/mark/" + "a" * 21 + "/start", "/mark/x/start/"):
            self.assertEqual(len(after(path)), 2, path)
        many = [chr(97 + n // 26) + chr(97 + n % 26) for n in range(300)]
        self.assertEqual(len(after(*(f"/mark/{name}/start" for name in many))), 100)

    def test_a_feed_that_nobody_agreed_on_makes_one_number_only(self):
        text = self.of(*(line(feed=f"feed-{n}", status="401") for n in range(200)))
        self.assertEqual(text.count('feed="other"'), 2)
        self.assertIn('front_answers_total{release="r1",feed="other",status="401"} 200', text)

    def test_a_line_that_cannot_be_read_is_counted(self):
        text = self.of("not json", "[]", "{}", line(status=None), b"\xff\xfe", line(seconds="soon"), line())
        self.assertIn("front_unreadable_lines_total 6", text)
        self.assertIn('front_answers_total{release="r1",feed="good",status="202"} 1', text)


class Following(unittest.TestCase):
    def setUp(self):
        place = tempfile.TemporaryDirectory()
        self.addCleanup(place.cleanup)
        self.path = pathlib.Path(place.name) / "answers.jsonl"
        self.tally, self.wanted = tally.Tally(), True

    def start(self):
        self.failed = None

        def read():
            try:
                tally.follow(str(self.path), self.tally, lambda: self.wanted, wait=0.01)
            except RuntimeError as problem:
                self.failed = problem
        self.thread = threading.Thread(target=read, daemon=True)
        self.thread.start()

    def until(self, lines):
        for _ in range(500):
            if self.tally.lines >= lines:
                return
            time.sleep(0.01)
        self.fail(f"{self.tally.lines} lines were read, and not {lines}")

    def stop(self):
        self.wanted = False
        self.thread.join(5)
        self.assertFalse(self.thread.is_alive())

    def test_a_list_that_is_not_there_yet_and_then_grows_in_pieces(self):
        self.start()
        time.sleep(0.05)
        text = "".join(line(release=f"r{n % 3}") + "\n" for n in range(300))
        with open(self.path, "w") as file:
            for n in range(0, len(text), 977):  # Nearly every piece ends in the middle of a line, and is read as it is.
                file.write(text[n:n + 977])
                file.flush()
                self.until(text[:n + 977].count("\n"))
        self.until(300)
        self.stop()
        self.assertEqual((self.tally.lines, self.tally.unreadable), (300, 0))

    def test_half_a_line_waits(self):
        self.start()
        self.path.write_text(line() + "\n" + line()[:20])
        self.until(1)
        time.sleep(0.1)
        self.assertEqual(self.tally.lines, 1)
        self.stop()

    def test_a_list_that_became_shorter_ends_it(self):
        self.path.write_text((line() + "\n") * 50)
        self.start()
        self.until(50)
        with open(self.path, "r+") as file:
            file.truncate(10)
        self.thread.join(5)
        self.assertIn("shorter", str(self.failed))

    def test_starting_again_comes_to_the_same_numbers(self):
        self.path.write_text("".join(line(status=str(200 + n % 3)) + "\n" for n in range(90)))
        self.start()
        self.until(90)
        self.stop()
        first, self.tally, self.wanted = self.tally.text(), tally.Tally(), True
        self.start()
        self.until(90)
        self.stop()
        self.assertEqual(first, self.tally.text())


class Program(unittest.TestCase):
    def test_it_says_so_when_it_no_longer_reads(self):
        with tempfile.TemporaryDirectory() as place:
            path = pathlib.Path(place) / "answers.jsonl"
            path.write_text((line() + "\n") * 5)
            process = subprocess.Popen([sys.executable, str(ROOT / "front" / "tally.py"), str(path), "0"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            try:
                port, kinds = int(process.stdout.readline().rsplit(" ", 1)[1]), {}

                def ask(where):
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                    connection.request("GET", where)
                    answer = connection.getresponse()
                    text = answer.read().decode()
                    connection.close()
                    kinds[where] = answer.getheader("content-type")
                    return answer.status, text

                def until(status):
                    for _ in range(500):
                        if ask("/metrics")[0] == status:
                            return
                        time.sleep(0.01)
                    self.fail(f"it never answered {status}")

                until(200)
                for _ in range(500):
                    if "front_lines_total 5" in ask("/metrics")[1]:
                        break
                    time.sleep(0.01)
                self.assertIn('front_answers_total{release="r1",feed="good",status="202"} 5', ask("/metrics")[1])
                self.assertEqual(json.loads(ask("/marks")[1]), {})
                # Without it Prometheus 3 reads nothing, and then every release is rolled back, also a good one.
                self.assertEqual(kinds, {"/metrics": "text/plain; version=0.0.4; charset=utf-8", "/marks": "application/json"})
                path.write_text("")
                until(503)
                self.assertEqual(ask("/health/live")[0], 503)
            finally:
                process.kill()
                process.wait()
                process.stdout.close()


if __name__ == "__main__":
    unittest.main()
