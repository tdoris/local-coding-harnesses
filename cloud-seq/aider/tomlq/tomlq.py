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

class _InlineTable(OrderedDict):
    """Dictionary that originated from an inline table; further extensions are forbidden."""
    pass

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
    """Unescape a basic string, rejecting illegal escape sequences."""
    # TOML only allows: \b \t \n \f \r \" \\ \uXXXX \UXXXXXXXX
    if re.search(r'\\(?![btnfr"\\uU])', s):
        raise ValueError('invalid escape sequence')
    try:
        return s.encode('utf-8').decode('unicode_escape')
    except UnicodeDecodeError as e:
        raise ValueError(str(e))

def _parse_string(token, lines_iter):
    """Parse a TOML string (basic, literal, or multiline)."""
    # Single‑line basic string
    if token.startswith('"') and token.endswith('"'):
        return _unescape_basic(token[1:-1])
    # Single‑line literal string
    if token.startswith("'") and token.endswith("'"):
        return token[1:-1]

    # Multiline basic string
    if token.startswith('"""'):
        # Grab everything after the opening delimiter on the same line
        after = token[3:]
        parts = []
        if after:
            parts.append(after)
        # Read subsequent lines until we encounter a closing delimiter
        while True:
            try:
                nxt = next(lines_iter)
            except StopIteration:
                raise ValueError('unterminated multiline basic string')
            if '"""' in nxt:
                before, _, after = nxt.partition('"""')
                parts.append(before)
                # any content after the closing delimiter is ignored (per TOML spec)
                break
            # Keep the newline character so the backslash‑newline removal works
            parts.append(nxt)
        # Re‑assemble the string
        full = ''.join(parts)   # newlines already present in parts
        # Trim first newline if present
        if full.startswith('\n'):
            full = full[1:]
        # Remove line‑ending backslash continuations (backslash + newline + optional ws)
        full = re.sub(r'\\\n[ \t]*', '', full)
        return _unescape_basic(full)

    # Multiline literal string
    if token.startswith("'''"):
        after = token[3:]
        parts = []
        if after:
            parts.append(after)
        while True:
            try:
                nxt = next(lines_iter)
            except StopIteration:
                raise ValueError('unterminated multiline literal string')
            if "'''" in nxt:
                before, _, after = nxt.partition("'''")
                parts.append(before)
                break
            parts.append(nxt.rstrip('\n'))
        full = '\n'.join(parts)
        if full.startswith('\n'):
            full = full[1:]
        return full

    raise ValueError('invalid string literal')

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
    """Parse a TOML array, handling possible multi‑line representation."""
    # Ensure we have the full array literal (balanced brackets)
    open_brackets = s.count('[')
    close_brackets = s.count(']')
    array_str = s
    while open_brackets > close_brackets:
        try:
            nxt = next(lines_iter)
        except StopIteration:
            raise ValueError('unterminated array')
        nxt_clean = _strip_comments(nxt).strip()
        array_str += ' ' + nxt_clean
        open_brackets += nxt_clean.count('[')
        close_brackets += nxt_clean.count(']')
    inner = array_str.strip()
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

class _InlineTable(OrderedDict):
    """Dictionary that originated from an inline table; further extensions are forbidden."""
    pass


def _parse_inline_table(s, lines_iter):
    """Parse an inline table, supporting dotted keys and forbidding later extension."""
    inner = s.strip()
    if inner.startswith('{') and inner.endswith('}'):
        inner = inner[1:-1]
    else:
        raise ValueError('invalid inline table')
    table = _InlineTable()
    items = _split_top_level(inner, ',')
    for item in items:
        if not item:
            continue
        if '=' not in item:
            raise ValueError('invalid inline table entry')
        k, v = item.split('=', 1)
        # support dotted keys inside inline table
        key_parts = [p.strip() for p in _split_top_level(k.strip(), '.')]
        sub_path = [_parse_key(p) for p in key_parts]
        value = _parse_value(v.strip(), lines_iter)
        # Insert value into the inline table dict
        cur = table
        for part in sub_path[:-1]:
            if part not in cur:
                cur[part] = _InlineTable()
            elif not isinstance(cur[part], dict):
                raise ValueError('attempt to redefine non‑table as table')
            cur = cur[part]
        final = sub_path[-1]
        if final in cur:
            raise ValueError('duplicate key in inline table')
        cur[final] = value
    return table

