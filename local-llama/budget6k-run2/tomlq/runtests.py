import json, os, subprocess, sys

D = 't'
os.makedirs(D, exist_ok=True)
ok = 0
fail = 0

def write(name, content):
    p = os.path.join(D, name)
    with open(p, 'w') as f:
        f.write(content)
    return p

def run(f, keypath=None):
    cmd = ['python3', 'tomlq.py', f]
    if keypath is not None:
        cmd.append(keypath)
    return subprocess.run(cmd, capture_output=True, text=True)

def expect_ok(content, expected, name='case.toml', keypath=None):
    global ok, fail
    p = write(name, content)
    r = run(p, keypath)
    if r.returncode != 0:
        print(f'FAIL {name}: rc={r.returncode} stderr={r.stderr!r}')
        fail += 1
        return
    if r.stderr != '':
        print(f'FAIL {name}: unexpected stderr {r.stderr!r}')
        fail += 1
        return
    try:
        d = json.loads(r.stdout)
    except Exception as e:
        print(f'FAIL {name}: bad JSON: {e}: {r.stdout!r}')
        fail += 1
        return
    if d != expected:
        print(f'FAIL {name}: {d!r} != {expected!r}')
        fail += 1
        return
    ok += 1
    print(f'ok   {name}' + (f'  [{keypath}]' if keypath else ''))

def expect_err(content, name='case.toml', keypath=None):
    global ok, fail
    p = write(name, content)
    r = run(p, keypath)
    if keypath is None:
        want = 1
    else:
        want = 2
    if r.returncode != want:
        print(f'FAIL {name}: rc={r.returncode} want {want}; stdout={r.stdout!r} stderr={r.stderr!r}')
        fail += 1
        return
    if r.stderr == '':
        print(f'FAIL {name}: empty stderr')
        fail += 1
        return
    ok += 1
    print(f'ok   {name}  [rc={r.returncode}]  {r.stderr.strip()}')

# ---------- valid ----------
expect_ok('', {}, 'v_empty.toml')
expect_ok('# only a comment\n\n   \n# another\n', {}, 'v_comments.toml')

expect_ok(r'''
"basic key" = 1
'literal key' = 2
"esc\"key" = 3
'a.b' = 4
"a".b.c = 5
x . y = 6
''', {'basic key': 1, 'literal key': 2, 'esc"key': 3, 'a.b': 4, 'a': {'b': {'c': 5}}, 'x': {'y': 6}},
     'v_keys.toml')

expect_ok('a = 1\nb = 2\nc = 3\n', {'a': 1, 'b': 2, 'c': 3}, 'v_order.toml')
r = run(os.path.join(D, 'v_order.toml'))
assert r.stdout.index('a') < r.stdout.index('b') < r.stdout.index('c')
print('ok   key order preserved')
ok += 1

expect_ok('''
i = [1, 2,
     3, 4]
e = [
]
t = [1, 2,]
n = [[1], [2, [3, [4]]]]
m = [
  1, # one
  # two
  2,
]
''', {'i': [1, 2, 3, 4], 'e': [], 't': [1, 2], 'n': [[1], [2, [3, [4]]]], 'm': [1, 2]}, 'v_arrays.toml')

expect_ok('''
it = {}
it2 = { a = 1 }
it3 = { a = 1, b = { c = [1, 2] } }
''', {'it': {}, 'it2': {'a': 1}, 'it3': {'a': 1, 'b': {'c': [1, 2]}}}, 'v_inline.toml')

expect_ok('''
d = +1.0
e = 1e06
f = -2E-2
g = 6.626e-34
h = 1_000.5
k = 0.01
''', {'d': 1.0, 'e': 1e6, 'f': -0.02, 'g': 6.626e-34, 'h': 1000.5, 'k': 0.01}, 'v_floats.toml')
r = run(os.path.join(D, 'v_floats.toml'))
for tok in ['1.0', '1000000.0', '-0.02', '1000.5', '0.01']:
    assert tok in r.stdout, (tok, r.stdout)
print('ok   float formatting')
ok += 1

expect_ok('''
[[servers]]
name = "a"
[servers.db]
host = "x"
[[servers]]
name = "b"
''', {'servers': [{'name': 'a', 'db': {'host': 'x'}}, {'name': 'b'}]}, 'v_aot.toml')

expect_ok('''
[servers.db]
host = "x"
[servers]
name = "a"
''', {'servers': {'db': {'host': 'x'}, 'name': 'a'}}, 'v_super.toml')

