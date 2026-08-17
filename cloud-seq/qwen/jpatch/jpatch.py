#!/usr/bin/env python3
"""jpatch.py – apply a JSON Patch (RFC 6902) to a JSON document.

Usage: python3 jpatch.py DOC.json PATCH.json

Prints the patched document to stdout on success, exits with code 0.
On any error prints a message to stderr, no stdout, exits with code 1.
"""

import sys
import json
import copy
import re

# ---------- Helper functions ----------

def _error(msg: str) -> None:
    """Print error message to stderr and exit with code 1."""
    print(msg, file=sys.stderr)
    sys.exit(1)

def _decode_reference(token: str) -> str:
    """Decode a reference token per RFC 6901 ("~1" -> "/", "~0" -> "~").
    The order of decoding is important: first replace "~1" then "~0".
    """
    return token.replace('~1', '/').replace('~0', '~')

def _parse_path(path: str):
    """Parse a JSON Pointer path into a list of decoded reference tokens.
    Raises ValueError if the path is malformed.
    """
    if path == "":
        return []  # points to the whole document
    if not path.startswith('/'):
        raise ValueError('JSON pointer must be "" or start with "/"')
    # split on '/', ignore the first empty element
    parts = path.split('/')[1:]
    return [_decode_reference(p) for p in parts]

def _is_valid_array_index(idx_str: str, allow_dash: bool = False):
    """Return True if idx_str is a valid array index token.
    """
    if allow_dash and idx_str == '-':
        return True
    # No leading zeros unless the number is exactly "0"
    if not re.fullmatch(r'(0|[1-9][0-9]*)', idx_str):
        return False
    return True

def _get_parent(container, tokens, create_missing=False, for_add=False):
    """Traverse container according to tokens except the last one.
    Returns (parent, last_token).
    If create_missing is True, intermediate objects are created as empty dicts.
    If for_add is True, the final parent must exist but the last token may be new.
    Raises KeyError or IndexError on missing components.
    """
    current = container
    for i, tok in enumerate(tokens[:-1]):
        if isinstance(current, dict):
            if tok not in current:
                if create_missing:
                    current[tok] = {}
                else:
                    raise KeyError(tok)
            current = current[tok]
        elif isinstance(current, list):
            if not _is_valid_array_index(tok):
                raise ValueError('Invalid array index')
            idx = int(tok)
            if idx < 0 or idx >= len(current):
                raise IndexError(tok)
            current = current[idx]
        else:
            raise TypeError('Parent is neither object nor array')
    return current, tokens[-1] if tokens else (current, None)

def _resolve(container, tokens):
    """Resolve a JSON Pointer to a value. Raises if not found.
    """
    if not tokens:
        return container
    current = container
    for tok in tokens:
        if isinstance(current, dict):
            if tok not in current:
                raise KeyError(tok)
            current = current[tok]
        elif isinstance(current, list):
            if not _is_valid_array_index(tok):
                raise ValueError('Invalid array index')
            idx = int(tok)
            if idx < 0 or idx >= len(current):
                raise IndexError(tok)
            current = current[idx]
        else:
            raise TypeError('Encountered non-traversable element')
    return current

def _json_equal(a, b):
    """Compare two JSON values for the `test` operation.
    - Numbers compare by numeric value (1 == 1.0)
    - Booleans must have same type
    - Strings, null, etc. compare by equality
    - Objects compare unordered (key order ignored) and values recursively
    - Arrays compare order and values recursively
    """
    # Bool handling: ensure same type
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    # Numbers
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    # Dictionaries (ignore key order for equality)
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_json_equal(a[k], b[k]) for k in a)
    # Lists (order matters)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_json_equal(x, y) for x, y in zip(a, b))
    # Fallback to strict type equality
    return type(a) is type(b) and a == b

# ---------- Operation implementations ----------

def op_add(doc, path, value):
    tokens = _parse_path(path)
    if not tokens:
        # replace whole document
        return value
    parent, last = _get_parent(doc, tokens, create_missing=False, for_add=True)
    if isinstance(parent, dict):
        # add or replace member
        parent[last] = value
    elif isinstance(parent, list):
        # last must be an index or '-'
        if not _is_valid_array_index(last, allow_dash=True):
            raise ValueError('Invalid array index for add')
        if last == '-':
            parent.append(value)
        else:
            idx = int(last)
            if idx > len(parent):
                raise IndexError('Array index out of range for add')
            # Insertion shifts later elements
            parent.insert(idx, value)
    else:
        raise TypeError('Parent is neither object nor array for add')
    return doc

