# local-agent

Run a coding-agent harness (Claude Code, OpenCode, Qwen Code, Aider, pi, Codex)
against a **local Ollama model**, with the Ollama side tuned so that:

1. the harness's system prompt + a real task actually fit in the context window,
2. the model stays **100% on the GPU** (no silent CPU offload → 20× slowdown), and
3. sampling is pinned to the model's own recommended values (Ollama's
   OpenAI-compatible endpoint would otherwise let clients fill in `top_p=1`,
   or aider would send `temperature=0` — greedy-decoding a thinking model).

It does this by standing up a **private `ollama serve`** (default
`127.0.0.1:11435`) tuned per-model, then injecting the correct base URL,
context window, output limit, and sampling into each harness's config.
Your system Ollama on `:11434` is left alone except that its resident
models are unloaded first to free VRAM.

This is the reusable piece from the [bake-off](../local-coding-harnesses-report.html);
the scripts in `../scripts/` are run-specific, but `local-agent` is meant to
be used standalone.

## Requirements

- `ollama` on `PATH`, with a model in `ollama list` (defaults assume `qwen3.8`)
- `python3` (config generation), `curl`, `awk`
- ~24 GB VRAM GPU for the default config (qwen3.8 @ 81920 ctx). For less,
  lower `--ctx` (e.g. 32768) so the KV cache fits.

## Setup

Put `bin/` on your `PATH` (the script is expected to be found as `local-agent`):

```sh
export PATH="$PWD/bin:$PATH"
```

No other installation. State (server log, per-harness config dirs) goes to
`$XDG_CACHE_HOME/local-agent/` (default `~/.cache/local-agent/`).

## Usage

```
local-agent [opts] <tool> [tool args...]

Tools:
  claude    Claude Code   (via `ollama launch claude`)
  opencode  OpenCode      (config injected via OPENCODE_CONFIG_CONTENT)
  qwen      Qwen Code     (own QWEN_HOME w/ trimmed settings; add --approval-mode yolo for -p)
  aider     Aider         (ollama_chat/<model>, generated model settings)
  pi        pi (pi.dev)   (own PI_CODING_AGENT_DIR w/ models.json)
  codex     Codex CLI     (via `ollama launch codex`; untested)
  serve     just run the tuned server in the foreground (Ctrl-C stops it)
  ps        show models loaded on the private server
  stop      stop the private server(s)

Options (before the tool name):
  --model NAME       Ollama model (default: qwen3.8, or $CLAUDE_OLLAMA_MODEL)
  --ctx TOKENS       context window (default: 81920)
  --kv TYPE          KV cache type (default: q8_0)
  --port N           private server port (default: 11435)
  --max-output N     max output tokens (default: 32000)

Env (same meaning as the flags):
  CLAUDE_OLLAMA_MODEL / _CTX / _KV / _PORT / _MAX_OUTPUT
  CLAUDE_OLLAMA_NO_UNLOAD=1   don't unload models from the system Ollama
  CLAUDE_OLLAMA_SYSTEM_HOST   system Ollama to unload from (default 127.0.0.1:11434)
  CLAUDE_OLLAMA_SYSTEM_PORT   port for cloud models (default 11434)
```

`local-agent -h` (or with no tool) prints the built-in help.

### Examples

```sh
# qwen3.8 through pi (the bake-off's recommended combo), one-shot
local-agent pi -p "Summarize this codebase"

# qwen3.8 through pi, interactive, in a repo
cd myproj && local-agent pi

# Claude Code against qwen3.8
local-agent claude

# gemma4 with a smaller context (e.g. 16 GB card)
local-agent --model gemma4:26b --ctx 32768 opencode

# Cloud-hosted model via signed-in system Ollama (name must end in -cloud/:cloud,
# e.g. gpt-oss:120b-cloud) — no local GPU work, context auto-detected
local-agent --model gpt-oss:120b-cloud pi -p "..."

# Just a tuned OpenAI/Anthropic-compatible endpoint
local-agent serve
#   OpenAI:    http://127.0.0.1:11435/v1
#   Anthropic: http://127.0.0.1:11435
#   native:    http://127.0.0.1:11435
```

`claude-ollama` (same directory) is a thin alias: `claude-ollama ...` ≡
`local-agent claude ...`.

## What happens on each run

1. **Free the GPU** — models resident in the *system* Ollama (`:11434`) are
   unloaded (`keep_alive: 0`). Skipped for cloud models or with
   `CLAUDE_OLLAMA_NO_UNLOAD=1`.
