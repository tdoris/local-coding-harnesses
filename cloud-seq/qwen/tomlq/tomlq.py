#!/usr/bin/env python3
"""tomlq: minimal TOML parser (subset) to JSON output.
Usage: python3 tomlq.py FILE [KEYPATH]
"""
import sys, json, re
from collections import OrderedDict

class ParseError(Exception):
    pass

# Helpers for key parsing
def unquote_basic(s: str) -> str:
    # s without surrounding double quotes
    # Handle escape sequences per TOML spec (basic string)
    # Use python's unicode_escape after replacing \u and \U with corresponding escapes
    esc_map = {
        "\\b": "\b",
        "\\t": "\t",
        "\\n": "\n",
        "\\f": "\f",
        "\\r": "\r",
        "\\\"": "\"",
        "\\\\": "\\",
    }
    # Replace known escapes
    def replace(m):
        seq = m.group(0)
        if seq in esc_map:
            return esc_map[seq]
        if seq.startswith('\\u'):
            return chr(int(seq[2:], 16))
        if seq.startswith('\\U'):
            return chr(int(seq[2:], 16))
        # Should not happen
        return seq
    return re.sub(r"\\\\[btnfr\\\"]|\\\\u[0-9a-fA-F]{4}|\\\\U[0-9a-fA-F]{8}", replace, s)

def parse_key_part(part: str) -> str:
    part = part.strip()
    if not part:
        raise ParseError('empty key part')
    if part[0] == '"':
        if len(part) < 2 or part[-1] != '"':
            raise ParseError('unterminated basic string key')
        return unquote_basic(part[1:-1])
    if part[0] == "'":
        if len(part) < 2 or part[-1] != "'":
            raise ParseError('unterminated literal string key')
        return part[1:-1]
    # bare key
    if not re.fullmatch(r"[A-Za-z0-9_-]+", part):
        raise ParseError(f'invalid bare key {part}')
    return part

def split_key(key: str):
    # split on dots, allowing whitespace around dots
    parts = []
    buf = ''
    in_quote = False
    quote_char = ''
    i = 0
    while i < len(key):
        ch = key[i]
        if in_quote:
            if ch == quote_char:
                in_quote = False
            buf += ch
        else:
            if ch in "'\"":
                in_quote = True
                quote_char = ch
                buf += ch
            elif ch == '.':
                parts.append(buf.strip())
                buf = ''
            else:
                buf += ch
        i += 1
    if buf:
        parts.append(buf.strip())
    return [parse_key_part(p) for p in parts]

# Value parsing
_int_re = re.compile(r"^[+-]?([0-9]_?)*[0-9]$")
_hex_re = re.compile(r"^0x[0-9a-fA-F_]+$")
_oct_re = re.compile(r"^0o[0-7_]+$")
_bin_re = re.compile(r"^0b[01_]+$")
_float_re = re.compile(r"^[+-]?([0-9]_?)*[0-9]\.[0-9_]*([eE][+-]?[0-9_]+)?$|^[+-]?([0-9]_?)*[0-9]([eE][+-]?[0-9_]+)$")


def parse_number(tok: str):
    t = tok.replace('_', '')
    if _hex_re.match(t):
        return int(t, 16)
    if _oct_re.match(t):
        return int(t, 8)
    if _bin_re.match(t):
        return int(t, 2)
    if _int_re.match(t):
        # No leading zeros allowed unless the number is zero
        if t.lstrip('+-').startswith('0') and t.lstrip('+-') != '0':
            raise ParseError('leading zeros in decimal integer')
        return int(t, 10)
    if _float_re.match(t):
        return float(t)
    raise ParseError('invalid number')


def parse_basic_string(s: str) -> str:
    # s includes surrounding double quotes
    return unquote_basic(s[1:-1])

def parse_literal_string(s: str) -> str:
    return s[1:-1]

def parse_multiline_basic(lines, start_idx, delim):
    # delim is """ or '''
    content_lines = []
    i = start_idx
    first_line = lines[i]
    # Trim the opening delimiter
    rest = first_line.split(delim, 1)[1]
    if rest.startswith('\n'):
        rest = rest[1:]
    content_lines.append(rest)
    i += 1
    while i < len(lines):
        line = lines[i]
        if delim in line:
            before, after = line.split(delim, 1)
            content_lines.append(before)
            # handle line-ending backslash for basic multiline
            if delim == '"""' and before.endswith('\\'):
                # remove backslash and following whitespace/newlines until next non-space char
                # Simplify: join lines without the backslash and following newline
                # Already split lines, so just remove backslash
                content_lines[-1] = before[:-1]
            return '\n'.join(content_lines), i
        else:
            content_lines.append(line)
        i += 1
    raise ParseError('unterminated multiline string')

