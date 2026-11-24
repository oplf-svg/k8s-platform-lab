"""Everything together without a cluster: two stand-ins, clients, a front that only pretends to be nginx, the tally, the count
and the judge. What the cluster does is pretended too: the new release gets one request of ten, and then none."""

import contextlib
import http.client
import http.server
import io
import itertools
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
for part in ("standin", "clients", "count", "front"):
    sys.path.insert(0, str(ROOT / part))
import clients  # noqa: E402
import count  # noqa: E402
import judge  # noqa: E402
import tally  # noqa: E402


@contextlib.contextmanager
def stand_in(**settings):
    process = subprocess.Popen([sys.executable, str(ROOT / "standin" / "app.py")], stdout=subprocess.PIPE, text=True,
                               env={**os.environ, "PORT": "0", "HOST": "127.0.0.1", "DRAIN_SECONDS": "0.1", **settings})
    try:
        yield int(re.search(r"(\d+)$", process.stdout.readline().strip()).group(1))
    finally:
        process.kill()
        process.wait()
        process.stdout.close()


class Front(http.server.ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 256

    def __init__(self, path, old, new, until, phase, look):
        self.list, self.old, self.new, self.until, self.phase, self.look = open(path, "a", encoding="utf-8"), old, new, until, phase, look
        self.lock, self.began, self.numbers = threading.Lock(), None, itertools.count()
        super().__init__(("127.0.0.1", 0), Handler)

    def write(self, **line):
        with self.lock:
            self.list.write(json.dumps({"id": "", "upstream": "", "release": "", "pod": "", "seconds": "0.001", "at": f"{time.time():.3f}", **line}) + "\n")
            self.list.flush()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def answer(self, status, body=b"", **headers):
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name.replace("_", "-"), value)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/mark/"):
            self.server.write(path=self.path, status="204")
            if self.path.endswith("/end"):
                # The walker sees the mark and goes back at once, so who asks afterwards hears of something else.
                self.server.phase = "Progressing"
            return self.answer(204)
        rows = [{"name": "standin", "phase": self.server.phase}]
        if self.path == "/status/gate":
            rows = [{"name": "standin-b2-2-1", "metric": look, "phase": "Failed" if look == self.server.look else "Successful"} for look in judge.LOOKS]
        self.answer(200, json.dumps({"status": "success", "data": {"result": [{"metric": row, "value": [0, "1"]} for row in rows]}}).encode())

    def do_POST(self):
        front, began = self.server, time.monotonic()
        with front.lock:
            front.began = front.began or began
            number = next(front.numbers)
        new = number % 10 == 7 and began - front.began < front.until
        body, status, release, pod = self.rfile.read(int(self.headers["content-length"])), 502, "", ""
        back = http.client.HTTPConnection("127.0.0.1", front.new if new else front.old, timeout=5)
        try:
            back.request("POST", self.path, body, {name: self.headers[name] for name in ("webhook-id", "webhook-timestamp", "webhook-signature")})
            got = back.getresponse()
            got.read()
            status, release, pod = got.status, got.getheader("x-release"), got.getheader("x-pod")
        except (OSError, http.client.HTTPException):
            pass
        finally:
            back.close()
        front.write(id=self.headers["webhook-id"], path=self.path, status=str(status), upstream=str(status), release=release, pod=pod, seconds=f"{time.monotonic() - began:.3f}")
        self.answer(status, **({"x_release": release, "x_pod": pod} if release else {}))


class Chain(unittest.TestCase):
    def tried(self, scenario, phase, until=3.5, seconds=9, rate=200):
        """Returns what was counted, what the judge says, and the numbers that Prometheus would read."""
        with tempfile.TemporaryDirectory() as folder, stand_in(RELEASE="a1") as old, stand_in(RELEASE="b2", FAIL=scenario) as new:
            place = pathlib.Path(folder)
            front = Front(place / "answers.jsonl", old, new, until, phase, {"errors": "clearly-wrong", "drops": "unanswered"}[scenario])
            threading.Thread(target=front.serve_forever, daemon=True).start()
            try:
                sent = clients.main(["--front", f"127.0.0.1:{front.server_address[1]}", "--run", scenario, "--seconds", str(seconds),
                                     "--rate", str(rate), "--out", str(place / "clients.jsonl"), "--status", str(place / "status.json")])
            finally:
                front.shutdown()
                front.server_close()
                front.list.close()
            self.assertEqual(sent, 0)
            numbers = tally.Tally()
            tally.follow(str(place / "answers.jsonl"), numbers, lambda: False)
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                counted = count.main(["--clients", str(place / "clients.jsonl"), "--front", str(place / "answers.jsonl"), "--run", scenario])
            self.assertEqual(counted, 0, printed.getvalue())
            (place / "counted.json").write_text(printed.getvalue())
            with contextlib.redirect_stdout(io.StringIO()) as said:
                verdict = judge.main(["--scenario", scenario, "--counted", str(place / "counted.json"), "--clients", str(place / "clients.jsonl"), "--status", str(place / "status.json")])
            return json.loads(printed.getvalue()), (verdict, said.getvalue()), numbers

    def test_a_release_with_errors_that_is_rolled_back(self):
        counted, (verdict, said), numbers = self.tried("errors", "Abort")
        self.assertEqual(verdict, 0, said)
        self.assertEqual((counted["sent"], counted["problems"], sorted(counted["answers by release"])), (1800, [], ["a1", "b2"]))
        # What the gate would read is what the clients saw.
        self.assertEqual(numbers.answers["b2", "good", "500"], counted["seen errors"])
        self.assertGreater(counted["seen errors"], 0)
        self.assertEqual(numbers.answers["front", "good", "502"], 0)
        self.assertEqual(json.loads(numbers.runs()), {"errors": "ended"})

    def test_a_release_that_drops_requests(self):
        counted, (verdict, said), numbers = self.tried("drops", "Abort")
        self.assertEqual(verdict, 0, said)
        # Only the front knows of them, because the release had no answer.
        self.assertEqual(numbers.answers["front", "good", "502"], counted["seen errors"])
        self.assertGreater(counted["seen errors"], 0)
        self.assertEqual(numbers.answers["b2", "good", "500"], 0)

    def test_a_controller_that_calls_a_bad_release_good(self):
        _, (verdict, said), _ = self.tried("errors", "Completed", until=2.0, seconds=8)
        self.assertEqual(verdict, 1)
        self.assertIn("and not Abort", said)


if __name__ == "__main__":
    unittest.main()
