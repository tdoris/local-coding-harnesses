#!/usr/bin/env bash
M=~/repos/scratch/local-coding-harnesses/models-clean; T=~/repos/scratch/local-coding-harnesses/cloud/tasks; L=~/repos/scratch/local-coding-harnesses/local-llama
TOMLP="$(cat $L/prompt-tomlA.txt)"; JP="$(cat $T/jpatch/spec.md)"
ENVU=(env -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION)
run() { local label=$1 task=$2; shift 2; local dir=$M/$label/$task; mkdir -p $dir
  [[ $task == jpatch ]] && cp $T/jpatch/test_jpatch.py $dir/
  local prompt; if [[ $task == toml ]]; then prompt="$TOMLP"; else prompt="$JP"; fi
  local t0=$(date +%s)
  ( cd $dir && "${ENVU[@]}" CLAUDE_OLLAMA_NO_UNLOAD=1 timeout 1500 "$@" "$prompt" </dev/null > $M/$label/out-$task.log 2>&1 ); local rc=$?
  local g; if [[ $task == toml ]]; then g=$(python3 $T/tomlq/grade.py $dir --json); else g=$(python3 $T/jpatch/grade.py $dir --json); fi
  echo "### $label $task exit=$rc wall=$(( $(date +%s)-t0 ))s :: $(echo "$g" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["passed"],"/",d["total"],"forbidden:",d.get("forbidden_imports"))')"
}
nohup local-agent serve > /tmp/las-qparity.log 2>&1 & sleep 8
for h in opencode qwen; do
  case $h in opencode) A=(opencode run);; qwen) A=(qwen --approval-mode yolo -p);; esac
  run qwen38-$h toml   local-agent --model qwen3.8 "${A[@]}"
  run qwen38-$h jpatch local-agent --model qwen3.8 "${A[@]}"
done
local-agent stop
echo QWEN-PARITY-DONE
