#!/usr/bin/env bash
until grep -q LOCAL-COMPARE-DONE /tmp/local-compare.log; do sleep 30; done
M=~/repos/scratch/harness-test/models; T=~/repos/scratch/harness-test/cloud/tasks; L=~/repos/scratch/harness-test/local-llama
TOMLP="$(cat $L/prompt-tomlA.txt)"; JP="$(cat $T/jpatch/spec.md)"
ENVU=(env -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION)
run() { # run <label> <task:toml|jpatch> <cmd...>
  local label=$1 task=$2; shift 2; local dir=$M/$label/$task; mkdir -p $dir
  [[ $task == jpatch ]] && cp $T/jpatch/test_jpatch.py $dir/
  local prompt; if [[ $task == toml ]]; then prompt="$TOMLP"; else prompt="$JP"; fi
  local t0=$(date +%s)
  ( cd $dir && "${ENVU[@]}" CLAUDE_OLLAMA_NO_UNLOAD=1 timeout 2400 "$@" -p "$prompt" </dev/null > $M/$label/out-$task.log 2>&1 ); local rc=$?
  echo "### $label $task exit=$rc wall=$(( $(date +%s)-t0 ))s"
  if [[ $task == toml ]]; then echo "GRADE $label toml: $(python3 $T/tomlq/grade.py $dir --json | cut -c1-160)"; else echo "GRADE $label jpatch: $(python3 $T/jpatch/grade.py $dir --json | cut -c1-160)"; fi
}
mkdir -p $M
# --- Ollama runs (private server on 11435)
nohup local-agent serve > /tmp/local-agent-serve.log 2>&1 & sleep 8
run gemma4-ollama toml   local-agent --model gemma4:26b pi
run gemma4-ollama jpatch local-agent --model gemma4:26b pi
run qwen38-ollama jpatch local-agent --model qwen3.8 pi
local-agent stop; sleep 5
# --- llama-server qwen3.8 with reasoning budget 6000 / low
( cd ~/repos/scratch/harness-test/llama && REASONING_BUDGET=6000 REASONING_EFFORT=low nohup ./run-llama-server.sh > llama-server.log 2>&1 & echo $! > llama-server.pid )
for i in $(seq 1 150); do curl -sf 127.0.0.1:11436/health >/dev/null 2>&1 && break; sleep 2; done
run qwen38-llama-budget6k jpatch env PI_CODING_AGENT_DIR=$L/pi-agent pi --provider llama --model qwen3.8
kill $(cat ~/repos/scratch/harness-test/llama/llama-server.pid) 2>/dev/null
echo MODELS-DONE
