#!/usr/bin/env python3
"""Tests for jpatch.py — run: python3 test_jpatch.py  (do not modify)"""
import json, os, subprocess, sys, tempfile, unittest

PROG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jpatch.py")

def run(doc, patch):
    with tempfile.TemporaryDirectory() as td:
        dp, pp = os.path.join(td, "doc.json"), os.path.join(td, "patch.json")
        json.dump(doc, open(dp, "w")); json.dump(patch, open(pp, "w"))
        r = subprocess.run([sys.executable, PROG, dp, pp], capture_output=True, text=True, timeout=20)
    return r.returncode, r.stdout, r.stderr

def strict_eq(a, b):
    if type(a) is bool or type(b) is bool: return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)): return a == b
    if isinstance(a, dict) and isinstance(b, dict): return list(a) == list(b) and all(strict_eq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list): return len(a) == len(b) and all(strict_eq(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b

class TestJpatch(unittest.TestCase):
    def test_A1_add_member(self):
        rc, out, err = run(json.loads("{\"foo\": \"bar\"}"), json.loads("[{\"op\": \"add\", \"path\": \"/baz\", \"value\": \"qux\"}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"foo\": \"bar\", \"baz\": \"qux\"}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_A2_add_array_element(self):
        rc, out, err = run(json.loads("{\"foo\": [\"bar\", \"baz\"]}"), json.loads("[{\"op\": \"add\", \"path\": \"/foo/1\", \"value\": \"qux\"}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"foo\": [\"bar\", \"qux\", \"baz\"]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_A3_remove_member(self):
        rc, out, err = run(json.loads("{\"baz\": \"qux\", \"foo\": \"bar\"}"), json.loads("[{\"op\": \"remove\", \"path\": \"/baz\"}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"foo\": \"bar\"}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_A4_remove_array_element(self):
        rc, out, err = run(json.loads("{\"foo\": [\"bar\", \"qux\", \"baz\"]}"), json.loads("[{\"op\": \"remove\", \"path\": \"/foo/1\"}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"foo\": [\"bar\", \"baz\"]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_A5_replace(self):
        rc, out, err = run(json.loads("{\"baz\": \"qux\", \"foo\": \"bar\"}"), json.loads("[{\"op\": \"replace\", \"path\": \"/baz\", \"value\": \"boo\"}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"baz\": \"boo\", \"foo\": \"bar\"}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_A6_move(self):
        rc, out, err = run(json.loads("{\"foo\": {\"bar\": \"baz\", \"waldo\": \"fred\"}, \"qux\": {\"corge\": \"grault\"}}"), json.loads("[{\"op\": \"move\", \"from\": \"/foo/waldo\", \"path\": \"/qux/thud\"}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"foo\": {\"bar\": \"baz\"}, \"qux\": {\"corge\": \"grault\", \"thud\": \"fred\"}}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_A7_move_array_element(self):
        rc, out, err = run(json.loads("{\"foo\": [\"all\", \"grass\", \"cows\", \"eat\"]}"), json.loads("[{\"op\": \"move\", \"from\": \"/foo/1\", \"path\": \"/foo/3\"}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"foo\": [\"all\", \"cows\", \"eat\", \"grass\"]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_A8_test_success(self):
        rc, out, err = run(json.loads("{\"baz\": \"qux\", \"foo\": [\"a\", 2, \"c\"]}"), json.loads("[{\"op\": \"test\", \"path\": \"/baz\", \"value\": \"qux\"}, {\"op\": \"test\", \"path\": \"/foo/1\", \"value\": 2}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"baz\": \"qux\", \"foo\": [\"a\", 2, \"c\"]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_A9_test_error(self):
        rc, out, err = run(json.loads("{\"baz\": \"qux\"}"), json.loads("[{\"op\": \"test\", \"path\": \"/baz\", \"value\": \"bar\"}]"))
        self.assertEqual(rc, 1, f"expected exit 1 (error), got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_A10_add_nested_object(self):
        rc, out, err = run(json.loads("{\"foo\": \"bar\"}"), json.loads("[{\"op\": \"add\", \"path\": \"/child\", \"value\": {\"grandchild\": {}}}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"foo\": \"bar\", \"child\": {\"grandchild\": {}}}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_A11_ignore_unrecognized(self):
        rc, out, err = run(json.loads("{\"foo\": \"bar\"}"), json.loads("[{\"op\": \"add\", \"path\": \"/baz\", \"value\": \"qux\", \"xyz\": 123}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"foo\": \"bar\", \"baz\": \"qux\"}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_A12_add_nonexistent_target(self):
        rc, out, err = run(json.loads("{\"foo\": \"bar\"}"), json.loads("[{\"op\": \"add\", \"path\": \"/baz/bat\", \"value\": \"qux\"}]"))
        self.assertEqual(rc, 1, f"expected exit 1 (error), got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_A14_tilde_escape(self):
        rc, out, err = run(json.loads("{\"/\": 9, \"~1\": 10}"), json.loads("[{\"op\": \"test\", \"path\": \"/~01\", \"value\": 10}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"/\": 9, \"~1\": 10}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_A15_string_vs_number(self):
        rc, out, err = run(json.loads("{\"/\": 9, \"~1\": 10}"), json.loads("[{\"op\": \"test\", \"path\": \"/~01\", \"value\": \"10\"}]"))
        self.assertEqual(rc, 1, f"expected exit 1 (error), got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_A16_add_array_value(self):
        rc, out, err = run(json.loads("{\"foo\": [\"bar\"]}"), json.loads("[{\"op\": \"add\", \"path\": \"/foo/-\", \"value\": [\"abc\", \"def\"]}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"foo\": [\"bar\", [\"abc\", \"def\"]]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_add_dash_append(self):
        rc, out, err = run(json.loads("{\"a\": [1, 2]}"), json.loads("[{\"op\": \"add\", \"path\": \"/a/-\", \"value\": 3}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": [1, 2, 3]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_add_index_eq_len(self):
        rc, out, err = run(json.loads("{\"a\": [1, 2]}"), json.loads("[{\"op\": \"add\", \"path\": \"/a/2\", \"value\": 3}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": [1, 2, 3]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_add_index_gt_len(self):
        rc, out, err = run(json.loads("{\"a\": [1, 2]}"), json.loads("[{\"op\": \"add\", \"path\": \"/a/5\", \"value\": 3}]"))
        self.assertEqual(rc, 1, f"expected exit 1 (error), got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_add_replaces_existing_member(self):
        rc, out, err = run(json.loads("{\"a\": 1}"), json.loads("[{\"op\": \"add\", \"path\": \"/a\", \"value\": 2}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": 2}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_add_null_and_false(self):
        rc, out, err = run(json.loads("{}"), json.loads("[{\"op\": \"add\", \"path\": \"/n\", \"value\": null}, {\"op\": \"add\", \"path\": \"/f\", \"value\": false}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"n\": null, \"f\": false}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_add_slash_key(self):
        rc, out, err = run(json.loads("{}"), json.loads("[{\"op\": \"add\", \"path\": \"/a~1b\", \"value\": 1}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a/b\": 1}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_add_missing_value_member(self):
        rc, out, err = run(json.loads("{\"a\": 1}"), json.loads("[{\"op\": \"add\", \"path\": \"/b\"}]"))
        self.assertEqual(rc, 1, f"expected exit 1 (error), got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_remove_missing_member(self):
        rc, out, err = run(json.loads("{\"a\": 1}"), json.loads("[{\"op\": \"remove\", \"path\": \"/b\"}]"))
        self.assertEqual(rc, 1, f"expected exit 1 (error), got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_remove_nested(self):
        rc, out, err = run(json.loads("{\"a\": {\"b\": {\"c\": 1, \"d\": 2}}}"), json.loads("[{\"op\": \"remove\", \"path\": \"/a/b/c\"}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": {\"b\": {\"d\": 2}}}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_replace_missing(self):
        rc, out, err = run(json.loads("{\"a\": 1}"), json.loads("[{\"op\": \"replace\", \"path\": \"/b\", \"value\": 2}]"))
        self.assertEqual(rc, 1, f"expected exit 1 (error), got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_replace_array_element(self):
        rc, out, err = run(json.loads("{\"a\": [1, 2, 3]}"), json.loads("[{\"op\": \"replace\", \"path\": \"/a/1\", \"value\": \"two\"}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": [1, \"two\", 3]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_move_into_own_child(self):
        rc, out, err = run(json.loads("{\"a\": {\"b\": 1}}"), json.loads("[{\"op\": \"move\", \"from\": \"/a\", \"path\": \"/a/b/c\"}]"))
        self.assertEqual(rc, 1, f"expected exit 1 (error), got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_move_missing_from(self):
        rc, out, err = run(json.loads("{\"a\": 1}"), json.loads("[{\"op\": \"move\", \"from\": \"/x\", \"path\": \"/y\"}]"))
        self.assertEqual(rc, 1, f"expected exit 1 (error), got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_copy_member(self):
        rc, out, err = run(json.loads("{\"a\": {\"b\": [1, 2]}}"), json.loads("[{\"op\": \"copy\", \"from\": \"/a/b\", \"path\": \"/c\"}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": {\"b\": [1, 2]}, \"c\": [1, 2]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_copy_array_element_append(self):
        rc, out, err = run(json.loads("{\"a\": [1, 2]}"), json.loads("[{\"op\": \"copy\", \"from\": \"/a/0\", \"path\": \"/a/-\"}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": [1, 2, 1]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_test_object_key_order(self):
        rc, out, err = run(json.loads("{\"a\": {\"x\": 1, \"y\": 2}}"), json.loads("[{\"op\": \"test\", \"path\": \"/a\", \"value\": {\"y\": 2, \"x\": 1}}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": {\"x\": 1, \"y\": 2}}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_test_array_element(self):
        rc, out, err = run(json.loads("{\"a\": [1, [2, 3]]}"), json.loads("[{\"op\": \"test\", \"path\": \"/a/1\", \"value\": [2, 3]}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": [1, [2, 3]]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_empty_patch(self):
        rc, out, err = run(json.loads("{\"a\": 1}"), json.loads("[]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"a\": 1}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

    def test_unknown_op(self):
        rc, out, err = run(json.loads("{\"a\": 1}"), json.loads("[{\"op\": \"frobnicate\", \"path\": \"/a\"}]"))
        self.assertEqual(rc, 1, f"expected exit 1 (error), got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_patch_not_array(self):
        rc, out, err = run(json.loads("{\"a\": 1}"), json.loads("{\"op\": \"add\", \"path\": \"/b\", \"value\": 1}"))
        self.assertEqual(rc, 1, f"expected exit 1 (error), got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_atomic_failure_no_partial(self):
        rc, out, err = run(json.loads("{\"a\": 1}"), json.loads("[{\"op\": \"add\", \"path\": \"/b\", \"value\": 2}, {\"op\": \"remove\", \"path\": \"/zzz\"}]"))
        self.assertEqual(rc, 1, f"expected exit 1 (error), got {rc}; stdout={out!r}")
        self.assertEqual(out.strip(), "")

    def test_sequence_many_ops(self):
        rc, out, err = run(json.loads("{\"users\": []}"), json.loads("[{\"op\": \"add\", \"path\": \"/users/-\", \"value\": {\"name\": \"ann\", \"tags\": []}}, {\"op\": \"add\", \"path\": \"/users/0/tags/-\", \"value\": \"x\"}, {\"op\": \"add\", \"path\": \"/users/-\", \"value\": {\"name\": \"bob\"}}, {\"op\": \"move\", \"from\": \"/users/0/tags\", \"path\": \"/users/1/tags\"}, {\"op\": \"copy\", \"from\": \"/users/1\", \"path\": \"/users/0\"}, {\"op\": \"test\", \"path\": \"/users/0/name\", \"value\": \"bob\"}, {\"op\": \"replace\", \"path\": \"/users/2/name\", \"value\": \"cid\"}, {\"op\": \"remove\", \"path\": \"/users/0/tags/0\"}]"))
        self.assertEqual(rc, 0, err)
        expected = json.loads("{\"users\": [{\"name\": \"bob\", \"tags\": []}, {\"name\": \"ann\"}, {\"name\": \"cid\", \"tags\": [\"x\"]}]}")
        self.assertTrue(strict_eq(json.loads(out), expected), f"got {out.strip()} expected {json.dumps(expected)}")

if __name__ == "__main__":
    unittest.main(verbosity=1)
