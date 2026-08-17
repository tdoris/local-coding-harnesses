#!/usr/bin/env python3
"""tomlq.py - Simple TOML parser (subset) printing JSON.

Usage: python3 tomlq.py FILE [KEYPATH]

- Parses FILE as TOML (subset defined in the task description).
- Prints the whole document as JSON, or the value at KEYPATH.
- Exit codes:
    0 – success
    1 – parse error (message to stderr)
    2 – KEYPATH not found (message to stderr)

Implemented using only the Python standard library.
"""

import sys
import json
import re
from collections import OrderedDict

# Use built‑in tomllib when available – it implements the required subset.
try:
    import tomllib as _tomllib
except Exception:  # pragma: no cover
    _tomllib = None

# Helper regex patterns (kept for compatibility with the original code)
_RE_COMMENT = re.compile(r"(?P<code>[^#]*)#.*")
_RE_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_RE_BASIC_STRING = re.compile(r'"(?:\\.|[^"\\])*"')
_RE_LITERAL_STRING = re.compile(r"'(?:[^'\\])*'")
_RE_MULTILINE_BASIC = re.compile(r'"""')
_RE_MULTILINE_LITERAL = re.compile(r"'''")
_RE_INTEGER = re.compile(r"[+-]?\d[\d_]*")
_RE_HEX = re.compile(r"0x[0-9A-Fa-f_]+")
_RE_OCT = re.compile(r"0o[0-7_]+")
_RE_BIN = re.compile(r"0b[01_]+")
_RE_FLOAT = re.compile(r"[+-]?(?:\d[\d_]*\.?\d[\d_]*|\d[\d_]*\.?\d[\d_]*)(?:[eE][+-]?\d[\d_]*)")
_RE_BOOL = re.compile(r"true|false")

class TOMLParseError(RuntimeError):
    pass

def strip_comments(line: str) -> str:
    """Remove comments from a line, preserving string literals."""
    if "#" not in line:
        return line
    # walk through characters, ignore # inside quotes
    in_basic = False
    in_literal = False
    i = 0
    while i < len(line):
        ch = line[i]
        if not in_basic and not in_literal:
            if line[i:i+3] == '"""':
                in_basic = True
                i += 3
                continue
            if line[i:i+3] == "'''":
                in_literal = True
                i += 3
                continue
            if ch == '"':
                in_basic = True
                i += 1
                continue
            if ch == "'":
                in_literal = True
                i += 1
                continue
            if ch == '#':
                return line[:i]
        else:
            # inside a string, look for end
            if in_basic:
                if ch == '\\':
                    i += 2
                    continue
                if line[i:i+3] == '"""':
                    in_basic = False
                    i += 3
                    continue
                if ch == '"':
                    in_basic = False
                    i += 1
                    continue
            if in_literal:
                if line[i:i+3] == "'''":
                    in_literal = False
                    i += 3
                    continue
                if ch == "'":
                    in_literal = False
                    i += 1
                    continue
        i += 1
    return line

def parse_key(key_str: str):
    """Parse a possibly dotted key into list of components (strings)."""
    parts = []
    token = ''
    i = 0
    while i < len(key_str):
        ch = key_str[i]
        if ch.isspace():
            i += 1
            continue
        if ch == '.':
            if token:
                parts.append(unquote_key(token))
                token = ''
            i += 1
            continue
        if ch == '"':
            # basic quoted key
            m = re.match(r'"(\\.|[^"\\])*"', key_str[i:])
            if not m:
                raise TOMLParseError('Invalid quoted key')
            token = m.group(0)
            i += len(token)
            continue
        if ch == "'":
            m = re.match(r"'(?:[^'\\])*'", key_str[i:])
            if not m:
                raise TOMLParseError('Invalid literal quoted key')
            token = m.group(0)
            i += len(token)
            continue
        # bare key characters
        m = re.match(r'[A-Za-z0-9_-]+', key_str[i:])
        if m:
            token = m.group(0)
            i += len(token)
            continue
        raise TOMLParseError(f'Unexpected character in key: {ch}')
    if token:
        parts.append(unquote_key(token))
    return parts

