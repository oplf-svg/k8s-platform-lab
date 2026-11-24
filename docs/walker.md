# What the walker may do, and what it cannot

A release is tried in the cluster without anybody outside having a right in there. A list of releases is merged into this repo,
and a small job in the cluster, [the walker](../k8s/walk/walker.py), walks through it. It waits until a run is marked as begun
at the front, changes two settings of the Rollout, and changes them back when the run is marked as over. So whoever counts from
outside says *when*, the merged list says *what*, and a person only merges.

**It may** read the Rollout `standin`, and set its two settings to a release that is known. That is one right on one object. But
a right to change a Rollout is also the right to change its image or to take the gate away. So
[a policy of Kubernetes itself](../k8s/walk/policy.yaml) looks at each of its changes, and refuses what it cannot look at.

## What it cannot do

[Each of these is tried](../.github/scripts/cannot.sh), as the walker, in every pull request. Each has to be refused, and for the
reason that stands here. The rights of the walker are compared with those of an account that has none: they may differ by one
line.

| Tried | Refused by the |
|---|---|
| another image | policy |
| other words for the program | policy |
| a second container | policy |
| a container before the first | policy |
| a Secret as a file | policy |
| another account for the pods | policy |
| the network of the machine | policy |
| one setting more | policy |
| a setting that reads a Secret | policy |
| the name that the cluster gives | policy |
| a release that is not known | policy |
| a failure that is not known | policy |
| a good release that fails | policy |
| a release without the gate | policy |
| more time to become ready | policy |
| fewer pods | policy |
| another label on the pods | policy |
| a note on the Rollout | policy |
| waving a release through | right |
| deleting the Rollout | right |
| another Rollout | right |
| changing the gate | right |
| changing the program | right |
| changing the list | right |
| reading Secrets | right |
| seeing pods | right |
| going into a pod | right |
| a pod of its own | right |
| a token | right |
| more rights | right |
| the policy that binds it | right |
| another place | right |

## What is left

- **It can try a known release at the wrong moment, and again and again.** The gate is still there, so each bad one shows what a
  bad one shows. The run that counts ends as not right.
- **Anybody can make a mark at the front,** so anybody can let the next release of the list begin early. They cannot choose
  which, and the run that counts ends as not right, because a mark is there twice.
- **Whoever can change the list on `main` can choose the releases.** That is what a merge is for.
