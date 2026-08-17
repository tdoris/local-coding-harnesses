import json, random, subprocess, sys, tomllib

random.seed(20240614)

BARE = ['a', 'b2', 'x-y', 'z_z', 'k9']
QUOTED = ['"q k"', "'l-k'", '"esc\\t"', "'raw \\ back'"]
KEYPARTS = BARE + QUOTED

def rand_key():
    if random.random() < 0.7:
        n = random.randint(1, 3)
        return '.'.join(random.choice(KEYPARTS) for _ in range(n))
    return random.choice(KEYPARTS)

def rand_string():
    kind = random.random()
    if kind < 0.4:
        body = ''.join(random.choice('ab \\nt"') for _ in range(random.randint(0, 4)))
        body = body.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')
        return '"' + body + '"'
    if kind < 0.55:
        body = ''.join(random.choice('ab \\t') for _ in range(random.randint(0, 4)))
        return "'" + body + "'"
    if kind < 0.75:
        lines = ['line%d' % i for i in range(random.randint(0, 3))]
        inner = '\\n'.join(lines)
        if random.random() < 0.5:
            inner = inner.replace('line1', 'line1\\', 1) if 'line1' in inner else inner
        return '"""' + inner + '"""'
    lines = ['raw', 'x\\y'][:random.randint(1, 2)]
    return "'''" + '\\n'.join(lines) + "'''"

def rand_scalar():
    r = random.random()
    if r < 0.15:
        return random.choice(['true', 'false'])
    if r < 0.35:
        return rand_string()
    if r < 0.6:
        sign = random.choice(['', '+', '-'])
        d = random.choice(['0', '5', '42', '1_000', '9_9'])
        if random.random() < 0.5 and not d.startswith('0') or d == '0':
            return sign + d
        return '3735928559' if random.random() < 0.5 else d
    if r < 0.85:
        f = random.choice(['3.14', '-0.01', '5e+22', '1e06', '6.626e-34', '+1.0', '2_5.5_5'])
        return f
    return random.choice(['0xDEADbeef', '0o755', '0b1101'])

def rand_value(depth=0):
    r = random.random()
    if depth > 2 or r < 0.65:
        return rand_scalar()
    if r < 0.85:
        n = random.randint(0, 3)
        return '[' + ', '.join(rand_value(depth + 1) for _ in range(n)) + ']'
    n = random.randint(0, 3)
    parts = []
    used = set()
    for _ in range(n):
        k = random.choice(BARE)
        if k in used:
            continue
        used.add(k)
        parts.append('%s = %s' % (k, rand_value(depth + 1)))
    return '{ ' + ', '.join(parts) + ' }'

def gen_doc():
    lines = []
    root_keys = set()
    # some root key/values (some dotted)
    for _ in range(random.randint(0, 3)):
        k = rand_key()
        first = k.split('.')[0].strip('"\'')
        if first in root_keys or first in ('fruits', 't'):
            continue
        root_keys.add(first)
        lines.append('%s = %s' % (k, rand_value()))
    # some static tables
    for _ in range(random.randint(0, 3)):
        depth = random.randint(1, 3)
        parts = [random.choice(BARE) for _ in range(depth)]
        path = '.'.join(parts)
        lines.append('[%s]' % path)
        for _ in range(random.randint(0, 2)):
            k = random.choice(BARE)
            lines.append('%s = %s' % (k, rand_value()))
    # maybe an array of tables
    if random.random() < 0.5:
        name = 'fruits'
        for _ in range(random.randint(1, 3)):
            lines.append('[[%s]]' % name)
            lines.append('name = "%s"' % random.choice(['a', 'b', 'c']))
            if random.random() < 0.5:
                lines.append('[%s.physical]' % name)
                lines.append('color = "%s"' % random.choice(['red', 'blue']))
    return '\n'.join(lines) + '\n'

fails = 0
for i in range(400):
    doc = gen_doc()
    try:
        expected = tomllib.loads(doc)
        valid = True
    except tomllib.TOMLDecodeError as e:
        # our generator can occasionally emit things tomllib rejects
        # (e.g. accidental duplicate headers); in that case both must reject,
        # but we only assert that we reject too (we are stricter-or-equal is fine
        # for generation artifacts). Actually the generator is meant to produce
        # valid docs; treat as generator bug -> skip.
        continue
    open('fuzz.toml', 'w').write(doc)
    p = subprocess.run([sys.executable, 'tomlq.py', 'fuzz.toml'],
                       capture_output=True, text=True)
    try:
        got = json.loads(p.stdout)
    except Exception:
        got = None
    if p.returncode != 0 or got != expected or p.stderr:
        fails += 1
        print('FUZZ FAIL', i)
        print(doc)
        print('rc=%d stderr=%r' % (p.returncode, p.stderr))
        print('want:', json.dumps(expected))
        print('got :', p.stdout[:300])
        if fails > 3:
            break
print('fuzz done, %d failures' % fails)
