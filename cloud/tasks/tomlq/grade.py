#!/usr/bin/env python3
"""grade.py <dir-containing-tomlq.py> [--visible-only] [--json]
Runs the corpus against tomlq.py; expected values come from tomllib (the oracle)."""
import json, os, re, subprocess, sys, tempfile, tomllib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cases import CASES

def strict_eq(a, b):
    if type(a) is bool or type(b) is bool: return type(a) is type(b) and a == b
    if isinstance(a, int) and isinstance(b, int): return a == b
    if isinstance(a, float) and isinstance(b, float): return a == b or (a != a and b != b)
    if isinstance(a, (int, float)) or isinstance(b, (int, float)): return False  # int vs float mismatch
    if isinstance(a, dict) and isinstance(b, dict):
        return list(a.keys()) == list(b.keys()) and all(strict_eq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(strict_eq(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b

def expected_for(text, keypath):
    doc = tomllib.loads(text)
    if keypath is None: return doc
    cur = doc
    for part in keypath.split('.'):
        cur = cur[part]
    return cur

def main():
    d = sys.argv[1]; visible_only = '--visible-only' in sys.argv; as_json = '--json' in sys.argv
    prog = os.path.join(d, 'tomlq.py')
    results = []
    if not os.path.exists(prog):
        print(json.dumps({"passed": 0, "total": len(CASES), "error": "tomlq.py missing"}) if as_json else "tomlq.py missing"); return
    src = open(prog, errors='ignore').read()
    forbidden = re.findall(r'^\s*(?:import|from)\s+(tomllib|toml|tomli|tomlkit)\b', src, re.M)
    for name, text, keypath, expect, visible in CASES:
        if visible_only and not visible: continue
        with tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False) as f:
            f.write(text); path = f.name
        cmd = [sys.executable, prog, path] + ([keypath] if keypath else [])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            results.append((name, False, 'timeout')); os.unlink(path); continue
        os.unlink(path)
        ok, why = False, ''
        if expect == 'ok':
            if r.returncode != 0: why = f'exit {r.returncode}, stderr: {r.stderr.strip()[:120]}'
            else:
                try:
                    got = json.loads(r.stdout)
                    exp = expected_for(text, keypath)
                    ok = strict_eq(got, exp)
                    if not ok: why = f'got {json.dumps(got)[:150]} expected {json.dumps(exp)[:150]}'
                except Exception as e: why = f'bad json output: {e}; stdout={r.stdout[:100]!r}'
        elif expect == 'parse_error':
            ok = r.returncode == 1 and r.stdout.strip() == ''
            if not ok: why = f'exit {r.returncode}, stdout={r.stdout.strip()[:80]!r}'
        elif expect == 'missing_key':
            ok = r.returncode == 2 and r.stdout.strip() == ''
            if not ok: why = f'exit {r.returncode}, stdout={r.stdout.strip()[:80]!r}'
        results.append((name, ok, why))
    passed = sum(1 for _, ok, _ in results if ok)
    if as_json:
        print(json.dumps({"passed": passed, "total": len(results), "forbidden_imports": forbidden,
                          "failed": [{"name": n, "why": w} for n, ok, w in results if not ok]}))
    else:
        for n, ok, w in results:
            if not ok: print(f'FAIL {n}: {w}')
        if forbidden: print(f'FORBIDDEN IMPORTS: {forbidden}')
        print(f'{passed}/{len(results)} passed')

if __name__ == '__main__': main()
