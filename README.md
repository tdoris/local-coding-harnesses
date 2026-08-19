# Local coding-harness bake-off

Experiments comparing terminal coding agents (pi, OpenCode, Qwen Code, Aider,
Claude Code) and models (qwen3.8, gemma4:26b, gpt-oss:120b) on an RTX 4090 via
Ollama. See the two HTML reports for findings.

## Layout
- `bin/local-agent` — the wrapper: runs a harness against a local Ollama model
  with a tuned private server (context, q8_0 KV cache, pinned sampling). Expects
  to live on `$PATH`; `claude-ollama` is a thin alias for `local-agent claude`.
  Full usage docs: [bin/README.md](bin/README.md).
- `cloud/tasks/` — the objective tasks: `tomlq` and `jpatch` specs, hidden-test
  graders, and oracle-generated case corpora (build_cases / grade / cases).
- `scripts/` — run orchestration (bake-off drivers, per-stage runners) and
  `scripts/validate/` (headless-Chrome game validator over the DevTools protocol).
- `prompts/` — staged Space Invaders prompts.
- `llama/` — llama-server + froggeric fixed Jinja template for qwen3.8
  reasoning-effort control (Ollama's renderer ignores the effort level).
- `<harness>/`, `models*/`, `cloud*/`, `local-llama/` — produced programs and run logs.

Scripts hard-code absolute paths from the original run and are kept as a record,
not a turnkey suite. `local-agent` is the reusable piece.
