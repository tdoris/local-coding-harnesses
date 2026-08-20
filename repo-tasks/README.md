# repo-tasks — large-repository coding benchmark

The bake-off's original tasks (`tomlq`, `jpatch`) are single-file, written from
scratch, and both parse structured text. The report says as much: they "say
nothing about UI work, large-codebase navigation." They are also **saturated**
for pi + qwen3.8 (70/70 and 65/67), so they can no longer detect an
improvement.

These tasks fix that: real bugs in a real 281k-LOC Go repository, where the
agent must locate the relevant code among 1251 files before it can fix anything.

## Design

SWE-bench style, with the repository's own test suite as the oracle:

1. Check out a real fix commit — tests are in their post-fix state.
2. Revert **only** the non-test source files to the parent commit.
3. Give the agent the symptom. It must re-implement the fix.
4. Grade by running the package's tests.

No hand-written grader and no oracle implementation: ollama's 296 test files
already encode correct behaviour.

## Why ollama

| Repo | Why not |
|---|---|
| open-webui | zero Python test files — nothing to grade against |
| postgres | full C build per iteration; far too slow for edit→test |
| btop | one test-ish file; no real suite |
| **ollama** | **296 Go test files, 281k LOC, 1251 files, 0.2–10s per package** |

Go's fast compile is what makes the edit→test loop viable at all.

## Usage

```bash
./run.sh <task-id> <harness> [model]      # one task
./run-all.sh <harness> [model]            # all tasks
BENCH_MODE=hard ./run-all.sh pi qwen3.8   # navigation mode
```

`BENCH_MODE`:

- `easy` (default) — descriptive symptom, package named. Tests comprehension
  and editing.
- `hard` — terse issue title only, package **not** named. Tests repo navigation.

The clone lives at `/home/jim/bench-repos/ollama` and each task runs in its own
`git worktree`, so runs are isolated and your own checkout is never touched.
Results land in `runs/<mode>/<model>/<harness>/`.

## Anti-cheat

A model can trivially "pass" by editing the test. Every `*_test.go` in the
package is sha256-pinned at setup and re-verified at grade time; `solved` is
false if any test file is modified or deleted. Control-tested:

| Control | Expected | Result |
|---|---|---|
| Apply the real fix | solved | `solved: true` |
| Append a line to a test | caught | `cheated: true` |
| Delete the test file | caught | `cheated: true`, file named |

## Task validation

Every task is mechanically verified before inclusion: tests must **pass** at the
fix commit and **fail** with the fix reverted. A tenth candidate
(`632ff0079`, "remove duplicate template parsing") was rejected because it is a
pure refactor — reverting it broke nothing, so it cannot discriminate.

## Anti-leak (important)

An earlier version checked out the fix commit as HEAD and reverted the source in
the working tree. That left the answer one `git restore --source=HEAD` away, and
the agent found it — it reported *"Restored llm/llama_server.go from HEAD"* and
finished a 44-line fix in 19s. All results from that version were discarded.

Task directories now contain **no upstream history**: `git archive` the fix
commit's tree, roll back the source files, then `git init` a fresh single-commit
repo. The agent keeps git for diffing its own work; the fix is unreachable.
Verified: 1 commit, no upstream refs, fix commit absent, and
`git restore --source=HEAD` returns the *broken* code.

## Tiers

| File | Tier | Shape |
|---|---|---|
| `tasks.json` | single | one-file bug fixes |
| `tasks-multi.json` | multi | bug fixes spanning up to 5 packages |
| `tasks-feature.json` | feature | **feature additions** requiring new files (1-4) wired into existing registries, 200-1785 added lines, 1-8 packages |

Select a tier with `TASKS_FILE=tasks-feature.json ./run-all.sh pi qwen3.8`.

## Results

See [RESULTS.md](RESULTS.md).

| Tier | Easy | Hard |
|---|---|---|
| Single-file bug fixes (9) | 9/9 | 9/9 |
| Multi-file bug fixes (4) | 3/4 | 3/4 |
| **Feature additions (8)** | **4/8** | **4/8** |

The bug-fix tiers are saturated for pi + qwen3.8. The feature tier is the one
that discriminates, and it is where new tasks should be mined.

## Where difficulty comes from

Confirmed empirically: **bug-fix commits are too tractable for this pairing;
feature additions are not.** Within the feature tier, what predicts failure is
how *dispersed* a change is across packages, not how large it is — the smallest
task (+200 lines, 3 packages) failed while a +1442-line task with four new files
succeeded. Mine for dispersed multi-package features, not for big diffs.

Two caveats worth keeping attached to any number here:

- **One sampled run per cell at temperature 1.** Four of the eight feature tasks
  flip between easy and hard mode, two in each direction, while the aggregate
  stays 4/8. Treat per-task easy/hard differences as noise until repeated.
- **A 2400s timeout is load-bearing.** Two feature runs hit it. Tasks that do not
  converge in 40 minutes are recorded as failures at whatever partial credit they
  reached.
