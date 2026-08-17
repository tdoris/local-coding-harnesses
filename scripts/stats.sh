#!/usr/bin/env bash
# stats.sh <start_line> — summarize server log since line
LOG=~/.cache/local-agent/server.log
tail -n +$(( $1 + 1 )) "$LOG" | grep -E 'new prompt|truncated = 1' | sed -E 's/.*n_ctx_slot = ([0-9]+).*task.n_tokens = ([0-9]+)/\2/; s/.*truncated = 1.*/TRUNC/' | tr '\n' ' ' | sed 's/^/prompt_tokens per request: /'; echo
tail -n +$(( $1 + 1 )) "$LOG" | grep -E ' eval time' | grep -v prompt | sed -E 's|.*/ +([0-9]+) tokens.*|\1|' | awk '{s+=$1} END{print "generated tokens total:", s}'
