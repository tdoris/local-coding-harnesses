#!/usr/bin/env python3
"""jpatch.py – apply a JSON Patch (RFC 6902) to a JSON document.
Usage: python3 jpatch.py DOC.json PATCH.json
"""

import sys, json, copy

def _error(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)

def decode_pointer(ptr: str):
    if ptr == "":
        return []
    if not ptr.startswith('/'):
        raise ValueError('JSON pointer must be "" or start with "/"')
    parts = ptr.split('/')[1:]
    # decode per RFC 6901 – ~1 before ~0
    def dec(p: str) -> str:
        return p.replace('~1', '/').replace('~0', '~')
    return [dec(p) for p in parts]

def _is_canonical_index(tok: str):
    # non‑negative integer without leading zeros (except "0")
    return tok.isdigit() and (tok == "0" or not tok.startswith('0'))

def _resolve(doc, tokens, *, create_parent=False, for_add=False):
    """Return (container, final_token).
    If create_parent is True, the path up to the last token must exist (used for add).
    For add, the final token may be '-' for array appends.
    """
    cur = doc
    for i, tok in enumerate(tokens[:-1]):
        if isinstance(cur, dict):
            if tok not in cur:
                raise KeyError(f"object does not contain key {tok!r}")
            cur = cur[tok]
        elif isinstance(cur, list):
            if not _is_canonical_index(tok):
                raise ValueError(f"invalid array index {tok!r}")
            idx = int(tok)
            if idx < 0 or idx >= len(cur):
                raise IndexError(f"array index out of range {idx}")
            cur = cur[idx]
        else:
            raise TypeError('encountered non‑container while traversing')
    # now cur is the parent container
    final = tokens[-1] if tokens else ''
    return cur, final

def _get_target(doc, tokens):
    if not tokens:
        return doc
    parent, final = _resolve(doc, tokens)
    if isinstance(parent, dict):
        if final not in parent:
            raise KeyError
        return parent[final]
    elif isinstance(parent, list):
        if final == '-':
            raise ValueError('"-" is not valid for existing target')
        if not _is_canonical_index(final):
            raise ValueError('invalid array index')
        idx = int(final)
        if idx < 0 or idx >= len(parent):
            raise IndexError
        return parent[idx]
    else:
        raise TypeError('parent is neither dict nor list')

def _set_in_parent(parent, token, value, op_type='add'):
    if isinstance(parent, dict):
        # add replaces existing member or inserts at end
        parent[token] = value
    elif isinstance(parent, list):
        if token == '-':
            parent.append(value)
        else:
            if not _is_canonical_index(token):
                raise ValueError('invalid array index')
            idx = int(token)
            if op_type == 'add':
                if idx < 0 or idx > len(parent):
                    raise IndexError('add index out of range')
                parent.insert(idx, value)
            else:
                # replace/remove expects existing index
                if idx < 0 or idx >= len(parent):
                    raise IndexError('index out of range')
                parent[idx] = value
    else:
        raise TypeError('parent is neither dict nor list')

def _remove_in_parent(parent, token):
    if isinstance(parent, dict):
        del parent[token]
    elif isinstance(parent, list):
        if not _is_canonical_index(token):
            raise ValueError('invalid array index for removal')
        idx = int(token)
        if idx < 0 or idx >= len(parent):
            raise IndexError('removal index out of range')
        del parent[idx]
    else:
        raise TypeError('parent is neither dict nor list')

def json_equal(a, b):
    # booleans must match type
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    # numbers (int/float) compare by numeric value
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    # dicts: compare key order‑independent but values recursively
    if isinstance(a, dict) and isinstance(b, dict):
        if list(a.keys()) != list(b.keys()):
            # order does not matter for equality
            if set(a.keys()) != set(b.keys()):
                return False
        for k in a:
            if k not in b:
                return False
            if not json_equal(a[k], b[k]):
                return False
        return True
    # lists: order matters
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(json_equal(x, y) for x, y in zip(a, b))
    # everything else must match type and value exactly
    return type(a) is type(b) and a == b

