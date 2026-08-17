#!/usr/bin/env python3
"""grade.py <dir-containing-jpatch.py> [--visible-only] [--json]"""
import json, os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
CASES = json.load(open(os.path.join(HERE, 'cases.json')))

def strict_eq(a, b):
    if type(a) is bool or type(b) is bool: return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)): return a == b   # JSON numeric equality
    if isinstance(a, dict) and isinstance(b, dict): return list(a) == list(b) and all(strict_eq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list): return len(a) == len(b) and all(strict_eq(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b

def main():
    d = sys.argv[1]; visible_only = '--visible-only' in sys.argv; as_json = '--json' in sys.argv
    prog = os.path.join(d, 'jpatch.py')
    if not os.path.exists(prog):
        print(json.dumps({"passed": 0, "total": len(CASES), "error": "jpatch.py missing"}) if as_json else "jpatch.py missing"); return
    src = open(prog, errors='ignore').read()
    forbidden = re.findall(r'^\s*(?:import|from)\s+(jsonpatch|jsonpointer)\b', src, re.M)
    results = []
    for c in CASES:
        if visible_only and not c['visible']: continue
        with tempfile.TemporaryDirectory() as td:
            dp, pp = os.path.join(td, 'doc.json'), os.path.join(td, 'patch.json')
            json.dump(c['doc'], open(dp, 'w')); json.dump(c['patch'], open(pp, 'w'))
            try: r = subprocess.run([sys.executable, prog, dp, pp], capture_output=True, text=True, timeout=20)
            except subprocess.TimeoutExpired: results.append((c['name'], False, 'timeout')); continue
        ok, why = False, ''
        if c['expected'] == 'error':
            ok = r.returncode == 1 and r.stdout.strip() == ''
            if not ok: why = f'expected error exit 1, got exit {r.returncode}, stdout={r.stdout.strip()[:80]!r}'
        else:
            if r.returncode != 0: why = f'exit {r.returncode}: {r.stderr.strip()[:120]}'
            else:
                try:
                    got = json.loads(r.stdout); ok = strict_eq(got, c['expected'])
                    if not ok: why = f'got {json.dumps(got)[:120]} expected {json.dumps(c["expected"])[:120]}'
                except Exception as e: why = f'bad json: {e}'
        results.append((c['name'], ok, why))
    passed = sum(1 for _, ok, _ in results if ok)
    if as_json:
        print(json.dumps({"passed": passed, "total": len(results), "forbidden_imports": forbidden, "failed": [{"name": n, "why": w} for n, ok, w in results if not ok]}))
    else:
        for n, ok, w in results:
            if not ok: print(f'FAIL {n}: {w}')
        if forbidden: print('FORBIDDEN IMPORTS:', forbidden)
        print(f'{passed}/{len(results)} passed')
if __name__ == '__main__': main()
