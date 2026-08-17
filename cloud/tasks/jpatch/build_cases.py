#!/usr/bin/env python3
"""Builds cases.json for jpatch using the jsonpatch library as oracle.
Run with: uv run --with jsonpatch python3 build_cases.py"""
import json, copy, jsonpatch

# (name, doc, patch, visible) — expected computed below; "error" if the oracle raises
RAW = [
 # RFC 6902 Appendix A
 ("A1_add_member", {"foo": "bar"}, [{"op": "add", "path": "/baz", "value": "qux"}], True),
 ("A2_add_array_element", {"foo": ["bar", "baz"]}, [{"op": "add", "path": "/foo/1", "value": "qux"}], True),
 ("A3_remove_member", {"baz": "qux", "foo": "bar"}, [{"op": "remove", "path": "/baz"}], True),
 ("A4_remove_array_element", {"foo": ["bar", "qux", "baz"]}, [{"op": "remove", "path": "/foo/1"}], True),
 ("A5_replace", {"baz": "qux", "foo": "bar"}, [{"op": "replace", "path": "/baz", "value": "boo"}], True),
 ("A6_move", {"foo": {"bar": "baz", "waldo": "fred"}, "qux": {"corge": "grault"}}, [{"op": "move", "from": "/foo/waldo", "path": "/qux/thud"}], True),
 ("A7_move_array_element", {"foo": ["all", "grass", "cows", "eat"]}, [{"op": "move", "from": "/foo/1", "path": "/foo/3"}], True),
 ("A8_test_success", {"baz": "qux", "foo": ["a", 2, "c"]}, [{"op": "test", "path": "/baz", "value": "qux"}, {"op": "test", "path": "/foo/1", "value": 2}], True),
 ("A9_test_error", {"baz": "qux"}, [{"op": "test", "path": "/baz", "value": "bar"}], True),
 ("A10_add_nested_object", {"foo": "bar"}, [{"op": "add", "path": "/child", "value": {"grandchild": {}}}], True),
 ("A11_ignore_unrecognized", {"foo": "bar"}, [{"op": "add", "path": "/baz", "value": "qux", "xyz": 123}], True),
 ("A12_add_nonexistent_target", {"foo": "bar"}, [{"op": "add", "path": "/baz/bat", "value": "qux"}], True),
 ("A14_tilde_escape", {"/": 9, "~1": 10}, [{"op": "test", "path": "/~01", "value": 10}], True),
 ("A15_string_vs_number", {"/": 9, "~1": 10}, [{"op": "test", "path": "/~01", "value": "10"}], True),
 ("A16_add_array_value", {"foo": ["bar"]}, [{"op": "add", "path": "/foo/-", "value": ["abc", "def"]}], True),
 # add
 ("add_dash_append", {"a": [1, 2]}, [{"op": "add", "path": "/a/-", "value": 3}], True),
 ("add_index_eq_len", {"a": [1, 2]}, [{"op": "add", "path": "/a/2", "value": 3}], True),
 ("add_index_gt_len", {"a": [1, 2]}, [{"op": "add", "path": "/a/5", "value": 3}], True),
 ("add_index_leading_zero", {"a": [1, 2]}, [{"op": "add", "path": "/a/01", "value": 3}], False),
 ("add_index_nonnumeric", {"a": [1, 2]}, [{"op": "add", "path": "/a/x", "value": 3}], False),
 ("add_replaces_existing_member", {"a": 1}, [{"op": "add", "path": "/a", "value": 2}], True),
 ("add_root", {"a": 1}, [{"op": "add", "path": "", "value": {"b": 2}}], False),
 ("add_null_and_false", {}, [{"op": "add", "path": "/n", "value": None}, {"op": "add", "path": "/f", "value": False}], True),
 ("add_slash_key", {}, [{"op": "add", "path": "/a~1b", "value": 1}], True),
 ("add_tilde_key", {}, [{"op": "add", "path": "/m~0n", "value": 1}], False),
 ("add_empty_key", {}, [{"op": "add", "path": "/", "value": 1}], False),
 ("add_missing_value_member", {"a": 1}, [{"op": "add", "path": "/b"}], True),
 ("add_at_negative_index", {"a": [1]}, [{"op": "add", "path": "/a/-1", "value": 0}], False),
 ("add_into_nested_array_object", {"a": [{"b": []}]}, [{"op": "add", "path": "/a/0/b/0", "value": "x"}], False),
 # remove
 ("remove_dash", {"a": [1, 2]}, [{"op": "remove", "path": "/a/-"}], False),
 ("remove_missing_member", {"a": 1}, [{"op": "remove", "path": "/b"}], True),
 ("remove_out_of_range", {"a": [1]}, [{"op": "remove", "path": "/a/1"}], False),
 ("remove_nested", {"a": {"b": {"c": 1, "d": 2}}}, [{"op": "remove", "path": "/a/b/c"}], True),
 ("remove_last_element", {"a": [1, 2, 3]}, [{"op": "remove", "path": "/a/2"}], False),
 # replace
 ("replace_missing", {"a": 1}, [{"op": "replace", "path": "/b", "value": 2}], True),
 ("replace_array_element", {"a": [1, 2, 3]}, [{"op": "replace", "path": "/a/1", "value": "two"}], True),
 ("replace_root", {"a": 1}, [{"op": "replace", "path": "", "value": [1, 2]}], False),
 ("replace_out_of_range", {"a": [1]}, [{"op": "replace", "path": "/a/3", "value": 0}], False),
 # move / copy
 ("move_into_own_child", {"a": {"b": 1}}, [{"op": "move", "from": "/a", "path": "/a/b/c"}], True),
 ("move_missing_from", {"a": 1}, [{"op": "move", "from": "/x", "path": "/y"}], True),
 ("move_missing_from_member", {"a": 1}, [{"op": "move", "path": "/y"}], False),
 ("move_array_to_object", {"a": [1, 2], "o": {}}, [{"op": "move", "from": "/a/0", "path": "/o/k"}], False),
 ("move_same_location", {"a": {"b": 1}}, [{"op": "move", "from": "/a", "path": "/a"}], False),
 ("copy_member", {"a": {"b": [1, 2]}}, [{"op": "copy", "from": "/a/b", "path": "/c"}], True),
 ("copy_array_element_append", {"a": [1, 2]}, [{"op": "copy", "from": "/a/0", "path": "/a/-"}], True),
 ("copy_missing_from", {"a": 1}, [{"op": "copy", "from": "/z", "path": "/c"}], False),
 ("copy_then_modify_independent", {"a": {"b": 1}}, [{"op": "copy", "from": "/a", "path": "/c"}, {"op": "replace", "path": "/c/b", "value": 2}], False),
 # test
 ("test_object_key_order", {"a": {"x": 1, "y": 2}}, [{"op": "test", "path": "/a", "value": {"y": 2, "x": 1}}], True),
 ("test_int_vs_float_equal", {"a": 1}, [{"op": "test", "path": "/a", "value": 1.0}], False),
 ("test_null_vs_missing", {"a": {}}, [{"op": "test", "path": "/a/b", "value": None}], False),
 ("test_array_element", {"a": [1, [2, 3]]}, [{"op": "test", "path": "/a/1", "value": [2, 3]}], True),
 ("test_array_order_matters", {"a": [1, 2]}, [{"op": "test", "path": "/a", "value": [2, 1]}], False),
 ("test_root", {"a": 1}, [{"op": "test", "path": "", "value": {"a": 1}}], False),
 ("test_nested_fail", {"a": {"b": {"c": 1}}}, [{"op": "test", "path": "/a/b", "value": {"c": 2}}], False),
 # structural
 ("empty_patch", {"a": 1}, [], True),
 ("unknown_op", {"a": 1}, [{"op": "frobnicate", "path": "/a"}], True),
 ("missing_op", {"a": 1}, [{"path": "/a", "value": 1}], False),
 ("missing_path", {"a": 1}, [{"op": "add", "value": 1}], False),
 ("path_without_leading_slash", {"a": 1}, [{"op": "replace", "path": "a", "value": 2}], False),
 ("patch_not_array", {"a": 1}, {"op": "add", "path": "/b", "value": 1}, True),
 ("op_not_object", {"a": 1}, ["add"], False),
 ("atomic_failure_no_partial", {"a": 1}, [{"op": "add", "path": "/b", "value": 2}, {"op": "remove", "path": "/zzz"}], True),
 ("sequence_many_ops", {"users": []}, [
     {"op": "add", "path": "/users/-", "value": {"name": "ann", "tags": []}},
     {"op": "add", "path": "/users/0/tags/-", "value": "x"},
     {"op": "add", "path": "/users/-", "value": {"name": "bob"}},
     {"op": "move", "from": "/users/0/tags", "path": "/users/1/tags"},
     {"op": "copy", "from": "/users/1", "path": "/users/0"},
     {"op": "test", "path": "/users/0/name", "value": "bob"},
     {"op": "replace", "path": "/users/2/name", "value": "cid"},
     {"op": "remove", "path": "/users/0/tags/0"}], True),
 ("numeric_string_object_key", {"foo": {"0": "zero", "1": "one"}}, [{"op": "remove", "path": "/foo/0"}], False),
 ("pointer_into_scalar", {"a": 5}, [{"op": "add", "path": "/a/b", "value": 1}], False),
 ("deep_add_creates_nothing_implicitly", {"a": {}}, [{"op": "add", "path": "/a/b/c", "value": 1}], False),
 ("preserve_key_order_and_append", {"z": 1, "a": 2}, [{"op": "add", "path": "/m", "value": 3}], False),
]

def build():
    cases = []
    for name, doc, patch, visible in RAW:
        try:
            res = jsonpatch.apply_patch(copy.deepcopy(doc), copy.deepcopy(patch), in_place=False)
            exp = res
        except Exception as e:
            exp = "error"
        cases.append({"name": name, "doc": doc, "patch": patch, "expected": exp, "visible": visible})
    json.dump(cases, open("cases.json", "w"), indent=1)
    print(len(cases), "cases;", sum(1 for c in cases if c["visible"]), "visible;", sum(1 for c in cases if c["expected"] == "error"), "errors")
    for c in cases: print(f'{c["name"]:36} {"ERROR" if c["expected"]=="error" else json.dumps(c["expected"])[:70]}')

if __name__ == "__main__": build()
