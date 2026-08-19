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

## Baseline: pi + qwen3.8, easy mode

| Task | Wall | Solved |
|---|---|---|
| `discover-radeon-igpu` | 22s | yes |
| `llm-cached-tokens` | 23s | yes |
| `llm-projector-offload` | 27s | yes |
| `server-mmproj-layers` | 28s | yes |
| `tools-json-braces` | 29s | yes |
| `llm-sse-ping` | 33s | yes |
| `llm-mmap-doublecount` | 85s | yes |
| `llm-shift-headroom` | 103s | yes |
| `llm-load-stall` | 146s | yes |

**9/9 solved**, 22–146s. Every solve was verified by hand: each touched exactly
one source file and none touched a test file. Effort tracks difficulty — the
one-line fixes finished in ~25s, the 44-line `llm-load-stall` fix took 146s.

## Known limitation

Easy mode is **saturated** for this pairing, exactly as `tomlq`/`jpatch` are. A
100% solve rate establishes a floor — pi + qwen3.8 genuinely can locate and fix
real bugs in a 281k-LOC repository — but it cannot discriminate between
harnesses or measure an improvement.

`hard` mode (terse issue title, package not named) exists for that reason and
has not yet been run. If it also saturates, the next lever is multi-file fixes
or tasks whose failing test does not name the symptom.
