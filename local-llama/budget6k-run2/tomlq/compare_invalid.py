import subprocess, sys, tomllib

B = chr(92)
invalid_docs = [
    'x = 1\nx = 2\n',
    '[x]\n[x]\n',
    'x = 1\n[x]\n',
    '[x]\ny = 1\n[x]\nz = 2\n',
    'x = [1]\n[[x]]\n',
    '[[x]]\nx = 1\n[[x]]\nx = 1\n[x]\n',
    'a = { b = 1 }\na.c = 2\n',
    'a = { b = 1 }\n[a.c]\n',
    'a = { b = 1, }\n',
    'a = { b = 1,\n  c = 2 }\n',
    'a = { b = 1, b = 2 }\n',
    'a = 007\n',
    'a = 010\n',
    'a = +0x1\n',
    'a = -0x1\n',
    'a = 0x_1\n',
    'a = 1_\n',
    'a = _1\n',
    'a = 1__2\n',
    'a = 1.\n',
    'a = .5\n',
    'a = 1e\n',
    'a = 1e+\n',
    'a = 0x\n',
    'a = "unterminated\n',
    'a = "line\nbreak"\n',
    "a = 'line\nbreak'\n",
    'a = "bad ' + B + 'q"\n',
    'a = "bad ' + B + 'u12"\n',
    'a = "bad ' + B + 'U12345"\n',
    'a = truex\n',
    'a = falsey\n',
    'a = true false\n',
    'a = 1979-05-27\n',
    'a = 07:32:00\n',
    'a = 1979-05-27T07:32:00Z\n',
    'a = inf\n',
    'a = -inf\n',
    'a = nan\n',
    'a = +nan\n',
    'a = 1 2\n',
    '= 1\n',
    'a =\n',
    '[ ]\n',
    '[a.]\n',
    '[a..b]\n',
    'a..b = 1\n',
    'a = b = 1\n',
    'a = [1, 2\n',
    'a = [1, 2]]\n',
    'a = { b = 1\n',
    'a = { b 1 }\n',
    'a = [1] ]\n',
    '[[a\n',
    '[[a]\n',
    '[a]]\n',
    'a = """unterminated\n',
    "a = '''unterminated\n",
    'a = 5e\n',
    'a = 5e2.5\n',
    'a = 1.2.3\n',
    'a = 0b2\n',
    'a = 0o8\n',
    'a = 0xG\n',
    'a = 0x1G\n',
    'a = 0o18\n',
    'a = 0b12\n',
    'a = "a" "b"\n',
    'a = [1 2]\n',
    'a = {b = 1}c\n',
    'a = {b = 1},\n',
    '\ta = 1\tjunk\n',
    '[a] b\n',
    'a = 1\n[a.b]\n',
    'a.b = 1\n[a.b]\n',
    'a = 1\na = 2\n[a]\n',
    'x = 1\n[[x]]\n',
    'a = "ok"\na = 5\n',
    '[fruit]\napple.color = "red"\n[fruit.apple]\ncolor = "green"\n',
    '[fruit.apple]\ncolor = "red"\n[fruit]\napple.color = "green"\n',
    'a = { x = 1 }\na.x = 2\n',
    'a = 1\n[b]\na = 2\n',   # b.a is fine... this one is actually VALID (different table). will be caught by tomllib comparison
]

# drop the last one which is actually valid
invalid_docs = invalid_docs[:-1]

fails = 0
for idx, doc in enumerate(invalid_docs):
    try:
        tomllib.loads(doc)
        tl_ok = True
    except Exception:
        tl_ok = False
    p = '/tmp/inv_%d.toml' % idx
    with open(p, 'w') as f:
        f.write(doc)
    r = subprocess.run(['python3', 'tomlq.py', p], capture_output=True, text=True)
    accepted = r.returncode == 0
    if accepted:
        print(f'FAIL[{idx}] tomlq ACCEPTED invalid doc: {doc!r}')
        fails += 1
    elif r.returncode != 1:
        print(f'FAIL[{idx}] tomlq rc={r.returncode} (want 1): {doc!r} {r.stderr!r}')
        fails += 1
    elif not tl_ok:
        pass  # both reject: good
    else:
        print(f'WARN[{idx}] tomlq rejects but tomllib accepts: {doc!r}  -> {r.stderr.strip()}')

print()
print('ALL INVALID REJECTED' if fails == 0 else f'{fails} FAILURES')
sys.exit(1 if fails else 0)