def parse_array(s: str):
    # Remove surrounding brackets and parse elements recursively
    s = s.strip()
    if not s.startswith('[') or not s.endswith(']'):
        raise ParseError('invalid array')
    inner = s[1:-1]
    # Remove comments
    inner = re.sub(r"#.*", "", inner)
    # Split respecting nested structures
    items = []
    buf = ''
    depth = 0
    in_str = False
    str_char = ''
    i = 0
    while i < len(inner):
        ch = inner[i]
        if in_str:
            if ch == str_char:
                in_str = False
            elif ch == '\\':
                buf += ch
                i += 1
                if i < len(inner):
                    buf += inner[i]
                i += 1
                continue
            buf += ch
        else:
            if ch in "'\"":
                in_str = True
                str_char = ch
                buf += ch
            elif ch in '[{' :
                depth += 1
                buf += ch
            elif ch in ']}' :
                depth -= 1
                buf += ch
            elif ch == ',' and depth == 0:
                if buf.strip():
                    items.append(buf.strip())
                buf = ''
            else:
                buf += ch
        i += 1
    if buf.strip():
        items.append(buf.strip())
    return [parse_value(item) for item in items]

def parse_inline_table(s: str):
    s = s.strip()
    if not s.startswith('{') or not s.endswith('}'):
        raise ParseError('invalid inline table')
    inner = s[1:-1].strip()
    if not inner:
        return OrderedDict()
    result = OrderedDict()
    # split by commas not inside strings or braces
    parts = []
    buf = ''
    depth = 0
    in_str = False
    str_char = ''
    i = 0
    while i < len(inner):
        ch = inner[i]
        if in_str:
            if ch == str_char:
                in_str = False
            elif ch == '\\':
                buf += ch
                i += 1
                if i < len(inner):
                    buf += inner[i]
                i += 1
                continue
            buf += ch
        else:
            if ch in "'\"":
                in_str = True
                str_char = ch
                buf += ch
            elif ch in '{[':
                depth += 1
                buf += ch
            elif ch in '}]':
                depth -= 1
                buf += ch
            elif ch == ',' and depth == 0:
                parts.append(buf.strip())
                buf = ''
            else:
                buf += ch
        i += 1
    if buf.strip():
        parts.append(buf.strip())
    for p in parts:
        if '=' not in p:
            raise ParseError('invalid inline table entry')
        k, v = p.split('=', 1)
        key = k.strip()
        # key may be quoted
        key_name = parse_key_part(key)
        if key_name in result:
            raise ParseError('duplicate key in inline table')
        result[key_name] = parse_value(v.strip())
    return result

def parse_value(token: str):
    token = token.strip()
    # booleans
    if token == 'true':
        return True
    if token == 'false':
        return False
    # strings
    if token.startswith('"""'):
        # multiline basic handled elsewhere; fallback to basic string without delimiters
        inner = token[3:-3]
        return unquote_basic(inner)
    if token.startswith("'''"):
        return token[3:-3]
    if token.startswith('"') and token.endswith('"'):
        return parse_basic_string(token)
    if token.startswith("'") and token.endswith("'"):
        return parse_literal_string(token)
    # array
    if token.startswith('[') and token.endswith(']'):
        return parse_array(token)
    # inline table
    if token.startswith('{') and token.endswith('}'):
        return parse_inline_table(token)
    # numbers
    try:
        return parse_number(token)
    except ParseError:
        raise ParseError(f'cannot parse value: {token}')

def set_path(root, path, value, is_table=False, array_of_tables=False):
    cur = root
    for i, part in enumerate(path):
        if i == len(path) - 1:
            # final part
            if is_table:
                if part not in cur:
                    cur[part] = OrderedDict()
                elif not isinstance(cur[part], dict):
                    raise ParseError('key already assigned a non-table value')
                return cur[part]
            else:
                if part in cur:
                    raise ParseError('duplicate key')
                cur[part] = value
                return None
        else:
            if part not in cur:
                cur[part] = OrderedDict()
            elif not isinstance(cur[part], dict):
                raise ParseError('intermediate key is not a table')
            cur = cur[part]
    return None

