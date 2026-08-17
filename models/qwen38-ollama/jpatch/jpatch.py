#!/usr/bin/env python3
"""Apply a JSON Patch (RFC 6902) to a JSON document.

Usage: python3 jpatch.py DOC.json PATCH.json
"""
import copy
import json
import sys


class PatchError(Exception):
    pass


def decode_token(token):
    return token.replace("~1", "/").replace("~0", "~")


def parse_pointer(pointer):
    if not isinstance(pointer, str):
        raise PatchError("JSON pointer must be a string")
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise PatchError(f"malformed JSON pointer: {pointer!r}")
    return [decode_token(t) for t in pointer[1:].split("/")]


def is_canonical_index(token):
    return token != "" and token.isdigit() and (token == "0" or not token.startswith("0"))


def locate(doc, tokens, must_exist=True):
    """Walk to parent container and last token.
    Returns (parent, last_token). Raises PatchError if not resolvable.
    """
    cur = doc
    for i, tok in enumerate(tokens[:-1]):
        if isinstance(cur, list):
            if not is_canonical_index(tok) or int(tok) >= len(cur):
                raise PatchError(f"JSON pointer does not resolve: {tokens[i]!r} (array index)")
            cur = cur[int(tok)]
        elif isinstance(cur, dict):
            if tok not in cur:
                raise PatchError(f"JSON pointer does not resolve: {tok!r} (object key)")
            cur = cur[tok]
        else:
            raise PatchError("JSON pointer does not resolve: cannot descend into a scalar")
    if not tokens:
        return None, None
    last = tokens[-1]
    if isinstance(cur, list):
        if last != "-" and not is_canonical_index(last):
            raise PatchError(f"malformed array index: {last!r}")
        if last != "-" and must_exist and int(last) >= len(cur):
            raise PatchError(f"array index out of range: {last}")
    elif isinstance(cur, dict):
        if must_exist and last not in cur:
            raise PatchError(f"missing object member: {last!r}")
    else:
        raise PatchError("JSON pointer does not resolve: cannot target a scalar")
    return cur, last


def get_value(doc, pointer):
    tokens = parse_pointer(pointer)
    if not tokens:
        return doc
    parent, last = locate(doc, tokens, must_exist=True)
    if isinstance(parent, list):
        return parent[int(last)]
    return parent[last]


def add_value(doc, pointer, value):
    tokens = parse_pointer(pointer)
    if not tokens:
        raise PatchError("cannot add to the whole document")
    parent, last = locate(doc, tokens, must_exist=False)
    if isinstance(parent, list):
        if last == "-":
            parent.append(value)
        elif int(last) > len(parent):
            raise PatchError(f"array index out of range: {last}")
        else:
            parent.insert(int(last), value)
    else:
        parent[last] = value


def json_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def check_move(from_ptr, to_ptr):
    """Reject moving a location into one of its own children."""
    if not to_ptr.startswith(from_ptr):
        return
    if len(to_ptr) < len(from_ptr):
        return
    rest = to_ptr[len(from_ptr):]
    if not rest.startswith("/"):
        return
    # to is strictly inside from
    raise PatchError("cannot move a value into one of its own children")


def apply_op(doc, op):
    if not isinstance(op, dict):
        raise PatchError("patch operation must be an object")
    if "op" not in op:
        raise PatchError("patch operation is missing 'op'")
    if "path" not in op:
        raise PatchError("patch operation is missing 'path'")
    opname = op["op"]
    path = op["path"]
    if opname not in ("add", "remove", "replace", "move", "copy", "test"):
        raise PatchError(f"unknown op: {opname!r}")

    if opname in ("add", "replace", "test") and "value" not in op:
        raise PatchError(f"operation {opname!r} is missing 'value'")
    if opname in ("move", "copy") and "from" not in op:
        raise PatchError(f"operation {opname!r} is missing 'from'")

    if opname == "add":
        add_value(doc, path, copy.deepcopy(op["value"]))
    elif opname == "remove":
        tokens = parse_pointer(path)
        if not tokens:
            raise PatchError("cannot remove the whole document")
        parent, last = locate(doc, tokens, must_exist=True)
        if isinstance(parent, list):
            del parent[int(last)]
        else:
            del parent[last]
    elif opname == "replace":
        tokens = parse_pointer(path)
        if not tokens:
            raise PatchError("cannot replace the whole document")
        parent, last = locate(doc, tokens, must_exist=True)
        if isinstance(parent, list):
            parent[int(last)] = copy.deepcopy(op["value"])
        else:
            parent[last] = copy.deepcopy(op["value"])
    elif opname == "move":
        frm = op["from"]
        check_move(frm, path)
        value = get_value(doc, frm)
        tokens = parse_pointer(frm)
        if not tokens:
            raise PatchError("cannot move the whole document")
        parent, last = locate(doc, tokens, must_exist=True)
        moved = parent[int(last)] if isinstance(parent, list) else parent[last]
        if isinstance(parent, list):
            del parent[int(last)]
        else:
            del parent[last]
        add_value(doc, path, moved)
    elif opname == "copy":
        add_value(doc, path, copy.deepcopy(get_value(doc, op["from"])))
    elif opname == "test":
        if not json_equal(get_value(doc, path), op["value"]):
            raise PatchError("test operation failed: values are not equal")


def main():
    if len(sys.argv) != 3:
        print("usage: jpatch.py DOC.json PATCH.json", file=sys.stderr)
        return 1
    try:
        with open(sys.argv[1]) as f:
            doc = json.load(f)
    except Exception as e:
        print(f"error reading document: {e}", file=sys.stderr)
        return 1
    try:
        with open(sys.argv[2]) as f:
            patch = json.load(f)
    except Exception as e:
        print(f"error reading patch: {e}", file=sys.stderr)
        return 1
    try:
        if not isinstance(patch, list):
            raise PatchError("patch must be a JSON array of operations")
        for op in patch:
            apply_op(doc, op)
    except PatchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    json.dump(doc, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
