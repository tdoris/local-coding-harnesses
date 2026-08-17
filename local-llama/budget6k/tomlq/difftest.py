import json, subprocess, sys, tomllib

CASES = [
    # valid
    'a = 1\nb = 2\n',
    'a.b.c = 1\n',
    'a = 1.5\nb = 5e+22\nc = -0.01\nd = 1e06\ne = +1.0\n',
    'a = 1__000\nb = 0x_dead\n',
    'a = [1, 2, 3]\n',
    'a = [1,\n2, 3,]\n',
    'a = []\n',
    'a = [ [1,2], [3] ]\n',
    'a = { x = 1, y = { z = 2 } }\n',
    'a = {}\n',
    'a = "basic \\t \\n \\u00e9 \\U0001F600"\n',
    "a = 'literal'\n",
    'a = """\nmulti"""\n',
    'a = """x\\\n     y"""\n',
    "a = '''\nmulti'''\n",
    "a = '''''\n",
    'a = """""\n',
    'true = true\nfalse = false\n',
    'x = 0b1101\ny = 0o755\nz = 0xDEADbeef\n',
    '[t]\nk = 1\n[t.sub]\nk2 = 2\n[t]\nk3 = 3\n',
    '[[fruits]]\nname = "a"\n[fruits.physical]\ncolor = "red"\n[[fruits]]\nname = "b"\n[fruits.physical]\ncolor = "blue"\n',
    'a = [1, # comment\n 2, # another\n]\n',
    'a = 1 # trailing\n',
    '  spaced  =  42  \n',
    '"quoted key" = 1\n\'lit key\' = 2\n',
    'a."b.c" = 1\n',
    'a . b = 2\n',
    '[ a . b ]\nx = 1\n',
    '[[a]]\nx = 1\n[[a]]\nx = 2\n[a.b]\ny = 3\n',
    'a.b = [ { x = 1 }, { y = 2 } ]\n',
    'a = "ends with quote """"\n',
    'a = "tab\there"\n',
    'a = 1\n\n# blank lines ok\nb = 2\n',
    'a = 5.\n',
    'a = """"\n',
    'a = "x" # c\nb = 2\n',
    '[[t]]\n[[t]]\nx=1\n[[t]]\ny=1\n[t.last]\nz=2\n',
    'a = 1__0\n',
    'a = -0\n',
    'a = +0\n',
    'a = 1e3\n',
    'a = 0.5\n',
    'a = 1979-05-27T00:32:00Z\n',  # date: tomllib valid, we must reject -> skip
    # invalid
    'a = 1\na = 2\n',
    '[t]\n[t]\n',
    '[t.s]\n[t.s]\n',
    'a = 1\n[a]\n',
    '[a]\na = 1\n[a]\n',
    'a = [1]\n[[a]]\n',
    '[a]\n[[a]]\n',
    '[[a]]\n[a]\n',
    'a = { x = 1, }\n',
    'a = { x = 1 y = 2 }\n',
    'a = 01\n',
    'a = 0123\n',
    'a = "unterminated\n',
    'a = \'unterminated\n',
    'a = """unterminated\n',
    "a = '''unterminated\n",
    'a = 1__\n',
    'a = _1\n',
    'a = 0x\n',
    'a = 0x_\n',
    'a = 0x1_\n',
    'a = 0xGG\n',
    'a = 0o8\n',
    'a = 0b2\n',
    'a = 1e\n',
    'a = 1e+\n',
    'a = 1.2.3\n',
    'a = ..\n',
    'a = +\n',
    'a = -\n',
    'a = .5\n',
    'a = 1 b\n',
    'a = 1\nb\n',
    '= 1\n',
    'a =\n',
    '[t]x = 1\n',
    'a = 1 b = 2\n',
    '[t]\n a.b = 1\n[t]\n',
    'a = [1, 2\n',
    'a = [1, 2\nx = 3\n',
    'a = "x" "y"\n',
    'a = 1 2\n',
    'a = true\nb = false\nc = truex\n',
    'a = 0xDEAD\nb = 0xDEADf\n',
    '[a.]\nx=1\n',
    '[.a]\nx=1\n',
    'a..b = 1\n',
    'a = { b = 1, c = 2 } extra\n',
    'a = "line\\\ncont"\n',
    'a = "\\n" b = 2\n',
    'a = [1, "two", 3.0, true, nullx\n',
    '[a]x = 1\n',
    '[[a]]x = 1\n',
    'a = 1.5e_2\n',
    'a = 5.e1\n',
    'a = 1.5_e2\n',
    '[a] # comment\n',
    '[[a]] # c\nb = 1\n',
    'a = -0.0\n',
    'a = 0.0\n',
]
# cases where tomllib and we legitimately differ (features we may reject)
SKIP = {
    'a = 1979-05-27T00:32:00Z\n',
}

fails = 0
tested = 0
for case in CASES:
    try:
        expected = tomllib.loads(case)
        valid = True
    except tomllib.TOMLDecodeError:
        valid = False
    open('case.toml', 'w').write(case)
    p = subprocess.run([sys.executable, 'tomlq.py', 'case.toml'],
                       capture_output=True, text=True)
    if valid:
        if case in SKIP:
            # we are allowed to reject; just make sure we exit 1 cleanly
            if p.returncode != 1 or p.stdout != '':
                fails += 1
                print('FAIL(skip-reject):', repr(case), p.returncode, p.stdout, p.stderr)
            continue
        tested += 1
        try:
            got = json.loads(p.stdout)
        except Exception:
            got = None
        ok = (p.returncode == 0 and p.stderr == '' and got == expected
              and json.dumps(got, sort_keys=True) == json.dumps(expected, sort_keys=True))
        if not ok:
            fails += 1
            print('FAIL(valid)  :', repr(case))
            print('  rc=%d stderr=%r' % (p.returncode, p.stderr))
            print('  want:', json.dumps(expected))
            print('  got :', p.stdout[:300])
    else:
        tested += 1
        if p.returncode != 1 or p.stdout != '':
            fails += 1
            print('FAIL(invalid):', repr(case))
            print('  rc=%d stdout=%r stderr=%r' % (p.returncode, p.stdout, p.stderr))
print('done, %d failures out of %d cases' % (fails, tested))
