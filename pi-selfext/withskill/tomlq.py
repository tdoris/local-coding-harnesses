#!/usr/bin/env python3
"""tomlq.py – Minimal TOML subset parser converting to JSON.
Implementation follows the test suite requirements. No external libraries are used.
"""
import sys, json, re

class TomlParseError(Exception):
    pass

# Helper functions for string parsing
def parse_basic_string(s, i):
    i += 1
    out = []
    while i < len(s):
        c = s[i]
        if c == '"':
            return ''.join(out), i + 1
        if c == '\\':
            if i + 1 >= len(s):
                raise TomlParseError('Invalid escape at end of string')
            esc = s[i+1]
            if esc == 'b': out.append('\b')
            elif esc == 't': out.append('\t')
            elif esc == 'n': out.append('\n')
            elif esc == 'f': out.append('\f')
            elif esc == 'r': out.append('\r')
            elif esc == '"': out.append('"')
            elif esc == '\\': out.append('\\')
            elif esc == 'u':
                if i+5 >= len(s): raise TomlParseError('Invalid unicode escape')
                hexpart = s[i+2:i+6]
                if not re.fullmatch(r'[0-9A-Fa-f]{4}', hexpart):
                    raise TomlParseError('Invalid unicode escape')
                out.append(chr(int(hexpart,16)))
                i += 4
            elif esc == 'U':
                if i+9 >= len(s): raise TomlParseError('Invalid unicode escape')
                hexpart = s[i+2:i+10]
                if not re.fullmatch(r'[0-9A-Fa-f]{8}', hexpart):
                    raise TomlParseError('Invalid unicode escape')
                out.append(chr(int(hexpart,16)))
                i += 8
            else:
                raise TomlParseError(f'Invalid escape \\{esc}')
            i += 2
            continue
        if c == '\n':
            out.append('\n')
            i += 1
            continue
        out.append(c)
        i += 1
    raise TomlParseError('Unterminated basic string')

def parse_literal_string(s, i):
    i += 1
    out = []
    while i < len(s):
        c = s[i]
        if c == "'":
            return ''.join(out), i + 1
        out.append(c)
        i += 1
    raise TomlParseError('Unterminated literal string')

def parse_multiline_basic(s, i):
    if i < len(s) and s[i] == '\n':
        i += 1
    out = []
    while i < len(s):
        if s.startswith('"""', i):
            return ''.join(out), i + 3
        c = s[i]
        if c == '\\':
            j = i+1
            while j < len(s) and s[j] in ' \t':
                j += 1
            if j < len(s) and s[j] == '\n':
                # skip the newline
                j += 1
                # skip any whitespace including newlines
                while j < len(s) and s[j] in ' \t\n':
                    j += 1
                i = j
                continue
            if i+1 >= len(s): raise TomlParseError('Invalid escape in multiline string')
            esc = s[i+1]
            if esc == 'b': out.append('\b')
            elif esc == 't': out.append('\t')
            elif esc == 'n': out.append('\n')
            elif esc == 'f': out.append('\f')
            elif esc == 'r': out.append('\r')
            elif esc == '"': out.append('"')
            elif esc == '\\': out.append('\\')
            elif esc == 'u':
                if i+5 >= len(s): raise TomlParseError('Invalid unicode escape')
                hexpart = s[i+2:i+6]
                if not re.fullmatch(r'[0-9A-Fa-f]{4}', hexpart):
                    raise TomlParseError('Invalid unicode escape')
                out.append(chr(int(hexpart,16)))
                i += 4
            elif esc == 'U':
                if i+9 >= len(s): raise TomlParseError('Invalid unicode escape')
                hexpart = s[i+2:i+10]
                if not re.fullmatch(r'[0-9A-Fa-f]{8}', hexpart):
                    raise TomlParseError('Invalid unicode escape')
                out.append(chr(int(hexpart,16)))
                i += 8
            else:
                raise TomlParseError(f'Invalid escape \\{esc}')
            i += 2
            continue
        if c == '\n':
            out.append('\n')
            i += 1
            continue
        out.append(c)
        i += 1
    raise TomlParseError('Unterminated multiline basic string')

def parse_multiline_literal(s, i):
    if i < len(s) and s[i] == '\n':
        i += 1
    out = []
    while i < len(s):
        if s.startswith("'''", i):
            return ''.join(out), i + 3
        out.append(s[i])
        i += 1
    raise TomlParseError('Unterminated multiline literal string')

