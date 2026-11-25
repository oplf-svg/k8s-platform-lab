"""Where an image can stand in a pod, as the cluster describes it."""

import contextlib
import copy
import io
import json
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".github" / "scripts" / "places.py"
sys.path.insert(0, str(SCRIPT.parent))
import places  # noqa: E402

TEXT = {"type": "string"}


def to(name):
    """As Kubernetes writes it: what it points to stands in a list of parts."""
    return {"allOf": [{"$ref": f"#/components/schemas/{name}"}], "default": {}}


def many(of):
    return {"type": "array", "items": of}


# A small pod with everything that the real description has: parts, lists, names with values, and something that holds itself.
POD = {
    places.POD: {"properties": {
        "containers": many(to("Container")), "initContainers": many(to("Container")), "ephemeralContainers": many(to("Container")),
        "volumes": many(to("Volume")), "imagePullSecrets": many(to("Name")), "nodeName": TEXT,
        "nodeSelector": {"type": "object", "additionalProperties": TEXT}}},
    "Container": {"properties": {"image": TEXT, "imagePullPolicy": TEXT, "name": TEXT, "probe": to("Probe")}},
    "Volume": {"properties": {"image": to("Image"), "rbd": to("Disk"), "name": TEXT}},
    "Image": {"properties": {"reference": TEXT, "pullPolicy": TEXT}},
    "Disk": {"properties": {"image": TEXT, "pool": TEXT}},
    "Name": {"properties": {"name": TEXT}},
    "Probe": {"properties": {"path": TEXT, "after": to("Probe")}},
}


class Places(unittest.TestCase):
    def answer(self, schemas):
        said = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"components": {"schemas": schemas}}))), contextlib.redirect_stdout(said):
            return places.main(), said.getvalue()

    def with_one_more(self, where, **more):
        schemas = copy.deepcopy(POD)
        schemas[where]["properties"].update(more)
        return schemas

    def test_every_field_is_found_once(self):
        found = list(places.fields(POD, {"$ref": f"#/components/schemas/{places.POD}"}))
        self.assertEqual(len(found), len(set(found)))
        for path in ("nodeName", "nodeSelector{}", "containers[].image", "containers[].probe.path", "volumes[].image.reference", "volumes[].rbd.pool"):
            self.assertIn(path, found)

    def test_all_is_looked_at(self):
        self.assertEqual(self.answer(POD), (0, "An image can stand in 4 places of a pod, and each is looked at.\n"))

    def test_another_place(self):
        for where, more, path in (
                (places.POD, {"image": TEXT}, "image"),
                (places.POD, {"sidecars": many(to("Container"))}, "sidecars[].image"),
                (places.POD, {"images": {"type": "object", "additionalProperties": TEXT}}, "images{}"),
                (places.POD, {"images": {"type": "object", "additionalProperties": to("Name")}}, "images{}.name"),
                ("Container", {"extraImage": TEXT}, "initContainers[].extraImage"),
                ("Volume", {"artifact": to("Name")}, "volumes[].artifact.name"),
                ("Image", {"mirror": TEXT}, "volumes[].image.mirror"),
                ("Probe", {"oci": to("Name")}, "containers[].probe.oci.name")):
            with self.subTest(path):
                code, said = self.answer(self.with_one_more(where, **more))
                self.assertEqual(code, 1)
                self.assertIn(f"Another place for an image, and nobody looks at it: {path}\n", said)
                self.assertNotIn("each is looked at", said)

    def test_a_place_that_is_gone(self):
        schemas = copy.deepcopy(POD)
        del schemas["Volume"]["properties"]["image"]
        code, said = self.answer(schemas)
        self.assertEqual(code, 1)
        self.assertEqual(said, "A place for an image that this cluster does not have: volumes[].image.reference\n")

    def test_what_is_not_a_description_is_red(self):
        for words in ("", "{", "{}", '{"components": {"schemas": {}}}', json.dumps({"components": {"schemas": {places.POD: {}}}})):
            with self.subTest(words):
                done = subprocess.run([sys.executable, str(SCRIPT)], input=words, capture_output=True, text=True)
                self.assertNotEqual(done.returncode, 0)
                self.assertNotIn("each is looked at", done.stdout)

    def test_it_says_the_same_as_a_program(self):
        done = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps({"components": {"schemas": POD}}), capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertIn("each is looked at", done.stdout)


if __name__ == "__main__":
    unittest.main()
