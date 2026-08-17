#!/usr/bin/env python3
"""
jpatch.py – Apply a JSON Patch (RFC 6902) to a JSON document.

Usage:
    python3 jpatch.py DOC.json PATCH.json

If successful, the patched document is printed to stdout and the program exits with code 0.
On any error, an explanatory message is written to stderr, nothing is printed to stdout,
and the program exits with code 1.
"""

import sys
import json
import copy
import re

# ----------------------------------------------------------------------
# Helper exceptions
# ----------------------------------------------------------------------
class PatchError(Exception):
    """Raised for any JSON Patch processing error."""
    pass

# ----------------------------------------------------------------------
# JSON Pointer handling (RFC 6901)
# ----------------------------------------------------------------------
def _unescape(token: str) -> str:
    """Decode a single reference token."""
    return token.replace('~1', '/').replace('~0', '~')

def _split_pointer(ptr: str):
    """Split a JSON Pointer into unescaped tokens."""
    if ptr == '':
        return []
    if not ptr.startswith('/'):
        raise PatchError(f'Invalid JSON Pointer (must start with "/"): {ptr!r}')
    # split, drop leading empty string
    parts = ptr.split('/')[1:]
    return [_unescape(p) for p in parts]

def _resolve(doc, ptr: str, create_missing=False):
    """
    Resolve a JSON Pointer against *doc*.

    Returns a tuple (parent, token) where *parent* is the container
    (dict or list) that holds the final token, and *token* is the
    final reference (key or index). For the empty pointer "" the
    function returns (None, None) indicating the whole document.
    """
    tokens = _split_pointer(ptr)
    if not tokens:
        return (None, None)  # whole document

    cur = doc
    for i, token in enumerate(tokens[:-1]):
        if isinstance(cur, dict):
            if token not in cur:
                raise PatchError(f'Path not found: {" / ".join(tokens[:i+1])}')
            cur = cur[token]
        elif isinstance(cur, list):
            idx = _array_index(token, allow_dash=False)
            if idx >= len(cur):
                raise PatchError(f'Array index out of range at {" / ".join(tokens[:i+1])}')
            cur = cur[idx]
        else:
            raise PatchError(f'Cannot traverse into non-container at {" / ".join(tokens[:i])}')
    return (cur, tokens[-1])

# ----------------------------------------------------------------------
# Array index validation
# ----------------------------------------------------------------------
_ARRAY_INDEX_RE = re.compile(r'0|[1-9][0-9]*$')

def _array_index(token: str, allow_dash: bool):
    """
    Convert an array index token to an integer.

    *allow_dash* permits the special '-' token (used only for add).
    """
    if allow_dash and token == '-':
        return '-'
    if not _ARRAY_INDEX_RE.fullmatch(token):
        raise PatchError(f'Invalid array index: {token!r}')
    return int(token)

# ----------------------------------------------------------------------
# Core operation implementations
# ----------------------------------------------------------------------
def _op_add(doc, path, value):
    if path == '':
        # Replace the whole document
        return value

    parent, token = _resolve(doc, path, create_missing=False)

    if isinstance(parent, dict):
        parent[token] = value
        return doc
    elif isinstance(parent, list):
        idx = _array_index(token, allow_dash=True)
        if idx == '-':
            parent.append(value)
        else:
            if idx > len(parent):
                raise PatchError('Add index out of range')
            parent.insert(idx, value)
        return doc
    else:
        raise PatchError('Add target is not a container')

def _op_remove(doc, path):
    if path == '':
        raise PatchError('Remove operation with empty path is not allowed')
    parent, token = _resolve(doc, path)
    if isinstance(parent, dict):
        if token not in parent:
            raise PatchError('Remove target does not exist')
        del parent[token]
        return doc
    elif isinstance(parent, list):
        idx = _array_index(token, allow_dash=False)
        if idx >= len(parent):
            raise PatchError('Remove array index out of range')
        del parent[idx]
        return doc
    else:
        raise PatchError('Remove target is not a container')

def _op_replace(doc, path, value):
    if path == '':
        # Replace whole document
        return value
    parent, token = _resolve(doc, path)
    if isinstance(parent, dict):
        if token not in parent:
            raise PatchError('Replace target does not exist')
        parent[token] = value
        return doc
    elif isinstance(parent, list):
        idx = _array_index(token, allow_dash=False)
        if idx >= len(parent):
            raise PatchError('Replace array index out of range')
        parent[idx] = value
        return doc
    else:
        raise PatchError('Replace target is not a container')

