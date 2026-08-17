#!/usr/bin/env python3
"""jpatch.py – apply a JSON Patch (RFC 6902) to a JSON document.

Usage:
    python3 jpatch.py DOC.json PATCH.json

The program reads *DOC.json* and *PATCH.json* (a JSON array of operation
objects), applies the operations in order, and writes the resulting JSON
document to *stdout*.  On any error nothing is written to *stdout* and the
program exits with status 1, printing a terse message to *stderr*.

Implementation follows RFC 6901 (JSON Pointer) and RFC 6902.  It uses only
the Python standard library and preserves object key order.
"""

import sys
import json
import copy

# ---------------------------------------------------------------------------
# Helper exceptions
# ---------------------------------------------------------------------------
class PatchError(Exception):
    """Raised for any violation of the JSON Patch specification."""
    pass

# ---------------------------------------------------------------------------
# JSON Pointer handling (RFC 6901)
# ---------------------------------------------------------------------------
def _decode_token(tok: str) -> str:
    """Decode a single reference token.

    The RFC requires that "~1" be replaced with "/" and then "~0" with
    "~" (in that order).
    """
    return tok.replace("~1", "/").replace("~0", "~")


def _parse_pointer(ptr: str) -> list:
    """Parse a JSON Pointer string into a list of decoded tokens.

    An empty string points to the whole document.  Otherwise the pointer must
    start with a '/'.
    """
    if ptr == "":
        return []
    if not ptr.startswith("/"):
        raise PatchError(f"Invalid JSON Pointer '{ptr}' (must start with '/')")
    # Split on '/', discarding the leading empty part
    parts = ptr.split("/")[1:]
    return [_decode_token(p) for p in parts]

# ---------------------------------------------------------------------------
# Equality used by the "test" operation (RFC 6902 §4.5)
# ---------------------------------------------------------------------------
def _json_equal(a, b) -> bool:
    """Return True if *a* and *b* are equal according to JSON semantics.

    * Booleans are compared by type and value – ``True`` is *not* equal to
      ``1``.
    * Numbers (int/float) are compared by numeric value.
    * Objects are equal if they have the same set of members and each member
      is equal recursively (key order is ignored).
    * Arrays are equal if they have the same length and elements are equal
      in order.
    """
    # Booleans have to match both type and value
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b

    # Numbers – bool is already handled, so we can safely use isinstance
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b

    # Objects – order does not matter for equality
    if isinstance(a, dict) and isinstance(b, dict):
        if len(a) != len(b):
            return False
        for key, val in a.items():
            if key not in b:
                return False
            if not _json_equal(val, b[key]):
                return False
        return True

    # Arrays – order matters
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_json_equal(x, y) for x, y in zip(a, b))

    # Fallback – types must match and values be equal
    return type(a) is type(b) and a == b

# ---------------------------------------------------------------------------
# Navigation helpers for objects and arrays
# ---------------------------------------------------------------------------
def _canonical_array_index(tok: str) -> bool:
    """Return True if *tok* is a valid array index according to the spec.

    The index must be a decimal integer without leading zeros (except the
    single digit "0").  The special token "-" is handled separately.
    """
    return tok.isdigit() and (tok == "0" or not tok.startswith("0"))


def _resolve(doc, tokens):
    """Navigate *doc* using *tokens* and return the target value.

    Raises :class:`PatchError` if any step cannot be resolved.
    """
    cur = doc
    for tok in tokens:
        if isinstance(cur, dict):
            if tok not in cur:
                raise PatchError(f"Path token '{tok}' not found in object")
            cur = cur[tok]
        elif isinstance(cur, list):
            if tok == "-":
                raise PatchError("'-' token not allowed in this context")
            if not _canonical_array_index(tok):
                raise PatchError(f"Invalid array index '{tok}'")
            idx = int(tok)
            if idx < 0 or idx >= len(cur):
                raise PatchError(f"Array index {idx} out of range")
            cur = cur[idx]
        else:
            raise PatchError("Attempted to traverse non‑container value")
    return cur


