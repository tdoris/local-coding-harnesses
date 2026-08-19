# pi hardening skills

Skills for [pi](https://github.com/badlogic/pi-mono) that target the failure
modes observed in this repo's bake-off, rather than general-purpose helpers.

| Skill | Failure it targets | Evidence |
|---|---|---|
| `cli-contract` | Ships a valid module with no `__main__`/argv/print — runs, exits 0, emits nothing, scores 0 | `models-fair/gemma4-pi/toml`, `models-fair/gemma4-qwen/jpatch` (369 lines, zero argv hits) |
| `spec-to-tests` | Open-ended spec with no test file → the model plans instead of acting | tomlq scored 0 across most cells; jpatch (visible test file) scored 55–67 across all of them |
| `no-forbidden-deps` | Imports the very library the task said to reimplement | `pi-selfext/bare` 25/70 `forbidden=['tomllib']`; `cloud/qwen` 69/70 by importing `tomllib` |
| `error-path-coverage` | Happy path only; hidden suites are weighted toward malformed input | every surviving jpatch failure is an error path (`add_index_gt_len`, `add_root`, `replace_missing`, …) |
| `verify-before-finishing` | Declares done without running anything | bare 25/70 → +skill 62/70 on gpt-oss:120b |

## Install

Add the **absolute** path to `~/.pi/agent/settings.json`:

```json
{
  "skills": ["/home/you/repos/local-coding-harnesses/skills"],
  "enableSkillCommands": true
}
```

**A `~` in this path silently fails** — pi does not expand it, and skills just
never appear, with no warning. pi's own docs show `"~/.claude/skills"` as an
example, so this is easy to hit. Use `$HOME` expanded, or `--skill <abs-path>`.

Verify discovery (the model must support tools):

```bash
pi --provider ollama --model qwen3-vl:latest -p --no-session \
  "List every skill name available to you, one per line, nothing else."
```

## Caveat on progressive disclosure

Only skill *descriptions* sit in the system prompt; the model must choose to
`read` the full `SKILL.md`. pi's docs note models often don't. For a local
model, prefer `/skill:<name>` interactively, `--skill` plus an explicit
instruction headlessly, or fold the invariants into
`--append-system-prompt` when a check must fire every time.
