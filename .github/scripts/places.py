"""Reads from standard input how the cluster itself describes a pod, and says in which places an image can stand.

A place that is not known here is one that the first wall does not look at. So a new Kubernetes cannot open one without a word."""

import json
import sys

POD = "io.k8s.api.core.v1.PodSpec"
# The policy in k8s/walls/images.yaml looks at these.
LOOKED_AT = {"containers[].image", "initContainers[].image", "ephemeralContainers[].image", "volumes[].image.reference"}
# These speak of images and name none that is started or read: how one is fetched, with which Secret, and a kind of disk that is not
# allowed here.
NOTHING = {"containers[].imagePullPolicy", "initContainers[].imagePullPolicy", "ephemeralContainers[].imagePullPolicy",
           "volumes[].image.pullPolicy", "imagePullSecrets[].name", "volumes[].rbd.image"}
WORDS = ("image", "artifact", "oci")


def fields(schemas, node, path="", above=frozenset()):
    """The way to each field of it that holds no other fields."""
    name = node.get("$ref", "").rpartition("/")[2]
    inside = [(part, path) for part in node.get("allOf", [])]
    inside += [(field, f"{path}.{key}".lstrip(".")) for key, field in node.get("properties", {}).items()]
    if "items" in node:
        inside.append((node["items"], f"{path}[]"))
    if isinstance(node.get("additionalProperties"), dict):
        inside.append((node["additionalProperties"], f"{path}{{}}"))
    # What holds itself is not looked into again.
    if name and name not in above:
        yield from fields(schemas, schemas[name], path, above | {name})
    if not name and not inside:
        yield path
    for part, where in inside:
        yield from fields(schemas, part, where, above)


def main():
    schemas = json.load(sys.stdin)["components"]["schemas"]
    found = {path for path in fields(schemas, {"$ref": f"#/components/schemas/{POD}"}) if any(word in path.lower() for word in WORDS)}
    strange, gone = found - LOOKED_AT - NOTHING, LOOKED_AT - found
    for path in sorted(strange):
        print(f"Another place for an image, and nobody looks at it: {path}")
    for path in sorted(gone):
        print(f"A place for an image that this cluster does not have: {path}")
    if strange or gone:
        return 1
    print(f"An image can stand in {len(LOOKED_AT)} places of a pod, and each is looked at.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
