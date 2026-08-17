#!/usr/bin/env python3
"""jpatch.py – Apply a JSON Patch (RFC 6902) to a JSON document.

Usage: python3 jpatch.py DOC.json PATCH.json

On success, prints the resulting JSON document to stdout and exits with 0.
On any error, prints a message to stderr, prints nothing on stdout, and exits with 1.
"""

import sys
import json
import copy

# ---------- Helper functions ----------

def _error(message: str) -> None:
    """Print an error message to stderr and exit with status 1."""
    print(message, file=sys.stderr)
    sys.exit(1)


def _decode_pointer(ptr: str) -> list:
    """Decode a JSON Pointer (RFC 6901) into a list of reference tokens.
    Empty string -> [] (the whole document).
    """
    if ptr == "":
        return []
    if not ptr.startswith('/'):
        _error(f"Invalid JSON Pointer '{ptr}' (must be empty or start with '/')")
    # split on '/', ignore the leading empty part
    parts = ptr.split('/')[1:]
    # Unescape ~1 -> '/', ~0 -> '~' (decode ~1 before ~0 as per spec)
    def unescape(token: str) -> str:
        return token.replace('~1', '/').replace('~0', '~')
    return [unescape(p) for p in parts]


def _get_target(container, token):
    """Retrieve the target value from a container given a token.
    For dicts, token is a key; for lists, token must be a valid index (as integer).
    Returns the value, or raises KeyError/IndexError.
    """
    if isinstance(container, dict):
        return container[token]
    elif isinstance(container, list):
        # token should be a decimal index (no leading zeros except "0")
        if token == '-':
            _error("'-' is not allowed when retrieving a value")
        if not token.isdigit():
            _error(f"Invalid array index '{token}'")
        # Disallow leading zeros like "01"
        if len(token) > 1 and token.startswith('0'):
            _error(f"Invalid array index '{token}' (leading zeros)")
        idx = int(token)
        return container[idx]
    else:
        _error("Attempted to traverse non-container type")


def _set_value(container, token, value, allow_create: bool):
    """Set a value in a container.
    If allow_create is True, a missing key in a dict is created.
    For lists, token must be an integer index (or '-' for appending when creating).
    """
    if isinstance(container, dict):
        if token in container or allow_create:
            container[token] = value
        else:
            _error(f"Object member '{token}' does not exist for operation")
    elif isinstance(container, list):
        if token == '-':
            if not allow_create:
                _error("'-' is not allowed for this operation")
            container.append(value)
        else:
            if not token.isdigit():
                _error(f"Invalid array index '{token}'")
            if len(token) > 1 and token.startswith('0'):
                _error(f"Invalid array index '{token}' (leading zeros)")
            idx = int(token)
            if allow_create:
                if idx > len(container):
                    _error(f"Array index {idx} out of range for add operation")
                # Insertion: shift later elements
                container.insert(idx, value)
            else:
                # replace/remove: index must be within existing range
                if idx >= len(container):
                    _error(f"Array index {idx} out of range")
                container[idx] = value
    else:
        _error("Target is not a container for setting a value")


def _remove_value(container, token):
    """Remove a value from a container given a token."""
    if isinstance(container, dict):
        if token in container:
            del container[token]
        else:
            _error(f"Object member '{token}' does not exist for remove")
    elif isinstance(container, list):
        if token == '-':
            _error("'-' is not valid for remove operation on arrays")
        if not token.isdigit():
            _error(f"Invalid array index '{token}'")
        if len(token) > 1 and token.startswith('0'):
            _error(f"Invalid array index '{token}' (leading zeros)")
        idx = int(token)
        if idx >= len(container):
            _error(f"Array index {idx} out of range for remove")
        del container[idx]
    else:
        _error("Target is not a container for removal")


