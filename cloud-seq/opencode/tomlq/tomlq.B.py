import sys
import json
import re
from collections import OrderedDict

# Simple TOML subset parser (TOML v1.0.0 features as required)

class TomlParseError(Exception):
    pass

def strip_comments(line: str) -> str:
    # Remove comments not inside strings
    in_basic = False
    in_literal = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_basic:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_basic = False
        elif in_literal:
            if ch == "'":
                in_literal = False
        else:
            if ch == '"':
                # check for triple basic string start
                if line[i:i+3] == '"""':
                    in_basic = True
                    i += 2
                else:
                    in_basic = True
            elif ch == "'":
                if line[i:i+3] == "'''":
                    in_literal = True
                    i += 2
                else:
                    in_literal = True
            elif ch == '#':
                return line[:i]
        i += 1
    return line

def parse_integer(tok: str):
    # underscores allowed
    s = tok.replace('_', '')
    if re.fullmatch(r'[\+\-]?0', s):
        return int(s)
    if s.startswith('0x') or s.startswith('0X'):
        return int(s, 16)
    if s.startswith('0o') or s.startswith('0O'):
        return int(s, 8)
    if s.startswith('0b') or s.startswith('0B'):
        return int(s, 2)
    # decimal, must not have leading zero unless single zero
    if re.fullmatch(r'[\+\-]?[1-9][0-9]*', s) or re.fullmatch(r'[\+\-]?0', s):
        return int(s)
    raise TomlParseError(f'Invalid integer: {tok}')

def parse_float(tok: str):
    s = tok.replace('_', '')
    # Python float can parse most forms
    try:
        return float(s)
    except ValueError:
        raise TomlParseError(f'Invalid float: {tok}')

def parse_bool(tok: str):
    if tok == 'true':
        return True
    if tok == 'false':
        return False
    raise TomlParseError(f'Invalid boolean: {tok}')

def parse_basic_string(s: str) -> str:
    # JSON can parse basic strings with same escapes
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise TomlParseError(f'Invalid basic string: {s}')

def parse_literal_string(s: str) -> str:
    # strip the surrounding single quotes, no escapes
    return s[1:-1]

def parse_multiline_basic(lines: list) -> str:
    # lines already contain the opening delimiter """ and possibly following content
    # Join lines, handle line continuation with backslash at end
    # Remove the opening delimiter
    content = '\n'.join(lines)
    # Trim opening """ and closing """
    if not content.startswith('"""'):
        raise TomlParseError('Malformed multiline basic string')
    content = content[3:]
    # Find closing delimiter
    end_idx = content.rfind('"""')
    if end_idx == -1:
        raise TomlParseError('Unterminated multiline basic string')
    inner = content[:end_idx]
    # Remove first newline if present (as per spec)
    if inner.startswith('\n'):
        inner = inner[1:]
    # Handle line continuation backslash
    lines = inner.split('\n')
    processed = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.rstrip().endswith('\\'):
            # remove backslash and following whitespace
            line = line.rstrip()[:-1]
            # concatenate with next line after stripping leading whitespace
            if i + 1 < len(lines):
                line += lines[i+1].lstrip()
                i += 1
        processed.append(line)
        i += 1
    return '\n'.join(processed)

def parse_multiline_literal(lines: list) -> str:
    content = '\n'.join(lines)
    if not content.startswith("'''"):
        raise TomlParseError('Malformed multiline literal string')
    content = content[3:]
    end_idx = content.rfind("'''")
    if end_idx == -1:
        raise TomlParseError('Unterminated multiline literal string')
    inner = content[:end_idx]
    if inner.startswith('\n'):
        inner = inner[1:]
    return inner

