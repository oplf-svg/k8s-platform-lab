"""What a pod can hold, as the cluster describes it, and where an image can stand in it."""

import contextlib
import copy
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".github" / "scripts" / "places.py"
sys.path.insert(0, str(SCRIPT.parent))
import places  # noqa: E402

TEXT = {"type": "string"}


def to(name):
    """As Kubernetes writes it: what it points to stands in a list of parts."""
    return {"allOf": [{"$ref": f"#/components/schemas/a.{name}"}], "default": {}, "description": "Not a $ref."}


def many(of):
    return {"type": "array", "items": of}


# A small pod with everything that the real description has: parts, lists, names with values, a kind without fields, and one that
# holds itself.
POD = {
    places.POD: {"properties": {
        "containers": many(to("Container")), "initContainers": many(to("Container")), "ephemeralContainers": many(to("EphemeralContainer")),
        "volumes": many(to("Volume")), "nodeName": TEXT, "limits": {"type": "object", "additionalProperties": to("Quantity")}}},
    "a.Container": {"properties": {"image": TEXT, "name": TEXT, "probe": to("Probe")}},
    "a.EphemeralContainer": {"properties": {"image": TEXT, "name": TEXT}},
    "a.Volume": {"properties": {"image": to("ImageVolumeSource"), "name": TEXT}},
    "a.ImageVolumeSource": {"properties": {"reference": TEXT}},
    "a.Probe": {"properties": {"path": TEXT, "after": to("Probe")}},
    "a.Quantity": {"type": "string"},
    "a.NotReached": {"properties": {"image": TEXT}},
}
KNOWN = """\
# A note.
Container: image name probe
EphemeralContainer: image name
ImageVolumeSource: reference
PodSpec: containers ephemeralContainers initContainers limits nodeName volumes
Probe: after path
Volume: image name
"""


class Places(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.file = pathlib.Path(folder.name) / "pod.txt"
        self.file.write_text(KNOWN)
        patch = mock.patch.object(places, "KNOWN", self.file)
        patch.start()
        self.addCleanup(patch.stop)

    def answer(self, schemas):
        said = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"components": {"schemas": schemas}}))), contextlib.redirect_stdout(said):
            return places.main(), said.getvalue()

    def with_one_more(self, where, **more):
        schemas = copy.deepcopy(POD)
        schemas[where]["properties"].update(more)
        return schemas

    def test_all_is_known(self):
        self.assertEqual(self.answer(POD), (0, "A pod has 16 fields, and all of them are known. An image can stand in 4 places of a pod, and each is looked at.\n"))

    def test_another_field_whatever_it_is_called(self):
        for name in ("image2", "artifact", "bundle", "model", "package", "source", "registryReference", "x"):
            for where, kind in ((places.POD, "PodSpec"), ("a.Volume", "Volume"), ("a.Probe", "Probe"), ("a.ImageVolumeSource", "ImageVolumeSource")):
                with self.subTest(name=name, where=where):
                    code, said = self.answer(self.with_one_more(where, **{name: TEXT}))
                    self.assertEqual((code, said), (1, f"A field that nobody has looked at: {kind}.{name}\n"))

    def test_another_kind_behind_another_field(self):
        for node in (to("New"), many(to("New")), {"type": "object", "additionalProperties": to("New")}):
            schemas = self.with_one_more("a.Volume", bundle=node)
            schemas["a.New"] = {"properties": {"reference": TEXT}}
            self.assertEqual(self.answer(schemas), (1, "A field that nobody has looked at: New.reference\nA field that nobody has looked at: Volume.bundle\n"))

    def test_another_way_to_an_image_that_somebody_wrote_down(self):
        # The field stands in the list, and nobody changed the policy.
        self.file.write_text(KNOWN.replace("nodeName volumes", "nodeName sidecars volumes"))
        code, said = self.answer(self.with_one_more(places.POD, sidecars=many(to("Container"))))
        self.assertEqual((code, said), (1, "A place for an image that nobody looks at: sidecars[].image\n"))

    def test_a_way_over_a_kind_without_fields(self):
        self.file.write_text(KNOWN.replace("nodeName volumes", "nodeName more volumes"))
        schemas = self.with_one_more(places.POD, more=to("List"))
        schemas["a.List"] = many(to("Container"))
        self.assertEqual(self.answer(schemas), (1, "A place for an image that nobody looks at: more[].image\n"))

    def test_a_field_that_is_gone(self):
        schemas = copy.deepcopy(POD)
        del schemas["a.Volume"]["properties"]["image"]
        code, said = self.answer(schemas)
        self.assertEqual((code, said), (1, "A field that this cluster does not have: ImageVolumeSource.reference\nA field that this cluster does not have: Volume.image\n"
                                           "A place for an image that is not there: volumes[].image.reference\n"))

    def test_two_kinds_with_one_name(self):
        schemas = self.with_one_more("a.Volume", more={"$ref": "#/components/schemas/b.Container"})
        schemas["b.Container"] = {"properties": {"image": TEXT, "name": TEXT, "probe": TEXT}}
        with self.assertRaisesRegex(ValueError, "two kinds are called Container"):
            self.answer(schemas)

    def test_what_is_not_a_description_is_red(self):
        for words in ("", "{", "{}", '{"components": {"schemas": {}}}', json.dumps({"components": {"schemas": {places.POD: {}}}}),
                      json.dumps({"components": {"schemas": POD}})):
            with self.subTest(words[:60]):
                done = subprocess.run([sys.executable, str(SCRIPT)], input=words, capture_output=True, text=True)
                self.assertNotEqual(done.returncode, 0)
                self.assertNotIn("each is looked at", done.stdout)


class List(unittest.TestCase):
    lines = [line for line in places.KNOWN.read_text().splitlines() if not line.startswith("#")]

    def test_it_is_in_order_and_holds_nothing_twice(self):
        self.assertEqual(self.lines, sorted(set(self.lines)))
        for line in self.lines:
            kind, _, fields = line.partition(": ")
            self.assertRegex(kind, r"^[A-Z][A-Za-z0-9]+$")
            self.assertEqual(fields.split(" "), sorted(set(fields.split(" "))), kind)
        self.assertEqual(len(places.known()), 516)

    def test_the_places_for_an_image_stand_in_it(self):
        self.assertLess(places.IMAGES | {"Volume.image", "PodSpec.containers", "PodSpec.initContainers", "PodSpec.ephemeralContainers", "PodSpec.volumes"}, places.known())


if __name__ == "__main__":
    unittest.main()