def _traverse(doc, ptr_tokens, create_missing: bool=False):
    """Traverse the document according to ptr_tokens.
    Returns (parent, last_token).
    If create_missing is True, the parent must exist but the final token may be missing (used for add).
    """
    parent = doc
    for token in ptr_tokens[:-1]:
        if isinstance(parent, dict):
            if token not in parent:
                _error(f"Object member '{token}' does not exist in path")
            parent = parent[token]
        elif isinstance(parent, list):
            if token == '-':
                _error("'-' cannot be used in the middle of a JSON Pointer")
            if not token.isdigit():
                _error(f"Invalid array index '{token}' in path")
            if len(token) > 1 and token.startswith('0'):
                _error(f"Invalid array index '{token}' (leading zeros) in path")
            idx = int(token)
            if idx >= len(parent):
                _error(f"Array index {idx} out of range in path")
            parent = parent[idx]
        else:
            _error("Encountered non-container while traversing path")
    return parent, ptr_tokens[-1] if ptr_tokens else (parent, None)


def _deep_copy(value):
    return copy.deepcopy(value)


def _apply_op(doc, op_obj):
    if not isinstance(op_obj, dict):
        _error("Operation is not an object")
    # Required members: op, path
    if 'op' not in op_obj or 'path' not in op_obj:
        _error("Operation missing required 'op' or 'path' member")
    op = op_obj['op']
    path = op_obj['path']
    ptr_tokens = _decode_pointer(path)
    if op == 'add':
        if 'value' not in op_obj:
            _error("'add' operation missing required 'value'")
        value = op_obj['value']
        if ptr_tokens == []:
            # replace whole document
            return value
        parent, token = _traverse(doc, ptr_tokens, create_missing=True)
        # For add, the target's parent must exist; token may be new.
        if isinstance(parent, dict):
            # Insert or replace member. Existing members are replaced, new are appended.
            parent[token] = value
        elif isinstance(parent, list):
            if token == '-':
                parent.append(value)
            else:
                if not token.isdigit():
                    _error(f"Invalid array index '{token}' for add")
                if len(token) > 1 and token.startswith('0'):
                    _error(f"Invalid array index '{token}' (leading zeros) for add")
                idx = int(token)
                if idx > len(parent):
                    _error(f"Array index {idx} out of range for add")
                parent.insert(idx, value)
        else:
            _error("Parent of add operation is not a container")
        return doc
    elif op == 'remove':
        if ptr_tokens == []:
            _error("Cannot remove the whole document")
        parent, token = _traverse(doc, ptr_tokens)
        _remove_value(parent, token)
        return doc
    elif op == 'replace':
        if 'value' not in op_obj:
            _error("'replace' operation missing required 'value'")
        value = op_obj['value']
        if ptr_tokens == []:
            return value
        parent, token = _traverse(doc, ptr_tokens)
        # Ensure target exists
        _get_target(parent, token)  # will error if missing
        _set_value(parent, token, value, allow_create=False)
        return doc
    elif op == 'move':
        if 'from' not in op_obj:
            _error("'move' operation missing required 'from'")
        from_ptr = op_obj['from']
        from_tokens = _decode_pointer(from_ptr)
        # Resolve source value
        if from_tokens == []:
            src_parent = None
            src_token = None
            src_value = doc
        else:
            src_parent, src_token = _traverse(doc, from_tokens)
            src_value = _get_target(src_parent, src_token)
        # Check moving into own child
        # Simple string check: if destination path starts with source path + '/'
        if from_ptr != '' and path.startswith(from_ptr + '/'):
            _error("Cannot move a location into one of its own children")
        # Remove from source
        if from_tokens == []:
            # moving whole document is not allowed per RFC; treat as error
            _error("'from' pointer '' not allowed for move")
        else:
            _remove_value(src_parent, src_token)
        # Add to destination (as add)
        # Destination parent must exist
        if ptr_tokens == []:
            # replace whole doc with moved value
            doc = _deep_copy(src_value)
        else:
            dest_parent, dest_token = _traverse(doc, ptr_tokens, create_missing=True)
            if isinstance(dest_parent, dict):
                dest_parent[dest_token] = _deep_copy(src_value)
            elif isinstance(dest_parent, list):
                if dest_token == '-':
                    dest_parent.append(_deep_copy(src_value))
                else:
                    if not dest_token.isdigit():
                        _error(f"Invalid array index '{dest_token}' for move")
                    if len(dest_token) > 1 and dest_token.startswith('0'):
                        _error(f"Invalid array index '{dest_token}' (leading zeros) for move")
                    idx = int(dest_token)
                    if idx > len(dest_parent):
                        _error(f"Array index {idx} out of range for move")
                    dest_parent.insert(idx, _deep_copy(src_value))
            else:
                _error("Destination parent is not a container for move")
        return doc
    elif op == 'copy':
        if 'from' not in op_obj:
            _error("'copy' operation missing required 'from'")
        from_ptr = op_obj['from']
        from_tokens = _decode_pointer(from_ptr)
        if from_tokens == []:
            src_value = doc
        else:
            src_parent, src_token = _traverse(doc, from_tokens)
            src_value = _get_target(src_parent, src_token)
        # Add copy to destination (same handling as add)
        if ptr_tokens == []:
            # replace whole document with copy of src_value
            doc = _deep_copy(src_value)
        else:
            dest_parent, dest_token = _traverse(doc, ptr_tokens, create_missing=True)
            if isinstance(dest_parent, dict):
                dest_parent[dest_token] = _deep_copy(src_value)
            elif isinstance(dest_parent, list):
                if dest_token == '-':
                    dest_parent.append(_deep_copy(src_value))
                else:
                    if not dest_token.isdigit():
                        _error(f"Invalid array index '{dest_token}' for copy")
                    if len(dest_token) > 1 and dest_token.startswith('0'):
                        _error(f"Invalid array index '{dest_token}' (leading zeros) for copy")
                    idx = int(dest_token)
                    if idx > len(dest_parent):
                        _error(f"Array index {idx} out of range for copy")
                    dest_parent.insert(idx, _deep_copy(src_value))
            else:
                _error("Destination parent is not a container for copy")
        return doc
    elif op == 'test':
        if 'value' not in op_obj:
            _error("'test' operation missing required 'value'")
        test_value = op_obj['value']
        if ptr_tokens == []:
            target = doc
        else:
            parent, token = _traverse(doc, ptr_tokens)
            target = _get_target(parent, token)
        if not _json_equal(target, test_value):
            _error("test operation failed")
        return doc
    else:
        _error(f"Unknown operation '{op}'")