def parse_value(token: str, lines_iter) -> any:
    token = token.strip()
    # Multi-line basic string
    if token.startswith('"""'):
        # collect lines until closing triple quotes
        buf = [token]
        for line in lines_iter:
            buf.append(line.rstrip('\n'))
            if line.rstrip().endswith('"""'):
                break
        return parse_basic_string('"""' + parse_multiline_basic(buf) + '"""')
    if token.startswith("'''"):
        buf = [token]
        for line in lines_iter:
            buf.append(line.rstrip('\n'))
            if line.rstrip().endswith("'''"):
                break
        return parse_literal_string('"' + parse_multiline_literal(buf) + '"')
    # Basic string
    if token.startswith('"'):
        return parse_basic_string(token)
    if token.startswith("'"):
        return parse_literal_string(token)
    # Inline table
    if token.startswith('{'):
        # collect until matching }
        depth = 0
        txt = ''
        for ch in token:
            if ch == '{':
                depth += 1
            if ch == '}':
                depth -= 1
            txt += ch
            if depth == 0:
                break
        # Ensure we have full inline table on same line (spec allows no newline)
        inner = txt[1:-1].strip()
        if not inner:
            return {}
        return parse_inline_table(inner)
    # Array
    if token.startswith('['):
        # read possibly multi-line array
        arr_txt = token
        while not arr_txt.rstrip().endswith(']'):
            try:
                nxt = next(lines_iter).rstrip('\n')
            except StopIteration:
                raise TomlParseError('Unterminated array')
            arr_txt += '\n' + nxt
        return parse_array(arr_txt)
    # Boolean
    if token in ('true', 'false'):
        return parse_bool(token)
    # Integer or float detection
    if re.fullmatch(r'[\+\-]?([0-9][0-9_]*)([eE][\+\-]?[0-9_]+)?', token) or re.fullmatch(r'[\+\-]?[0-9][0-9_]*\.[0-9_]*([eE][\+\-]?[0-9_]+)?', token):
        # try int first, then float
        try:
            return parse_integer(token)
        except TomlParseError:
            return parse_float(token)
    # Float with exponent but no dot
    if re.fullmatch(r'[\+\-]?[0-9][0-9_]*[eE][\+\-]?[0-9_]+', token):
        return parse_float(token)
    raise TomlParseError(f'Unable to parse value: {token}')

def split_top_level(s: str, sep: str):
    parts = []
    depth = 0
    current = ''
    i = 0
    while i < len(s):
        ch = s[i]
        if ch in ('[', '{'):
            depth += 1
        elif ch in (']', '}'):
            depth -= 1
        elif ch == '"' or ch == "'":
            # skip string literals
            quote = ch
            current += ch
            i += 1
            while i < len(s) and s[i] != quote:
                if s[i] == '\\':
                    current += s[i:i+2]
                    i += 2
                    continue
                current += s[i]
                i += 1
            if i < len(s):
                current += s[i]
            i += 1
            continue
        if depth == 0 and s[i:i+len(sep)] == sep:
            parts.append(current.strip())
            current = ''
            i += len(sep)
            continue
        current += ch
        i += 1
    if current:
        parts.append(current.strip())
    return parts

def parse_array(text: str):
    # Remove surrounding brackets
    inner = text.strip()[1:-1]
    if not inner.strip():
        return []
    # split top-level commas
    elems = split_top_level(inner, ',')
    result = []
    for elem in elems:
        # allow comments after element
        elem = strip_comments(elem).strip()
        if not elem:
            continue
        # parse each element recursively using a dummy iterator
        result.append(parse_value(elem, iter([])))
    return result

def parse_inline_table(text: str):
    # split by commas at top level
    pairs = split_top_level(text, ',')
    tbl = {}
    for pair in pairs:
        if not pair:
            continue
        if '=' not in pair:
            raise TomlParseError('Invalid inline table entry')
        k, v = pair.split('=', 1)
        k = k.strip()
        v = v.strip()
        # keys in inline tables are simple (no dotted?) spec allows but we ignore complex
        key = parse_key(k)
        if isinstance(key, list):
            raise TomlParseError('Dotted keys not allowed in inline tables')
        if key in tbl:
            raise TomlParseError('Duplicate key in inline table')
        tbl[key] = parse_value(v, iter([]))
    return tbl

def parse_key(raw: str):
    raw = raw.strip()
    # Dotted key handling: split on '.' respecting quoted parts
    parts = []
    i = 0
    while i < len(raw):
        if raw[i] in ('"', "'"):
            quote = raw[i]
            start = i
            i += 1
            while i < len(raw) and raw[i] != quote:
                if raw[i] == '\\':
                    i += 2
                else:
                    i += 1
            i += 1  # include closing quote
            part = raw[start:i]
            parts.append(parse_key_part(part))
        else:
            # read until dot or end
            start = i
            while i < len(raw) and raw[i] not in ('.', ' '):
                i += 1
            part = raw[start:i].strip()
            if part:
                parts.append(parse_key_part(part))
        # skip whitespace and dot
        while i < len(raw) and raw[i] in (' ', '\t'):
            i += 1
        if i < len(raw) and raw[i] == '.':
            i += 1
            while i < len(raw) and raw[i] in (' ', '\t'):
                i += 1
    return parts if len(parts) > 1 else parts[0]