def parse_key(s, i, stop_char='='):
    parts = []
    while True:
        while i < len(s) and s[i] in ' \t':
            i += 1
        if i >= len(s):
            raise TomlParseError('Unexpected end while parsing key')
        if s[i] == '"':
            val, i = parse_basic_string(s, i)
            parts.append(val)
        elif s[i] == "'":
            val, i = parse_literal_string(s, i)
            parts.append(val)
        else:
            m = re.match(r'[A-Za-z0-9_-]+', s[i:])
            if not m:
                raise TomlParseError('Invalid bare key')
            parts.append(m.group(0))
            i += len(m.group(0))
        while i < len(s) and s[i] in ' \t':
            i += 1
        if i < len(s) and s[i] == '.':
            i += 1
            continue
        break
    if stop_char:
        while i < len(s) and s[i] in ' \t':
            i += 1
        if i >= len(s) or s[i] != stop_char:
            raise TomlParseError(f"Expected '{stop_char}' after key")
        i += 1
    return parts, i

def parse_number_token(tok):
    raw = tok.replace('_','')
    if raw == 'true':
        return True
    if raw == 'false':
        return False
    if raw.startswith('0x') or raw.startswith('0X'):
        return int(raw,16)
    if raw.startswith('0o') or raw.startswith('0O'):
        return int(raw,8)
    if raw.startswith('0b') or raw.startswith('0B'):
        return int(raw,2)
    sign = 1
    if raw and raw[0] in '+-':
        if raw[0] == '-': sign = -1
        raw_body = raw[1:]
    else:
        raw_body = raw
    if re.search(r'[\.eE]', raw_body):
        return sign * float(raw_body)
    if raw_body == '0':
        return sign * 0
    if raw_body.startswith('0'):
        raise TomlParseError('Leading zeros not allowed')
    if not raw_body.isdigit():
        raise TomlParseError('Invalid integer')
    return sign * int(raw_body)

def parse_value(s, i):
    while i < len(s) and s[i] in ' \t\r\n':
        i += 1
    if i >= len(s):
        raise TomlParseError('Missing value')
    c = s[i]
    if c == '"':
        if s.startswith('"""', i):
            return parse_multiline_basic(s, i+3)
        else:
            return parse_basic_string(s, i)
    if c == "'":
        if s.startswith("'''", i):
            return parse_multiline_literal(s, i+3)
        else:
            return parse_literal_string(s, i)
    if c == '[':
        return parse_array(s, i)
    if c == '{':
        return parse_inline_table(s, i)
    m = re.match(r'[^\s\,\]\}\#]+', s[i:])
    if not m:
        raise TomlParseError('Unable to parse value')
    token = m.group(0)
    i += len(token)
    return parse_number_token(token), i

def parse_array(s, i):
    i += 1
    arr = []
    while True:
        while i < len(s) and s[i] in ' \t\r\n':
            i += 1
        if i < len(s) and s[i] == '#':
            while i < len(s) and s[i] != '\n':
                i += 1
            continue
        if i < len(s) and s[i] == ']':
            i += 1
            return arr, i
        val, i = parse_value(s, i)
        arr.append(val)
        while i < len(s) and s[i] in ' \t\r\n':
            i += 1
        if i < len(s) and s[i] == '#':
            while i < len(s) and s[i] != '\n':
                i += 1
            continue
        if i < len(s) and s[i] == ',':
            i += 1
            continue
        if i < len(s) and s[i] == ']':
            i += 1
            return arr, i
        raise TomlParseError('Invalid array syntax')

def parse_inline_table(s, i):
    i += 1
    tbl = {}
    while True:
        while i < len(s) and s[i] in ' \t\r\n':
            i += 1
        if i < len(s) and s[i] == '#':
            while i < len(s) and s[i] != '\n':
                i += 1
            continue
        if i < len(s) and s[i] == '}':
            i += 1
            inline_table_ids.add(id(tbl))
            return tbl, i
        key_parts, i = parse_key(s, i, stop_char='=')
        val, i = parse_value(s, i)
        assign_into(tbl, key_parts, val, inline=True)
        while i < len(s) and s[i] in ' \t\r\n':
            i += 1
        if i < len(s) and s[i] == ',':
            i += 1
            continue
        if i < len(s) and s[i] == '}':
            i += 1
            inline_table_ids.add(id(tbl))
            return tbl, i
        raise TomlParseError('Invalid inline table syntax')

