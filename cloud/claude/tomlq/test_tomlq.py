#!/usr/bin/env python3
"""Tests for tomlq.py — run: python3 test_tomlq.py  (do not modify)"""
import json, os, subprocess, sys, tempfile, unittest

PROG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tomlq.py")

def run(toml_text, keypath=None):
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
        f.write(toml_text); path = f.name
    try:
        r = subprocess.run([sys.executable, PROG, path] + ([keypath] if keypath else []), capture_output=True, text=True, timeout=20)
    finally:
        os.unlink(path)
    return r.returncode, r.stdout, r.stderr

def strict_eq(a, b):
    if type(a) is bool or type(b) is bool: return type(a) is type(b) and a == b
    if isinstance(a, int) and isinstance(b, int): return a == b
    if isinstance(a, float) and isinstance(b, float): return a == b
    if isinstance(a, (int, float)) or isinstance(b, (int, float)): return False
    if isinstance(a, dict) and isinstance(b, dict): return list(a) == list(b) and all(strict_eq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list): return len(a) == len(b) and all(strict_eq(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b

class TestTomlq(unittest.TestCase):
    def test_empty_doc(self):
        rc, out, err = run('', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_comments_only(self):
        rc, out, err = run('# just a comment\n\n   # another\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_simple_kv(self):
        rc, out, err = run('title = "TOML"\nn = 42\nf = 3.5\nb = true\nc = false\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"title\": \"TOML\", \"n\": 42, \"f\": 3.5, \"b\": true, \"c\": false}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_bare_keys(self):
        rc, out, err = run('key-1 = 1\n_x = 2\n1234 = "num key"\nCamelCase = 3\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"key-1\": 1, \"_x\": 2, \"1234\": \"num key\", \"CamelCase\": 3}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_dotted_keys(self):
        rc, out, err = run('a.b.c = 1\na . d = 2\nx."y.z".w = 3\nsite."google.com" = true\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": {\"b\": {\"c\": 1}, \"d\": 2}, \"x\": {\"y.z\": {\"w\": 3}}, \"site\": {\"google.com\": true}}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_tabs_and_spaces(self):
        rc, out, err = run('key\t=\t"v"\n  indented   =   1  \n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"key\": \"v\", \"indented\": 1}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_hash_in_string(self):
        rc, out, err = run('s = "a # not a comment" # real comment\nt = \'#\'\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"s\": \"a # not a comment\", \"t\": \"#\"}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_escapes(self):
        rc, out, err = run('s = "tab\\there\\nnew \\"q\\" back\\\\slash \\u00e9 \\U0001F600 \\b\\f\\r"\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"s\": \"tab\\there\\nnew \\\"q\\\" back\\\\slash \\u00e9 \\ud83d\\ude00 \\b\\f\\r\"}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_literal_string(self):
        rc, out, err = run("p = 'C:\\Users\\x'\nre = '<\\i\\c*\\s*>'\n", None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"p\": \"C:\\\\Users\\\\x\", \"re\": \"<\\\\i\\\\c*\\\\s*>\"}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_ml_basic_trim(self):
        rc, out, err = run('s = """\nRoses are red\nViolets are blue"""\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"s\": \"Roses are red\\nViolets are blue\"}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_ml_basic_backslash(self):
        rc, out, err = run('s = """\nThe quick brown \\\n\n  fox jumps over \\\n    the lazy dog."""\nt = """\\\n  trimmed  \\\n  """\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"s\": \"The quick brown fox jumps over the lazy dog.\", \"t\": \"trimmed  \"}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_ml_literal(self):
        rc, out, err = run('s = \'\'\'\nraw \\n text\n\'\'\'\nre = \'\'\'I [dw]on\'t need \\d{2} apples\'\'\'\nq = \'\'\'Here are fifteen quotation marks: """""""""""""""\'\'\'\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"s\": \"raw \\\\n text\\n\", \"re\": \"I [dw]on't need \\\\d{2} apples\", \"q\": \"Here are fifteen quotation marks: \\\"\\\"\\\"\\\"\\\"\\\"\\\"\\\"\\\"\\\"\\\"\\\"\\\"\\\"\\\"\"}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_integers(self):
        rc, out, err = run('a = +99\nb = 42\nc = 0\nd = -17\ne = 1_000\nf = 5_349_221\ng = -0\nh = +0\nbig = 9223372036854775807\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": 99, \"b\": 42, \"c\": 0, \"d\": -17, \"e\": 1000, \"f\": 5349221, \"g\": 0, \"h\": 0, \"big\": 9223372036854775807}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_int_bases(self):
        rc, out, err = run('hex1 = 0xDEADBEEF\nhex2 = 0xdead_beef\noct1 = 0o01234567\noct2 = 0o755\nbin1 = 0b11010110\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"hex1\": 3735928559, \"hex2\": 3735928559, \"oct1\": 342391, \"oct2\": 493, \"bin1\": 214}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_floats(self):
        rc, out, err = run('a = +1.0\nb = 3.1415\nc = -0.01\nd = 5e+22\ne = 1e06\nf = -2E-2\ng = 6.626e-34\nh = 224_617.445_991_228\ni = 0.0\nj = -0.0\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": 1.0, \"b\": 3.1415, \"c\": -0.01, \"d\": 5e+22, \"e\": 1000000.0, \"f\": -0.02, \"g\": 6.626e-34, \"h\": 224617.445991228, \"i\": 0.0, \"j\": -0.0}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_int_vs_float(self):
        rc, out, err = run('i = 1\nf = 1.0\ne = 1e0\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"i\": 1, \"f\": 1.0, \"e\": 1.0}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_arrays(self):
        rc, out, err = run('ints = [ 1, 2, 3 ]\nstrs = [ "red", "yellow", "green" ]\nnested = [ [ 1, 2 ], [3, 4, 5] ]\nmixed = [ 1, "two", 3.0, true, [4] ]\nempty = []\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"ints\": [1, 2, 3], \"strs\": [\"red\", \"yellow\", \"green\"], \"nested\": [[1, 2], [3, 4, 5]], \"mixed\": [1, \"two\", 3.0, true, [4]], \"empty\": []}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_array_multiline(self):
        rc, out, err = run('a = [\n  1,\n  2, # comment\n\n  3,\n]\nb = [ "a,b", "]c[", # tricky\n  \'d\' ]\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": [1, 2, 3], \"b\": [\"a,b\", \"]c[\", \"d\"]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_array_of_inline_tables(self):
        rc, out, err = run('points = [ { x = 1, y = 2, z = 3 },\n           { x = 7, y = 8, z = 9 },\n           { x = 2, y = 4, z = 8 } ]\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"points\": [{\"x\": 1, \"y\": 2, \"z\": 3}, {\"x\": 7, \"y\": 8, \"z\": 9}, {\"x\": 2, \"y\": 4, \"z\": 8}]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_inline_tables(self):
        rc, out, err = run('name = { first = "Tom", last = "Preston-Werner" }\npoint = { x = 1, y = 2 }\nanimal = { type.name = "pug" }\nempty = {}\nnest = { a = { b = { c = [1, {d = 2}] } } }\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"name\": {\"first\": \"Tom\", \"last\": \"Preston-Werner\"}, \"point\": {\"x\": 1, \"y\": 2}, \"animal\": {\"type\": {\"name\": \"pug\"}}, \"empty\": {}, \"nest\": {\"a\": {\"b\": {\"c\": [1, {\"d\": 2}]}}}}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_tables(self):
        rc, out, err = run('[table-1]\nkey1 = "some string"\nkey2 = 123\n\n[table-2]\nkey1 = "another string"\nkey2 = 456\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"table-1\": {\"key1\": \"some string\", \"key2\": 123}, \"table-2\": {\"key1\": \"another string\", \"key2\": 456}}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_table_quoted_and_dotted(self):
        rc, out, err = run('[dog."tater.man"]\ntype.name = "pug"\n\n[ a . b . c ]\nq = 1\n\n[ "quoted key with spaces" ]\nz = 2\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"dog\": {\"tater.man\": {\"type\": {\"name\": \"pug\"}}}, \"a\": {\"b\": {\"c\": {\"q\": 1}}}, \"quoted key with spaces\": {\"z\": 2}}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_implicit_and_super_after_sub(self):
        rc, out, err = run('[x.y.z.w]\nv = 1\n\n[x.y]\nq = 2\n\n[x]\nz = 3\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"x\": {\"y\": {\"z\": {\"w\": {\"v\": 1}}, \"q\": 2}, \"z\": 3}}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_dotted_inside_table(self):
        rc, out, err = run('[owner]\nname.first = "a"\nname.last = "b"\nage = 3\n[owner.address]\ncity = "x"\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"owner\": {\"name\": {\"first\": \"a\", \"last\": \"b\"}, \"age\": 3, \"address\": {\"city\": \"x\"}}}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_array_of_tables(self):
        rc, out, err = run('[[products]]\nname = "Hammer"\nsku = 738594937\n\n[[products]]  # empty table within the array\n\n[[products]]\nname = "Nail"\nsku = 284758393\ncolor = "gray"\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"products\": [{\"name\": \"Hammer\", \"sku\": 738594937}, {}, {\"name\": \"Nail\", \"sku\": 284758393, \"color\": \"gray\"}]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_nested_array_of_tables(self):
        rc, out, err = run('[[fruits]]\nname = "apple"\n\n[fruits.physical]\ncolor = "red"\nshape = "round"\n\n[[fruits.varieties]]\nname = "red delicious"\n\n[[fruits.varieties]]\nname = "granny smith"\n\n[[fruits]]\nname = "banana"\n\n[[fruits.varieties]]\nname = "plantain"\n', None)
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"fruits\": [{\"name\": \"apple\", \"physical\": {\"color\": \"red\", \"shape\": \"round\"}, \"varieties\": [{\"name\": \"red delicious\"}, {\"name\": \"granny smith\"}]}, {\"name\": \"banana\", \"varieties\": [{\"name\": \"plantain\"}]}]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_kp_array(self):
        rc, out, err = run('[server]\nports = [ 8000, 8001, 8002 ]\nenabled = true\n', 'server.ports')
        self.assertEqual(rc, 0, err)
        expected = json.loads("[8000, 8001, 8002]")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_kp_string(self):
        rc, out, err = run('[owner]\nname = "Tom"\n', 'owner.name')
        self.assertEqual(rc, 0, err)
        expected = json.loads("\"Tom\"")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_kp_aot(self):
        rc, out, err = run('[[products]]\nname = "Hammer"\n[[products]]\nname = "Nail"\n', 'products')
        self.assertEqual(rc, 0, err)
        expected = json.loads("[{\"name\": \"Hammer\"}, {\"name\": \"Nail\"}]")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_kp_missing(self):
        rc, out, err = run('[server]\nports = [1]\n', 'server.host')
        self.assertEqual(rc, 2, f"expected missing-key exit 2, got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_dup_key(self):
        rc, out, err = run('a = 1\na = 2\n', None)
        self.assertEqual(rc, 1, f"expected parse error exit 1, got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_dup_table(self):
        rc, out, err = run('[a]\nx = 1\n[a]\ny = 2\n', None)
        self.assertEqual(rc, 1, f"expected parse error exit 1, got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_value_then_table(self):
        rc, out, err = run('[a]\nb = 1\n[a.b]\nc = 2\n', None)
        self.assertEqual(rc, 1, f"expected parse error exit 1, got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_inline_table_extended(self):
        rc, out, err = run('t = { a = 1 }\nt.b = 2\n', None)
        self.assertEqual(rc, 1, f"expected parse error exit 1, got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_leading_zero(self):
        rc, out, err = run('n = 007\n', None)
        self.assertEqual(rc, 1, f"expected parse error exit 1, got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_unterminated_string(self):
        rc, out, err = run('s = "abc\n', None)
        self.assertEqual(rc, 1, f"expected parse error exit 1, got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_missing_value(self):
        rc, out, err = run('key =\n', None)
        self.assertEqual(rc, 1, f"expected parse error exit 1, got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_bare_key_space(self):
        rc, out, err = run('my key = 1\n', None)
        self.assertEqual(rc, 1, f"expected parse error exit 1, got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_two_pairs_one_line(self):
        rc, out, err = run('a = 1 b = 2\n', None)
        self.assertEqual(rc, 1, f"expected parse error exit 1, got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_bad_escape(self):
        rc, out, err = run('s = "\\q"\n', None)
        self.assertEqual(rc, 1, f"expected parse error exit 1, got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_bad_literal(self):
        rc, out, err = run('x = tru\n', None)
        self.assertEqual(rc, 1, f"expected parse error exit 1, got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

if __name__ == "__main__":
    unittest.main(verbosity=1)