2. **Private server** — starts `ollama serve` on `:11435` with
   `OLLAMA_CONTEXT_LENGTH=$ctx`, `OLLAMA_KV_CACHE_TYPE=q8_0`,
   `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KEEP_ALIVE=2h` (log:
   `~/.cache/local-agent/server.log`). If a server is already up on that
   port it's reused and *not* killed on exit. A server the script started
   itself is stopped on exit.
3. **Load the model** — preloaded with a 2h keep-alive; the GPU split is
   reported and a warning printed if it isn't `100% GPU` (lower `--ctx`).
   For cloud models it verifies the system Ollama is signed in instead, and
   auto-detects the model's real context window (unless `--ctx` was given).
4. **Sampling** — reads the model's Modelfile `PARAMETER`s (via
   `ollama show --parameters`) and pushes `temperature` / `top_p` /
   `presence_penalty` into every harness explicitly. Models with no
   Modelfile params (e.g. gpt-oss) fall back to OpenAI's guidance
   (`temperature=1.0, top_p=1.0`).
5. **Launch the harness** with per-tool config (below). Thinking is left ON.

## Per-harness details

| Harness | How it's wired up |
|---------|-------------------|
| **claude** | `ollama launch claude --model M -- <args>`, plus `CLAUDE_CODE_AUTO_COMPACT_WINDOW=$ctx` (compact before Ollama's window overflows), `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, `API_TIMEOUT_MS=1800000` (long thinking turns), and `MAX_THINKING_TOKENS` unset. |
| **opencode** | `OPENCODE_CONFIG_CONTENT` generated inline: `ollama/<model>` via the OpenAI-compatible endpoint with `limit.context`/`limit.output`, `reasoning`+`tool_call` enabled, and the model's temperature/top_p set on every agent (build, plan, general, explore, title, summary, compaction). |
| **qwen** | Self-contained `QWEN_HOME` (`~/.cache/local-agent/qwen-home`) with a trimmed `settings.json`: the provider entry carries the real context window (Qwen Code otherwise assumes 200k and never compacts in time), and the token-wasting machinery is disabled — workflows, cron, artifacts, LLM tool-use summaries, auto-memory, follow-up suggestions, computer-use. Runs `qwen --model M --auth-type openai`. |
| **aider** | Talks to Ollama's native `/api/chat` via litellm. Generates a model-metadata JSON (real max input/output tokens) and a model-settings YAML (`num_ctx`, `max_tokens`, `top_p`, `presence_penalty`, `edit_format: diff`, repo map on). |
| **pi** | Private `PI_CODING_AGENT_DIR` (`~/.cache/local-agent/pi-agent`) with a generated `models.json` (ollama provider, `openai-completions` API, real contextWindow/maxTokens, model's sampling params, `supportsDeveloperRole`/`supportsReasoningEffort` off) and `settings.json` defaulting to it. `~/.pi/agent/models.json` is never touched. |
| **codex** | `ollama launch codex --model M -- <args>` (untested). |

## Sizing the context window

The defaults (qwen3.8, 81920 ctx, q8_0 KV, 32000 max output) are the
largest config that stays 100% on a 24 GB RTX 4090. The rule of thumb:

- KV cache ≈ `2 · layers · heads · head_dim · ctx · kv_bytes` — it grows
  **linearly with `--ctx`**, so that's the knob to turn.
- The harness needs its system prompt + working context to fit; pi uses the
  least (~1.5k tokens), Claude Code the most (~25k) — see the bake-off report.
- A model partly on CPU runs ~20× slower and looks "broken"; the script
  warns when this happens. Drop `--ctx` until you see `100% GPU`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `WARNING: model partly on CPU` | Lower `--ctx` (or `--kv q4_0`) and retry. |
| `failed to load <model>` | Check `ollama list`; model name includes tag (e.g. `gemma4:26b`). |
| `cannot reach <model>` on cloud model | System Ollama isn't signed in — run `ollama signin`. |
| `server failed to start` | See `~/.cache/local-agent/server.log`; port conflict? use `--port`. |
| Slow first response | Model still loading — check `local-agent ps`. |
| Leftover server after a crash | `local-agent stop` (kills user-owned `ollama serve` processes). |

## Caveats

- `stop` kills **all** user-owned `ollama serve` processes, including the
  system one if you run it as a plain process — use with care.
- `--kv q8_0` halves KV cache memory vs `q8_8`/`f16` at a small accuracy
  cost; the defaults are tuned for GPU residency first.
- A server already listening on the target port is reused **as-is** — if it
  was started with different flags, `--port` to a fresh port.
- Codex support is untested; Claude Code's 30-min `API_TIMEOUT_MS` was chosen
  for slow local thinking turns.
