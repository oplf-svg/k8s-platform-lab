"""Many small clients. Each request is sent once, on a connection of its own, and what came back is written down.

  clients.py --front HOST:PORT --run NAME --seconds 60 --rate 50 --out FILE --status FILE

Nothing is sent again: a retry would hide an error that a user saw.
"""

import argparse
import http.client
import json
import pathlib
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "standin"))
from app import signature  # noqa: E402

EXPECTED = {"good": 202, "forged": 401}
# One in ten is forged, so that 401 is sometimes the right answer.
FORGED_EVERY = 10
PATIENCE = 8.0


def name(run, number):
    return f"{run}-{number:07d}"


def feed_of(number):
    return "forged" if number % FORGED_EVERY == 0 else "good"


def send(front, run, number, planned=None, connect=http.client.HTTPConnection):
    event, feed = name(run, number), feed_of(number)
    body = json.dumps({"order": number}).encode()
    moment = str(int(time.time()))
    given = signature(event, moment, body if feed == "good" else body + b"x")
    began = time.monotonic()
    line = {"id": event, "number": number, "feed": feed, "expected": EXPECTED[feed], "at": time.time(),
            "late": round(began - planned, 3) if planned is not None else 0.0}
    connection = connect(*front, timeout=PATIENCE)
    try:
        connection.request("POST", f"/hooks/{feed}", body, {
            "webhook-id": event, "webhook-timestamp": moment, "webhook-signature": given,
            "content-type": "application/json", "connection": "close"})
        answer = connection.getresponse()
        answer.read()
        line.update(status=answer.status, release=answer.getheader("x-release", ""), pod=answer.getheader("x-pod", ""))
    except (OSError, http.client.HTTPException, socket.timeout) as problem:
        line.update(status=None, why=type(problem).__name__, release="", pod="")
    finally:
        connection.close()
    line["seconds"] = round(time.monotonic() - began, 3)
    return line


def mark(front, run, which):
    connection = http.client.HTTPConnection(*front, timeout=PATIENCE)
    try:
        connection.request("GET", f"/mark/{run}/{which}", headers={"connection": "close"})
        if connection.getresponse().status != 204:
            raise RuntimeError(f"the front did not take the mark {which}")
    finally:
        connection.close()


def asked(front, path):
    connection = http.client.HTTPConnection(*front, timeout=PATIENCE)
    try:
        connection.request("GET", path, headers={"connection": "close"})
        answer = connection.getresponse()
        text = answer.read()
        return json.loads(text) if answer.status == 200 else {"status": f"the front answered {answer.status}"}
    except (OSError, ValueError, http.client.HTTPException) as problem:
        return {"status": f"no answer: {type(problem).__name__}"}
    finally:
        connection.close()


def controller(front):
    """What the controller says, read just before the run is marked as over: the mark lets the next thing begin."""
    return json.dumps({"release": asked(front, "/status/release"), "gate": asked(front, "/status/gate")})


def run_all(front, run, total, rate, write, sender=send, workers=200):
    """Sends at fixed moments, whatever the answers do, as users do. Whatever could not be sent in time says so."""
    lock = threading.Lock()
    began = time.monotonic()

    def one(number):
        planned = began + (number - 1) / rate
        line = sender(front, run, number, planned)
        with lock:
            write(line)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        waiting = []
        for number in range(1, total + 1):
            time.sleep(max(0.0, began + (number - 1) / rate - time.monotonic()))
            waiting.append(pool.submit(one, number))
        for each in waiting:
            each.result()  # A client that breaks must break the run.


def main(argv=None):
    ask = argparse.ArgumentParser()
    ask.add_argument("--front", required=True)
    ask.add_argument("--run", required=True)
    ask.add_argument("--seconds", type=int, required=True)
    ask.add_argument("--rate", type=int, default=50)
    ask.add_argument("--out", required=True)
    ask.add_argument("--status", required=True)
    given = ask.parse_args(argv)
    host, port = given.front.rsplit(":", 1)
    front, total = (host, int(port)), given.seconds * given.rate
    with open(given.out, "w", encoding="utf-8") as out:
        mark(front, given.run, "start")

        def write(line):
            out.write(json.dumps(line) + "\n")
            out.flush()

        run_all(front, given.run, total, given.rate, write)
        pathlib.Path(given.status).write_text(controller(front))
        mark(front, given.run, "end")
        out.write(json.dumps({"end": given.run, "total": total}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
