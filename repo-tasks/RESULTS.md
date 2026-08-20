# Results — pi + qwen3.8 (leak-proof)

| Tier | Easy | Hard |
|---|---|---|
| Single-file bug fixes (9) | 9/9 | 9/9 |
| Multi-file bug fixes (4) | 3/4 | 3/4 |
| Feature additions (8) | 4/8 | 4/8 |

## Single-file bug fixes (9)

| Task | Easy | Hard |
|---|---|---|
| `llm-sse-ping` | ✓ 33s | ✓ 45s |
| `llm-projector-offload` | ✓ 30s | ✓ 36s |
| `llm-load-stall` | ✓ 133s | ✓ 169s |
| `llm-cached-tokens` | ✓ 42s | ✓ 45s |
| `llm-mmap-doublecount` | ✓ 127s | ✓ 161s |
| `tools-json-braces` | ✓ 26s | ✓ 37s |
| `llm-shift-headroom` | ✓ 235s | ✓ 140s |
| `server-mmproj-layers` | ✓ 65s | ✓ 63s |
| `discover-radeon-igpu` | ✓ 32s | ✓ 54s |

**9/9 easy, 9/9 hard.**

## Multi-file bug fixes (4)

| Task | Easy | Hard |
|---|---|---|
| `llama-server-followups` | ✓ 125s | ✓ 367s |
| `gemma4-12b-support` | ✓ 122s | ✓ 197s |
| `ornith9b-parser-renderer` | ✗ 0/2 77s | ✗ 0/2 23s |
| `server-native-chat-templates` | ✓ 557s | ✓ 273s |

**3/4 easy, 3/4 hard.**

## Feature additions (8)

| Task | Easy | Hard |
|---|---|---|
| `anthropic-local-image-paths` | ✗ 0/3 331s | ✓ 888s |
| `speculative-draft-length` | ✗ 1/2 2400s **TO** | ✗ 1/2 787s |
| `model-recommendations-endpoint` | ✓ 518s | ✓ 191s |
| `server-show-response-cache` | ✓ 519s | ✓ 289s |
| `startup-model-hydration` | ✗ 2/3 681s | ✓ 923s |
| `plan-aware-model-gating` | ✓ 522s | ✗ 2/5 2400s **TO** |
| `cohere2-moe-mlx` | ✓ 607s | ✗ 3/5 220s |
| `dflash-speculative-decoding` | ✗ 4/8 525s | ✗ 6/8 577s |

**4/8 easy, 4/8 hard.**

## Reading these numbers

**The bug-fix tiers are saturated.** 9/9 and 9/9 on single-file, 3/4 both modes on
multi-file. Real bugs in a 281k-LOC Go repo with no git shortcut — a genuine
capability result for pi + qwen3.8, but it cannot rank harnesses.

**The feature tier discriminates.** 4/8 in both modes, and the partial credit
spreads properly: 0/3, 1/2, 2/3, 2/5, 3/5, 4/8, 6/8 are distinct degrees of
failure, not a flat wall.

**Difficulty does not track size.** The smallest feature task (+200 lines) failed
in easy mode; the second largest (+1442, four new files) solved. What predicts
failure is how *dispersed* the change is across packages, not how big it is.

**Easy vs hard is noise here, not signal.** Both modes score 4/8 — but four of
the eight tasks flip between them, two in each direction. With one sampled run
per cell at temperature 1, that is consistent with sampling variance rather than
a prompt effect. Do not read the per-task easy/hard differences as meaningful
without repeats.

**The dominant failure mode is shipping unverified work.** Across the tier,
failures are incomplete-and-declared-done (touched one package of three, wrote a
file that does not compile) rather than wrong-approach. A `go build ./...` before
finishing would have caught several. That is what `skills/` targets, and this
tier is the first place with headroom to measure whether it helps.
