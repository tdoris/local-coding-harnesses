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

## Results

See [RESULTS.md](RESULTS.md). Summary for pi + qwen3.8:

| Tier | Easy | Hard |
|---|---|---|
| Single-file (9) | 9/9 | 9/9 |
| Multi-file (4) | 3/4 | 3/4 |

**Both single-file tiers are saturated.** 18/18 real bugs fixed in a 281k-LOC Go
repo with no git shortcut — a genuine capability result, but useless for ranking
harnesses.

**Hard mode barely matters for single-file tasks** (723s vs 750s total, same
score). ollama's commit subjects leak the package through domain vocabulary
("llama-server" → `llm`, "Radeon iGPU" → `discover`), so removing the explicit
package name changes little. On multi-file tasks it does cost real time
(1.6-2.9x), because with up to 5 packages the localization is no longer implied.

## The one discriminating task

`ornith9b-parser-renderer` is the only task never solved, in either mode. It is a
**feature addition** requiring new files rather than a bug fix, and it fails in
instructive ways:

- easy mode: wrote both new files, but with `newline in string` — Go that does
  not compile. It never built its own output.
- best observed: 1/2 packages, on a longer manual attempt.
- hard mode: twice returned an empty response and wrote nothing at all (pi exits
  0 printing nothing) — a real failure mode of a max-reasoning-effort model on an
  under-specified task.

This is the only task in the suite with headroom to measure whether the
`skills/` hardening (`verify-before-finishing`, `cli-contract`) actually helps:
a single `go build ./...` would have caught the easy-mode failure.

## Where difficulty should come from next

Bug-fix commits are too tractable for this pairing. Feature additions requiring
new files are not. Mine for those, and for commits whose tests are less
localized.
