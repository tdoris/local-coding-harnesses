#!/usr/bin/env python3
"""jpatch.py – apply a JSON Patch (RFC 6902) to a JSON document.

Usage:
    python3 jpatch.py DOC.json PATCH.json

On success prints the patched document to stdout and exits with code 0.
On any error prints a message to stderr, prints nothing to stdout and exits with code 1.
"""

import sys
import json
import copy

# ---------- JSON Pointer helpers ----------

def _decode_pointer(ptr):
    """Decode a JSON Pointer string into a list of reference tokens."""
    if not isinstance(ptr, str):
        raise ValueError("JSON Pointer must be a string")
    if ptr == "":
        return []
    if not ptr.startswith("/"):
        raise ValueError(f"Invalid JSON Pointer '{ptr}' (must start with '/')")
    tokens = ptr.split("/")[1:]
    # RFC 6901 decoding: ~1 -> /, ~0 -> ~ (decode ~1 before ~0)
    decoded = []
    for t in tokens:
        t = t.replace("~1", "/").replace("~0", "~")
        decoded.append(t)
    return decoded

def _is_canonical_index(token):
    """Return True if token is a canonical array index (no leading zeros, no sign)."""
    if token == "-":
        return True
    if token.isdigit():
        # Disallow leading zeros unless the token is exactly "0"
        return token == "0" or not token.startswith("0")
    return False

def _resolve(doc, ptr_tokens, create_parent=False, for_add=False):
    """
    Resolve a list of tokens against ``doc``.
    If ``create_parent`` is True, resolve up to the parent of the final token
    and return (parent, final_token). ``for_add`` signals that the final token
    may be '-' (array append) for an add operation.
    """
    cur = doc
    for i, token in enumerate(ptr_tokens):
        is_last = (i == len(ptr_tokens) - 1)
        if isinstance(cur, dict):
            if token not in cur:
                if is_last and create_parent:
                    # parent exists, target may be new
                    return cur, token
                raise ValueError(f"Object has no member '{token}'")
            if is_last:
                return cur, token
            cur = cur[token]
        elif isinstance(cur, list):
            # Allow '-' as the final token of an add operation
            if token == "-":
                if is_last and for_add:
                    return cur, token
                else:
                    raise ValueError("'-' is not allowed except as the final token of an add operation")
            if not _is_canonical_index(token):
                raise ValueError(f"Invalid array index '{token}'")
            idx = int(token)
            # For an add operation we permit idx == len(cur) (append)
            if is_last and for_add:
                if idx < 0 or idx > len(cur):
                    raise ValueError(f"Array index {idx} out of range")
            else:
                if idx < 0 or idx >= len(cur):
                    raise ValueError(f"Array index {idx} out of range")
            if is_last:
                return cur, idx
            cur = cur[idx]
        else:
            raise ValueError("Cannot traverse into non-container type")
    # If we get here, ptr_tokens was empty (i.e., pointer == "")
    return None, None  # caller should handle the empty‑pointer case separately

def _get_target(doc, ptr):
    """Return the value addressed by the pointer."""
    tokens = _decode_pointer(ptr)
    if not tokens:
        return doc
    parent, token = _resolve(doc, tokens)
    if isinstance(parent, dict):
        return parent[token]
    else:  # list
        return parent[token]

# ---------- Operation implementations ----------

def _op_add(doc, op):
    path = op["path"]
    value = op["value"]
    tokens = _decode_pointer(path)
    if not tokens:
        # replace the whole document
        return value
    parent, token = _resolve(doc, tokens, create_parent=True, for_add=True)
    if isinstance(parent, dict):
        # object add – replace if exists, otherwise append
        parent[token] = value
    else:  # list
        if token == "-":
            parent.append(value)
        else:
            if not _is_canonical_index(str(token)):
                raise ValueError(f"Invalid array index '{token}'")
            idx = int(token)
            if idx < 0 or idx > len(parent):
                raise ValueError(f"Array index {idx} out of range for add")
            parent.insert(idx, value)
    return doc

def _op_remove(doc, op):
    path = op["path"]
    tokens = _decode_pointer(path)
    if not tokens:
        raise ValueError("Cannot remove the whole document")
    parent, token = _resolve(doc, tokens)
    if isinstance(parent, dict):
        del parent[token]
    else:
        del parent[token]
    return doc

def _op_replace(doc, op):
    path = op["path"]
    value = op["value"]
    tokens = _decode_pointer(path)
    if not tokens:
        return value
    parent, token = _resolve(doc, tokens)
    if isinstance(parent, dict):
        parent[token] = value
    else:
        parent[token] = value
    return doc

def _op_test(doc, op):
    path = op["path"]
    expected = op["value"]
    actual = _get_target(doc, path)
    if not _json_equal(actual, expected):
        raise ValueError("test operation failed")
    return doc

def _op_move(doc, op):
    from_path = op["from"]
    path = op["path"]
    # Detect moving into own child
    if path == from_path or path.startswith(from_path.rstrip("/") + "/"):
        raise ValueError("Cannot move a value into one of its own children")
    value = _get_target(doc, from_path)
    # Perform remove first on a copy to keep atomicity
    doc = _op_remove(doc, {"op": "remove", "path": from_path})
    # Then add the value at the destination
    return _op_add(doc, {"op": "add", "path": path, "value": value})

def _op_copy(doc, op):
    from_path = op["from"]
    path = op["path"]
    value = _get_target(doc, from_path)
    value_copy = copy.deepcopy(value)
    return _op_add(doc, {"op": "add", "path": path, "value": value_copy})

# ---------- Helper for equality ----------

def _json_equal(a, b):
    """Compare two JSON values for equality per RFC 6902."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if type(a) != type(b):
        return False
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_json_equal(x, y) for x, y in zip(a, b))
    return a == b

# ---------- Main driver ----------

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 jpatch.py DOC.json PATCH.json", file=sys.stderr)
        sys.exit(1)

    doc_path, patch_path = sys.argv[1], sys.argv[2]

    try:
        with open(doc_path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        with open(patch_path, "r", encoding="utf-8") as f:
            patch = json.load(f)

        if not isinstance(patch, list):
            raise ValueError("Patch document must be a JSON array")

        # Work on a deep copy to keep operation atomic
        result = copy.deepcopy(doc)

        for op in patch:
            if not isinstance(op, dict):
                raise ValueError("Each operation must be an object")
            if "op" not in op or "path" not in op:
                raise ValueError("Operation missing required members 'op' or 'path'")

            operation = op["op"]
            if operation == "add":
                if "value" not in op:
                    raise ValueError("Add operation missing 'value'")
                result = _op_add(result, op)
            elif operation == "remove":
                result = _op_remove(result, op)
            elif operation == "replace":
                if "value" not in op:
                    raise ValueError("Replace operation missing 'value'")
                result = _op_replace(result, op)
            elif operation == "move":
                if "from" not in op:
                    raise ValueError("Move operation missing 'from'")
                result = _op_move(result, op)
            elif operation == "copy":
                if "from" not in op:
                    raise ValueError("Copy operation missing 'from'")
                result = _op_copy(result, op)
            elif operation == "test":
                if "value" not in op:
                    raise ValueError("Test operation missing 'value'")
                result = _op_test(result, op)
            else:
                raise ValueError(f"Unrecognized operation '{operation}'")

        # All operations succeeded – output result
        json.dump(result, sys.stdout, separators=(",", ":"), ensure_ascii=False)
        sys.stdout.write("\n")
        sys.exit(0)

    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
