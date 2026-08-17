import json, subprocess, sys, tomllib

B = chr(92)  # backslash
docs = [
    'title = "TOML"\n\n[owner]\nname = "Tom"\nbio = "GitHub CTO"\n',

    'name = "Orange"\nphysical.color = "orange"\nphysical.shape = "round"\n',

    '[fruit]\napple.color = "red"\napple.taste.sweet = true\n',

    '[[fruit]]\nname = "apple"\n\n[fruit.physical]\ncolor = "red"\n\n[[fruit]]\nname = "banana"\n[fruit.physical]\ncolor = "yellow"\n',

    '[fruit.apple]\ncolor = "red"\ntaste.sweet = true\n',

    'answer = 42\npi = 3.14\nbig = 5e+22\nsmall = 6.626e-34\nu = 1_000\n'
    'hx = 0xDEAD_BEEF\noc = 0o755\nbi = 0b1101\nneg = -17\npos = +17\n'
    'f1 = +1.0\nf2 = -0.01\nf3 = 1e06\nf4 = 2E-2\nf5 = 1_000.5\n',

    'a = [ 1, 2, 3 ]\nb = [ 1, 2, 3, ]\nc = [\n  1, 2, # comment\n  3,\n]\n'
    'd = [ [1, 2], [3] ]\ne = [ [1, 2], ["three", 4], { x = 1 }, ]\n',

    'point = { x = 1, y = 2 }\nnested = { a = { b = [1, { c = 2 }] } }\nempty = {}\n',

    '"with space" = 1\n\'lit\' = 2\n"a\\\\b" = 3\n'
    'tab = "x' + B + 'ty"\nuni = "e' + B + 'u00e9x"\n'
    'cap = "A' + B + 'U0001F600z"\n',

    'ml1 = """\nfirst line\nsecond line' + B + '\n   continued"""\n',

    "ml2 = '''\nliteral\nno escapes " + B + "n'''\n",

    'ml3 = """a' + B + 'tb"""\n',

    'ml4 = """\n' + "'''\n" + 'not a delimiter"""\n',

    "[a.b]\nx = 1\n\n[a]\ny = 2\n",

    '[[servers]]\nname = "edge1"\n[servers.tls]\nport = 443\n\n'
    '[[servers]]\nname = "edge2"\n[servers.tls]\nport = 8443\n',

    '',
    '# nothing\n\n# here\n',

    '[[a]]\nb.c = 1\n\n[[a]]\nb.d = 2\n',

    '"a.b" = 1\n"a".b = 2\nb."c d" = 3\n',

    '[t]\nk = [ [ [1] ] ]\narr = []\n',

    'x = "a"\n',

    # tabs around keys and values
    '\ta\t=\t1\n[b]\t\t\t\n\tk\t=\t"v"\t\n',
]

fails = 0
for idx, doc in enumerate(docs):
    p = f'/tmp/fuzz_{idx}.toml'
    with open(p, 'w') as f:
        f.write(doc)
    r = subprocess.run(['python3', 'tomlq.py', p], capture_output=True, text=True)
    if r.returncode != 0:
        print(f'FAIL[{idx}] tomlq rc={r.returncode}: {r.stderr.strip()}')
        print('   doc:', repr(doc))
        fails += 1
        continue
    try:
        mine = json.loads(r.stdout)
    except Exception as e:
        print(f'FAIL[{idx}] bad json: {e}')
        fails += 1
        continue
    try:
        ref = tomllib.loads(doc)
    except Exception as e:
        print(f'NOTE[{idx}] tomllib rejected doc (skipped): {e}')
        print('   doc:', repr(doc))
        continue
    if mine != ref:
        print(f'FAIL[{idx}] mismatch:')
        print('   doc  :', repr(doc))
        print('   mine :', mine)
        print('   ref  :', ref)
        fails += 1
    else:
        print(f'ok   [{idx}]')

print()
print('ALL MATCH' if fails == 0 else f'{fails} FAILURES')
sys.exit(1 if fails else 0)
