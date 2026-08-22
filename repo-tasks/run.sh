#!/usr/bin/env bash
# run.sh <task-id> <harness> [model]   env: BENCH_MODE=easy|hard  TASKS_FILE=...
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASKS="${TASKS_FILE:-$HERE/tasks.json}"
id="$1"; harness="${2:-pi}"; model="${3:-qwen3.8}"
tier=$(python3 -c "
import json
print([x for x in json.load(open('$TASKS'))['tasks'] if x['id']=='$id'][0].get('tier','single'))")
W="/home/jim/bench-repos/wd-$id-$harness"
OUT="$HERE/runs${BENCH_SUFFIX:-}/${BENCH_MODE:-easy}/$tier/$model/$harness${BENCH_TAG:+/$BENCH_TAG}"; mkdir -p "$OUT"

pkglist=$(python3 -c "
import json
t=[x for x in json.load(open('$TASKS'))['tasks'] if x['id']=='$id'][0]
print(', '.join(t.get('pkgs') or [t['pkg']]))")
symptom=$(python3 -c "
import json
print([x for x in json.load(open('$TASKS'))['tasks'] if x['id']=='$id'][0]['symptom'])")
title=$(python3 -c "
import json
print([x for x in json.load(open('$TASKS'))['tasks'] if x['id']=='$id'][0].get('title',''))")

TASKS_FILE="$TASKS" "$HERE/setup.sh" "$id" "$W" >/dev/null

if [ "${BENCH_MODE:-easy}" = hard ]; then
PROMPT="This is the ollama Go repository (Go, ~280k LOC).

ISSUE
$title

YOUR TASK
Locate every affected package yourself, find the cause, and fix it in the source.
The change may span several files and several packages.
Verify by running the affected packages' tests, e.g. 'go test ./<pkg>/...'.

Rules:
- Do NOT modify, delete, or add any *_test.go file. The tests define correct behaviour.
- Change only non-test source files.
- You are done when the affected packages' tests pass."
else
PROMPT="This is the ollama Go repository. Something is missing or broken across these package(s): $pkglist

REPORT
$symptom

YOUR TASK
Find the cause and fix it in the source. The change may span several files and
several packages. Verify with:

    go test ./<pkg>/...   (for each of: $pkglist)

Rules:
- Do NOT modify, delete, or add any *_test.go file. The tests define correct behaviour.
- Change only non-test source files.
- You are done when every listed package's tests pass."
fi

case "$harness" in
  pi)       A=(pi -p);;
  opencode) A=(opencode run);;
  qwen)     A=(qwen --approval-mode yolo -p);;
  aider)    A=(aider --yes --message);;
  *) echo "unknown harness $harness"; exit 1;;
esac

t0=$(date +%s)
( cd "$W" && CLAUDE_OLLAMA_NO_UNLOAD=1 timeout "${BENCH_TIMEOUT:-1800}" \
    local-agent --model "$model" "${A[@]}" "$PROMPT" </dev/null \
    > "$OUT/$id.log" 2>&1 ); rc=$?
wall=$(( $(date +%s) - t0 ))
verdict=$(TASKS_FILE="$TASKS" "$HERE/grade.sh" "$id" "$W")
echo "### $id $harness/$model exit=$rc wall=${wall}s :: $verdict" | tee -a "$OUT/results.txt"