inline_table_ids = set()

def assign_into(root, parts, value, inline=False):
    cur = root
    for idx, part in enumerate(parts[:-1]):
        if id(cur) in inline_table_ids:
            raise TomlParseError('Attempt to extend inline table')
        if part not in cur:
            cur[part] = {}
        elif not isinstance(cur[part], dict):
            raise TomlParseError('Key already set as non-table')
        cur = cur[part]
    last = parts[-1]
    if id(cur) in inline_table_ids:
        raise TomlParseError('Attempt to extend inline table')
    if last in cur:
        raise TomlParseError('Duplicate key')
    cur[last] = value
    # inline tables are marked after creation in parse_inline_table

def parse_toml(text):
    defined_table_paths = set()
    data = {}
    cur_ctx = data
    i = 0
    length = len(text)
    while i < length:
        while i < length and text[i] in ' \t\r\n':
            i += 1
        if i >= length:
            break
        if text[i] == '#':
            while i < length and text[i] != '\n':
                i += 1
            continue
        if text[i] == '[':
            if i+1 < length and text[i+1] == '[':
                i += 2
                start = i
                while i < length and not (text[i] == ']' and i+1 < length and text[i+1] == ']'):
                    i += 1
                if i+1 >= length:
                    raise TomlParseError('Unterminated array of tables header')
                header_str = text[start:i]
                i += 2
                while i < length and text[i] not in '\n':
                    if text[i] == '#':
                        while i < length and text[i] != '\n':
                            i += 1
                        break
                    i += 1
                path, _ = parse_key(header_str, 0, stop_char='')
                container = data
                for part in path[:-1]:
                    if part not in container:
                        container[part] = {}
                        container = container[part]
                    else:
                        val = container[part]
                        if isinstance(val, dict):
                            container = val
                        elif isinstance(val, list):
                            if not val:
                                raise TomlParseError('Array of tables empty')
                            container = val[-1]
                        else:
                            raise TomlParseError('Parent not a table')
                last = path[-1]
                lst = container.get(last)
                if lst is None:
                    lst = []
                    container[last] = lst
                elif not isinstance(lst, list):
                    raise TomlParseError('Expected list for array of tables')
                new_tbl = {}
                lst.append(new_tbl)
                cur_ctx = new_tbl
            else:
                i += 1
                start = i
                while i < length and text[i] != ']':
                    i += 1
                if i >= length:
                    raise TomlParseError('Unterminated table header')
                header_str = text[start:i]
                i += 1
                while i < length and text[i] != '\n':
                    if text[i] == '#':
                        while i < length and text[i] != '\n':
                            i += 1
                        break
                    i += 1
                path, _ = parse_key(header_str, 0, stop_char='')
                container = data
                for idx, part in enumerate(path):
                    if part not in container:
                        # create new table
                        container[part] = {}
                        container = container[part]
                    else:
                        val = container[part]
                        if isinstance(val, dict):
                            container = val
                        elif isinstance(val, list):
                            # array of tables, use last element
                            if not val:
                                raise TomlParseError('Array of tables empty')
                            container = val[-1]
                        else:
                            raise TomlParseError('Key already defined as non-table')
                cur_ctx = container
                path_tuple = tuple(path)
                if path_tuple in defined_table_paths:
                    raise TomlParseError('Duplicate table')
                defined_table_paths.add(path_tuple)
            continue
        key_parts, i = parse_key(text, i, stop_char='=')
        val, i = parse_value(text, i)
        while i < length and text[i] not in '\n':
            if text[i] == '#':
                while i < length and text[i] != '\n':
                    i += 1
                break
            if text[i] in ' \t\r':
                i += 1
                continue
            raise TomlParseError('Extra characters after value')
        assign_into(cur_ctx, key_parts, val)
    return data

def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print('Usage: python3 tomlq.py FILE [KEYPATH]', file=sys.stderr)
        sys.exit(1)
    path = sys.argv[1]
    keypath = sys.argv[2] if len(sys.argv) == 3 else None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        data = parse_toml(text)
        if keypath is None:
            print(json.dumps(data))
        else:
            cur = data
            for p in keypath.split('.'):                
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                else:
                    print('Key path not found', file=sys.stderr)
                    sys.exit(2)
            print(json.dumps(cur))
    except TomlParseError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
