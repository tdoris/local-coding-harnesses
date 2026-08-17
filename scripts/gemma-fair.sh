#!/usr/bin/env bash
until grep -q GEMMA-EXTRA-DONE /tmp/gemma-extra.log; do sleep 30; done
M=~/repos/scratch/local-coding-harnesses/models; T=~/repos/scratch/local-coding-harnesses/cloud/tasks; L=~/repos/scratch/local-coding-harnesses/local-llama
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
run gemma4-qwencode toml   local-agent --model gemma4:26b qwen --approval-mode yolo -p
run gemma4-qwencode jpatch local-agent --model gemma4:26b qwen --approval-mode yolo -p
local-agent stop
echo GEMMA-FAIR-DONE