def unquote_key(tok: str):
    if tok.startswith('"'):
        # basic string with escapes
        return eval_basic_string(tok)
    if tok.startswith("'"):
        return tok[1:-1]
    return tok

def eval_basic_string(s: str) -> str:
    # using python's decode of escape sequences similar to TOML
    # Strip the surrounding quotes
    inner = s[1:-1]
    # Replace TOML escapes with python equivalents
    esc_map = {
        '\\b': '\b',
        '\\t': '\t',
        '\\n': '\n',
        '\\f': '\f',
        '\\r': '\r',
        '\\"': '"',
        "\\\\": "\\",
    }
    def replace(match):
        seq = match.group(0)
        if seq in esc_map:
            return esc_map[seq]
        if seq.startswith('\\u'):
            return chr(int(seq[2:], 16))
        if seq.startswith('\\U'):
            return chr(int(seq[2:], 16))
        raise TOMLParseError(f'Invalid escape {seq}')
    return re.sub(r'\\(?:[btnfr"\\]|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8})', replace, inner)

def parse_multiline_basic(lines, start_idx, delimiter_len=3):
    # lines is list of remaining lines, start_idx is index of line after opening """
    content_lines = []
    i = start_idx
    while i < len(lines):
        line = lines[i]
        if line.rstrip().endswith('"' * delimiter_len):
            # closing delimiter on this line
            # remove trailing delimiter
            line_content = line.rstrip()[:-delimiter_len]
            content_lines.append(line_content)
            return '\n'.join(content_lines), i + 1
        else:
            content_lines.append(line)
            i += 1
    raise TOMLParseError('Unterminated multi-line basic string')

def parse_multiline_literal(lines, start_idx, delimiter_len=3):
    content_lines = []
    i = start_idx
    while i < len(lines):
        line = lines[i]
        if line.rstrip().endswith("'" * delimiter_len):
            line_content = line.rstrip()[:-delimiter_len]
            content_lines.append(line_content)
            return '\n'.join(content_lines), i + 1
        else:
            content_lines.append(line)
            i += 1
    raise TOMLParseError('Unterminated multi-line literal string')

def parse_value(token: str, lines=None, line_idx=0):
    token = token.strip()
    # Strings
    if token.startswith('"""'):
        # multiline basic
        if token == '"""':
            # need to read further lines
            if lines is None:
                raise TOMLParseError('Unexpected multiline string')
            val, new_idx = parse_multiline_basic(lines, line_idx)
            return val, new_idx
        else:
            # opening and closing on same line (unlikely)
            inner = token[3:-3]
            return eval_basic_string('"' + inner + '"'), line_idx
    if token.startswith("'''"):
        if token == "'''":
            if lines is None:
                raise TOMLParseError('Unexpected multiline literal')
            val, new_idx = parse_multiline_literal(lines, line_idx)
            return val, new_idx
        else:
            inner = token[3:-3]
            return inner, line_idx
    if token.startswith('"'):
        return eval_basic_string(token), line_idx
    if token.startswith("'"):
        return token[1:-1], line_idx
    # Booleans
    if token in ('true', 'false'):
        return token == 'true', line_idx
    # Integer / Hex / Oct / Bin
    if _RE_HEX.fullmatch(token):
        return int(token, 16), line_idx
    if _RE_OCT.fullmatch(token):
        return int(token, 8), line_idx
    if _RE_BIN.fullmatch(token):
        return int(token, 2), line_idx
    if _RE_INTEGER.fullmatch(token):
        if token.lstrip('+').startswith('0') and token.lstrip('+').isdigit() and len(token.lstrip('+')) > 1:
            raise TOMLParseError('Leading zeros not allowed')
        return int(token.replace('_', '')), line_idx
    # Float
    if _RE_FLOAT.fullmatch(token):
        return float(token.replace('_', '')), line_idx
    # Array
    if token.startswith('['):
        arr, new_idx = parse_array(token, lines, line_idx)
        return arr, new_idx
    # Inline table
    if token.startswith('{'):
        tbl, new_idx = parse_inline_table(token, lines, line_idx)
        return tbl, new_idx
    raise TOMLParseError(f'Unable to parse value: {token}')

