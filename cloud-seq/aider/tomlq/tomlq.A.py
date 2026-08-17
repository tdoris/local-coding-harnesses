#!/usr/bin/env python3
"""
tomlq.py – a tiny TOML subset parser that outputs JSON.

Usage:
    python3 tomlq.py FILE [KEYPATH]

* FILE      – path to a TOML file.
* KEYPATH   – optional dotted key path (e.g. "server.ports").
              If supplied, only the value at that path is printed.

Exit codes:
    0 – success
    1 – TOML parse error
    2 – KEYPATH not found
"""

import sys
import json
import re
from collections import OrderedDict

# ----------------------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------------------
def _strip_comments(line):
    """Remove comments from a line, respecting string literals."""
    in_basic = False
    in_literal = False
    i = 0
    while i < len(line):
        ch = line[i]
        if not in_basic and not in_literal:
            if ch == '#':
                return line[:i]
            if ch == '"':
                # start of basic string – check for triple quotes
                if line[i:i+3] == '"""':
                    i += 3
                    while i < len(line) and line[i:i+3] != '"""':
                        i += 1
                    i += 3
                    continue
                else:
                    in_basic = True
            elif ch == "'":
                if line[i:i+3] == "'''":
                    i += 3
                    while i < len(line) and line[i:i+3] != "'''":
                        i += 1
                    i += 3
                    continue
                else:
                    in_literal = True
        elif in_basic:
            if ch == '\\':
                i += 2
                continue
            if ch == '"':
                in_basic = False
        elif in_literal:
            if ch == "'":
                in_literal = False
        i += 1
    return line

def _unescape_basic(s):
    """Unescape a basic (\"…\") string, handling TOML escapes."""
    # First handle Unicode escapes by using unicode-escape codec
    s = s.encode('utf-8').decode('unicode_escape')
    # Then replace TOML specific escapes that differ from Python's
    s = s.replace('\\b', '\b') \
         .replace('\\t', '\t') \
         .replace('\\n', '\n') \
         .replace('\\f', '\f') \
         .replace('\\r', '\r')
    return s

def _parse_string(token, lines_iter):
    """Parse a TOML string (basic, literal, or multiline)."""
    if token.startswith('"""'):
        # multiline basic string
        content = token[3:]
        if content == '':
            # consume following lines until ending """
            gathered = []
            for line in lines_iter:
                if line.rstrip().endswith('"""'):
                    gathered.append(line.rstrip()[:-3])
                    break
                gathered.append(line.rstrip())
            content = '\n'.join(gathered)
        else:
            # closing delimiter on same line
            if content.endswith('"""'):
                content = content[:-3]
        # Trim first newline if present
        if content.startswith('\n'):
            content = content[1:]
        # Handle line‑ending backslash continuations
        content = re.sub(r'\\\r?\n[ \t]*', '', content)
        return _unescape_basic(content)
    if token.startswith("'''"):
        # multiline literal string – no escapes
        content = token[3:]
        if content == '':
            gathered = []
            for line in lines_iter:
                if line.rstrip().endswith("'''"):
                    gathered.append(line.rstrip()[:-3])
                    break
                gathered.append(line.rstrip())
            content = '\n'.join(gathered)
        else:
            if content.endswith("'''"):
                content = content[:-3]
        if content.startswith('\n'):
            content = content[1:]
        return content
    if token.startswith('"'):
        # basic string
        inner = token[1:-1]
        return _unescape_basic(inner)
    if token.startswith("'"):
        # literal string
        return token[1:-1]

def _parse_number(tok):
    """Parse integer or float literal."""
    if '_' in tok:
        clean = tok.replace('_', '')
    else:
        clean = tok
    # Hex, octal, binary integers
    if re.fullmatch(r'[+-]?0[xX][0-9a-fA-F]+', clean):
        return int(clean, 16)
    if re.fullmatch(r'0[oO][0-7]+', clean):
        return int(clean, 8)
    if re.fullmatch(r'0[bB][01]+', clean):
        return int(clean, 2)
    # Decimal integer (no leading zeros unless zero)
    if re.fullmatch(r'[+-]?[0-9]+', clean):
        if clean.lstrip('+-').startswith('0') and clean.lstrip('+-') != '0':
            raise ValueError('leading zero in decimal integer')
        return int(clean)
    # Float
    if re.fullmatch(r'[+-]?(?:[0-9][0-9_]*\.[0-9_]*|[0-9][0-9_]*\.|\.?[0-9][0-9_]*)(?:[eE][+-]?[0-9_]+)?', clean):
        return float(clean)
    raise ValueError('invalid numeric literal')

def _parse_bool(tok):
    if tok == 'true':
        return True
    if tok == 'false':
        return False
    raise ValueError('invalid boolean')

def _split_top_level(s, delim):
    """Split string s by delim, ignoring delimiters inside brackets/braces/quotes."""
    parts = []
    depth = 0
    in_basic = in_literal = False
    start = 0
    i = 0
    while i < len(s):
        ch = s[i]
        # handle strings
        if not in_basic and not in_literal:
            if ch == '"':
                if s[i:i+3] == '"""':
                    i += 3
                    while i < len(s) and s[i:i+3] != '"""':
                        i += 1
                    i += 2
                else:
                    in_basic = True
            elif ch == "'":
                if s[i:i+3] == "'''":
                    i += 3
                    while i < len(s) and s[i:i+3] != "'''":
                        i += 1
                    i += 2
                else:
                    in_literal = True
            elif ch in '[{':
                depth += 1
            elif ch in '}]':
                depth -= 1
            elif ch == delim and depth == 0:
                parts.append(s[start:i].strip())
                start = i + 1
        else:
            # inside string
            if in_basic:
                if ch == '\\':
                    i += 1  # skip escaped char
                elif ch == '"':
                    in_basic = False
            elif in_literal:
                if ch == "'":
                    in_literal = False
        i += 1
    parts.append(s[start:].strip())
    return parts

