"""Reads the list of the front while it grows, and says in numbers what stands in it. Prometheus reads those.

  tally.py FILE [PORT]

The numbers come from the front and not from the pods: a pod that dies cannot count the answer that it did not give, and a
bad release may count wrongly. Everything follows from the list, so a tally that starts again comes to the same numbers.
"""

import json
import os
import re
import sys
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FEEDS = ("good", "forged")
SLOW_FROM = 1.0
# The name for what the front answered itself, because no pod did.
NOBODY = "front"
MARK = re.compile(r"/mark/([a-z-]{1,20})/(start|end)")


class Tally:
    def __init__(self):
        self.lock = threading.Lock()
        self.answers, self.slow = Counter(), Counter()
        self.lines = self.unreadable = 0
        self.marks = {}
        self.meet(NOBODY)

    def meet(self, release):
        """All numbers of a release are there from its first answer, with 0. So "no wrong answer" is a number, and no number
        means that nothing is measured."""
        for feed in FEEDS:
            for status in ("202", "401", "500", "502", "504"):
                self.answers[release, feed, status] += 0
            self.slow[release, feed] += 0

    def add(self, text):
        with self.lock:
            self.lines += 1
            try:
                line = json.loads(text)
                path, status, release = str(line["path"]), str(int(line["status"])), str(line["release"]) or NOBODY
                seconds = float(line["seconds"])
            except (ValueError, KeyError, TypeError):
                self.unreadable += 1
                return
            if not path.startswith("/hooks/"):
                return self.mark(path)
            # A name that nobody agreed on must not make a new number for ever. The release comes from our own pods.
            feed = path.removeprefix("/hooks/")
            feed = feed if feed in FEEDS else "other"
            if (release, FEEDS[0], "202") not in self.answers:
                self.meet(release)
            self.answers[release, feed, status] += 1
            self.slow[release, feed] += seconds > SLOW_FROM

    def mark(self, path):
        """Which runs have begun and which are over. Anybody can make a mark, so there are not more than a hundred."""
        found = MARK.fullmatch(path)
        if found and (found[1] in self.marks or len(self.marks) < 100):
            if found[2] == "start":
                self.marks.setdefault(found[1], "started")
            elif found[1] in self.marks:
                self.marks[found[1]] = "ended"

    def runs(self):
        with self.lock:
            return json.dumps(self.marks)

    def text(self):
        with self.lock:
            lines = ["# TYPE front_answers_total counter"]
            lines += [f'front_answers_total{{release="{r}",feed="{f}",status="{s}"}} {n}' for (r, f, s), n in sorted(self.answers.items())]
            lines.append("# TYPE front_slow_answers_total counter")
            lines += [f'front_slow_answers_total{{release="{r}",feed="{f}"}} {n}' for (r, f), n in sorted(self.slow.items())]
            lines += ["# TYPE front_lines_total counter", f"front_lines_total {self.lines}"]
            lines += ["# TYPE front_unreadable_lines_total counter", f"front_unreadable_lines_total {self.unreadable}"]
        return "\n".join(lines) + "\n"


def follow(path, tally, more=lambda: True, wait=0.2):
    """Reads whole lines for as long as it is wanted. A list that became shorter is not the list any more."""
    while not os.path.exists(path):
        if not more():
            return
        time.sleep(wait)
    with open(path, "rb") as file:
        rest = b""
        while True:
            # Asked for before the reading, so that the last lines are still read.
            wanted = more()
            part = file.read()
            if part:
                *whole, rest = (rest + part).split(b"\n")
                for line in whole:
                    tally.add(line)
                continue
            if os.fstat(file.fileno()).st_size < file.tell():
                raise RuntimeError("the list became shorter")
            if not wanted:
                return
            time.sleep(wait)


def handler_for(tally, reading):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def log_message(self, *_):
            pass

        def do_GET(self):
            alive, body, kind = reading(), b"", "text/plain"
            if self.path == "/metrics":
                # Prometheus 3 reads nothing from an address that does not say what it gives.
                body, kind = tally.text().encode(), "text/plain; version=0.0.4; charset=utf-8"
            elif self.path == "/marks":
                body, kind = tally.runs().encode(), "application/json"
            elif self.path != "/health/live":
                return self.send_error(404)
            # Old numbers would look like a release that nobody asks, or worse like one that is still well.
            self.send_response(200 if alive else 503)
            self.send_header("content-type", kind)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main(argv):
    tally = Tally()
    reader = threading.Thread(target=follow, args=(argv[0], tally), daemon=True)
    reader.start()
    server = ThreadingHTTPServer(("0.0.0.0", int(argv[1]) if len(argv) > 1 else 9100), handler_for(tally, reader.is_alive))
    print(f"listening on {server.server_address[1]}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
