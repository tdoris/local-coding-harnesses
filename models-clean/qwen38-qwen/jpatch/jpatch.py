#!/usr/bin/env python3
"""Apply a JSON Patch (RFC 6902) to a JSON document.

Usage: python3 jpatch.py DOC.json PATCH.json

Reads the document and the patch (a JSON array of operation objects),
applies the operations in order, and prints the resulting document as JSON
on stdout. On any error, prints a message to stderr, nothing on stdout,
and exits 1. Application is atomic: on any error nothing is printed.
"""
import copy
import json
import re
import sys

VALID_OPS = {"add", "remove", "replace", "test", "move", "copy"}
# Canonical decimal index: no sign, no leading zeros ("0" itself is allowed).
CANONICAL_INDEX = re.compile(r"0|[1-9][0-9]*")


class PatchError(Exception):
    """Raised for any patch/pointer/operation error."""


def die(message):
    raise PatchError(message)


def unescape_token(token):
    # RFC 6901: decode ~1 -> "/" before ~0 -> "~" (order matters).
    return token.replace("~1", "/").replace("~0", "~")


def parse_pointer(pointer):
    """Return the list of decoded reference tokens for a JSON Pointer."""
    if not isinstance(pointer, str):
        die("JSON Pointer must be a string")
    if pointer == "":
        return []  # the whole document
    if not pointer.startswith("/"):
        die("Malformed JSON Pointer: must be empty or start with '/'")
    return [unescape_token(part) for part in pointer.split("/")[1:]]


def resolve_existing(doc, tokens):
    """Return the value at `tokens`, requiring every step to resolve to an
    existing location. Raises PatchError otherwise."""
    current = doc
    for token in tokens:
        if isinstance(current, dict):
            if token not in current:
                die("JSON Pointer does not resolve to an existing location")
            current = current[token]
        elif isinstance(current, list):
            if token == "-":
                die("Array index '-' is not a valid existing location")
            if not CANONICAL_INDEX.fullmatch(token):
                die("Array index is not a canonical decimal integer")
            index = int(token)
            if index >= len(current):
                die("Array index is out of range")
            current = current[index]
        else:
            die("JSON Pointer does not resolve to an existing location")
    return current


def json_equal(a, b):
    """RFC 6902 JSON equality: objects compare irrespective of key order,
    arrays in order, numbers by value (1 == 1.0), while strings, booleans,
    and null keep their exact type."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return False
        return all(json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(json_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def do_add(doc, tokens, value):
    if not tokens:
        return value  # add to the empty pointer replaces the document
    parent = resolve_existing(doc, tokens[:-1])
    last = tokens[-1]
    if isinstance(parent, dict):
        # New member appended at the end; existing member replaced in place.
        parent[last] = value
        return doc
    if isinstance(parent, list):
        if last == "-":
            index = len(parent)  # append
        else:
            if not CANONICAL_INDEX.fullmatch(last):
                die("Array index is not a canonical decimal integer")
            index = int(last)
            if index > len(parent):
                die("Array index is out of range")
        parent.insert(index, value)
        return doc
    die("Cannot add to a non-container value")


def do_remove(doc, tokens):
    if not tokens:
        die("Cannot remove the whole document")
    parent = resolve_existing(doc, tokens[:-1])
    last = tokens[-1]
    if isinstance(parent, dict):
        if last not in parent:
            die("Cannot remove a member that does not exist")
        del parent[last]
        return doc
    if isinstance(parent, list):
        if last == "-":
            die("Array index '-' is not a valid existing location")
        if not CANONICAL_INDEX.fullmatch(last):
            die("Array index is not a canonical decimal integer")
        index = int(last)
        if index >= len(parent):
            die("Array index is out of range")
        del parent[index]
        return doc
    die("Cannot remove from a non-container value")


def do_replace(doc, tokens, value):
    if not tokens:
        return value
    parent = resolve_existing(doc, tokens[:-1])
    last = tokens[-1]
    if isinstance(parent, dict):
        if last not in parent:
            die("Cannot replace a member that does not exist")
        parent[last] = value
        return doc
    if isinstance(parent, list):
        if last == "-":
            die("Array index '-' is not a valid existing location")
        if not CANONICAL_INDEX.fullmatch(last):
            die("Array index is not a canonical decimal integer")
        index = int(last)
        if index >= len(parent):
            die("Array index is out of range")
        parent[index] = value
        return doc
    die("Cannot replace on a non-container value")


def do_test(doc, tokens, value):
    target = resolve_existing(doc, tokens)
    if not json_equal(target, value):
        die("test failed: values are not equal")
    return doc


def is_proper_prefix(short, long):
    """True if `short` is a strict prefix of `long` (a proper parent)."""
    if len(short) >= len(long):
        return False
    return long[:len(short)] == short


def do_move(doc, from_tokens, path_tokens):
    if is_proper_prefix(from_tokens, path_tokens):
        die("Cannot move a location into one of its own children")
    value = resolve_existing(doc, from_tokens)
    doc = do_remove(doc, from_tokens)
    return do_add(doc, path_tokens, value)


def do_copy(doc, from_tokens, path_tokens):
    value = copy.deepcopy(resolve_existing(doc, from_tokens))
    return do_add(doc, path_tokens, value)


def apply_patch(doc, ops):
    if not isinstance(ops, list):
        die("Patch must be an array of operations")
    for position, op in enumerate(ops):
        if not isinstance(op, dict):
            die(f"Operation {position} is not an object")
        if "op" not in op:
            die(f"Operation {position} is missing 'op'")
        if "path" not in op:
            die(f"Operation {position} is missing 'path'")
        op_type = op["op"]
        if op_type not in VALID_OPS:
            die(f"Unknown operation type: {op_type!r}")
        path_tokens = parse_pointer(op["path"])
        if op_type == "add":
            if "value" not in op:
                die(f"Operation {position}: 'add' requires 'value'")
            doc = do_add(doc, path_tokens, op["value"])
        elif op_type == "remove":
            doc = do_remove(doc, path_tokens)
        elif op_type == "replace":
            if "value" not in op:
                die(f"Operation {position}: 'replace' requires 'value'")
            doc = do_replace(doc, path_tokens, op["value"])
        elif op_type == "test":
            if "value" not in op:
                die(f"Operation {position}: 'test' requires 'value'")
            doc = do_test(doc, path_tokens, op["value"])
        elif op_type in ("move", "copy"):
            if "from" not in op:
                die(f"Operation {position}: '{op_type}' requires 'from'")
            from_tokens = parse_pointer(op["from"])
            if op_type == "move":
                doc = do_move(doc, from_tokens, path_tokens)
            else:
                doc = do_copy(doc, from_tokens, path_tokens)
    return doc


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 jpatch.py DOC.json PATCH.json", file=sys.stderr)
        sys.exit(1)
    doc_path, patch_path = sys.argv[1], sys.argv[2]
    try:
        with open(doc_path, "r", encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError) as exc:
        print(f"error: failed to load document: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(patch_path, "r", encoding="utf-8") as handle:
            ops = json.load(handle)
    except (OSError, ValueError) as exc:
        print(f"error: failed to load patch: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        result = apply_patch(doc, ops)
    except PatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
