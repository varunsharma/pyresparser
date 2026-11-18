# CI test replay

Travis runs the existing complete pytest suite under coverage with the
`ci_replay` plugin. The plugin records test IDs before execution, reorders
unresolved failures and interrupted tests first, and stops at the first
failure. A 45-minute outer deadline bounds the pytest command.

## Test order

1. Previously failing tests and tests in a previously failing collection file.
2. Tests left unfinished by an earlier run.
3. Tests potentially affected by changed files, ordered by prior failure count.
4. Remaining tests, ordered by prior failure count.

There is no verified source-to-test dependency map in this repository. Any
source change or unknown Git ancestry conservatively treats the entire suite as
potentially affected. Replayed tests remain part of the same coverage run and
are not run twice. A previously failing or skipped test stays unresolved until
its call and teardown both pass.

## History and limits

Travis caches `.ci-replay-cache` by repository, branch, PR, Python version,
and test lane, keeping different PRs' failure histories separate. Each entry
holds bounded failed and pending test IDs,
failure counts, and the most recent 12 CI contexts: repository, branch, PR,
commit, run, job, lane, and Python version. It does not store assertion text,
logs, environment dumps, or secrets. Checkpoints are written atomically before
tests run and when failures are observed; an invalid history or checkpoint
write error stops test execution.

The Travis cache is best effort. Eviction, upload failure, concurrent builds,
or runner loss can remove or overwrite history. In particular, failed external
pull request runs may not update the cache. This is not an append-only durable
ledger and cannot guarantee that every earlier failure is available to a later
run. Travis also runs matrix jobs independently; pytest fail-fast stops work in
the current job but does not cancel other jobs in the same build.

Run the focused adapter contracts locally with:

```sh
python -m pytest ci_replay_tests/test_ci_replay.py -q -x
```