def _parse_key(raw):
    raw = raw.strip()
    if raw.startswith('"') or raw.startswith("'"):
        return _parse_string(raw, iter([]))
    # Bare keys must not contain whitespace
    if re.search(r'\s', raw):
        raise ValueError(f'invalid bare key: {raw}')
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
        elif isinstance(cur[part], _InlineTable):
            raise ValueError('cannot add sub-key to inline table')
        elif not isinstance(cur[part], dict):
            raise ValueError('attempt to redefine non‑table as table')
        cur = cur[part]
    final = path_parts[-1]
    if final in cur:
        raise ValueError('duplicate key')
    if isinstance(cur, _InlineTable):
        raise ValueError('cannot add sub-key to inline table')
    cur[final] = value

def parse_toml(lines):
    """Parse a sequence of lines (list of str) into an OrderedDict."""
    data = OrderedDict()
    current_ref = data
    last_aot_path = None
    last_aot_ref = None
    seen_tables = set()   # tracks standard table definitions

    lines_iter = iter(lines)
    for raw_line in lines_iter:
        line = _strip_comments(raw_line).strip()
        if not line:
            continue

        # Array of tables [[...]]
        if line.startswith('[[') and line.endswith(']]'):
            inner = line[2:-2].strip()
            parts = [p.strip() for p in _split_top_level(inner, '.')]
            path = [_parse_key(p) for p in parts]

            # Determine the base where this array should live.
            # Only treat as nested when the new path extends the previous AOT path.
            if last_aot_path and path[:len(last_aot_path)] == last_aot_path and len(path) > len(last_aot_path):
                base_tbl = last_aot_ref
                remaining = path[len(last_aot_path):]
            else:
                base_tbl = data
                remaining = path

            # Navigate to the parent (all but the final segment)
            for seg in remaining[:-1]:
                if seg not in base_tbl:
                    base_tbl[seg] = OrderedDict()
                elif not isinstance(base_tbl[seg], dict):
                    raise ValueError('parent is not a table')
                base_tbl = base_tbl[seg]

            arr_name = remaining[-1]
            if arr_name not in base_tbl:
                base_tbl[arr_name] = []
            elif not isinstance(base_tbl[arr_name], list):
                raise ValueError('cannot redefine non‑array as array of tables')

            new_tbl = OrderedDict()
            base_tbl[arr_name].append(new_tbl)
            current_ref = new_tbl
            last_aot_path = path
            last_aot_ref = new_tbl
            continue

        # Standard table [...]
        if line.startswith('[') and line.endswith(']'):
            inner = line[1:-1].strip()
            parts = [p.strip() for p in _split_top_level(inner, '.')]
            path = [_parse_key(p) for p in parts]

            path_tuple = tuple(path)
            if path_tuple in seen_tables:
                raise ValueError('duplicate table definition')
            seen_tables.add(path_tuple)

            # Sub‑table of most recent array‑of‑tables
            if last_aot_path and path[:len(last_aot_path)] == last_aot_path and len(path) > len(last_aot_path):
                tbl = last_aot_ref
                for seg in path[len(last_aot_path):]:
                    if seg not in tbl:
                        tbl[seg] = OrderedDict()
                    elif not isinstance(tbl[seg], dict):
                        raise ValueError('attempt to redefine non‑table as table')
                    tbl = tbl[seg]
                current_ref = tbl
                continue

            # Normal table creation
            tbl = data
            for seg in path:
                if seg not in tbl:
                    tbl[seg] = OrderedDict()
                elif isinstance(tbl[seg], list):
                    raise ValueError('attempt to redefine array as table')
                elif not isinstance(tbl[seg], dict):
                    raise ValueError('duplicate key')
                tbl = tbl[seg]
            current_ref = tbl

            if not (last_aot_path and path[:len(last_aot_path)] == last_aot_path):
                last_aot_path = None
                last_aot_ref = None
            continue

        # Key/value pair
        if '=' not in line:
            raise ValueError('invalid line (no =)')
        key_part, val_part = line.split('=', 1)
        key_str = key_part.strip()
        key_parts = [p.strip() for p in _split_top_level(key_str, '.')]
        key_path = [_parse_key(p) for p in key_parts]

        value = _parse_value(val_part.strip(), lines_iter)

        _set_path(current_ref, key_path, value)

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
