#!/usr/bin/env bash
# run-stage.sh <tool> <stage#>  — runs stage prompt in the tool's test dir with session continuation
tool=$1; stage=$2
P=~/repos/scratch/harness-test/prompts/stage$stage.txt
D=~/repos/scratch/harness-test/$tool
msg=$(cat "$P")
case $tool in
  opencode) if [[ $stage == 1 ]]; then set -- local-agent opencode run "$msg"; else set -- local-agent opencode run -c "$msg"; fi ;;
  qwen)     if [[ $stage -le 2 ]]; then set -- local-agent qwen --approval-mode yolo -p "$msg"; else set -- local-agent qwen --approval-mode yolo -c -p "$msg"; fi ;;
  aider)    if [[ $stage == 1 ]]; then set -- local-agent aider --yes-always --no-auto-commits --message "$msg"; else set -- local-agent aider --yes-always --no-auto-commits --restore-chat-history --file invaders.html --message "$msg"; fi ;;
  pi)       if [[ $stage == 1 ]]; then set -- local-agent pi -p "$msg"; else set -- local-agent pi -c -p "$msg"; fi ;;
  claude)   if [[ $stage == 1 ]]; then set -- local-agent claude --dangerously-skip-permissions -p "$msg" --output-format text; else set -- local-agent claude --dangerously-skip-permissions -c -p "$msg" --output-format text; fi ;;
esac
/tmp/runtest.sh "$tool-stage$stage" "$D" "$@"
if [[ -f "$D/invaders.html" ]]; then echo "invaders.html: $(wc -l < "$D/invaders.html") lines, $(wc -c < "$D/invaders.html") bytes"; cp "$D/invaders.html" "$D/invaders.stage$stage.html"; else echo "invaders.html: MISSING"; fi
