#!/usr/bin/env bash
R=~/repos/scratch/harness-test/local-llama; PROMPT="$(cat $R/prompt-tomlA.txt)"; G=~/repos/scratch/harness-test/cloud/tasks/tomlq/grade.py
runpi() { # runpi <label> <dir> <extra env...>
  local label=$1 dir=$2; shift 2; mkdir -p "$dir"; local t0=$(date +%s)
  ( cd "$dir" && env -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION "$@" timeout 2400 pi -p "$PROMPT" </dev/null > "$dir/../out-$label.log" 2>&1 ); local rc=$?
  echo "### $label exit=$rc wall=$(( $(date +%s)-t0 ))s"; echo "GRADE $label: $(python3 $G "$dir" --json | cut -c1-200)"
}
# A) llama-server, budget 6000, low (server already running)
runpi llama-budget6k-run2 $R/budget6k-run2/tomlq PI_CODING_AGENT_DIR=$R/pi-agent
kill $(cat ~/repos/scratch/harness-test/llama/llama-server.pid) 2>/dev/null; sleep 5
# B) Ollama, unlimited thinking (control)
nohup local-agent serve > /tmp/local-agent-serve.log 2>&1 & sleep 8
mkdir -p $R/ollama-unlimited/tomlq; t0=$(date +%s); ( cd $R/ollama-unlimited/tomlq && env -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION CLAUDE_OLLAMA_NO_UNLOAD=1 timeout 2400 local-agent pi -p "$PROMPT" </dev/null > $R/ollama-unlimited/out.log 2>&1 ); rc=$?
echo "### ollama-unlimited exit=$rc wall=$(( $(date +%s)-t0 ))s"; echo "GRADE ollama-unlimited: $(python3 $G $R/ollama-unlimited/tomlq --json | cut -c1-200)"
local-agent stop
echo LOCAL-COMPARE-DONE