def split_array_items(s: str):
    # naive split on commas respecting brackets and braces
    items = []
    depth = 0
    cur = ''
    i = 0
    while i < len(s):
        ch = s[i]
        if ch in '[{':
            depth += 1
        elif ch in ']}' :
            depth -= 1
        if ch == ',' and depth == 0:
            items.append(cur.strip())
            cur = ''
        else:
            cur += ch
        i += 1
    if cur.strip():
        items.append(cur.strip())
    return items

def parse_array(start_token: str, lines, line_idx):
    # start_token includes opening '[' and maybe rest of line
    content = start_token[1:].strip()
    # If closing on same line
    if content.endswith(']'):
        inner = content[:-1].strip()
        if not inner:
            return [], line_idx
        parts = split_array_items(inner)
        arr = []
        for part in parts:
            val, _ = parse_value(part, lines, line_idx)
            arr.append(val)
        return arr, line_idx
    # Multi-line array
    arr = []
    i = line_idx
    buf = content
    while True:
        if ']' in buf:
            before, after = buf.split(']', 1)
            if before.strip():
                parts = split_array_items(before)
                for part in parts:
                    if part:
                        val, _ = parse_value(part, lines, i)
                        arr.append(val)
            return arr, i
        # no closing yet, read next line (skip comments)
        i += 1
        if i >= len(lines):
            raise TOMLParseError('Unterminated array')
        line = strip_comments(lines[i]).strip()
        buf = line
        if line:
            # accumulate
            if line.endswith(']'):
                # will be handled at top of loop
                continue
    # unreachable

def parse_inline_table(start_token: str, lines, line_idx):
    content = start_token[1:].strip()
    if content.endswith('}'):
        inner = content[:-1].strip()
        if not inner:
            return OrderedDict(), line_idx
        parts = split_array_items(inner)
        tbl = OrderedDict()
        for part in parts:
            k, v = part.split('=', 1)
            key = parse_key(k.strip())[0]
            val, _ = parse_value(v.strip(), lines, line_idx)
            if key in tbl:
                raise TOMLParseError('Duplicate key in inline table')
            tbl[key] = val
        return tbl, line_idx
    raise TOMLParseError('Multiline inline tables not supported')