def apply_patch(doc, patch):
    if not isinstance(patch, list):
        raise ValueError('patch must be an array')
    # work on a mutable copy
    result = doc
    for op in patch:
        if not isinstance(op, dict):
            raise ValueError('operation must be an object')
        if 'op' not in op or 'path' not in op:
            raise ValueError('operation missing required members')
        operation = op['op']
        path = op['path']
        try:
            tokens = decode_pointer(path)
        except Exception as e:
            raise ValueError('malformed pointer')
        if operation == 'add':
            if 'value' not in op:
                raise ValueError('add missing value')
            value = op['value']
            if tokens == []:
                # replace whole document
                result = value
                continue
            parent, token = _resolve(result, tokens, create_parent=True, for_add=True)
            # for dict, token is key; for list, token may be index or '-'
            if isinstance(parent, dict):
                # token is key (any string)
                parent[token] = value
            elif isinstance(parent, list):
                if token == '-':
                    parent.append(value)
                else:
                    if not _is_canonical_index(token):
                        raise ValueError('invalid array index')
                    idx = int(token)
                    if idx < 0 or idx > len(parent):
                        raise IndexError('add index out of range')
                    parent.insert(idx, value)
            else:
                raise TypeError('parent not container')
        elif operation == 'remove':
            if tokens == []:
                raise ValueError('cannot remove whole document')
            parent, token = _resolve(result, tokens)
            # ensure target exists
            _remove_in_parent(parent, token)
        elif operation == 'replace':
            if 'value' not in op:
                raise ValueError('replace missing value')
            value = op['value']
            if tokens == []:
                result = value
                continue
            parent, token = _resolve(result, tokens)
            # must exist
            if isinstance(parent, dict):
                if token not in parent:
                    raise KeyError
                parent[token] = value
            elif isinstance(parent, list):
                if not _is_canonical_index(token):
                    raise ValueError('invalid array index')
                idx = int(token)
                if idx < 0 or idx >= len(parent):
                    raise IndexError('replace index out of range')
                parent[idx] = value
            else:
                raise TypeError('parent not container')
        elif operation == 'move':
            if 'from' not in op:
                raise ValueError('move missing from')
            from_path = op['from']
            try:
                from_tokens = decode_pointer(from_path)
            except Exception:
                raise ValueError('malformed from pointer')
            # check moving into own child
            if tokens[:len(from_tokens)] == from_tokens and len(tokens) > len(from_tokens):
                raise ValueError('move into own child')
            # resolve source
            src_parent, src_tok = _resolve(result, from_tokens)
            if isinstance(src_parent, dict):
                if src_tok not in src_parent:
                    raise KeyError
                val = src_parent[src_tok]
                # remove
                del src_parent[src_tok]
            elif isinstance(src_parent, list):
                if not _is_canonical_index(src_tok):
                    raise ValueError('invalid array index in from')
                idx = int(src_tok)
                if idx < 0 or idx >= len(src_parent):
                    raise IndexError('from index out of range')
                val = src_parent[idx]
                del src_parent[idx]
            else:
                raise TypeError('source parent not container')
            # add to destination
            if tokens == []:
                result = val
                continue
            dst_parent, dst_tok = _resolve(result, tokens, create_parent=True, for_add=True)
            if isinstance(dst_parent, dict):
                dst_parent[dst_tok] = val
            elif isinstance(dst_parent, list):
                if dst_tok == '-':
                    dst_parent.append(val)
                else:
                    if not _is_canonical_index(dst_tok):
                        raise ValueError('invalid array index in destination')
                    idx = int(dst_tok)
                    if idx < 0 or idx > len(dst_parent):
                        raise IndexError('destination index out of range')
                    dst_parent.insert(idx, val)
            else:
                raise TypeError('destination parent not container')
        elif operation == 'copy':
            if 'from' not in op:
                raise ValueError('copy missing from')
            from_path = op['from']
            try:
                from_tokens = decode_pointer(from_path)
            except Exception:
                raise ValueError('malformed from pointer')
            src_parent, src_tok = _resolve(result, from_tokens)
            if isinstance(src_parent, dict):
                if src_tok not in src_parent:
                    raise KeyError
                val = copy.deepcopy(src_parent[src_tok])
            elif isinstance(src_parent, list):
                if not _is_canonical_index(src_tok):
                    raise ValueError('invalid array index in from')
                idx = int(src_tok)
                if idx < 0 or idx >= len(src_parent):
                    raise IndexError('from index out of range')
                val = copy.deepcopy(src_parent[idx])
            else:
                raise TypeError('source parent not container')
            # add to destination
            if tokens == []:
                result = val
                continue
            dst_parent, dst_tok = _resolve(result, tokens, create_parent=True, for_add=True)
            if isinstance(dst_parent, dict):
                dst_parent[dst_tok] = val
            elif isinstance(dst_parent, list):
                if dst_tok == '-':
                    dst_parent.append(val)
                else:
                    if not _is_canonical_index(dst_tok):
                        raise ValueError('invalid array index in destination')
                    idx = int(dst_tok)
                    if idx < 0 or idx > len(dst_parent):
                        raise IndexError('destination index out of range')
                    dst_parent.insert(idx, val)
            else:
                raise TypeError('destination parent not container')
        elif operation == 'test':
            if 'value' not in op:
                raise ValueError('test missing value')
            expected = op['value']
            actual = _get_target(result, tokens)
            if not json_equal(actual, expected):
                raise ValueError('test operation failed')
        else:
            raise ValueError(f'unknown operation {operation!r}')
    return result

def main():
    if len(sys.argv) != 3:
        _error('Usage: python3 jpatch.py DOC.json PATCH.json')
    doc_path, patch_path = sys.argv[1], sys.argv[2]
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
        with open(patch_path, 'r', encoding='utf-8') as f:
            patch = json.load(f)
        result = apply_patch(doc, patch)
    except Exception as e:
        _error(str(e))
    # success – print result
    json.dump(result, sys.stdout, separators=(',', ':'))
    sys.stdout.write('\n')

if __name__ == '__main__':
    main()
