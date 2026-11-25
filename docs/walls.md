# The two walls

**Images.** Where the label `images=known` is, Kubernetes itself lets a pod start only with images that stand in
[a list](../k8s/walls/images.txt), each with its fingerprint and exactly as it is written there. The list is changed by a merge.
Without the list, or when it cannot be looked at, nothing starts.

**Connections.** Nothing may talk to anything that is [not named](../k8s/walls/network.yaml).

[All of this is tried](../.github/scripts/walls.sh) in every pull request. Each connection is tried first without the wall and has
to be open, because a way that was never open proves nothing when it is closed.

| Tried | Has to be |
|---|---|
| an image from the list | let through |
| an image that is not on the list | refused |
| an image from the list without its fingerprint | refused |
| an image from the list with another fingerprint | refused |
| another image before the first one | refused |
| another image in a pod that runs | refused |
| another image that joins a pod that runs | refused |
| an image from the list, when there is no list | refused |
| an image from the list, when the list is there again | let through |
| the program to Prometheus | closed |
| the program to the numbers of the front | closed |
| the program to the front | closed |
| the program to the internet | closed |
| the front to the internet | closed |
| the walker to the program | closed |
| the walker to Prometheus | closed |
| the walker to the internet | closed |
| the front to the program | open |
| the front to Prometheus | open |
| the walker to the numbers of the front | open |
| the walker to the cluster | open |

## What is left

- **Whoever can take the label off the namespace, or change the list in the cluster, is past the first wall.** Nothing of ours has
  that right.
- **An image on the list can be started with other words.** The list says what runs, and not what it is told to do.
- **An attestation is not looked at here.** The images on the list are public ones, taken as they are and pinned by their
  fingerprint. Nobody checked who made them. What looks at an attestation when a pod starts comes with the first image of our own.
- **The way to the API of the cluster cannot be closed here.** Kubernetes never closes the way from a pod to the machine that it
  runs on, and in this cluster the API runs on that machine. On a cloud it runs elsewhere. That is not tried yet.
- **In this cluster the second wall is kept by a program that comes with kind,** and when it is away or too busy, it lets everything
  through. On a cloud another one keeps it.
- **Prometheus and the controller are not tried from inside,** because there is no program in them that can open a connection.
