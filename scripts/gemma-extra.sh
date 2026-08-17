#!/usr/bin/env bash
M=~/repos/scratch/harness-test/models; T=~/repos/scratch/harness-test/cloud/tasks; L=~/repos/scratch/harness-test/local-llama
TOMLP="$(cat $L/prompt-tomlA.txt)"; JP="$(cat $T/jpatch/spec.md)"
ENVU=(env -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION)
run() { local label=$1 task=$2; shift 2; local dir=$M/$label/$task; mkdir -p $dir
  [[ $task == jpatch ]] && cp $T/jpatch/test_jpatch.py $dir/
  local prompt; if [[ $task == toml ]]; then prompt="$TOMLP"; else prompt="$JP"; fi
  local t0=$(date +%s)
  ( cd $dir && "${ENVU[@]}" CLAUDE_OLLAMA_NO_UNLOAD=1 timeout 2400 "$@" "$prompt" </dev/null > $M/$label/out-$task.log 2>&1 ); local rc=$?
  echo "### $label $task exit=$rc wall=$(( $(date +%s)-t0 ))s"
  if [[ $task == toml ]]; then echo "GRADE $label toml: $(python3 $T/tomlq/grade.py $dir --json | cut -c1-160)"; else echo "GRADE $label jpatch: $(python3 $T/jpatch/grade.py $dir --json | cut -c1-160)"; fi
}
nohup local-agent serve > /tmp/local-agent-serve.log 2>&1 & sleep 8
run gemma4-pi-retry jpatch local-agent --model gemma4:26b pi -p
run gemma4-opencode toml   local-agent --model gemma4:26b opencode run
run gemma4-opencode jpatch local-agent --model gemma4:26b opencode run
run qwen38-opencode toml   local-agent --model qwen3.8 opencode run
run qwen38-opencode jpatch local-agent --model qwen3.8 opencode run
local-agent stop
echo GEMMA-EXTRA-DONE
