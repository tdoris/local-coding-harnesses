#!/usr/bin/env python3
"""jpatch - apply a JSON Patch (RFC 6902) to a JSON document.

Usage:
    python3 jpatch.py DOC.json PATCH.json

Prints the resulting JSON document to stdout on success (exit code 0).
On any error prints a message to stderr, nothing to stdout and exits with code 1.
"""

import sys
import json
import copy

# Helper functions for JSON Pointer handling

def _decode_pointer(ptr: str) -> list:
    """Decode a JSON Pointer string into a list of reference tokens.
    Follows RFC 6901 decoding rules: ~1 => '/', ~0 => '~', performed left to right.
    """
    if not isinstance(ptr, str):
        raise TypeError('JSON Pointer must be a string')
    if ptr == "":
        return []
    if not ptr.startswith('/'):
        raise ValueError('JSON Pointer must be "" or start with "/"')
    # split and decode each reference token
    parts = ptr.split('/')[1:]
    decoded = []
    for p in parts:
        # decode ~1 before ~0 as spec
        p = p.replace('~1', '/').replace('~0', '~')
        decoded.append(p)
    return decoded


def _is_valid_array_index(token: str, allow_dash: bool = False) -> bool:
    if allow_dash and token == '-':
        return True
    if not token.isdigit():
        return False
    # canonical decimal: no leading zeros unless the token is exactly "0"
    return token == '0' or not token.startswith('0')


def _traverse(doc, tokens, create_parent=False):
    """Traverse the document following tokens.
    Returns (parent, last_token) where parent is the container (dict or list) of the target.
    If tokens is empty, returns (None, None) indicating the document itself.
    If create_parent is True, the function will ensure that all intermediate containers exist (used for add).
    """
    if not tokens:
        return (None, None)
    cur = doc
    for i, t in enumerate(tokens[:-1]):
        if isinstance(cur, dict):
            if t not in cur:
                raise KeyError(f'Path segment "{t}" does not exist')
            cur = cur[t]
        elif isinstance(cur, list):
            if not _is_valid_array_index(t):
                raise KeyError(f'Invalid array index "{t}"')
            idx = int(t)
            if idx < 0 or idx >= len(cur):
                raise IndexError(f'Array index out of range: {t}')
            cur = cur[idx]
        else:
            raise TypeError('Cannot traverse into non-container type')
    return (cur, tokens[-1])


def _get_target(doc, path):
    tokens = _decode_pointer(path)
    if not tokens:
        return doc
    parent, last = _traverse(doc, tokens)
    if isinstance(parent, dict):
        if last not in parent:
            raise KeyError(f'Path "{path}" does not exist')
        return parent[last]
    elif isinstance(parent, list):
        if not _is_valid_array_index(last):
            raise KeyError(f'Invalid array index "{last}"')
        idx = int(last)
        if idx < 0 or idx >= len(parent):
            raise IndexError(f'Array index out of range: {last}')
        return parent[idx]
    else:
        raise TypeError('Parent is not a container')


def _add(doc, path, value):
    tokens = _decode_pointer(path)
    if not tokens:
        # replace whole document
        return value
    parent, last = _traverse(doc, tokens, create_parent=False)
    if isinstance(parent, dict):
        # add or replace member
        parent[last] = value
    elif isinstance(parent, list):
        # array insertion
        if not _is_valid_array_index(last, allow_dash=True):
            raise KeyError(f'Invalid array index for add: "{last}"')
        if last == '-':
            parent.append(value)
        else:
            idx = int(last)
            if idx < 0 or idx > len(parent):
                raise IndexError('Array index out of range for add')
            parent.insert(idx, value)
    else:
        raise TypeError('Parent is not a container for add')
    return doc


