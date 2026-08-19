#!/usr/bin/env bash
# grade.sh <task-id> <workdir>  -> JSON verdict
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
id="$1"; work="$2"
pkg=$(python3 -c "
import json
print([x for x in json.load(open('$HERE/tasks.json'))['tasks'] if x['id']=='$id'][0]['pkg'])")

cd "$work" || { echo '{"error":"no workdir"}'; exit 1; }

# 1. anti-cheat: test files must be byte-identical to the pristine state
tampered=$(sha256sum -c .bench-test-hashes 2>/dev/null | grep -v ': OK$' | sed 's/: FAILED.*//' | paste -sd, -)
# also catch deleted test files
missing=$(cut -d' ' -f3- .bench-test-hashes | while read -r f; do [ -f "$f" ] || echo "$f"; done | paste -sd, -)

# 2. run the package tests
out=$(timeout 600 go test -count=1 "./$pkg/..." 2>&1)
if echo "$out" | grep -qE "^(FAIL|--- FAIL)|^# |build failed"; then result=FAIL
elif echo "$out" | grep -qE "^ok"; then result=PASS
else result=NOTESTS; fi

# 3. what did the agent actually change?
changed=$(git -C "$work" status --porcelain | wc -l)

python3 - "$result" "$tampered" "$missing" "$changed" <<'PY'
import json,sys
result,tampered,missing,changed=sys.argv[1:5]
cheated=bool(tampered or missing)
print(json.dumps({
 "result": result,
 "solved": result=="PASS" and not cheated,
 "cheated": cheated,
 "tampered_tests": [t for t in tampered.split(",") if t],
 "missing_tests": [m for m in missing.split(",") if m],
 "files_changed": int(changed),
}))
PY
