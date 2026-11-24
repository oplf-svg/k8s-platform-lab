"""The stand-in itself: as a program that is started, asked and ended."""

import http.client
import os
import pathlib
import re
import subprocess
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "standin"))
sys.path.insert(0, str(ROOT / "clients"))
import app  # noqa: E402
import clients  # noqa: E402


class Running:
    def __init__(self, **settings):
        self.process = subprocess.Popen([sys.executable, str(ROOT / "standin" / "app.py")], stdout=subprocess.PIPE, text=True,
                                        env={**os.environ, "PORT": "0", "HOST": "127.0.0.1", "DRAIN_SECONDS": "0.2", **settings})
        self.port = int(re.search(r"(\d+)$", self.process.stdout.readline().strip()).group(1))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.process.kill()
        self.process.wait()
        self.process.stdout.close()

    def get(self, path):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request("GET", path)
        answer = connection.getresponse()
        text = answer.read().decode()
        connection.close()
        return answer.status, text

    def send(self, number, run="t"):
        return clients.send(("127.0.0.1", self.port), run, number)


class StandIn(unittest.TestCase):
    def test_good_and_forged(self):
        with Running() as one:
            self.assertEqual([one.send(n)["status"] for n in (1, 2, 10, 20)], [202, 202, 401, 401])
            self.assertEqual(one.get("/health/ready")[0], 200)
            # It counts nothing. The front does.
            self.assertEqual(one.get("/metrics")[0], 404)

    def test_errors_follow_from_the_id(self):
        with Running(FAIL="errors", RELEASE="bad") as one:
            lines = [one.send(n) for n in range(1, 200)]
        good = [line for line in lines if line["feed"] == "good"]
        failed = {line["id"] for line in good if line["status"] == 500}
        self.assertEqual(failed, {line["id"] for line in good if app.picked(line["id"], 5)})
        self.assertTrue(0.1 < len(failed) / len(good) < 0.3, len(failed))
        self.assertEqual({line["release"] for line in lines}, {"bad"})

    def test_few_errors_follow_from_the_id_too(self):
        with Running(FAIL="few") as one:
            good = [line for line in (one.send(n) for n in range(1, 400)) if line["feed"] == "good"]
        failed = {line["id"] for line in good if line["status"] == 500}
        self.assertEqual(failed, {line["id"] for line in good if app.picked(line["id"], 14)})
        self.assertTrue(0.03 < len(failed) / len(good) < 0.13, len(failed))

    def test_drops(self):
        with Running(FAIL="drops") as one:
            good = [line for line in (one.send(n) for n in range(1, 200)) if line["feed"] == "good"]
            self.assertEqual({line["id"] for line in good if line["status"] is None}, {line["id"] for line in good if app.picked(line["id"], 5)})
            self.assertEqual({line["status"] for line in good}, {202, None})
            # It is still there, so it was not the whole program that ended.
            self.assertEqual(one.get("/health/ready")[0], 200)

    def test_every_answer_says_which_release_and_which_pod(self):
        with Running(RELEASE="abc", HOSTNAME="pod-1") as one:
            for number in (1, 10):
                self.assertEqual((one.send(number)["release"], one.send(number)["pod"]), ("abc", "pod-1"))

    def test_refuses(self):
        with Running(FAIL="refuses") as one:
            self.assertEqual(one.send(1)["status"], 401)

    def test_slow(self):
        with Running(FAIL="slow") as one:
            line = one.send(1)
            self.assertEqual(line["status"], 202)
            self.assertGreater(line["seconds"], 2.9)

    def test_never_ready(self):
        with Running(FAIL="never-ready") as one:
            self.assertEqual((one.get("/health/live")[0], one.get("/health/ready")[0]), (200, 503))

    def test_dies(self):
        done = subprocess.run([sys.executable, str(ROOT / "standin" / "app.py")], env={**os.environ, "FAIL": "dies"}, capture_output=True, timeout=20)
        self.assertEqual(done.returncode, 1)

    def test_a_typo_does_not_make_a_good_release(self):
        done = subprocess.run([sys.executable, str(ROOT / "standin" / "app.py")], env={**os.environ, "FAIL": "error"}, capture_output=True, timeout=20)
        self.assertNotEqual(done.returncode, 0)

    def test_ends_when_it_is_told_to(self):
        with Running() as one:
            one.process.terminate()
            self.assertEqual(one.process.wait(timeout=10), 0)

    def test_is_not_ready_while_it_ends(self):
        with Running(DRAIN_SECONDS="2") as one:
            one.process.terminate()
            time.sleep(0.5)
            self.assertEqual(one.get("/health/ready")[0], 503)
            self.assertEqual(one.send(1)["status"], 202)

    def asked(self, event="a", moment="1000", given=None, length=0, body=b"", kind="", **instead):
        one = app.StandIn(kind, clock=lambda: 1000)
        headers = {"webhook-id": [event], "webhook-timestamp": [moment], "webhook-signature": [app.signature(event, moment, body) if given is None else given]}
        headers.update({name.replace("_", "-"): value for name, value in instead.items()})
        return one.decide(headers, length, lambda: body)

    def test_the_same_answers_as_the_real_program(self):
        self.assertEqual(self.asked(), 202)
        for name in app.HEADERS:
            for value in ([], ["a", "a"]):
                self.assertEqual(self.asked(**{name.replace("-", "_"): value}), 400, (name, value))
        for event, answer in (("a" * 100, 202), ("a" * 101, 400), ("", 400), ("a.b", 400), ("a b", 400), ("\u00e4", 400), ("a\n", 400), ("A_b:c-9", 202)):
            self.assertEqual(self.asked(event=event), answer, event)
        for moment, answer in (("700", 202), ("699", 401), ("1300", 202), ("1301", 401), ("x", 400), ("", 400), ("-1000", 400), ("+1000", 400),
                               ("1000.0", 400), ("1" * 12, 401), ("1" * 13, 400), ("\u0661\u0660\u0660\u0660", 400), ("1000\n", 400)):
            self.assertEqual(self.asked(moment=moment), answer, moment)
        for given, answer in (("", 400), ("v1,wrong", 401), ("v1,\u00e4", 401), ("v1,wrong " + app.signature("a", "1000", b""), 202), (app.signature("a", "1000", b"x"), 401)):
            self.assertEqual(self.asked(given=given), answer, given)

    def test_the_order_is_the_same_too(self):
        self.assertEqual(self.asked(length=app.LARGEST), 202)
        self.assertEqual(self.asked(length=app.LARGEST + 1), 413)
        self.assertEqual(self.asked(length=app.LARGEST + 1, moment="1"), 413)
        self.assertEqual(self.asked(length=app.LARGEST + 1, moment="x"), 400)
        for kind in ("errors", "refuses", "drops"):
            self.assertEqual((self.asked(moment="x", kind=kind), self.asked(moment="1", kind=kind)), (400, 401))

    def test_what_is_too_large_is_refused_by_the_program_too(self):
        with Running() as one:
            connection = http.client.HTTPConnection("127.0.0.1", one.port, timeout=10)
            connection.putrequest("POST", "/hooks/good")
            for name, value in (("webhook-id", "a"), ("webhook-timestamp", str(int(time.time()))), ("webhook-signature", "v1,x"), ("content-length", str(app.LARGEST + 1))):
                connection.putheader(name, value)
            connection.endheaders()
            self.assertEqual(connection.getresponse().status, 413)
            connection.close()

    def test_no_answer_is_written_down(self):
        with Running() as one:
            port = one.port
        line = clients.send(("127.0.0.1", port), "t", 1)
        self.assertIsNone(line["status"])
        self.assertIn("Refused", line["why"])


if __name__ == "__main__":
    unittest.main()