def parse_toml(content: str):
    lines = content.splitlines()
    root = OrderedDict()
    current_table = root
    last_array_path = None  # list of parts
    i = 0
    while i < len(lines):
        raw = lines[i]
        # strip comments (but not inside strings) – simple approach: remove after # if not in string
        def strip_comment(s):
            in_str = False
            delim = ''
            for idx, ch in enumerate(s):
                if in_str:
                    if ch == delim:
                        in_str = False
                    elif ch == '\\':
                        # skip escaped char
                        continue
                else:
                    if ch in "'\"":
                        in_str = True
                        delim = ch
                    elif ch == '#':
                        return s[:idx]
            return s
        line = strip_comment(raw).strip()
        if not line:
            i += 1
            continue
        # Table header
        if line.startswith('['):
            if line.startswith('[[', 0):
                # array of tables
                if not line.endswith(']]'):
                    raise ParseError('malformed array of tables header')
                inner = line[2:-2].strip()
                parts = split_key(inner)
                # Ensure array exists
                arr_parent = root
                for p in parts[:-1]:
                    if p not in arr_parent:
                        arr_parent[p] = OrderedDict()
                    elif not isinstance(arr_parent[p], dict):
                        raise ParseError('array parent not a table')
                    arr_parent = arr_parent[p]
                arr_name = parts[-1]
                arr = arr_parent.get(arr_name)
                if arr is None:
                    arr = []
                    arr_parent[arr_name] = arr
                elif not isinstance(arr, list):
                    raise ParseError('cannot redefine a value as array of tables')
                new_tbl = OrderedDict()
                arr.append(new_tbl)
                current_table = new_tbl
                last_array_path = parts
                i += 1
                continue
            else:
                # standard table
                if not line.endswith(']'):
                    raise ParseError('malformed table header')
                inner = line[1:-1].strip()
                parts = split_key(inner)
                # Determine base context (maybe after an array of tables)
                base = root
                if last_array_path and parts[:len(last_array_path)] == last_array_path:
                    # use last element of that array
                    arr = root
                    for p in last_array_path:
                        arr = arr[p]
                    if not isinstance(arr, list) or not arr:
                        raise ParseError('array of tables missing for subtable')
                    base = arr[-1]
                    remaining = parts[len(last_array_path):]
                else:
                    remaining = parts
                # create tables for remaining parts
                cur = base
                for p in remaining:
                    if p not in cur:
                        cur[p] = OrderedDict()
                    elif not isinstance(cur[p], dict):
                        raise ParseError('key already defined as non-table')
                    cur = cur[p]
                current_table = cur
                i += 1
                continue
        # Key/value line
        # Find first = not inside quotes
        def find_eq(s):
            in_str = False
            delim = ''
            for idx, ch in enumerate(s):
                if in_str:
                    if ch == delim:
                        in_str = False
                    elif ch == '\\':
                        continue
                else:
                    if ch in "'\"":
                        in_str = True
                        delim = ch
                    elif ch == '=':
                        return idx
            return -1
        eq_idx = find_eq(line)
        if eq_idx == -1:
            raise ParseError('invalid line, no =')
        key_part = line[:eq_idx].strip()
        value_part = line[eq_idx+1:].strip()
        # Handle multi-line values (arrays, inline tables, multiline strings) by gathering lines until closed
        # Simple detection: if value starts with '[' and does not end with ']' (consider nesting) -> gather
        # same for '{' and '}' and for triple quotes.
        def starts_multiline(val):
            return (val.startswith('[') and not val.endswith(']')) or (val.startswith('{') and not val.endswith('}')) or (val.startswith(''''') and not val.endswith(''''') ) or (val.startswith('"""') and not val.endswith('"""'))
        # For arrays and inline tables, we need to collect until balanced brackets/braces are closed.
        if value_part.startswith('[') and not value_part.endswith(']'):
            # collect lines until matching ]
            bal = 0
            for ch in value_part:
                if ch == '[': bal += 1
                elif ch == ']': bal -= 1
            j = i+1
            while bal > 0 and j < len(lines):
                nxt = strip_comment(lines[j]).strip()
                for ch in nxt:
                    if ch == '[': bal += 1
                    elif ch == ']': bal -= 1
                value_part += ' ' + nxt
                j += 1
            i = j-1
        elif value_part.startswith('{') and not value_part.endswith('}'):
            bal = 0
            for ch in value_part:
                if ch == '{': bal += 1
                elif ch == '}': bal -= 1
            j = i+1
            while bal > 0 and j < len(lines):
                nxt = strip_comment(lines[j]).strip()
                for ch in nxt:
                    if ch == '{': bal += 1
                    elif ch == '}': bal -= 1
                value_part += ' ' + nxt
                j += 1
            i = j-1
        elif value_part.startswith('"""'):
            # multiline basic string
            content, new_i = parse_multiline_basic(lines, i, '"""')
            value_part = '"' + content.replace('"', '\\"') + '"'  # reuse basic string parser after cleaning
            i = new_i
        elif value_part.startswith("'''"):
            content, new_i = parse_multiline_basic(lines, i, "'''")
            value_part = "'" + content + "'"
            i = new_i
        # parse key path
        key_path = split_key(key_part)
        # set value in current_table
        try:
            set_path(root, key_path, parse_value(value_part))
        except ParseError as e:
            raise
        i += 1
    return root

def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print('Usage: python3 tomlq.py FILE [KEYPATH]', file=sys.stderr)
        sys.exit(1)
    file_path = sys.argv[1]
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f'Error reading file: {e}', file=sys.stderr)
        sys.exit(1)
    try:
        data = parse_toml(content)
    except ParseError as e:
        print(f'Parse error: {e}', file=sys.stderr)
        sys.exit(1)
    if len(sys.argv) == 3:
        keypath = sys.argv[2]
        parts = keypath.split('.') if keypath else []
        cur = data
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                print(f'Key path not found: {keypath}', file=sys.stderr)
                sys.exit(2)
        result = cur
    else:
        result = data
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write('\n')

if __name__ == '__main__':
    main()