def parse_key_part(part: str):
    part = part.strip()
    if part.startswith('"'):
        return parse_basic_string(part)
    if part.startswith("'"):
        return parse_literal_string(part)
    return part

def insert_key(root: dict, key_path, value, array_of_table=False):
    # key_path may be string or list
    if isinstance(key_path, list):
        parts = key_path
    else:
        parts = [key_path]
    cur = root
    for i, part in enumerate(parts):
        if i == len(parts) - 1:
            # final key
            if part in cur:
                raise TomlParseError('Duplicate key')
            cur[part] = value
            return
        # intermediate tables
        if part not in cur:
            cur[part] = {}
        elif not isinstance(cur[part], dict):
            raise TomlParseError('Key already has non-table value')
        cur = cur[part]

def ensure_table(root: dict, path):
    # path is list of parts
    cur = root
    for part in path:
        if part not in cur:
            cur[part] = {}
        elif not isinstance(cur[part], dict):
            raise TomlParseError('Path part already set as non-table')
        cur = cur[part]
    return cur

def parse_toml(lines):
    root = {}
    current_table = root
    array_of_table_stack = []  # stack of current tables for array of tables
    lines_iter = iter(lines)
    for raw_line in lines_iter:
        line = raw_line.rstrip('\n')
        line_nocom = strip_comments(line).strip()
        if not line_nocom:
            continue
        if line_nocom.startswith('['):
            # header
            if line_nocom.startswith('[[', 0):
                # array of tables
                if not line_nocom.endswith(']]'):
                    raise TomlParseError('Malformed array of tables header')
                inside = line_nocom[2:-2].strip()
                path = parse_key(inside)
                if isinstance(path, list):
                    parts = path
                else:
                    parts = [path]
                # ensure parent tables exist
                parent = ensure_table(root, parts[:-1])
                arr_key = parts[-1]
                if arr_key not in parent:
                    parent[arr_key] = []
                elif not isinstance(parent[arr_key], list):
                    raise TomlParseError('Array of tables conflict with existing value')
                new_tbl = {}
                parent[arr_key].append(new_tbl)
                current_table = new_tbl
                array_of_table_stack = parts
                continue
            else:
                # normal table
                if not line_nocom.endswith(']'):
                    raise TomlParseError('Malformed table header')
                inside = line_nocom[1:-1].strip()
                path = parse_key(inside)
                if isinstance(path, list):
                    parts = path
                else:
                    parts = [path]
                # create tables
                current_table = ensure_table(root, parts)
                continue
        # key/value line
        if '=' not in line_nocom:
            raise TomlParseError('Expected key/value pair')
        key_str, val_str = line_nocom.split('=', 1)
        key = parse_key(key_str)
        # Parse value possibly multi-line, need iterator that can feed extra lines
        value = parse_value(val_str.strip(), lines_iter)
        # Insert into current table respecting dotted keys
        if isinstance(key, list):
            # nested insertion
            cur = current_table
            for part in key[:-1]:
                if part not in cur:
                    cur[part] = {}
                elif not isinstance(cur[part], dict):
                    raise TomlParseError('Dotted key conflict with existing value')
                cur = cur[part]
            final = key[-1]
            if final in cur:
                raise TomlParseError('Duplicate key')
            cur[final] = value
        else:
            if key in current_table:
                raise TomlParseError('Duplicate key')
            current_table[key] = value
    return root

def main():
    if len(sys.argv) < 2:
        print('Usage: python3 tomlq.py FILE [KEYPATH]', file=sys.stderr)
        sys.exit(1)
    filename = sys.argv[1]
    keypath = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        data = parse_toml(lines)
    except FileNotFoundError:
        print(f'File not found: {filename}', file=sys.stderr)
        sys.exit(1)
    except TomlParseError as e:
        print(f'Parse error: {e}', file=sys.stderr)
        sys.exit(1)
    if keypath:
        parts = keypath.split('.')
        cur = data
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                print(f'Key path not found: {keypath}', file=sys.stderr)
                sys.exit(2)
        print(json.dumps(cur, ensure_ascii=False))
    else:
        print(json.dumps(data, ensure_ascii=False))

if __name__ == '__main__':
    main()
