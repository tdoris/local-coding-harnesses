#!/usr/bin/env python3
"""jpatch.py – Apply a JSON Patch (RFC 6902) to a JSON document.

Usage: python3 jpatch.py DOC.json PATCH.json

The script reads the JSON document and the JSON Patch (an array of operation
objects) from the supplied file paths, applies the operations atomically, and
writes the resulting JSON document to stdout.  On any error a message is printed
to stderr, nothing is written to stdout and the process exits with status 1.

The implementation follows RFC 6901 for JSON Pointers and RFC 6902 for the
patch semantics.  It uses only the Python standard library and preserves object
key order (Python 3.7+ dicts retain insertion order).
"""

import sys
import json
import copy
from typing import Any, List, Tuple


class JSONPatchError(Exception):
    """Raised for any JSON Patch application error."""


def decode_pointer(pointer: str) -> List[str]:
    """Decode a JSON Pointer (RFC 6901) into a list of reference tokens.

    The pointer must be the empty string or start with a '/'.  Tokens are
    unescaped by replacing "~1" with '/' and then "~0" with '~', in that
    order.
    """
    if not isinstance(pointer, str):
        raise JSONPatchError("JSON Pointer must be a string")
    if pointer == "":
        return []
    if not pointer.startswith('/'):
        raise JSONPatchError(f"Invalid JSON Pointer '{pointer}' (must start with '/')")
    # split on '/' and decode each token
    raw_tokens = pointer.split('/')[1:]  # first element is before the leading '/'
    tokens = []
    for raw in raw_tokens:
        # Decode per RFC 6901 – '~1' to '/', then '~0' to '~'
        token = raw.replace('~1', '/').replace('~0', '~')
        tokens.append(token)
    return tokens


def is_canonical_array_index(token: str) -> bool:
    """Return True if token is a canonical non‑negative integer without leading zeros.

    The empty string or '-' are not considered canonical indexes.
    """
    if not token.isdigit():
        return False
    # disallow leading zeros except for the single digit "0"
    return token == "0" or not token.startswith('0')


def resolve_path(doc: Any, tokens: List[str]) -> Any:
    """Resolve a full JSON Pointer and return the referenced value.

    Raises JSONPatchError if any part of the path cannot be traversed.
    """
    if not tokens:
        return doc
    cur = doc
    for token in tokens:
        if isinstance(cur, dict):
            if token in cur:
                cur = cur[token]
            else:
                raise JSONPatchError(f"Path token '{token}' not found in object")
        elif isinstance(cur, list):
            if token == '-':
                raise JSONPatchError("'-' not allowed in a non‑terminal array pointer")
            if not is_canonical_array_index(token):
                raise JSONPatchError(f"Invalid array index token '{token}'")
            idx = int(token)
            if idx < 0 or idx >= len(cur):
                raise JSONPatchError(f"Array index {idx} out of bounds")
            cur = cur[idx]
        else:
            raise JSONPatchError("Attempted to index into a non‑container value")
    return cur


def resolve_parent(doc: Any, tokens: List[str]) -> Tuple[Any, str]:
    """Return (parent, final_token) for a pointer.

    The parent must exist; the final token may refer to a key that does not yet
    exist (used by "add").  For an empty token list the parent is None and the
    caller must treat the operation as affecting the whole document.
    """
    if not tokens:
        return None, ''
    parent_tokens = tokens[:-1]
    final_token = tokens[-1]
    parent = resolve_path(doc, parent_tokens) if parent_tokens else doc
    return parent, final_token


def json_strict_eq(a: Any, b: Any) -> bool:
    """Strict JSON equality as required by the test suite.

    * Booleans must be of type bool and compare equal.
    * Numbers (int/float) compare by numeric value.
    * Strings compare by value.
    * Lists compare order‑wise.
    * Objects compare key order and recursively compare values.
    """
    # Booleans have higher priority because isinstance(True, int) is True
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        # key order matters
        if list(a) != list(b):
            return False
        for key in a:
            if not json_strict_eq(a[key], b[key]):
                return False
        return True
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(json_strict_eq(x, y) for x, y in zip(a, b))
    # Fallback – type must match and equality must hold
    return type(a) is type(b) and a == b