def _resolve_parent(doc, tokens, allow_dash=False):
    """Return ``(parent, final_token)`` for *tokens*.

    ``parent`` is the container (object or array) that holds the target.
    ``final_token`` is the last token of *tokens*.
    ``allow_dash`` permits the final token to be "-" (used only for the
    ``add`` operation on arrays).
    """
    if not tokens:
        raise PatchError("Path points to the whole document")
    parent = doc
    for tok in tokens[:-1]:
        if isinstance(parent, dict):
            if tok not in parent:
                raise PatchError(f"Path token '{tok}' not found in object")
            parent = parent[tok]
        elif isinstance(parent, list):
            if tok == "-":
                raise PatchError("'-' token not allowed in intermediate path")
            if not _canonical_array_index(tok):
                raise PatchError(f"Invalid array index '{tok}'")
            idx = int(tok)
            if idx < 0 or idx >= len(parent):
                raise PatchError(f"Array index {idx} out of range")
            parent = parent[idx]
        else:
            raise PatchError("Attempted to traverse non‑container value")
    return parent, tokens[-1]

# ---------------------------------------------------------------------------
# Core patch application
# ---------------------------------------------------------------------------
def _apply_patch(doc, patch):
    """Apply *patch* (a list of operation objects) to *doc*.

    The function mutates *doc* in place and returns it.  On any error a
    :class:`PatchError` is raised and the original document is left untouched.
    """
    if not isinstance(patch, list):
        raise PatchError("Patch document is not an array")

    for op in patch:
        if not isinstance(op, dict):
            raise PatchError("Patch operation is not an object")
        if 'op' not in op or 'path' not in op:
            raise PatchError("Operation missing required 'op' or 'path' member")

        operation = op['op']
        path = op['path']
        tokens = _parse_pointer(path)

        if operation == 'add':
            if 'value' not in op:
                raise PatchError("'add' operation missing 'value'")
            value = op['value']
            # Adding to the whole document replaces it entirely.
            if not tokens:
                doc = value
                continue
            parent, last = _resolve_parent(doc, tokens, allow_dash=True)
            if isinstance(parent, dict):
                # Object member – replace if it already exists, otherwise append.
                parent[last] = value
            elif isinstance(parent, list):
                if last == '-':
                    parent.append(value)
                else:
                    if not _canonical_array_index(last):
                        raise PatchError(f"Invalid array index '{last}' for add")
                    idx = int(last)
                    if idx < 0 or idx > len(parent):
                        raise PatchError("Array index out of range for add")
                    parent.insert(idx, value)
            else:
                raise PatchError("Add target's parent is neither object nor array")

        elif operation == 'remove':
            if not tokens:
                raise PatchError("Cannot remove the whole document")
            parent, last = _resolve_parent(doc, tokens, allow_dash=False)
            if isinstance(parent, dict):
                if last not in parent:
                    raise PatchError("Remove target member does not exist")
                del parent[last]
            elif isinstance(parent, list):
                if not _canonical_array_index(last):
                    raise PatchError(f"Invalid array index '{last}' for remove")
                idx = int(last)
                if idx < 0 or idx >= len(parent):
                    raise PatchError("Array index out of range for remove")
                del parent[idx]
            else:
                raise PatchError("Remove target's parent is neither object nor array")

        elif operation == 'replace':
            if 'value' not in op:
                raise PatchError("'replace' operation missing 'value'")
            value = op['value']
            if not tokens:
                # Replace whole document.
                doc = value
                continue
            parent, last = _resolve_parent(doc, tokens, allow_dash=False)
            if isinstance(parent, dict):
                if last not in parent:
                    raise PatchError("Replace target member does not exist")
                parent[last] = value
            elif isinstance(parent, list):
                if not _canonical_array_index(last):
                    raise PatchError(f"Invalid array index '{last}' for replace")
                idx = int(last)
                if idx < 0 or idx >= len(parent):
                    raise PatchError("Array index out of range for replace")
                parent[idx] = value
            else:
                raise PatchError("Replace target's parent is neither object nor array")

        elif operation == 'move':
            if 'from' not in op:
                raise PatchError("'move' operation missing 'from'")
            from_path = op['from']
            from_tokens = _parse_pointer(from_path)
            # Detect moving a location into one of its own children.
            if from_tokens and tokens[:len(from_tokens)] == from_tokens and len(tokens) > len(from_tokens):
                raise PatchError("Cannot move a value into one of its own children")
            # Resolve source value.
            src_parent, src_last = _resolve_parent(doc, from_tokens, allow_dash=False)
            if isinstance(src_parent, dict):
                if src_last not in src_parent:
                    raise PatchError("Move source member does not exist")
                value = src_parent[src_last]
                del src_parent[src_last]
            elif isinstance(src_parent, list):
                if not _canonical_array_index(src_last):
                    raise PatchError(f"Invalid array index '{src_last}' for move source")
                idx = int(src_last)
                if idx < 0 or idx >= len(src_parent):
                    raise PatchError("Array index out of range for move source")
                value = src_parent[idx]
                del src_parent[idx]
            else:
                raise PatchError("Move source's parent is neither object nor array")
            # Perform the add at the destination.
            if not tokens:
                doc = value
                continue
            dst_parent, dst_last = _resolve_parent(doc, tokens, allow_dash=True)
            if isinstance(dst_parent, dict):
                dst_parent[dst_last] = value
            elif isinstance(dst_parent, list):
                if dst_last == '-':
                    dst_parent.append(value)
                else:
                    if not _canonical_array_index(dst_last):
                        raise PatchError(f"Invalid array index '{dst_last}' for move destination")
                    idx = int(dst_last)
                    if idx < 0 or idx > len(dst_parent):
                        raise PatchError("Array index out of range for move destination")
                    dst_parent.insert(idx, value)
            else:
                raise PatchError("Move destination's parent is neither object nor array")

        elif operation == 'copy':
            if 'from' not in op:
                raise PatchError("'copy' operation missing 'from'")
            from_path = op['from']
            from_tokens = _parse_pointer(from_path)
            # Resolve source value (deep copy).
            src_val = copy.deepcopy(_resolve(doc, from_tokens))
            if not tokens:
                doc = src_val
                continue
            dst_parent, dst_last = _resolve_parent(doc, tokens, allow_dash=True)
            if isinstance(dst_parent, dict):
                dst_parent[dst_last] = src_val
            elif isinstance(dst_parent, list):
                if dst_last == '-':
                    dst_parent.append(src_val)
                else:
                    if not _canonical_array_index(dst_last):
                        raise PatchError(f"Invalid array index '{dst_last}' for copy destination")
                    idx = int(dst_last)
                    if idx < 0 or idx > len(dst_parent):
                        raise PatchError("Array index out of range for copy destination")
                    dst_parent.insert(idx, src_val)
            else:
                raise PatchError("Copy destination's parent is neither object nor array")

        elif operation == 'test':
            if 'value' not in op:
                raise PatchError("'test' operation missing 'value'")
            expected = op['value']
            if not tokens:
                target = doc
            else:
                target = _resolve(doc, tokens)
            if not _json_equal(target, expected):
                raise PatchError("Test operation failed")
        else:
            raise PatchError(f"Unsupported operation '{operation}'")

    return doc

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) != 3:
        sys.stderr.write("Usage: python3 jpatch.py DOC.json PATCH.json\n")
        sys.exit(1)

    doc_path, patch_path = sys.argv[1], sys.argv[2]
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
        with open(patch_path, 'r', encoding='utf-8') as f:
            patch = json.load(f)
    except Exception as e:
        sys.stderr.write(f"Error reading input files: {e}\n")
        sys.exit(1)

    # Work on a deep copy so that the original is untouched on error.
    doc_copy = copy.deepcopy(doc)
    try:
        result = _apply_patch(doc_copy, patch)
    except PatchError as e:
        sys.stderr.write(f"Error applying patch: {e}\n")
        sys.exit(1)
    except Exception as e:
        # Unexpected errors – still report them as failure.
        sys.stderr.write(f"Unexpected error: {e}\n")
        sys.exit(1)

    # Successful – emit the resulting document.
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write('\n')
    sys.exit(0)

if __name__ == '__main__':
    main()
