#!/usr/bin/env bash
# run-msg.sh <tool> <label> <promptfile> — continue the tool's session with a prompt
tool=$1; label=$2; msg=$(cat "$3"); D=~/repos/scratch/harness-test/$tool
case $tool in
  opencode) set -- local-agent opencode run -c "$msg" ;;
  qwen)     set -- local-agent qwen --approval-mode yolo -c -p "$msg" ;;
  aider)    set -- local-agent aider --yes-always --no-auto-commits --restore-chat-history --file invaders.html --message "$msg" ;;
  pi)       set -- local-agent pi -c -p "$msg" ;;
  claude)   set -- local-agent claude --dangerously-skip-permissions -c -p "$msg" --output-format text ;;
esac
/tmp/runtest.sh "$tool-$label" "$D" "$@"
[[ -f "$D/invaders.html" ]] && { echo "invaders.html: $(wc -l < "$D/invaders.html") lines"; cp "$D/invaders.html" "$D/invaders.$label.html"; }
