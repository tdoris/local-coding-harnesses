#!/usr/bin/env bash
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
harness="${1:-pi}"; model="${2:-qwen3.8}"
ids=$(python3 -c "
import json
print(' '.join(t['id'] for t in json.load(open('$HERE/tasks.json'))['tasks']))")
for id in $ids; do BENCH_TIMEOUT=${BENCH_TIMEOUT:-1800} "$HERE/run.sh" "$id" "$harness" "$model"; done
echo "REPO-TASKS-DONE $harness $model"
