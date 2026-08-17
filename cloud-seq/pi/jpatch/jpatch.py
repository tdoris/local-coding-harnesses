#!/usr/bin/env python3
"""jpatch.py – Apply a JSON Patch (RFC 6902) to a JSON document.
Usage: python3 jpatch.py DOC.json PATCH.json
"""
import sys, json, copy

def error(msg: str):
    print(msg, file=sys.stderr)
    sys.exit(1)

def decode_pointer(ptr: str):
    if ptr == "":
        return []
    if not ptr.startswith('/'):
        error(f"Invalid JSON Pointer (must start with '/'): {ptr}")
    parts = ptr.split('/')[1:]
    # decode ~1 then ~0
    res = []
    for p in parts:
        p = p.replace('~1', '/').replace('~0', '~')
        res.append(p)
    return res

def is_canonical_index(tok: str):
    # integer without leading zeros (except 0)
    return tok.isdigit() and (tok == '0' or not tok.startswith('0'))

def get_parent_and_key(doc, tokens, allow_missing_target=False, for_add=False):
    """Traverse tokens up to the penultimate, returning (parent, last_token).
    If allow_missing_target is False, the final token must refer to an existing
    value (except when for_add is True, where parent must exist but the final
    token may be absent).
    """
    cur = doc
    for i, tok in enumerate(tokens[:-1]):
        if isinstance(cur, list):
            if not is_canonical_index(tok):
                error(f"Invalid array index '{tok}' in pointer")
            idx = int(tok)
            if idx < 0 or idx >= len(cur):
                error(f"Array index out of range: {idx}")
            cur = cur[idx]
        elif isinstance(cur, dict):
            if tok not in cur:
                error(f"Object member '{tok}' does not exist")
            cur = cur[tok]
        else:
            error("Cannot traverse into non-container")
    # now cur is the parent
    last = tokens[-1] if tokens else ''
    return cur, last

def resolve(doc, tokens):
    """Return the value at tokens, raising error if missing or malformed."""
    cur = doc
    for tok in tokens:
        if isinstance(cur, list):
            if not is_canonical_index(tok):
                error(f"Invalid array index '{tok}' in pointer")
            idx = int(tok)
            if idx < 0 or idx >= len(cur):
                error(f"Array index out of range: {idx}")
            cur = cur[idx]
        elif isinstance(cur, dict):
            if tok not in cur:
                error(f"Object member '{tok}' does not exist")
            cur = cur[tok]
        else:
            error("Cannot traverse into non-container")
    return cur