def op_remove(doc, path):
    tokens = _parse_path(path)
    if not tokens:
        raise ValueError('Remove on whole document is not allowed')
    parent, last = _get_parent(doc, tokens, create_missing=False)
    if isinstance(parent, dict):
        if last not in parent:
            raise KeyError('Member to remove does not exist')
        del parent[last]
    elif isinstance(parent, list):
        if not _is_valid_array_index(last):
            raise ValueError('Invalid array index for remove')
        idx = int(last)
        if idx < 0 or idx >= len(parent):
            raise IndexError('Array index out of range for remove')
        del parent[idx]
    else:
        raise TypeError('Parent is neither object nor array for remove')
    return doc

def op_replace(doc, path, value):
    # replace is like add but target must exist
    tokens = _parse_path(path)
    if not tokens:
        return value
    parent, last = _get_parent(doc, tokens, create_missing=False)
    if isinstance(parent, dict):
        if last not in parent:
            raise KeyError('Member to replace does not exist')
        parent[last] = value
    elif isinstance(parent, list):
        if not _is_valid_array_index(last):
            raise ValueError('Invalid array index for replace')
        idx = int(last)
        if idx < 0 or idx >= len(parent):
            raise IndexError('Array index out of range for replace')
        parent[idx] = value
    else:
        raise TypeError('Parent is neither object nor array for replace')
    return doc

def op_move(doc, from_path, path):
    # Check for moving into own child
    if from_path == path or (path.startswith(from_path + '/') and from_path != ""):
        raise ValueError('Cannot move a location into one of its own children')
    # Get value from source
    from_tokens = _parse_path(from_path)
    value = _resolve(doc, from_tokens)
    # Remove from source
    doc = op_remove(doc, from_path)
    # Add to destination (deep copy)
    doc = op_add(doc, path, copy.deepcopy(value))
    return doc

def op_copy(doc, from_path, path):
    from_tokens = _parse_path(from_path)
    value = _resolve(doc, from_tokens)
    doc = op_add(doc, path, copy.deepcopy(value))
    return doc

def op_test(doc, path, value):
    tokens = _parse_path(path)
    target = _resolve(doc, tokens) if tokens else doc
    if not _json_equal(target, value):
        raise ValueError('Test operation failed')
    return doc

# Mapping of operation names to handler functions
_OP_HANDLERS = {
    'add': lambda d, o: op_add(d, o['path'], o['value']),
    'remove': lambda d, o: op_remove(d, o['path']),
    'replace': lambda d, o: op_replace(d, o['path'], o['value']),
    'move': lambda d, o: op_move(d, o['from'], o['path']),
    'copy': lambda d, o: op_copy(d, o['from'], o['path']),
    'test': lambda d, o: op_test(d, o['path'], o['value']),
}

def apply_patch(document, patch_ops):
    # Work on a deep copy to guarantee atomicity
    doc = copy.deepcopy(document)
    for op in patch_ops:
        if not isinstance(op, dict):
            raise ValueError('Patch operation is not an object')
        if 'op' not in op or 'path' not in op:
            raise ValueError('Missing required member in operation')
        op_name = op['op']
        handler = _OP_HANDLERS.get(op_name)
        if handler is None:
            raise ValueError('Unknown operation')
        # Validate required members for each op (value or from)
        if op_name in ('add', 'replace', 'test') and 'value' not in op:
            raise ValueError('Missing required member "value"')
        if op_name in ('move', 'copy') and 'from' not in op:
            raise ValueError('Missing required member "from"')
        doc = handler(doc, op)
    return doc

# ---------- Main execution ----------

def main():
    if len(sys.argv) != 3:
        _error('Usage: python3 jpatch.py DOC.json PATCH.json')
    doc_path, patch_path = sys.argv[1], sys.argv[2]
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            document = json.load(f)
    except Exception as e:
        _error(f'Failed to read document: {e}')
    try:
        with open(patch_path, 'r', encoding='utf-8') as f:
            patch = json.load(f)
    except Exception as e:
        _error(f'Failed to read patch: {e}')
    if not isinstance(patch, list):
        _error('Patch is not an array')
    try:
        result = apply_patch(document, patch)
    except Exception as e:
        _error(str(e))
    # Successful – output result JSON
    json.dump(result, sys.stdout, separators=(',', ':'), ensure_ascii=False)
    sys.stdout.write('\n')
    sys.exit(0)

if __name__ == '__main__':
    main()
