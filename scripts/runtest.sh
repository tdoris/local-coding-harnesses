#!/usr/bin/env bash
# runtest.sh <name> <dir> <cmd...>  — runs cmd in dir, reports time + server-side prompt stats
name=$1; dir=$2; shift 2
LOG=~/.cache/local-agent/server.log
start_lines=$(wc -l < "$LOG")
t0=$(date +%s)
( cd "$dir" && env -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u GEMINI_API_KEY timeout 1500 "$@" </dev/null ) > /tmp/out-$name.log 2>&1
rc=$?
t1=$(date +%s)
echo "### $name: exit=$rc  wall=$((t1-t0))s"
/tmp/stats.sh $start_lines
