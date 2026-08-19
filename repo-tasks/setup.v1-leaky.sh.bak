#!/usr/bin/env bash
# setup.sh <task-id> <workdir>
# Prepares an isolated git worktree with the fix reverted. Prints the workdir.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${BENCH_REPO:-/home/jim/bench-repos/ollama}"
id="$1"; work="$2"
read -r sha pkg < <(python3 -c "
import json,sys
t=[x for x in json.load(open('$HERE/tasks.json'))['tasks'] if x['id']=='$id']
if not t: sys.exit('unknown task: $id')
print(t[0]['sha'], t[0]['pkg'])")

rm -rf "$work"
git -C "$SRC" worktree prune >/dev/null 2>&1 || true
git -C "$SRC" worktree add -q --detach "$work" "$sha"

# Revert only non-test source files touched by the fix commit
srcs=$(git -C "$SRC" show --name-only --format= "$sha" | grep '\.go$' | grep -v '_test\.go$' || true)
for f in $srcs; do
  git -C "$work" checkout "$sha^" -- "$f" 2>/dev/null || rm -f "$work/$f"
done

# Record the pristine hash of every test file in the package, for anti-cheat
find "$work/$pkg" -name '*_test.go' -exec sha256sum {} \; \
  | sed "s|$work/||" | sort > "$work/.bench-test-hashes"
echo "$work"
