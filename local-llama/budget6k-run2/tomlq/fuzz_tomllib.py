import json, random, subprocess, tomllib

random.seed(20240527)

def rand_key():
    r = random.random()
    if r < 0.5:
        return random.choice(['a', 'b', 'key', 'x-y', 'n_1', 'UPPER'])
    if r < 0.75:
        return '"' + random.choice(['a b', 'esc\\"q', 'tab\\t', 'plain', '']) + '"'
    return "'" + random.choice(['lit', 'a.b', 'apos']) + "'"

def s(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    return str(v)

def rand_value(depth):
    r = random.random()
    if depth > 2 or r < 0.6:
        kind = random.random()
        if kind < 0.25:
            return random.choice([0, 1, 42, -17, 1000, 0xdead, 0o755, 0b101])
        if kind < 0.45:
            return random.choice([1.5, -0.5, 5e2, 1e-3, 0.0])
        if kind < 0.6:
            return random.choice([True, False])
        if kind < 0.8:
            return '"' + random.choice(['hi', 'a\\tb', '\\n', 'e\\u00e9', '']) + '"'
        inner = ', '.join(s(rand_value(depth + 1)) for _ in range(random.randint(0, 3)))
        return '[' + inner + ']'
    if r < 0.85:
        n = random.randint(1, 3)
        parts = ', '.join(f'{rand_key()} = {s(rand_value(depth + 1))}' for _ in range(n))
        return '{ ' + parts + ' }'
    return random.choice(['5', '-3', '2.25', 'true', 'false', '"x"'])

def rand_doc():
    lines = []
    path = []
    for _ in range(random.randint(1, 8)):
        op = random.random()
        if op < 0.3 and path:
            path = path[:random.randint(0, len(path))]
        elif op < 0.55:
            path = [random.choice(['a', 'b', 'grp']) for _ in range(random.randint(1, 2))]
            lines.append('[' + '.'.join(path) + ']')
        else:
            key = rand_key()
            if random.random() < 0.3 and path:
                key = random.choice(['a', 'b']) + '.' + key
            lines.append(f'{key} = {s(rand_value(0))}')
    return '\n'.join(lines) + '\n'

fails = mismatches = skipped = 0
trials = 300
for i in range(trials):
    doc = rand_doc()
    with open('/tmp/fuzzr.toml', 'w') as f:
        f.write(doc)
    try:
        ref = tomllib.loads(doc)
    except Exception as e:
        r = subprocess.run(['python3', 'tomlq.py', '/tmp/fuzzr.toml'],
                           capture_output=True, text=True)
        if r.returncode == 0:
            print(f'MISMATCH[{i}] tomlq accepted but tomllib rejected: {e}')
            print(repr(doc))
            fails += 1
        else:
            skipped += 1
        continue
    r = subprocess.run(['python3', 'tomlq.py', '/tmp/fuzzr.toml'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f'MISMATCH[{i}] tomlq rejected valid doc: {r.stderr.strip()}')
        print(repr(doc))
        fails += 1
        continue
    mine = json.loads(r.stdout)
    if mine != ref:
        mismatches += 1
        print(f'MISMATCH[{i}] output differs:')
        print('   doc :', repr(doc))
        print('   mine:', mine)
        print('   ref :', ref)

print(f'{trials} trials: {fails} accept/reject mismatches, {mismatches} output mismatches, {skipped} both-rejected')
raise SystemExit(1 if fails or mismatches else 0)
