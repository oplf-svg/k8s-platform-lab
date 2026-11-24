# 0001: What a bad release is

24 November 2026. The numbers were proposed by Claude, and the owner of this repo chose to use them. Three were added by Claude
afterwards and are marked: the limit for slow answers, because a rule without it would let a slow release through; the early
look, because without it the 150 errors below could not be kept; and what nobody answered, because a pod that dies would
otherwise not count.

A release is bad when **one** of these is true. Everything is measured at the front, and for the new release alone.

| | Bad when | Why |
|---|---|---|
| Wrong answers | More than 2% of at least 300 requests, after 75 seconds | See the table below |
| Slow answers (added) | More than 2% of the same requests take longer than 1 second | The stand-in answers at once when it is well, so 1 second is far away from good |
| Clearly bad (added) | More than 10% of at least 50 requests are wrong, or slow. Looked at every 5 seconds | What is clearly bad should not be shown to people for 75 seconds |
| Unanswered (added) | In the last 30 seconds more than 1% of all requests, if there were 250, got no answer from any pod | Nobody can say which release it was. In doubt the new one goes back |
| Not ready | After 120 seconds | The default of Argo Rollouts is 600 seconds, and then it only says that it is late |
| Nothing measured | Fewer than 300 requests after 75 seconds, or no answer from Prometheus | No numbers are not good numbers |

And this is acceptable when a release is bad:

| | At most | Why |
|---|---|---|
| Errors that clients saw | 150, at 50 requests a second | See the table below |
| Until it is rolled back | 120 seconds after its first answer | 75 seconds for the long look, and the rest to read, decide and remove the pods |

**Why 75 seconds and not 60.** In 60 seconds the one new pod gets 300 requests on average, so every second time it would be
fewer. In 75 seconds it is 375, and fewer than 300 is four standard deviations away.

## What it catches, and what people see until then

Calculated with 4,000 made-up runs for each line: 1 pod of 10, 50 requests a second, errors that do not depend on each other.

| Errors of the release | Stopped in the first step | Errors seen, usually | In 99 of 100 runs below | Without the early look |
|---|---|---|---|---|
| all | 100% | 90 | 118 | **389** |
| 20% | 100% | 18 | 29 | 78 |
| 7.4% | 100% | 24 | 38 | 29 |
| 5% | 99.8% | 19 | 30 | 19 |
| 2% | 47% | 10 | 16 | 10 |
| 1%, which may be acceptable | 4% | | | |
| 0.5% | 0.1% | | | |

## What one run measured

The run of 24 November 2026, 22:11 UTC, of [pull request 1](https://github.com/oplf-svg/k8s-platform-lab/pull/1), one time each, 50
requests a second. One run shows that it works. It does not show how often. GitHub keeps
[its page](https://github.com/oplf-svg/k8s-platform-lab/actions/runs/45498599872) for 90 days, so until about 22 February 2027. The
numbers stay here.

| Release | Stopped by | Seconds in which it answered | Errors that clients saw | Calculated before |
|---|---|---|---|---|
| refuses every good request | the early look, at 92.9% wrong | 18.8 | 82 | 90, in 99 of 100 below 118 |
| 20% errors | the early look, at 14.1% | 14.0 | 13 | 18, below 29 |
| 7.4% errors | the long look, at 5.8% | 78.5 | 21 | 24, below 38 |
| slow, 3 seconds | the early look, at 100% slow | 19.3 | 0 | |
| ends 20% without an answer | unanswered, at 1.1% of all | 17.6 | 17 | |
| never ready, or ends at once | not ready in 120 seconds | never | 0 | |
| good | nothing, all five looks passed twice | stayed | 0 of 15,000 requests | |

In all eight together, 73,000 requests, both lists agreed in every line, and no request left late.

## What it lets through

- A release with 2% errors passes the first step every second time. The second step looks again, with half of the pods.
- Errors that come only after a while, or only for rare requests, pass.
- A release that leaves fewer than about one in ten of its own requests unanswered is under the 1% of all, and passes that rule.
- The looks trust the front. If it counts wrongly, only the clients can tell, so only the tests.
- The numbers are calculated. Runs are compared with them, and they change here if a run shows something else.
