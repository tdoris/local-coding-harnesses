#!/usr/bin/env bash
export CLOUD_ROOT=~/repos/scratch/local-coding-harnesses/cloud-seq XDG_CACHE_HOME=/tmp/cloudseq-cache
mkdir -p $CLOUD_ROOT $XDG_CACHE_HOME
for t in pi opencode aider qwen claude; do /tmp/cloud-run2.sh $t; done
echo CLOUD-SEQ-DONE
