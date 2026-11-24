# What this has to survive

The claim is: **a bad release rolls itself back, and the errors that users saw are counted.** It counts as proven only when
tests that could have failed did not. This page says what that means, so that the tests, the code and the cluster can each
be checked against the same list.

## Words

- A **release** is one version of the program behind the front. Going from one to the next starts with 1 pod of 10.
- The **clients** know what each request should be answered. A **seen error** is every other answer, and no answer at all.
  A 401 is right for a forged request and wrong for a good one, so the status alone does not decide.
- The **two lists**: what the clients got, and what the front answered. Each request has an id of its own in both.
- The **gate** is the rule that says what a bad release is. The numbers of it stand in
  [the decision](decisions/0001-bad-release.md), which also says whose they are. It reads what the front wrote, never what a
  pod says about itself.

## The stand-in

Until the program of webhook-platform has an image, a stand-in answers in its place. It answers the same addresses in the
same way, and a setting says how it fails.

| Setting `FAIL` | What it does |
|---|---|
| empty | Answers as it should: 202 to a good request, 401 to a forged one |
| `errors` | Answers 500 to one good request in five. Which ones follows from the id, so it can be checked from outside |
| `few` | Answers 500 to one good request in fourteen, so that only a longer look finds it |
| `drops` | Ends the connection of one good request in five without an answer, as if it had died |
| `refuses` | Answers 401 to every request, also to good ones |
| `slow` | Answers as it should, after 3 seconds |
| `never-ready` | Runs, but never says that it is ready |
| `dies` | Ends at once |

## What can happen

| # | What happens | What must be true afterwards |
|---|---|---|
| 1 | A good release | All pods are new. No seen error, and both lists agree |
| 2 | A release with 20% errors | Rolled back without a person, within the agreed time. At most the agreed number of seen errors |
| 3 | Every request | Its id is in both lists with the same answer, or it is named as "only the client knows" or "cut off" and counted |
| 4 | An answer that never came | A seen error, also if the front never knew of the request |
| 5 | A release that answers 401 to good requests | Bad. Looking only at 5xx would miss it |
| 6 | A release that is slow | Bad above the agreed time |
| 7 | A release that is never ready, or ends at once | Rolled back. That is not the default of Argo Rollouts |
| 8 | Nothing is measured, because no request came | Not a success |
| 9 | Prometheus is gone | Not a success. The release stops and is rolled back |
| 10 | The measurement reads old and new pods together | Noticed, because 20% in 1 of 10 pods would look like 2% |
| 11 | Clients keep their connections | Noticed: the share of the new pods is measured, not assumed |
| 12 | The front repeats a failed request | Noticed. It would hide errors from the clients |
| 13 | A list is cut off | Noticed: its first and last entry and every number between must be there |
| 14 | After a rollback | The old version answers alone, the release is marked as degraded, and it stays so when the controller starts again |
| 15 | The controller ends in the middle of a bad release | The rollback is completed after it is back. The errors until then are counted |
| 16 | A pod ends a connection without an answer | The front writes it down, the gate looks at it, and it is a seen error. The pod could not have counted it |
| 17 | The program that counts at the front stops reading | Noticed: it answers 503, so nothing is measured, and that is not a success |
| 18 | The job that changes the releases is taken over | It can try a known release, and nothing else: [what it cannot do](walker.md) |
| 19 | A release goes back for another reason than it should, for example because nothing could be read | Noticed: the judge asks which look stopped it |

## What it does not cover

- **The very first release.** There is nothing to go back to, and Argo Rollouts skips all steps.
- **What gets bad only after everybody has it.**
- **A wrong answer with the right status.** "202" without storing is the claim `once` of webhook-platform.
- **The wish in Git.** After a rollback it still names the bad release. A person has to change it.
- **Who wants to stop a good release.** Anybody can send wrong requests to a good address, and the gate cannot tell them from a
  release that refuses good ones. The release then goes back, which is the safe side, and the requests are counted as
  strangers.
