#!/usr/bin/env bash
# setup.sh <task-id> <workdir>
# Builds a task directory with NO upstream git history, so the fix cannot be
# recovered with git. Supports single-package tasks ("pkg") and multi-package
# tasks ("pkgs": [...]). Task file selectable via TASKS_FILE.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${BENCH_REPO:-/home/jim/bench-repos/ollama}"
TASKS="${TASKS_FILE:-$HERE/tasks.json}"
id="$1"; work="$2"
sha=$(python3 -c "
import json,sys
t=[x for x in json.load(open('$TASKS'))['tasks'] if x['id']=='$id']
if not t: sys.exit('unknown task: $id')
print(t[0]['sha'])")
pkgs=$(python3 -c "
import json
t=[x for x in json.load(open('$TASKS'))['tasks'] if x['id']=='$id'][0]
print(' '.join(t.get('pkgs') or [t['pkg']]))")

rm -rf "$work"; mkdir -p "$work"
git -C "$SRC" archive "$sha" | tar -x -C "$work"

srcs=$(git -C "$SRC" show --name-only --format= "$sha" | grep '\.go$' | grep -v '_test\.go$' || true)
for f in $srcs; do
  if git -C "$SRC" cat-file -e "$sha^:$f" 2>/dev/null; then
    mkdir -p "$work/$(dirname "$f")"; git -C "$SRC" show "$sha^:$f" > "$work/$f"
  else rm -f "$work/$f"; fi
done

git -C "$work" init -q
git -C "$work" -c user.email=bench@local -c user.name=bench add -A
git -C "$work" -c user.email=bench@local -c user.name=bench commit -qm "task: $id"

: > "$work/.bench-test-hashes"
for p in $pkgs; do
  [ -d "$work/$p" ] && find "$work/$p" -name '*_test.go' -exec sha256sum {} \; \
    | sed "s|$work/||" >> "$work/.bench-test-hashes"
done
sort -o "$work/.bench-test-hashes" "$work/.bench-test-hashes"
echo "$work"