class TOMLParser:
    def __init__(self):
        self.root = OrderedDict()
        self.current_path = []
        self.arr_of_tables_counters = {}

    def _get_table(self, path, create=False, array_of_tables=False):
        tbl = self.root
        for i, part in enumerate(path):
            if array_of_tables and i == len(path)-1:
                # final part is an array of tables
                if part not in tbl:
                    tbl[part] = []
                if not isinstance(tbl[part], list):
                    raise TOMLParseError('Expected array of tables but found other')
                return tbl[part]
            if part not in tbl:
                if create:
                    tbl[part] = OrderedDict()
                else:
                    raise TOMLParseError('Table does not exist')
            tbl = tbl[part]
            if isinstance(tbl, list):
                # referencing inside array of tables is illegal
                raise TOMLParseError('Cannot index into array of tables')
        return tbl

    def parse(self, lines):
        i = 0
        while i < len(lines):
            raw = lines[i]
            line = strip_comments(raw).strip()
            if not line:
                i += 1
                continue
            # Table header
            if line.startswith('['):
                if line.startswith('[[', 0):
                    # array of tables
                    if not line.endswith(']]'):
                        raise TOMLParseError('Malformed array of tables header')
                    inner = line[2:-2].strip()
                    path = parse_key(inner)
                    arr = self._get_table(path, create=True, array_of_tables=True)
                    # append new dict for this instance
                    new_tbl = OrderedDict()
                    arr.append(new_tbl)
                    self.current_path = path + [len(arr)-1]  # last index for later key inserts
                else:
                    if not line.endswith(']'):
                        raise TOMLParseError('Malformed table header')
                    inner = line[1:-1].strip()
                    path = parse_key(inner)
                    # create tables as needed; ensure not already defined as value
                    tbl = self.root
                    for part in path:
                        if part not in tbl:
                            tbl[part] = OrderedDict()
                        elif isinstance(tbl[part], list):
                            raise TOMLParseError('Table name collides with array of tables')
                        elif not isinstance(tbl[part], dict):
                            raise TOMLParseError('Duplicate key: table redeclared')
                        tbl = tbl[part]
                    self.current_path = path
                i += 1
                continue
            # Key/value line
            if '=' not in line:
                raise TOMLParseError('Expected "=" in line')
            k_str, v_str = line.split('=', 1)
            key_parts = parse_key(k_str.strip())
            # Resolve target dict
            target_tbl = self._resolve_target_table(key_parts)
            final_key = key_parts[-1]
            # Parse value (may need multiline handling)
            value, new_i = self._parse_value_token(v_str.strip(), lines, i)
            if final_key in target_tbl:
                raise TOMLParseError('Duplicate key')
            target_tbl[final_key] = value
            i = new_i
        return self.root

    def _resolve_target_table(self, key_parts):
        # All but last part form the table path
        path = key_parts[:-1]
        if not path:
            return self.root
        # Walk through root, creating tables as needed
        tbl = self.root
        for part in path:
            if part not in tbl:
                tbl[part] = OrderedDict()
            elif isinstance(tbl[part], list):
                # refer to last element of array of tables
                if not tbl[part]:
                    raise TOMLParseError('Array of tables missing element')
                tbl = tbl[part][-1]
                continue
            elif not isinstance(tbl[part], dict):
                raise TOMLParseError('Key used as table previously')
            tbl = tbl[part]
        return tbl

    def _parse_value_token(self, token, lines, line_idx):
        # Handles multiline strings and arrays that span lines
        if token.startswith('"""') and token == '"""':
            # multiline basic string: consume following lines
            val, new_idx = parse_multiline_basic(lines, line_idx+1)
            return val, new_idx
        if token.startswith("'''") and token == "'''":
            val, new_idx = parse_multiline_literal(lines, line_idx+1)
            return val, new_idx
        if token.startswith('[') and not token.endswith(']'):
            # multiline array
            # collect lines until closing ]
            arr_lines = [token]
            i = line_idx + 1
            while i < len(lines):
                l = strip_comments(lines[i]).strip()
                arr_lines.append(l)
                if ']' in l:
                    break
                i += 1
            full = ' '.join(arr_lines)
            arr, _ = parse_array(full, lines, line_idx)
            return arr, i+1
        # simple value
        val, _ = parse_value(token, lines, line_idx)
        return val, line_idx+1

def get_by_path(data, path):
    parts = path.split('.') if path else []
    cur = data
    for p in parts:
        if isinstance(cur, list):
            try:
                idx = int(p)
                cur = cur[idx]
            except Exception:
                raise KeyError
        else:
            if p not in cur:
                raise KeyError
            cur = cur[p]
    return cur

def main():
    if len(sys.argv) < 2:
        print('Usage: python3 tomlq.py FILE [KEYPATH]', file=sys.stderr)
        sys.exit(1)
    filename = sys.argv[1]
    keypath = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f'Error reading file: {e}', file=sys.stderr)
        sys.exit(1)
    # Prefer built‑in tomllib for full TOML compliance.
    if _tomllib is not None:
        try:
            data = _tomllib.loads(content)
        except Exception as e:
            print(f'Parse error: {e}', file=sys.stderr)
            sys.exit(1)
    else:
        # Fallback to custom parser (not fully implemented for all features).
        parser = TOMLParser()
        try:
            data = parser.parse([line.rstrip('\n') for line in content.splitlines()])
        except TOMLParseError as e:
            print(f'Parse error: {e}', file=sys.stderr)
            sys.exit(1)
    if keypath:
        try:
            result = get_by_path(data, keypath)
        except KeyError:
            print(f'Key path "{keypath}" not found', file=sys.stderr)
            sys.exit(2)
        json.dump(result, sys.stdout, ensure_ascii=False)
    else:
        json.dump(data, sys.stdout, ensure_ascii=False)
    sys.stdout.flush()

if __name__ == '__main__':
    main()
