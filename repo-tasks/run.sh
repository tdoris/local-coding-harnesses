#!/usr/bin/env bash
# run.sh <task-id> <harness> [model]   e.g. run.sh tools-json-braces pi qwen3.8
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
id="$1"; harness="${2:-pi}"; model="${3:-qwen3.8}"
W="/home/jim/bench-repos/wt-$id-$harness"
OUT="$HERE/runs/${BENCH_MODE:-easy}/$model/$harness"; mkdir -p "$OUT"

read -r pkg symptom < <(python3 -c "
import json
t=[x for x in json.load(open('$HERE/tasks.json'))['tasks'] if x['id']=='$id'][0]
print(t['pkg'], t['symptom'])")
symptom=$(python3 -c "
import json
print([x for x in json.load(open('$HERE/tasks.json'))['tasks'] if x['id']=='$id'][0]['symptom'])")

"$HERE/setup.sh" "$id" "$W" >/dev/null

title=$(python3 -c "
import json
print([x for x in json.load(open('$HERE/tasks.json'))['tasks'] if x['id']=='$id'][0].get('title',''))")

# BENCH_MODE=easy  -> descriptive symptom + the package is named  (tests comprehension + editing)
# BENCH_MODE=hard  -> terse issue title only, package NOT named   (tests repo navigation)
if [ "${BENCH_MODE:-easy}" = hard ]; then
PROMPT="This is the ollama Go repository (Go, ~280k LOC).

ISSUE
$title

YOUR TASK
Locate the affected package yourself, find the cause, and fix it in the source.
Then verify by running that package's tests, e.g. 'go test ./<pkg>/...'.

Rules:
- Do NOT modify, delete, or add any *_test.go file. The tests define correct behaviour.
- Change only non-test source files.
- You are done when the affected package's tests pass."
else
PROMPT="This is the ollama Go repository. There is a bug in the \`$pkg\` package.

BUG REPORT
$symptom

YOUR TASK
Find the cause and fix it in the source. Verify with:

    go test ./$pkg/...

Rules:
- Do NOT modify, delete, or add any *_test.go file. The tests define correct behaviour.
- Change only non-test source files.
- The fix is small. Locate the relevant code before editing.
- You are done when 'go test ./$pkg/...' passes."
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
verdict=$("$HERE/grade.sh" "$id" "$W")
echo "### $id $harness/$model exit=$rc wall=${wall}s :: $verdict" | tee -a "$OUT/results.txt"
