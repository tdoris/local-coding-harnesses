# Results — pi + qwen3.8 (leak-proof)

### Single-file tier (9 tasks)

| Task | Easy | Hard |
|---|---|---|
| `discover-radeon-igpu` | ✓ 32s | ✓ 54s |
| `llm-cached-tokens` | ✓ 42s | ✓ 45s |
| `llm-load-stall` | ✓ 133s | ✓ 169s |
| `llm-mmap-doublecount` | ✓ 127s | ✓ 161s |
| `llm-projector-offload` | ✓ 30s | ✓ 36s |
| `llm-shift-headroom` | ✓ 235s | ✓ 140s |
| `llm-sse-ping` | ✓ 33s | ✓ 45s |
| `server-mmproj-layers` | ✓ 65s | ✓ 63s |
| `tools-json-braces` | ✓ 26s | ✓ 37s |

**Solved: 9/9 easy, 9/9 hard.**

### Multi-file tier (4 tasks)

| Task | Easy | Hard |
|---|---|---|
| `gemma4-12b-support` | ✓ 122s | ✓ 197s |
| `llama-server-followups` | ✓ 125s | ✓ 367s |
| `ornith9b-parser-renderer` | ✗ 77s (0/2) | ✗ 23s (0/2) |
| `server-native-chat-templates` | ✓ 557s | ✓ 273s |

**Solved: 3/4 easy, 3/4 hard.**