# ---------- invalid (rc=1) ----------
expect_err('x = 1\nx = 2\n', 'e_dupkey.toml')
expect_err('[x]\n[x]\n', 'e_duptable.toml')
expect_err('x = 1\n[x]\n', 'e_val_then_table.toml')
# NOTE: [x] followed by 'x = 1' is VALID (the key lives inside table x)
expect_ok('[x]\nx = 1\n', {'x': {'x': 1}}, 'v_table_selfkey.toml')
expect_err('x = [1]\n[[x]]\n', 'e_static_then_aot.toml')
expect_err('[[x]]\n[x]\n', 'e_aot_then_table.toml')
expect_err('a = { b = 1 }\na.c = 2\n', 'e_extend_inline_dotted.toml')
expect_err('a = { b = 1 }\n[a.c]\n', 'e_extend_inline_header.toml')
expect_err('a = { b = 1 }\n[[a]]\n', 'e_aot_over_inline.toml')
expect_err('a = 007\n', 'e_leading_zero.toml')
expect_err('a = +0x1\n', 'e_signed_hex.toml')
expect_err('a = -0b1\n', 'e_signed_bin.toml')
expect_err('a = { b = 1, }\n', 'e_inline_trailing_comma.toml')
expect_err('a = { b = 1,\nc = 2 }\n', 'e_inline_newline.toml')
expect_err('a = 1.\n', 'e_dot_only.toml')
expect_err('a = .5\n', 'e_leading_dot.toml')
expect_err('a = 1e\n', 'e_bare_e.toml')
expect_err('a = 0x\n', 'e_bare_x.toml')
expect_err('a = 0o\n', 'e_bare_o.toml')
expect_err('a = 0b\n', 'e_bare_b.toml')
expect_err('a = "bad \\q"\n', 'e_bad_escape.toml')
expect_err('a = "unterminated\n', 'e_unterminated.toml')
expect_err('a = "line\nbreak"\n', 'e_newline_basic.toml')
expect_err("a = 'line\nbreak'\n", 'e_newline_literal.toml')
expect_err('a = truex\n', 'e_truex.toml')
expect_err('a = falsey\n', 'e_falsey.toml')
expect_err('a = 1979-05-27\n', 'e_date.toml')
expect_err('a = inf\n', 'e_inf.toml')
expect_err('a = nan\n', 'e_nan.toml')
expect_err('a = { b = 1, b = 2 }\n', 'e_inline_dup.toml')
expect_err('a = 1\na.b = 2\n', 'e_dotted_over_value.toml')
expect_err('a = 1\n[a.b]\n', 'e_header_over_value.toml')
expect_err('a..b = 1\n', 'e_empty_key_part.toml')
expect_err('[a.]\n', 'e_header_empty_part.toml')
expect_err('= 1\n', 'e_no_key.toml')
expect_err('[ ]\n', 'e_empty_header.toml')
expect_err('x =\n', 'e_missing_value.toml')
expect_err('x = 1 2\n', 'e_trailing_junk.toml')
expect_err('[x] 2\n', 'e_header_junk.toml')
expect_err('a = """unterminated\n', 'e_unterm_ml_basic.toml')
expect_err("a = '''unterminated\n", 'e_unterm_ml_lit.toml')
expect_err('a = 1_\n', 'e_trailing_underscore.toml')
expect_err('a = _1\n', 'e_leading_underscore.toml')
expect_err('a = 1__2\n', 'e_double_underscore.toml')
expect_err('a = 1.2.3\n', 'e_two_dots.toml')
# NOTE: after [[a]] the current table is the element, so 'a.b = 1' is valid there.
# Real error case: dotted key whose intermediate resolves to an array of tables.
expect_err('[[t.x]]\ny = 1\n[t]\nx.z = 2\n', 'e_dotted_into_aot.toml')
expect_err('a = 0x_1\n', 'e_hex_us_1.toml')
expect_err('a = 0x1_\n', 'e_hex_us_2.toml')
expect_err('a = 1_e5\n', 'e_exp_us_1.toml')
expect_err('a = 1.2_\n', 'e_frac_us.toml')

# ---------- keypath errors (rc=2) ----------
p = write('v_kp.toml', 'a = 1\n[b]\nc = 2\n')
expect_err('a = 1\n[b]\nc = 2\n', 'v_kp.toml', keypath='nope')
expect_err('a = 1\n[b]\nc = 2\n', 'v_kp.toml', keypath='b.nope')
expect_err('a = 1\n[b]\nc = 2\n', 'v_kp.toml', keypath='a.c')
expect_err('a = 1\n[b]\nc = 2\n', 'v_kp.toml', keypath='b.c.x')

# valid keypath lookups
expect_ok('a = 1\n[b]\nc = 2\n', 2, 'v_kp.toml', keypath='b.c')
expect_ok('a = 1\n[b]\nc = 2\n', 1, 'v_kp.toml', keypath='a')
expect_ok('x = [1, 2]\n', [1, 2], 'v_kp2.toml', keypath='x')

print()
print(f'{ok} passed, {fail} failed')
sys.exit(1 if fail else 0)
