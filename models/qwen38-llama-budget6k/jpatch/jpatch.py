#!/usr/bin/env python3
"""Apply a JSON Patch (RFC 6902) to a JSON document.

Usage: python3 jpatch.py DOC.json PATCH.json

Reads the document and the patch (a JSON array of operation objects),
applies the operations in order, and prints the resulting document as
JSON on stdout.  On any error, prints a message to stderr and exits 1
without printing anything on stdout (application is atomic).
"""
import copy
import json
import re
import sys

_INDEX_RE = re.compile(r"^(0|[1-9][0-9]*)$")


class PatchError(Exception):
    pass


def fail(message):
    print("jpatch: %s" % message, file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- pointer --

def decode_token(token):
    # RFC 6901: decode ~1 to / first, then ~0 to ~
    return token.replace("~1", "/").replace("~0", "~")


def parse_index(token, pointer):
    if _INDEX_RE.match(token):
        return int(token)
    raise PatchError('path %r: %r is not a valid array index' % (pointer, token))


def locate(doc, pointer):
    """Resolve a JSON Pointer.

    Returns (parent, last_token); for the empty pointer (whole document)
    parent is None and last_token is None.  The final token is *not*
    checked for existence -- the caller decides what must exist.
    """
    if pointer == "":
        return None, None
    if not pointer.startswith("/"):
        raise PatchError(
            'malformed JSON Pointer %r: must be "" or start with "/"' % pointer)
    tokens = [decode_token(t) for t in pointer[1:].split("/")]
    cur = doc
    for t in tokens[:-1]:
        if isinstance(cur, dict):
            if t not in cur:
                raise PatchError(
                    'path %r does not resolve: key %r not found' % (pointer, t))
            cur = cur[t]
        elif isinstance(cur, list):
            i = parse_index(t, pointer)
            if i >= len(cur):
                raise PatchError(
                    'path %r does not resolve: index %r out of range' % (pointer, t))
            cur = cur[i]
        else:
            raise PatchError(
                'path %r does not resolve: cannot index into %s'
                % (pointer, type(cur).__name__))
    return cur, tokens[-1]


def target_exists(parent, last, pointer):
    if parent is None:
        return False
    if isinstance(parent, dict):
        return last in parent
    if isinstance(parent, list):
        return bool(_INDEX_RE.match(last)) and int(last) < len(parent)
    return False


def get_target(parent, last, pointer):
    if isinstance(parent, dict):
        return parent[last]
    if isinstance(parent, list):
        return parent[int(last)]
    raise PatchError('path %r does not resolve' % pointer)


def set_target(parent, last, value, pointer):
    if isinstance(parent, dict):
        parent[last] = value
        return
    if isinstance(parent, list):
        parent[int(last)] = value
        return
    raise PatchError(
        'path %r: parent is a %s, not an object or array'
        % (pointer, type(parent).__name__))


def remove_target(parent, last, pointer):
    if isinstance(parent, dict):
        del parent[last]
        return
    if isinstance(parent, list):
        del parent[int(last)]
        return
    raise PatchError(
        'path %r: parent is a %s, not an object or array'
        % (pointer, type(parent).__name__))


def get_value(doc, pointer):
    """Value at an existing target location (root allowed)."""
    parent, last = locate(doc, pointer)
    if parent is None:
        return doc
    if not target_exists(parent, last, pointer):
        raise PatchError(
            'path %r does not resolve: target does not exist' % pointer)
    return get_target(parent, last, pointer)


def add_value(doc, parent, last, value, pointer):
    """RFC 6902 add: parent must exist; target may be new.

    Returns the (possibly new) document.
    """
    if parent is None:
        return value  # add to the whole document replaces it
    if isinstance(parent, dict):
        parent[last] = value
        return doc
    if isinstance(parent, list):
        if last == "-":
            parent.append(value)
        else:
            i = parse_index(last, pointer)
            if i > len(parent):
                raise PatchError(
                    'path %r: index %r is out of range' % (pointer, last))
            parent.insert(i, value)
        return doc
    raise PatchError(
        'path %r: parent is a %s, not an object or array'
        % (pointer, type(parent).__name__))


# ------------------------------------------------------------- json equality

def json_eq(a, b):
    """JSON equality per RFC 6902: objects irrespective of key order,
    arrays in order, numbers by numeric value (1 == 1.0), strings,
    booleans and null by exact type."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        if len(a) != len(b):
            return False
        return all(k in b and json_eq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_eq(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


# ------------------------------------------------------------------ patch --

def apply_patch(doc, patch, i):
    if not isinstance(patch, list):
        raise PatchError("patch must be a JSON array of operation objects")
    for i, op in enumerate(patch):
        if not isinstance(op, dict):
            raise PatchError("operation %d: must be an object" % i)
        kind = op.get("op")
        if not isinstance(kind, str):
            raise PatchError('operation %d: missing or invalid "op" member' % i)
        path = op.get("path")
        if not isinstance(path, str):
            raise PatchError('operation %d: missing or invalid "path" member' % i)

        if kind == "test":
            if "value" not in op:
                raise PatchError('operation %d (test): missing "value" member' % i)
            expected = get_value(doc, path)
            if not json_eq(expected, op["value"]):
                raise PatchError("operation %d (test): test failed" % i)

        elif kind == "add":
            if "value" not in op:
                raise PatchError('operation %d (add): missing "value" member' % i)
            value = copy.deepcopy(op["value"])
            parent, last = locate(doc, path)
            doc = add_value(doc, parent, last, value, path)

        elif kind == "replace":
            if "value" not in op:
                raise PatchError('operation %d (replace): missing "value" member' % i)
            value = copy.deepcopy(op["value"])
            parent, last = locate(doc, path)
            if parent is None:
                doc = value
            elif not target_exists(parent, last, path):
                raise PatchError(
                    'operation %d (replace): path %r does not resolve' % (i, path))
            else:
                set_target(parent, last, value, path)

        elif kind in ("move", "copy"):
            frm = op.get("from")
            if not isinstance(frm, str):
                raise PatchError('operation %d (%s): missing or invalid "from" member' % (i, kind))
            fvalue = get_value(doc, frm)  # raises if "from" does not resolve
            if kind == "move":
                if fvalue is doc or frm == "":
                    raise PatchError(
                        "operation %d (move): cannot move the whole document" % i)
                if path == frm or path.startswith(frm + "/"):
                    raise PatchError(
                        "operation %d (move): cannot move %r into one of its own children (%r)"
                        % (i, frm, path))
                fparent, flast = locate(doc, frm)
                remove_target(fparent, flast, frm)
            value = copy.deepcopy(fvalue)
            parent, last = locate(doc, path)
            doc = add_value(doc, parent, last, value, path)

        elif kind == "remove":
            parent, last = locate(doc, path)
            if parent is None or not target_exists(parent, last, path):
                raise PatchError(
                    'operation %d (remove): path %r does not resolve' % (i, path))
            remove_target(parent, last, path)

        else:
            raise PatchError("operation %d: unknown op %r" % (i, kind))
    return doc


def main():
    if len(sys.argv) != 3:
        fail("usage: python3 jpatch.py DOC.json PATCH.json")
    try:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        fail("cannot read document: %s" % e)
    try:
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            patch = json.load(f)
    except (OSError, ValueError) as e:
        fail("cannot read patch: %s" % e)
    try:
        doc = apply_patch(doc, patch, 0)
    except PatchError as e:
        fail(str(e))
    except (RecursionError, ValueError) as e:
        fail(str(e) or type(e).__name__)
    print(json.dumps(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