def _parse_array(s, lines_iter):
    """Parse a TOML array, possibly spanning multiple lines."""
    # Ensure surrounding brackets are stripped
    inner = s.strip()
    if inner.startswith('[') and inner.endswith(']'):
        inner = inner[1:-1]
    else:
        raise ValueError('invalid array literal')
    elements = []
    tokens = _split_top_level(inner, ',')
    for token in tokens:
        if token == '':
            continue
        elements.append(_parse_value(token, lines_iter))
    return elements

def _parse_inline_table(s, lines_iter):
    """Parse an inline table { k = v, ... }."""
    inner = s.strip()
    if inner.startswith('{') and inner.endswith('}'):
        inner = inner[1:-1]
    else:
        raise ValueError('invalid inline table')
    table = OrderedDict()
    items = _split_top_level(inner, ',')
    for item in items:
        if not item:
            continue
        if '=' not in item:
            raise ValueError('invalid inline table entry')
        k, v = item.split('=', 1)
        key = _parse_key(k.strip())
        value = _parse_value(v.strip(), lines_iter)
        if key in table:
            raise ValueError('duplicate key in inline table')
        table[key] = value
    return table

def _parse_key(raw):
    raw = raw.strip()
    if raw.startswith('"') or raw.startswith("'"):
        return _parse_string(raw, iter([]))
    else:
        return raw

def _parse_value(token, lines_iter):
    token = token.strip()
    # Strings
    if token.startswith('"') or token.startswith("'"):
        return _parse_string(token, lines_iter)
    # Arrays
    if token.startswith('['):
        return _parse_array(token, lines_iter)
    # Inline tables
    if token.startswith('{'):
        return _parse_inline_table(token, lines_iter)
    # Booleans
    if token in ('true', 'false'):
        return _parse_bool(token)
    # Numbers
    try:
        return _parse_number(token)
    except ValueError:
        raise ValueError(f'Unable to parse value: {token}')

def _set_path(root, path_parts, value):
    cur = root
    for part in path_parts[:-1]:
        if part not in cur:
            cur[part] = OrderedDict()
        elif not isinstance(cur[part], dict):
            raise ValueError('attempt to redefine non‑table as table')
        cur = cur[part]
    final = path_parts[-1]
    if final in cur:
        raise ValueError('duplicate key')
    cur[final] = value

def parse_toml(lines):
    """Parse a sequence of lines (list of str) into an OrderedDict."""
    data = OrderedDict()
    current_path = []          # list of strings
    array_table_stack = []     # for [[...]] handling
    lines_iter = iter(lines)
    for raw_line in lines_iter:
        line = _strip_comments(raw_line).strip()
        if not line:
            continue
        # Table headers
        if line.startswith('[[') and line.endswith(']]'):
            inner = line[2:-2].strip()
            parts = [p.strip() for p in _split_top_level(inner, '.')]
            path = [_parse_key(p) for p in parts]
            # Navigate to parent array
            tbl = data
            for seg in path[:-1]:
                if seg not in tbl:
                    tbl[seg] = OrderedDict()
                elif not isinstance(tbl[seg], dict):
                    raise ValueError('parent is not a table')
                tbl = tbl[seg]
            arr_name = path[-1]
            if arr_name not in tbl:
                tbl[arr_name] = []
            elif not isinstance(tbl[arr_name], list):
                raise ValueError('cannot redefine non‑array as array of tables')
            # Append new table
            new_tbl = OrderedDict()
            tbl[arr_name].append(new_tbl)
            current_path = path
            # set context to the newly created table
            data_ref = new_tbl
            continue
        if line.startswith('[') and line.endswith(']'):
            inner = line[1:-1].strip()
            parts = [p.strip() for p in _split_top_level(inner, '.')]
            path = [_parse_key(p) for p in parts]
            # Create tables along the path
            tbl = data
            for seg in path:
                if seg not in tbl:
                    tbl[seg] = OrderedDict()
                elif isinstance(tbl[seg], list):
                    raise ValueError('attempt to redefine array as table')
                elif not isinstance(tbl[seg], dict):
                    raise ValueError('duplicate key')
                tbl = tbl[seg]
            current_path = path
            data_ref = tbl
            continue
        # Key/value pair
        if '=' not in line:
            raise ValueError('invalid line (no =)')
        key_part, val_part = line.split('=', 1)
        key_str = key_part.strip()
        key_parts = [p.strip() for p in _split_top_level(key_str, '.')]
        key_path = [_parse_key(p) for p in key_parts]
        full_path = current_path + key_path
        value = _parse_value(val_part.strip(), lines_iter)
        # Insert value
        _set_path(data, full_path, value)
    return data

def _traverse_path(doc, keypath):
    parts = keypath.split('.')
    cur = doc
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            raise KeyError(p)
        cur = cur[p]
    return cur

def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print('Usage: python3 tomlq.py FILE [KEYPATH]', file=sys.stderr)
        sys.exit(1)
    file_path = sys.argv[1]
    keypath = sys.argv[2] if len(sys.argv) == 3 else None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        doc = parse_toml(lines)
    except Exception as e:
        print(f'Parse error: {e}', file=sys.stderr)
        sys.exit(1)
    try:
        if keypath:
            result = _traverse_path(doc, keypath)
        else:
            result = doc
        json.dump(result, sys.stdout, ensure_ascii=False)
        sys.stdout.write('\n')
    except KeyError:
        print(f'Key path not found: {keypath}', file=sys.stderr)
        sys.exit(2)

if __name__ == '__main__':
    main()