def _op_move(doc, from_path, path):
    # Disallow moving into own child
    if path.startswith(from_path.rstrip('/') + '/'):
        raise PatchError('Cannot move a location into one of its own children')
    # Resolve source value and remove it
    src_parent, src_token = _resolve(doc, from_path)
    if isinstance(src_parent, dict):
        if src_token not in src_parent:
            raise PatchError('Move source does not exist')
        val = src_parent[src_token]
        del src_parent[src_token]
    elif isinstance(src_parent, list):
        idx = _array_index(src_token, allow_dash=False)
        if idx >= len(src_parent):
            raise PatchError('Move source index out of range')
        val = src_parent[idx]
        del src_parent[idx]
    else:
        raise PatchError('Move source is not a container')

    # Add the value at destination (deep copy per RFC)
    return _op_add(doc, path, copy.deepcopy(val))

def _op_copy(doc, from_path, path):
    src_parent, src_token = _resolve(doc, from_path)
    if isinstance(src_parent, dict):
        if src_token not in src_parent:
            raise PatchError('Copy source does not exist')
        val = src_parent[src_token]
    elif isinstance(src_parent, list):
        idx = _array_index(src_token, allow_dash=False)
        if idx >= len(src_parent):
            raise PatchError('Copy source index out of range')
        val = src_parent[idx]
    else:
        raise PatchError('Copy source is not a container')
    return _op_add(doc, path, copy.deepcopy(val))

def _op_test(doc, path, value):
    if path == '':
        target = doc
    else:
        parent, token = _resolve(doc, path)
        if isinstance(parent, dict):
            if token not in parent:
                raise PatchError('Test target does not exist')
            target = parent[token]
        elif isinstance(parent, list):
            idx = _array_index(token, allow_dash=False)
            if idx >= len(parent):
                raise PatchError('Test array index out of range')
            target = parent[idx]
        else:
            raise PatchError('Test target is not a container')
    if target != value:
        raise PatchError('Test operation failed')
    return doc

# ----------------------------------------------------------------------
# Dispatcher
# ----------------------------------------------------------------------
_OP_HANDLERS = {
    'add': lambda doc, op: _op_add(doc, op['path'], op['value']),
    'remove': lambda doc, op: _op_remove(doc, op['path']),
    'replace': lambda doc, op: _op_replace(doc, op['path'], op['value']),
    'move': lambda doc, op: _op_move(doc, op['from'], op['path']),
    'copy': lambda doc, op: _op_copy(doc, op['from'], op['path']),
    'test': lambda doc, op: _op_test(doc, op['path'], op['value']),
}

# ----------------------------------------------------------------------
# Main routine
# ----------------------------------------------------------------------
def apply_patch(doc, patch):
    """Apply a list of patch operations to *doc* atomically."""
    if not isinstance(patch, list):
        raise PatchError('Patch must be a JSON array')
    # Work on a deep copy to guarantee atomicity
    result = copy.deepcopy(doc)
    for op in patch:
        if not isinstance(op, dict):
            raise PatchError('Each operation must be an object')
        if 'op' not in op or 'path' not in op:
            raise PatchError('Operation missing required "op" or "path" member')
        operation = op['op']
        if operation not in _OP_HANDLERS:
            raise PatchError(f'Unknown operation: {operation!r}')
        # Validate required members for each op
        if operation in ('add', 'replace', 'test') and 'value' not in op:
            raise PatchError(f'"{operation}" operation missing required "value" member')
        if operation in ('move', 'copy') and 'from' not in op:
            raise PatchError(f'"{operation}" operation missing required "from" member')
        # Dispatch
        result = _OP_HANDLERS[operation](result, op)
    return result

def main():
    if len(sys.argv) != 3:
        print(f'Usage: {sys.argv[0]} DOC.json PATCH.json', file=sys.stderr)
        sys.exit(1)
    doc_path, patch_path = sys.argv[1], sys.argv[2]
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
        with open(patch_path, 'r', encoding='utf-8') as f:
            patch = json.load(f)
        result = apply_patch(doc, patch)
        json.dump(result, sys.stdout, separators=(',', ':'))
        sys.stdout.write('\n')
    except PatchError as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Any unexpected error is also treated as a patch error
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
