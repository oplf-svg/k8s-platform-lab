"""Reads from standard input how the cluster itself describes a pod, and compares it with k8s/walls/pod.txt, field by field.

A field that does not stand there is one that nobody has looked at, whatever it is called. So a new Kubernetes cannot bring another
place for an image without a word. What hides in the value of a field is not seen."""

import json
import pathlib
import sys

POD = "io.k8s.api.core.v1.PodSpec"
KNOWN = pathlib.Path(__file__).resolve().parent.parent.parent / "k8s" / "walls" / "pod.txt"
# The fields that name an image, and every way to them. The policy in k8s/walls/images.yaml looks at all of these ways.
IMAGES = {"Container.image", "EphemeralContainer.image", "ImageVolumeSource.reference"}
LOOKED_AT = {"containers[].image", "initContainers[].image", "ephemeralContainers[].image", "volumes[].image.reference"}


def short(name):
    return name.rpartition(".")[2]


def pointed_to(node):
    """The kinds that it names, wherever they stand in it."""
    if isinstance(node, dict):
        if isinstance(node.get("$ref"), str):
            yield node["$ref"].rpartition("/")[2]
        for value in node.values():
            yield from pointed_to(value)
    elif isinstance(node, list):
        for value in node:
            yield from pointed_to(value)


def described(schemas):
    """Every field of every kind of thing that a pod can hold."""
    found, kinds, todo = set(), {}, [POD]
    while todo:
        name = todo.pop()
        if kinds.get(short(name)) == name:
            continue
        if short(name) in kinds:
            raise ValueError(f"two kinds are called {short(name)}")
        kinds[short(name)] = name
        found |= {f"{short(name)}.{field}" for field in schemas[name].get("properties", {})}
        todo += pointed_to(schemas[name])
    return found


def ways(schemas, name=POD, way="", above=frozenset()):
    """The ways from a pod to a field that names an image."""
    for field, node in schemas[name].get("properties", {"": schemas[name]}).items():
        here = f"{way}.{field}".strip(".") + ("[]" if node.get("type") == "array" else "")
        if f"{short(name)}.{field}" in IMAGES:
            yield here
        # What holds itself is not looked into again.
        for other in set(pointed_to(node)) - above - {name}:
            yield from ways(schemas, other, here, above | {name})


def known():
    lines = [line.partition(": ") for line in KNOWN.read_text().splitlines() if line and not line.startswith("#")]
    return {f"{kind}.{field}" for kind, _, fields in lines for field in fields.split()}


def main():
    schemas = json.load(sys.stdin)["components"]["schemas"]
    has, knows, leads = described(schemas), known(), set(ways(schemas))
    wrong = [f"A field that nobody has looked at: {field}" for field in sorted(has - knows)]
    wrong += [f"A field that this cluster does not have: {field}" for field in sorted(knows - has)]
    wrong += [f"A place for an image that nobody looks at: {way}" for way in sorted(leads - LOOKED_AT)]
    wrong += [f"A place for an image that is not there: {way}" for way in sorted(LOOKED_AT - leads)]
    if wrong:
        print("\n".join(wrong))
        return 1
    print(f"A pod has {len(has)} fields, and all of them are known. An image can stand in {len(leads)} places of a pod, and each is looked at.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
