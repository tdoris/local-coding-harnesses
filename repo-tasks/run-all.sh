#!/usr/bin/env bash
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASKS="${TASKS_FILE:-$HERE/tasks.json}"
harness="${1:-pi}"; model="${2:-qwen3.8}"
ids=$(python3 -c "
import json
print(' '.join(t['id'] for t in json.load(open('$TASKS'))['tasks']))")
for id in $ids; do TASKS_FILE="$TASKS" BENCH_TIMEOUT=${BENCH_TIMEOUT:-1800} "$HERE/run.sh" "$id" "$harness" "$model"; done
echo "REPO-TASKS-DONE ${BENCH_MODE:-easy} $harness $model"
