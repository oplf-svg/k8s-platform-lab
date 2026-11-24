"""A stand-in for the program of webhook-platform. It answers like it and fails on purpose, see docs/contract.md.

It needs nothing but Python. FAIL says how it fails, RELEASE is the name that it answers with, PORT may be 0.
It counts nothing. A bad release could count wrongly, and a pod that dies cannot count at all, so the front does it.
"""

import base64
import hashlib
import hmac
import os
import re
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = b"not-a-secret-only-for-tests"
KINDS = ("", "errors", "few", "drops", "refuses", "slow", "never-ready", "dies")
# How many good requests fail: one in five, or one in fourteen.
ONE_IN = {"errors": 5, "few": 14, "drops": 5}
HEADERS = ("webhook-id", "webhook-timestamp", "webhook-signature")
# The form that the real program asks for, in the same order: malformed, too large, wrong time, wrong signature.
EVENT = re.compile(r"[A-Za-z0-9_:-]{1,100}")
MOMENT = re.compile(r"[0-9]{1,12}")
LARGEST = 256 * 1024
SLOW_FOR = 3.0
CLOCK = 300
NO_ANSWER = None


def signature(event, moment, body):
    text = f"{event}.{moment}.".encode() + body
    return "v1," + base64.b64encode(hmac.new(SECRET, text, hashlib.sha256).digest()).decode()


def picked(event, one_in):
    """Whether this one fails. Who knows the id can say so beforehand, so the counting can check it."""
    return hashlib.sha256(event.encode()).digest()[0] % one_in == 0


class StandIn:
    def __init__(self, kind="", release="stable", pod="local", clock=time.time):
        if kind not in KINDS:
            # A typo must not turn a bad release into a good one.
            raise ValueError(f"FAIL={kind!r} is not one of {KINDS}")
        self.kind, self.release, self.pod, self.clock = kind, release, pod, clock
        self.closing = False

    def ready(self):
        return self.kind != "never-ready" and not self.closing

    def decide(self, headers, length, read):
        """The answer to one request. Each header is a list, because one that is there twice is malformed."""
        if any(len(headers[name]) != 1 for name in HEADERS):
            return 400
        event, moment, given = (headers[name][0] for name in HEADERS)
        if not EVENT.fullmatch(event) or not MOMENT.fullmatch(moment) or not given:
            return 400
        if length > LARGEST:
            return 413
        if abs(self.clock() - int(moment)) > CLOCK:
            return 401
        body = read()
        if self.kind == "refuses":
            return 401
        # Bytes, because compare_digest refuses text that is not ASCII.
        right = signature(event, moment, body).encode()
        if not any(hmac.compare_digest(right, one.encode("latin-1", "replace")) for one in given.split(" ")):
            return 401
        if self.kind in ONE_IN and picked(event, ONE_IN[self.kind]):
            return NO_ANSWER if self.kind == "drops" else 500
        return 202


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        # HTTP/1.0, so every answer ends its connection.
        timeout = 10

        def log_message(self, *_):
            pass

        def answer(self, status):
            self.send_response(status)
            self.send_header("x-release", app.release)
            self.send_header("x-pod", app.pod)
            self.send_header("content-length", "0")
            self.end_headers()

        def do_GET(self):
            if self.path == "/health/live":
                self.answer(200)
            elif self.path == "/health/ready":
                self.answer(200 if app.ready() else 503)
            else:
                self.answer(404)

        def do_POST(self):
            parts = self.path.split("/")
            if len(parts) != 3 or parts[1] != "hooks" or not parts[2]:
                return self.answer(404)
            given = self.headers.get("content-length", "0")
            if not MOMENT.fullmatch(given):
                return self.answer(400)
            length = int(given)
            status = app.decide({name: self.headers.get_all(name) or [] for name in HEADERS}, length, lambda: self.rfile.read(length))
            if app.kind == "slow":
                time.sleep(SLOW_FOR)
            # Without an answer the connection just ends, as if the pod had died.
            return None if status is NO_ANSWER else self.answer(status)

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = 128


def main(env=os.environ):
    app = StandIn(env.get("FAIL", ""), env.get("RELEASE", "stable"), env.get("HOSTNAME", "local"))
    if app.kind == "dies":
        print("ends at once, on purpose", flush=True)
        return 1
    server = Server((env.get("HOST", "0.0.0.0"), int(env.get("PORT", "8080"))), handler_for(app))

    # A process with number 1 in a container ignores the signal to end, unless it says what to do.
    def stop(*_):
        app.closing = True
        threading.Timer(float(env.get("DRAIN_SECONDS", "5")), server.shutdown).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f"listening on {server.server_address[1]}", flush=True)
    server.serve_forever(poll_interval=0.1)
    server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
