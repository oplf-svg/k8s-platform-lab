# k8s-platform-lab

Part of the public portfolio of Luis Orozco.
[The other parts](https://github.com/oplf-svg).

Rolls a bad release back by itself, and counts the errors that users saw until then. The company behind it is made up: no
shop, customer or order in here is real.

**Not proven yet.** So far it runs in a cluster inside of the CI machine, with a stand-in for the real program. What each
run counted is on its page under [Actions](../../actions/workflows/ci.yml) for 90 days, and [what one run measured](docs/decisions/0001-bad-release.md)
stands beside what was calculated before it.

## The claim

> A bad release rolls itself back, and the errors that users saw are counted.

| | |
|---|---|
| [What it has to survive](docs/contract.md) | 19 things that can happen, what must be true afterwards, and what is not covered |
| [What a bad release is](docs/decisions/0001-bad-release.md) | The numbers, why they are these, and what they let through |
| [The stand-in](standin/app.py) | Answers like the program of webhook-platform and fails on purpose, until that program has an image |
| [The clients](clients/clients.py) | Send each request once, whatever the answers do, and write down what came back |
| [The front](front/nginx.conf) | Writes one line for each answer. It repeats nothing and hides nothing. [Beside it](front/tally.py) the lines become numbers |
| [Counted from outside](count/count.py) | Compares both lists, request by request. Anything that is not explained ends the run |
| [The judge](count/judge.py) | Says whether the run was what the contract asks for. What the controller says about itself is only one part |
| [Many runs](count/many.py) | One run shows that it works and not how often. [A workflow](.github/workflows/often.yml) that is started by hand tries every release twenty times on main. Then all of them are judged again from their lists: the same files, each at the first try |
| [The walker](docs/walker.md) | Walks through the merged list of releases inside of the cluster. What it cannot do is tried, as the walker, in every pull request |
| [The two walls](docs/walls.md) | Only images from a list, and only connections that are named. What they have to refuse is tried in every pull request |
| [Tests that can fail](tests/wrong.py) | More than 100 mistakes that are easy to make, one at a time. The tests have to notice each of them |

## How it works

```mermaid
flowchart LR
  clients[Clients] -- each request once --> front[Front]
  front -- 9 of 10 --> old[Old release]
  front -- 1 of 10 --> new[New release]
  front -- numbers of the new release --> gate{Gate}
  gate -- bad, or nothing measured --> back[Rolled back]
  gate -- good --> more[More pods]
  clients -. list .-> count[Compared request by request]
  front -. list .-> count
```

- **The gate reads only the new release.** 20% errors in 1 of 10 pods would look like 2% otherwise.
- **It reads the front, not the pods.** A pod that dies cannot count the answer that it did not give, and a bad release may
  count wrongly. So nothing in the cluster needs a right for it either.
- **No numbers are not good numbers.** A release that nobody asked, or that cannot be measured, is rolled back.
- **What decides is checked from outside.** The gate trusts the front. The clients, who are outside, have a list of their own, and
  every line of both has to agree.
- **Nobody outside has a right in the cluster.** A list of releases is merged, and the walker tries them. Its only right is to
  change two settings of one object.
- **The same on every cluster.** [One folder](k8s/clouds) for each place, and nearly nothing in it.
- **No load balancer that Kubernetes makes, and no disk,** because a cloud would make them outside of what the code knows, and
  they would stay.

## Who made this

Directed and approved by Luis Orozco. Code, tests and texts are written by Claude, an AI agent that proposes its changes under an identity of its own.

The numbers of the gate were proposed by Claude, and Luis Orozco decided to use them. To reach Luis Orozco:
[GitHub](https://github.com/oplf-svg), [LinkedIn](https://www.linkedin.com/in/lforozcop/). Licence: [Apache 2.0](LICENSE), see
[NOTICE](NOTICE).