def json_eq(a: Any, b: Any) -> bool:
    """JSON equality for test operations (ignores object key order)."""
    # Booleans must match type
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    # Numbers compare by value
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    # Dictionaries: ignore key order
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        for k in a:
            if not json_eq(a[k], b[k]):
                return False
        return True
    # Lists: order matters
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(json_eq(x, y) for x, y in zip(a, b))
    # Fallback – compare types and values
    return type(a) is type(b) and a == b


def apply_patch(doc: Any, patch: List[Any]) -> Any:
    """Apply a JSON Patch to *doc* and return the resulting document.

    The operation is performed on a deepcopy of *doc* to guarantee atomicity.
    """
    result = copy.deepcopy(doc)
    for op_index, operation in enumerate(patch):
        if not isinstance(operation, dict):
            raise JSONPatchError(f"Patch operation at index {op_index} is not an object")
        # Required members
        if 'op' not in operation or 'path' not in operation:
            raise JSONPatchError("Operation missing required 'op' or 'path' fields")
        op_type = operation['op']
        path = operation['path']
        # Decode the path pointer
        try:
            path_tokens = decode_pointer(path)
        except JSONPatchError as e:
            raise JSONPatchError(f"Invalid path in operation {op_index}: {e}")
        # Dispatch based on operation type
        if op_type == 'add':
            if 'value' not in operation:
                raise JSONPatchError("'add' operation missing required 'value'")
            value = operation['value']
            if path_tokens == []:
                # Replace the whole document
                result = value
                continue
            parent, token = resolve_parent(result, path_tokens)
            if isinstance(parent, dict):
                # Add or replace object member – insertion order is preserved
                parent[token] = value
            elif isinstance(parent, list):
                # token must be an integer or '-'
                if token == '-':
                    parent.append(value)
                else:
                    if not is_canonical_array_index(token):
                        raise JSONPatchError(f"Invalid array index '{token}' for add operation")
                    idx = int(token)
                    if idx < 0 or idx > len(parent):
                        raise JSONPatchError(f"Array index {idx} out of bounds for add operation")
                    parent.insert(idx, value)
            else:
                raise JSONPatchError("Add operation parent is neither object nor array")
        elif op_type == 'remove':
            if path_tokens == []:
                raise JSONPatchError("Cannot remove the entire document")
            parent, token = resolve_parent(result, path_tokens)
            if isinstance(parent, dict):
                if token in parent:
                    del parent[token]
                else:
                    raise JSONPatchError(f"Member '{token}' does not exist for remove")
            elif isinstance(parent, list):
                if token == '-':
                    raise JSONPatchError("'-' not allowed in remove operation path")
                if not is_canonical_array_index(token):
                    raise JSONPatchError(f"Invalid array index '{token}' for remove operation")
                idx = int(token)
                if idx < 0 or idx >= len(parent):
                    raise JSONPatchError(f"Array index {idx} out of bounds for remove")
                del parent[idx]
            else:
                raise JSONPatchError("Remove operation parent is neither object nor array")
        elif op_type == 'replace':
            if 'value' not in operation:
                raise JSONPatchError("'replace' operation missing required 'value'")
            value = operation['value']
            if path_tokens == []:
                # Replace entire document
                result = value
                continue
            # Verify target exists
            parent, token = resolve_parent(result, path_tokens)
            if isinstance(parent, dict):
                if token not in parent:
                    raise JSONPatchError(f"Member '{token}' does not exist for replace")
                parent[token] = value
            elif isinstance(parent, list):
                if token == '-':
                    raise JSONPatchError("'-' not allowed in replace operation path")
                if not is_canonical_array_index(token):
                    raise JSONPatchError(f"Invalid array index '{token}' for replace operation")
                idx = int(token)
                if idx < 0 or idx >= len(parent):
                    raise JSONPatchError(f"Array index {idx} out of bounds for replace")
                parent[idx] = value
            else:
                raise JSONPatchError("Replace operation parent is neither object nor array")
        elif op_type == 'move':
            if 'from' not in operation:
                raise JSONPatchError("'move' operation missing required 'from' field")
            from_path = operation['from']
            try:
                from_tokens = decode_pointer(from_path)
            except JSONPatchError as e:
                raise JSONPatchError(f"Invalid 'from' pointer in move operation: {e}")
            # Disallow moving a location into its own child
            # Compare raw pointer strings – using the original literals ensures correctness
            if path == '' and from_path == '':
                # moving root to root – no‑op
                continue
            if path.startswith(from_path.rstrip('/') + '/'):
                raise JSONPatchError("Cannot move a value into one of its own children")
            # Retrieve the value to move
            value_to_move = resolve_path(result, from_tokens)
            # Remove from the source location
            if from_tokens == []:
                raise JSONPatchError("Cannot move the entire document")
            from_parent, from_token = resolve_parent(result, from_tokens)
            if isinstance(from_parent, dict):
                del from_parent[from_token]
            elif isinstance(from_parent, list):
                if from_token == '-':
                    raise JSONPatchError("'-' not allowed in 'from' of move operation")
                if not is_canonical_array_index(from_token):
                    raise JSONPatchError(f"Invalid array index '{from_token}' in 'from' of move operation")
                idx = int(from_token)
                if idx < 0 or idx >= len(from_parent):
                    raise JSONPatchError(f"Array index {idx} out of bounds in 'from' of move operation")
                del from_parent[idx]
            else:
                raise JSONPatchError("'from' parent is neither object nor array")
            # Now add the value at the destination (same semantics as add)
            # Re‑decode destination tokens because the structure may have changed
            dest_parent, dest_token = resolve_parent(result, path_tokens)
            if isinstance(dest_parent, dict):
                dest_parent[dest_token] = value_to_move
            elif isinstance(dest_parent, list):
                if dest_token == '-':
                    dest_parent.append(value_to_move)
                else:
                    if not is_canonical_array_index(dest_token):
                        raise JSONPatchError(f"Invalid array index '{dest_token}' for move destination")
                    idx = int(dest_token)
                    if idx < 0 or idx > len(dest_parent):
                        raise JSONPatchError(f"Array index {idx} out of bounds for move destination")
                    dest_parent.insert(idx, value_to_move)
            else:
                raise JSONPatchError("Move destination parent is neither object nor array")
        elif op_type == 'copy':
            if 'from' not in operation:
                raise JSONPatchError("'copy' operation missing required 'from' field")
            from_path = operation['from']
            try:
                from_tokens = decode_pointer(from_path)
            except JSONPatchError as e:
                raise JSONPatchError(f"Invalid 'from' pointer in copy operation: {e}")
            value_to_copy = resolve_path(result, from_tokens)
            # Deep copy to avoid aliasing mutable structures
            value_copy = copy.deepcopy(value_to_copy)
            if path_tokens == []:
                result = value_copy
                continue
            dest_parent, dest_token = resolve_parent(result, path_tokens)
            if isinstance(dest_parent, dict):
                dest_parent[dest_token] = value_copy
            elif isinstance(dest_parent, list):
                if dest_token == '-':
                    dest_parent.append(value_copy)
                else:
                    if not is_canonical_array_index(dest_token):
                        raise JSONPatchError(f"Invalid array index '{dest_token}' for copy destination")
                    idx = int(dest_token)
                    if idx < 0 or idx > len(dest_parent):
                        raise JSONPatchError(f"Array index {idx} out of bounds for copy destination")
                    dest_parent.insert(idx, value_copy)
            else:
                raise JSONPatchError("Copy destination parent is neither object nor array")
        elif op_type == 'test':
            if 'value' not in operation:
                raise JSONPatchError("'test' operation missing required 'value'")
            expected = operation['value']
            actual = resolve_path(result, path_tokens) if path_tokens else result
            if not json_eq(actual, expected):
                raise JSONPatchError("Test operation failed")
        else:
            raise JSONPatchError(f"Unsupported operation '{op_type}'")
    return result


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python3 jpatch.py DOC.json PATCH.json", file=sys.stderr)
        sys.exit(1)
    doc_path = sys.argv[1]
    patch_path = sys.argv[2]
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
        with open(patch_path, 'r', encoding='utf-8') as f:
            patch_raw = json.load(f)
        if not isinstance(patch_raw, list):
            raise JSONPatchError("Patch document is not a JSON array")
        result = apply_patch(doc, patch_raw)
        # Output the resulting document as compact JSON (preserving key order)
        json.dump(result, sys.stdout, separators=(',', ':'), ensure_ascii=False)
        sys.stdout.write('\n')
    except JSONPatchError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Catch JSON decode errors, IO errors, etc.
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
