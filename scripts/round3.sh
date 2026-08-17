#!/usr/bin/env bash
P=~/repos/scratch/local-coding-harnesses/prompts
/tmp/run-msg.sh opencode fix2 $P/fix-opencode2.txt
for s in 1 2 3; do /tmp/run-stage.sh pi $s; done
/tmp/run-msg.sh pi stage4 $P/stage4.txt
echo ROUND3-DONE
