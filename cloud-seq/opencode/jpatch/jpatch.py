#!/usr/bin/env python3
"""jpatch: apply a JSON Patch (RFC 6902) to a JSON document.
Usage: python3 jpatch.py DOC.json PATCH.json
"""

import sys, json, copy

def _unescape(token: str) -> str:
    # RFC 6901 unescaping: ~1 -> /, ~0 -> ~ (decode ~1 before ~0)
    return token.replace('~1', '/').replace('~0', '~')

def _split_pointer(ptr: str):
    if ptr == "":
        return []
    if not ptr.startswith('/'):
        raise ValueError('JSON Pointer must be empty string or start with "/"')
    parts = ptr.lstrip('/').split('/')
    return [_unescape(p) for p in parts]

def _is_int(s: str) -> bool:
    # No leading zeros unless exactly "0"
    if not s.isdigit():
        return False
    return s == "0" or not s.startswith('0')

def _resolve(doc, ptr_parts, create_parent=False, allow_dash=False):
    """Resolve pointer to (parent, token) where token is last part.
    If create_parent is True, the parent must exist but the final token may be missing.
    allow_dash permits token '-' for array append.
    Returns (parent, token, is_last_exists) where is_last_exists indicates if token presently exists.
    """
    cur = doc
    for i, part in enumerate(ptr_parts[:-1]):
        if isinstance(cur, dict):
            if part not in cur:
                raise KeyError(f'Path component "{part}" not found')
            cur = cur[part]
        elif isinstance(cur, list):
            if not _is_int(part):
                raise ValueError('Array index must be a non‑negative integer')
            idx = int(part)
            if idx < 0 or idx >= len(cur):
                raise IndexError('Array index out of range')
            cur = cur[idx]
        else:
            raise TypeError('Cannot traverse into non‑container')
    if not ptr_parts:
        # whole document
        return (None, None, True)
    last = ptr_parts[-1]
    if isinstance(cur, dict):
        exists = last in cur
        return (cur, last, exists)
    elif isinstance(cur, list):
        if allow_dash and last == '-':
            return (cur, '-', True)
        if not _is_int(last):
            raise ValueError('Array index must be a non‑negative integer')
        idx = int(last)
        exists = 0 <= idx < len(cur)
        return (cur, idx, exists)
    else:
        raise TypeError('Cannot resolve pointer against non‑container')

def _get_value(doc, ptr):
    parts = _split_pointer(ptr)
    if not parts:
        return doc
    parent, token, exists = _resolve(doc, parts)
    if not exists:
        raise KeyError('Target does not exist')
    if isinstance(parent, dict):
        return parent[token]
    else:
        return parent[token]

def _json_equal(a, b):
    # Equality per RFC 6902 test operation: objects ignore key order, arrays order matters, numbers numeric, bool strict, null strict
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_json_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b

def apply_patch(doc, patch):
    # Work on a deepcopy to ensure atomicity
    working = copy.deepcopy(doc)
    for op_idx, operation in enumerate(patch):
        if not isinstance(operation, dict):
            raise ValueError('Operation must be an object')
        if 'op' not in operation or 'path' not in operation:
            raise ValueError('Missing required member "op" or "path"')
        op = operation['op']
        path = operation['path']
        try:
            parts = _split_pointer(path)
        except Exception as e:
            raise ValueError('Malformed JSON Pointer')

        if op == 'add':
            if 'value' not in operation:
                raise ValueError('add operation missing "value"')
            value = operation['value']
            parent, token, _ = _resolve(working, parts, create_parent=True, allow_dash=True)
            if parent is None:
                # adding to the whole document replaces it
                working = value
                continue
            if isinstance(parent, dict):
                # replace if exists, else insert (preserves order)
                parent[token] = value
            else:  # list
                if token == '-':
                    parent.append(value)
                else:
                    idx = token
                    if idx < 0 or idx > len(parent):
                        raise IndexError('Array index out of range for add')
                    parent.insert(idx, value)
        elif op == 'remove':
            parent, token, exists = _resolve(working, parts)
            if not exists:
                raise KeyError('remove target does not exist')
            if parent is None:
                # removing whole document makes it null? RFC disallows; treat as error
                raise ValueError('Cannot remove the whole document')
            if isinstance(parent, dict):
                del parent[token]
            else:
                del parent[token]
        elif op == 'replace':
            if 'value' not in operation:
                raise ValueError('replace operation missing "value"')
            value = operation['value']
            parent, token, exists = _resolve(working, parts)
            if not exists:
                raise KeyError('replace target does not exist')
            if isinstance(parent, dict):
                parent[token] = value
            else:
                parent[token] = value
        elif op == 'move':
            if 'from' not in operation:
                raise ValueError('move operation missing "from"')
            from_path = operation['from']
            # detect moving into own child
            if path.startswith(from_path.rstrip('/') + '/'):
                raise ValueError('move into own child')
            # get value
            val = _get_value(working, from_path)
            # remove source
            from_parts = _split_pointer(from_path)
            f_parent, f_token, f_exists = _resolve(working, from_parts)
            if not f_exists:
                raise KeyError('move source does not exist')
            if isinstance(f_parent, dict):
                del f_parent[f_token]
            else:
                del f_parent[f_token]
            # add to destination
            parent, token, _ = _resolve(working, parts, create_parent=True, allow_dash=True)
            if parent is None:
                working = val
                continue
            if isinstance(parent, dict):
                parent[token] = val
            else:
                if token == '-':
                    parent.append(val)
                else:
                    idx = token
                    if idx < 0 or idx > len(parent):
                        raise IndexError('Array index out of range for move')
                    parent.insert(idx, val)
        elif op == 'copy':
            if 'from' not in operation:
                raise ValueError('copy operation missing "from"')
            from_path = operation['from']
            val = copy.deepcopy(_get_value(working, from_path))
            parent, token, _ = _resolve(working, parts, create_parent=True, allow_dash=True)
            if parent is None:
                working = val
                continue
            if isinstance(parent, dict):
                parent[token] = val
            else:
                if token == '-':
                    parent.append(val)
                else:
                    idx = token
                    if idx < 0 or idx > len(parent):
                        raise IndexError('Array index out of range for copy')
                    parent.insert(idx, val)
        elif op == 'test':
            if 'value' not in operation:
                raise ValueError('test operation missing "value"')
            expected = operation['value']
            actual = _get_value(working, path)
            if not _json_equal(actual, expected):
                raise ValueError('test operation failed')
        else:
            raise ValueError(f'unknown operation "{op}"')
    return working

def main():
    if len(sys.argv) != 3:
        sys.stderr.write('Usage: jpatch.py DOC.json PATCH.json\n')
        sys.exit(1)
    doc_path, patch_path = sys.argv[1], sys.argv[2]
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
        with open(patch_path, 'r', encoding='utf-8') as f:
            patch = json.load(f)
    except Exception as e:
        sys.stderr.write(str(e) + '\n')
        sys.exit(1)
    if not isinstance(patch, list):
        sys.stderr.write('Patch must be a JSON array\n')
        sys.exit(1)
    try:
        result = apply_patch(doc, patch)
    except Exception as e:
        sys.stderr.write(str(e) + '\n')
        sys.exit(1)
    json.dump(result, sys.stdout, separators=(',', ':'), ensure_ascii=False)
    sys.stdout.write('\n')

if __name__ == '__main__':
    main()