def _json_equal(a, b):
    """Compare two JSON values for equality as per RFC 6902 rules.
    Numbers are compared by numeric value, booleans and strings by type and value.
    Objects are equal irrespective of key order.
    """
    # Numbers
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    # Booleans
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    # Strings, null, etc.
    if type(a) != type(b):
        return False
    if isinstance(a, dict):
        if len(a) != len(b):
            return False
        for key in a:
            if key not in b:
                return False
            if not _json_equal(a[key], b[key]):
                return False
        return True
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_json_equal(x, y) for x, y in zip(a, b))
    return a == b


def main():
    if len(sys.argv) != 3:
        _error("Usage: python3 jpatch.py DOC.json PATCH.json")
    doc_path = sys.argv[1]
    patch_path = sys.argv[2]
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
        with open(patch_path, 'r', encoding='utf-8') as f:
            patch = json.load(f)
    except Exception as e:
        _error(str(e))
    if not isinstance(patch, list):
        _error("Patch is not a JSON array")
    # Work on a deep copy to ensure atomicity
    result = copy.deepcopy(doc)
    try:
        for op_obj in patch:
            result = _apply_op(result, op_obj)
    except SystemExit:
        # _error already printed and exited, but we want to ensure no output on stdout
        sys.exit(1)
    # If we reach here, all operations succeeded
    json.dump(result, sys.stdout, separators=(',', ':'), ensure_ascii=False)
    sys.stdout.flush()

if __name__ == "__main__":
    main()