def _remove(doc, path):
    tokens = _decode_pointer(path)
    if not tokens:
        raise ValueError('Cannot remove the whole document')
    parent, last = _traverse(doc, tokens)
    if isinstance(parent, dict):
        if last not in parent:
            raise KeyError(f'Path "{path}" does not exist for remove')
        del parent[last]
    elif isinstance(parent, list):
        if not _is_valid_array_index(last):
            raise KeyError(f'Invalid array index for remove: "{last}"')
        idx = int(last)
        if idx < 0 or idx >= len(parent):
            raise IndexError('Array index out of range for remove')
        parent.pop(idx)
    else:
        raise TypeError('Parent is not a container for remove')
    return doc


def _replace(doc, path, value):
    # replace requires target to exist
    tokens = _decode_pointer(path)
    if not tokens:
        return value
    parent, last = _traverse(doc, tokens)
    if isinstance(parent, dict):
        if last not in parent:
            raise KeyError(f'Path "{path}" does not exist for replace')
        parent[last] = value
    elif isinstance(parent, list):
        if not _is_valid_array_index(last):
            raise KeyError(f'Invalid array index for replace: "{last}"')
        idx = int(last)
        if idx < 0 or idx >= len(parent):
            raise IndexError('Array index out of range for replace')
        parent[idx] = value
    else:
        raise TypeError('Parent is not a container for replace')
    return doc


def _move(doc, from_path, path):
    # Prevent moving into own child
    if from_path == path or (path.startswith(from_path.rstrip('/') + '/') and from_path != ""):
        raise ValueError('Cannot move a location into one of its own children')
    value = _get_target(doc, from_path)
    # Deep copy as per spec
    value_copy = copy.deepcopy(value)
    # Remove source
    doc = _remove(doc, from_path)
    # Add destination (value_copy)
    doc = _add(doc, path, value_copy)
    return doc


def _copy(doc, from_path, path):
    value = _get_target(doc, from_path)
    value_copy = copy.deepcopy(value)
    doc = _add(doc, path, value_copy)
    return doc


def _test(doc, path, value):
    target = _get_target(doc, path)
    # Use JSON equality semantics: Python's == works for numbers, strings, bool, None, list order, dict unordered.
    if target != value:
        raise ValueError('Test operation failed')
    return doc


def apply_patch(document, patch_ops):
    # Work on a deep copy to ensure atomicity
    doc = copy.deepcopy(document)
    for op in patch_ops:
        if not isinstance(op, dict):
            raise TypeError('Operation is not an object')
        if 'op' not in op or 'path' not in op:
            raise KeyError('Missing required member "op" or "path"')
        operation = op['op']
        path = op['path']
        # Dispatch based on operation
        if operation == 'add':
            if 'value' not in op:
                raise KeyError('add operation missing "value"')
            doc = _add(doc, path, op['value'])
        elif operation == 'remove':
            doc = _remove(doc, path)
        elif operation == 'replace':
            if 'value' not in op:
                raise KeyError('replace operation missing "value"')
            doc = _replace(doc, path, op['value'])
        elif operation == 'move':
            if 'from' not in op:
                raise KeyError('move operation missing "from"')
            doc = _move(doc, op['from'], path)
        elif operation == 'copy':
            if 'from' not in op:
                raise KeyError('copy operation missing "from"')
            doc = _copy(doc, op['from'], path)
        elif operation == 'test':
            if 'value' not in op:
                raise KeyError('test operation missing "value"')
            doc = _test(doc, path, op['value'])
        else:
            raise ValueError(f'Unknown operation "{operation}"')
        # Unrecognized members are ignored automatically by not touching them
    return doc


def main():
    if len(sys.argv) != 3:
        print('Usage: python3 jpatch.py DOC.json PATCH.json', file=sys.stderr)
        sys.exit(1)
    doc_path, patch_path = sys.argv[1], sys.argv[2]
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            document = json.load(f)
        with open(patch_path, 'r', encoding='utf-8') as f:
            patch = json.load(f)
        if not isinstance(patch, list):
            raise TypeError('Patch is not an array')
        result = apply_patch(document, patch)
        json.dump(result, sys.stdout, separators=(',', ':'))
        sys.stdout.write('\n')
        sys.exit(0)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
