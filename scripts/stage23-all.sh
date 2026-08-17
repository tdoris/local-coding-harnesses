#!/usr/bin/env bash
for t in opencode aider qwen claude; do /tmp/run-stage.sh $t 2; done
for t in opencode aider qwen claude; do /tmp/run-stage.sh $t 3; done
echo ALL-DONE
