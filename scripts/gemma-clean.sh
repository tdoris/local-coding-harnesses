#!/usr/bin/env bash
# Round 2 gemma4 driver.
#
# 2026-08-19: two fixes.
#  1. Removed CLAUDE_OLLAMA_CTX=40960. qwen3.8 ran this head-to-head at the
#     wrapper default (81920), so gemma4 was being given half the window against
#     the same 7.5k-16k harness prompts — confounding the model comparison with
#     the prompt-crowding effect the report identifies as decisive. gemma4:26b's
#     native window is 262144 and it loads at 81920 fully on GPU, so 40960 was
#     never a hardware constraint.
#  2. Paths derive from the repo instead of the old ~/repos/scratch location.
# Output goes to models-fair/ so the original models-clean/ results survive
# for comparison.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT_DIR:-$REPO/models-fair}"
T="$REPO/cloud/tasks"; L="$REPO/local-llama"
TOMLP="$(cat "$L/prompt-tomlA.txt")"; JP="$(cat "$T/jpatch/spec.md")"
ENVU=(env -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION)

run() { local label=$1 task=$2; shift 2; local dir=$OUT/$label/$task; mkdir -p "$dir"
  [[ $task == jpatch ]] && cp "$T/jpatch/test_jpatch.py" "$dir/"
  local prompt; if [[ $task == toml ]]; then prompt="$TOMLP"; else prompt="$JP"; fi
  local t0; t0=$(date +%s)
  ( cd "$dir" && "${ENVU[@]}" CLAUDE_OLLAMA_NO_UNLOAD=1 timeout 1500 "$@" "$prompt" </dev/null > "$OUT/$label/out-$task.log" 2>&1 ); local rc=$?
  local g
  if [[ $task == toml ]]; then g=$(python3 "$T/tomlq/grade.py" "$dir" --json); else g=$(python3 "$T/jpatch/grade.py" "$dir" --json); fi
  echo "### $label $task exit=$rc wall=$(( $(date +%s)-t0 ))s :: $(echo "$g" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["passed"],"/",d["total"],"forbidden:",d.get("forbidden_imports"))')"
}

mkdir -p "$OUT"; nohup local-agent --model gemma4:26b serve > /tmp/las-gemma.log 2>&1 & sleep 8
for h in pi opencode qwen; do
  case $h in pi) A=(pi -p);; opencode) A=(opencode run);; qwen) A=(qwen --approval-mode yolo -p);; esac
  run gemma4-$h toml   local-agent --model gemma4:26b "${A[@]}"
  run gemma4-$h jpatch local-agent --model gemma4:26b "${A[@]}"
done
local-agent stop
echo GEMMA-CLEAN-DONE