def test_equal(a, b):
    # numbers compare by value, bools distinct, dict order ignored, list order matters
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(test_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(test_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b

def apply_patch(doc, patch):
    # work on a deep copy to avoid side‑effects on failure
    state = copy.deepcopy(doc)
    for op_obj in patch:
        if not isinstance(op_obj, dict):
            error("Patch operation is not an object")
        op = op_obj.get('op')
        path = op_obj.get('path')
        if op is None or path is None:
            error("Operation missing required 'op' or 'path'")
        if not isinstance(op, str) or not isinstance(path, str):
            error("'op' and 'path' must be strings")
        tokens = decode_pointer(path)
        if op == 'add':
            if 'value' not in op_obj:
                error("'add' operation missing 'value'")
            value = op_obj['value']
            if tokens == []:
                # replace whole document
                state = value
                continue
            parent, last = get_parent_and_key(state, tokens, for_add=True)
            if isinstance(parent, list):
                if last == '-':
                    idx = len(parent)
                else:
                    if not is_canonical_index(last):
                        error(f"Invalid array index '{last}' for add")
                    idx = int(last)
                    if idx < 0 or idx > len(parent):
                        error(f"Array index out of range for add: {idx}")
                parent.insert(idx, value)
            elif isinstance(parent, dict):
                parent[last] = value
            else:
                error("Add target parent is not an array or object")
        elif op == 'remove':
            if tokens == []:
                error("Cannot remove the whole document")
            parent, last = get_parent_and_key(state, tokens)
            if isinstance(parent, list):
                if not is_canonical_index(last):
                    error(f"Invalid array index '{last}' for remove")
                idx = int(last)
                if idx < 0 or idx >= len(parent):
                    error(f"Array index out of range for remove: {idx}")
                parent.pop(idx)
            elif isinstance(parent, dict):
                if last not in parent:
                    error(f"Object member '{last}' does not exist for remove")
                del parent[last]
            else:
                error("Remove target parent is not an array or object")
        elif op == 'replace':
            if 'value' not in op_obj:
                error("'replace' operation missing 'value'")
            value = op_obj['value']
            if tokens == []:
                state = value
                continue
            parent, last = get_parent_and_key(state, tokens)
            if isinstance(parent, list):
                if not is_canonical_index(last):
                    error(f"Invalid array index '{last}' for replace")
                idx = int(last)
                if idx < 0 or idx >= len(parent):
                    error(f"Array index out of range for replace: {idx}")
                parent[idx] = value
            elif isinstance(parent, dict):
                if last not in parent:
                    error(f"Object member '{last}' does not exist for replace")
                parent[last] = value
            else:
                error("Replace target parent is not an array or object")
        elif op == 'move':
            from_path = op_obj.get('from')
            if from_path is None:
                error("'move' operation missing 'from'")
            if not isinstance(from_path, str):
                error("'from' must be a string")
            from_tokens = decode_pointer(from_path)
            # obtain value
            value = resolve(state, from_tokens)
            # check moving into own child
            if tokens[:len(from_tokens)] == from_tokens and len(tokens) > len(from_tokens):
                error("Cannot move a value into one of its own children")
            # perform remove then add (add uses same semantics)
            # remove source
            parent_src, last_src = get_parent_and_key(state, from_tokens)
            if isinstance(parent_src, list):
                idx_src = int(last_src)
                parent_src.pop(idx_src)
            else:
                del parent_src[last_src]
            # add to destination
            if tokens == []:
                state = value
            else:
                parent_dst, last_dst = get_parent_and_key(state, tokens, for_add=True)
                if isinstance(parent_dst, list):
                    if last_dst == '-':
                        idx_dst = len(parent_dst)
                    else:
                        if not is_canonical_index(last_dst):
                            error(f"Invalid array index '{last_dst}' for move destination")
                        idx_dst = int(last_dst)
                        if idx_dst < 0 or idx_dst > len(parent_dst):
                            error(f"Array index out of range for move destination: {idx_dst}")
                    parent_dst.insert(idx_dst, value)
                else:
                    parent_dst[last_dst] = value
        elif op == 'copy':
            from_path = op_obj.get('from')
            if from_path is None:
                error("'copy' operation missing 'from'")
            from_tokens = decode_pointer(from_path)
            value = copy.deepcopy(resolve(state, from_tokens))
            if tokens == []:
                state = value
            else:
                parent_dst, last_dst = get_parent_and_key(state, tokens, for_add=True)
                if isinstance(parent_dst, list):
                    if last_dst == '-':
                        idx_dst = len(parent_dst)
                    else:
                        if not is_canonical_index(last_dst):
                            error(f"Invalid array index '{last_dst}' for copy destination")
                        idx_dst = int(last_dst)
                        if idx_dst < 0 or idx_dst > len(parent_dst):
                            error(f"Array index out of range for copy destination: {idx_dst}")
                    parent_dst.insert(idx_dst, value)
                else:
                    parent_dst[last_dst] = value
        elif op == 'test':
            if 'value' not in op_obj:
                error("'test' operation missing 'value'")
            expected = op_obj['value']
            actual = resolve(state, tokens) if tokens else state
            if not test_equal(actual, expected):
                error("Test operation failed")
        else:
            error(f"Unknown operation '{op}'")
    return state

def main():
    if len(sys.argv) != 3:
        error("Usage: python3 jpatch.py DOC.json PATCH.json")
    doc_path, patch_path = sys.argv[1], sys.argv[2]
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
        with open(patch_path, 'r', encoding='utf-8') as f:
            patch = json.load(f)
    except Exception as e:
        error(str(e))
    if not isinstance(patch, list):
        error("Patch is not an array")
    result = apply_patch(doc, patch)
    json.dump(result, sys.stdout, separators=(',', ':'), ensure_ascii=False)

if __name__ == '__main__':
    main()
