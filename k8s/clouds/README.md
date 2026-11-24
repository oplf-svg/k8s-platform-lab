# What differs between clusters

`k8s/base` is the same everywhere and names no cloud. Each folder here is one place that it runs on. A new one, for example
Oracle's OKE as `oci`, is a folder and a line in `clouds.json`. The tests go through that list and count to nothing.

| | kind | EKS, AKS, GKE | OKE, later |
|---|---|---|---|
| The way in | a port of the machine, 30080 | the same port, opened in the cloud's own network rules | the same |
| Load balancer | none | none that Kubernetes makes: it would be outside of what our code knows, and it would stay. AKS makes one for its way out, which goes with the cluster | none |
| Disks | none | none, until a database runs inside | none |
| Closed network | its own plug-in | a setting of the cluster, and a test that it is really on | a plug-in of its own |
| Workload's own identity | none | needed only by what talks to the cloud | only in clusters that cost |
| Kind of machine | x86 | x86, like the image | x86. The free machines are Arm, and the image is not |

So the folders are almost empty, and that is what they should be. What a cluster itself is made of, its version, machines
and network, stands with the code that makes it.
