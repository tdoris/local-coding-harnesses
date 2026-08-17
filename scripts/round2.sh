#!/usr/bin/env bash
P=~/repos/scratch/local-coding-harnesses/prompts
/tmp/run-msg.sh claude fix $P/fix-claude.txt
/tmp/run-msg.sh aider fix $P/fix-aider.txt
/tmp/run-msg.sh opencode fix $P/fix-opencode.txt
for t in qwen opencode aider claude; do /tmp/run-msg.sh $t stage4 $P/stage4.txt; done
echo ROUND2-DONE
