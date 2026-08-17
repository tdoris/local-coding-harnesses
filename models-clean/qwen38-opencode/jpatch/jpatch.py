#!/usr/bin/env python3
"""Apply a JSON Patch (RFC 6902) to a JSON document.

Usage: python3 jpatch.py DOC.json PATCH.json
"""
import copy
import json
import re
import sys

INDEX_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")


class PatchError(Exception):
    pass


def decode_token(token):
    return token.replace("~1", "/").replace("~0", "~")


def split_pointer(path):
    if not isinstance(path, str):
        raise PatchError("'path' must be a string")
    if path == "":
        return []
    if not path.startswith("/"):
        raise PatchError("malformed JSON Pointer %r: must be empty or start with '/'" % path)
    return [decode_token(t) for t in path[1:].split("/")]


def traverse(cur, token):
    if isinstance(cur, list):
        if not INDEX_RE.match(token):
            raise PatchError("invalid array index %r" % token)
        idx = int(token)
        if idx >= len(cur):
            raise PatchError("array index %d out of range (length %d)" % (idx, len(cur)))
        return cur[idx]
    if isinstance(cur, dict):
        if token not in cur:
            raise PatchError("member %r not found" % token)
        return cur[token]
    raise PatchError("cannot traverse into %s" % type(cur).__name__)


def resolve_parent(doc, tokens):
    cur = doc
    for token in tokens:
        cur = traverse(cur, token)
    return cur


def resolve_target(doc, tokens):
    cur = doc
    for token in tokens:
        cur = traverse(cur, token)
    return cur


def json_equal(a, b):
    if type(a) is bool or type(b) is bool:
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def do_add(doc, path, value):
    tokens = split_pointer(path)
    if not tokens:
        return copy.deepcopy(value)
    parent = resolve_parent(doc, tokens[:-1])
    last = tokens[-1]
    value = copy.deepcopy(value)
    if isinstance(parent, list):
        if last == "-":
            parent.append(value)
            return
        if not INDEX_RE.match(last):
            raise PatchError("invalid array index %r" % last)
        idx = int(last)
        if idx > len(parent):
            raise PatchError("array index %d out of range (length %d)" % (idx, len(parent)))
        parent.insert(idx, value)
    elif isinstance(parent, dict):
        parent[last] = value
    else:
        raise PatchError("cannot add into %s" % type(parent).__name__)


def do_remove(doc, path):
    tokens = split_pointer(path)
    if not tokens:
        raise PatchError("cannot remove the whole document")
    parent = resolve_parent(doc, tokens[:-1])
    last = tokens[-1]
    if isinstance(parent, list):
        if not INDEX_RE.match(last):
            raise PatchError("invalid array index %r" % last)
        idx = int(last)
        if idx >= len(parent):
            raise PatchError("array index %d out of range (length %d)" % (idx, len(parent)))
        del parent[idx]
    elif isinstance(parent, dict):
        if last not in parent:
            raise PatchError("member %r not found" % last)
        del parent[last]
    else:
        raise PatchError("cannot remove from %s" % type(parent).__name__)


def do_replace(doc, path, value):
    tokens = split_pointer(path)
    if not tokens:
        raise PatchError("cannot replace the whole document")
    parent = resolve_parent(doc, tokens[:-1])
    last = tokens[-1]
    if isinstance(parent, list):
        if not INDEX_RE.match(last):
            raise PatchError("invalid array index %r" % last)
        idx = int(last)
        if idx >= len(parent):
            raise PatchError("array index %d out of range (length %d)" % (idx, len(parent)))
        parent[idx] = copy.deepcopy(value)
    elif isinstance(parent, dict):
        if last not in parent:
            raise PatchError("member %r not found" % last)
        parent[last] = copy.deepcopy(value)
    else:
        raise PatchError("cannot replace in %s" % type(parent).__name__)


def do_test(doc, path, value):
    tokens = split_pointer(path)
    actual = resolve_target(doc, tokens)
    if not json_equal(actual, value):
        raise PatchError("test operation failed at %r" % path)


def do_move(doc, path, frm):
    p_tokens = split_pointer(path)
    f_tokens = split_pointer(frm)
    if not f_tokens:
        raise PatchError("cannot move the whole document")
    if len(p_tokens) > len(f_tokens) and p_tokens[: len(f_tokens)] == f_tokens:
        raise PatchError("cannot move a value into its own child")
    value = copy.deepcopy(resolve_target(doc, f_tokens))
    do_remove(doc, frm)
    if not p_tokens:
        return value
    do_add(doc, path, value)
    return doc


def do_copy(doc, path, frm):
    value = resolve_target(doc, split_pointer(frm))
    if not split_pointer(path):
        return copy.deepcopy(value)
    do_add(doc, path, value)
    return doc


def apply_op(doc, opobj, i):
    if not isinstance(opobj, dict):
        raise PatchError("operation %d: not an object" % i)
    opname = opobj.get("op")
    if not isinstance(opname, str):
        raise PatchError("operation %d: missing 'op'" % i)
    if "path" not in opobj or not isinstance(opobj["path"], str):
        raise PatchError("operation %d: missing 'path'" % i)
    path = opobj["path"]
    if opname == "add":
        if "value" not in opobj:
            raise PatchError("operation %d: add requires 'value'" % i)
        new = do_add(doc, path, opobj["value"])
        return new if new is not None else doc
    if opname == "remove":
        do_remove(doc, path)
        return doc
    if opname == "replace":
        if "value" not in opobj:
            raise PatchError("operation %d: replace requires 'value'" % i)
        do_replace(doc, path, opobj["value"])
        return doc
    if opname == "test":
        if "value" not in opobj:
            raise PatchError("operation %d: test requires 'value'" % i)
        do_test(doc, path, opobj["value"])
        return doc
    if opname == "move":
        if "from" not in opobj or not isinstance(opobj["from"], str):
            raise PatchError("operation %d: move requires 'from'" % i)
        return do_move(doc, path, opobj["from"])
    if opname == "copy":
        if "from" not in opobj or not isinstance(opobj["from"], str):
            raise PatchError("operation %d: copy requires 'from'" % i)
        return do_copy(doc, path, opobj["from"])
    raise PatchError("operation %d: unknown op %r" % (i, opname))


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: python3 jpatch.py DOC.json PATCH.json\n")
        return 1
    try:
        with open(argv[1], "r", encoding="utf-8") as f:
            doc = json.load(f)
        with open(argv[2], "r", encoding="utf-8") as f:
            patch = json.load(f)
    except (OSError, ValueError) as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 1
    try:
        if not isinstance(patch, list):
            raise PatchError("patch must be a JSON array of operations")
        for i, opobj in enumerate(patch):
            doc = apply_op(doc, opobj, i)
    except PatchError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 1
    sys.stdout.write(json.dumps(doc) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
