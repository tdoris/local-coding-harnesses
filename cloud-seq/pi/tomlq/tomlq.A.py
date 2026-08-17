#!/usr/bin/env python3
"""tomlq.py - minimal TOML subset parser to JSON

Usage: python3 tomlq.py FILE [KEYPATH]

Implements the subset described in the prompt.  It does not depend on any
external libraries – only the Python standard library.

The implementation focuses on correctness for the required features while
remaining reasonably compact.  It is deliberately written in a single file
so that it can be executed directly.
"""

import sys
import json
import re
from typing import Any, List, Tuple, Dict

# ------------------------------------------------------------
# Helper utilities
# ------------------------------------------------------------

def error(message: str, code: int = 1) -> None:
    sys.stderr.write(message + "\n")
    sys.exit(code)

# ------------------------------------------------------------
# Lexical helpers – comment stripping, string detection
# ------------------------------------------------------------

def strip_comment(line: str) -> str:
    """Remove a comment from a line, respecting quoted strings.
    The first unescaped '#' that is not inside a string terminates the line.
    """
    in_basic = False
    in_literal = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"' and not in_literal:
            # check for triple-quote start – we treat it like a normal quote for comment stripping
            if line[i:i+3] == '"""':
                # skip the three quotes
                i += 3
                continue
            in_basic = not in_basic
            i += 1
            continue
        if ch == "'" and not in_basic:
            if line[i:i+3] == "'''":
                i += 3
                continue
            in_literal = not in_literal
            i += 1
            continue
        if ch == "#" and not in_basic and not in_literal:
            return line[:i].rstrip()
        i += 1
    return line.rstrip()

# ------------------------------------------------------------
# Parsing of values
# ------------------------------------------------------------

def parse_basic_string(s: str) -> str:
    # assumes leading and trailing double quotes have been removed
    esc = {
        'b': '\b',
        't': '\t',
        'n': '\n',
        'f': '\f',
        'r': '\r',
        '"': '"',
        '\\': '\\',
    }
    res = ''
    i = 0
    while i < len(s):
        if s[i] == '\\':
            i += 1
            if i >= len(s):
                error('Invalid escape in string')
            ch = s[i]
            if ch in esc:
                res += esc[ch]
                i += 1
                continue
            if ch == 'u':
                hexpart = s[i+1:i+5]
                if len(hexpart) != 4 or not re.fullmatch(r'[0-9A-Fa-f]{4}', hexpart):
                    error('Invalid \u escape')
                res += chr(int(hexpart, 16))
                i += 5
                continue
            if ch == 'U':
                hexpart = s[i+1:i+9]
                if len(hexpart) != 8 or not re.fullmatch(r'[0-9A-Fa-f]{8}', hexpart):
                    error('Invalid \U escape')
                res += chr(int(hexpart, 16))
                i += 9
                continue
            error('Unknown escape \\%s' % ch)
        else:
            res += s[i]
            i += 1
    return res


def parse_literal_string(s: str) -> str:
    # no processing, just return content between the quotes
    return s


def parse_number(tok: str) -> Any:
    # underscores are allowed and should be ignored
    plain = tok.replace('_', '')
    if plain.lower().startswith('0x'):
        return int(plain, 16)
    if plain.lower().startswith('0o'):
        return int(plain, 8)
    if plain.lower().startswith('0b'):
        return int(plain, 2)
    # decimal integer?
    if re.fullmatch(r'[+-]?\d+', plain):
        # leading zeros not allowed unless the number is exactly '0'
        if plain.lstrip('+-').startswith('0') and plain.lstrip('+-') != '0':
            error('Invalid leading zero in integer')
        return int(plain)
    # float?
    if re.fullmatch(r'[+-]?(?:\d+_?)*\d*\.\d+(?:[eE][+-]?\d+)?', plain) or \
       re.fullmatch(r'[+-]?\d+(?:[eE][+-]?\d+)', plain):
        return float(plain)
    error('Invalid number: %s' % tok)


def parse_bool(tok: str) -> bool:
    if tok == 'true':
        return True
    if tok == 'false':
        return False
    error('Invalid boolean: %s' % tok)


def split_array_items(content: str) -> List[str]:
    # split on commas, respecting nested brackets/braces and strings
    items = []
    level = 0
    current = ''
    i = 0
    while i < len(content):
        ch = content[i]
        if ch in '"' or ch == "'":
            # quoted string – consume till matching quote (handling escapes for ")
            quote = ch
            current += ch
            i += 1
            while i < len(content):
                current += content[i]
                if content[i] == '\\':
                    i += 1
                    if i < len(content):
                        current += content[i]
                        i += 1
                    continue
                if content[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch == '[' or ch == '{':
            level += 1
        elif ch == ']' or ch == '}':
            level -= 1
        if ch == ',' and level == 0:
            items.append(current.strip())
            current = ''
            i += 1
            continue
        current += ch
        i += 1
    if current.strip():
        items.append(current.strip())
    return items


def parse_array(tok: str) -> List[Any]:
    # expects string starting with '[' and ending with ']'
    inner = tok[1:-1].strip()
    if not inner:
        return []
    items = split_array_items(inner)
    return [parse_value(item) for item in items]


def parse_inline_table(tok: str) -> Dict[str, Any]:
    # expects string starting with '{' and ending with '}'
    inner = tok[1:-1].strip()
    if not inner:
        return {}
    # split on commas not inside structures
    parts = split_array_items(inner)  # reuse splitter (commas at top level)
    table = {}
    for part in parts:
        if '=' not in part:
            error('Invalid inline table entry: %s' % part)
        k, v = part.split('=', 1)
        key = parse_key(k.strip())
        if len(key) != 1:
            error('Dotted keys not allowed inside inline tables')
        if key[0] in table:
            error('Duplicate key in inline table: %s' % key[0])
        table[key[0]] = parse_value(v.strip())
    return table


def parse_key(text: str) -> List[str]:
    # Handles bare, quoted, and dotted keys. Returns list of key parts.
    parts = []
    token = ''
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in ' \t':
            i += 1
            continue
        if ch == '.':
            if token == '':
                error('Empty key part')
            parts.append(token)
            token = ''
            i += 1
            continue
        if ch == '"' or ch == "'":
            quote = ch
            end = i + 1
            escaped = False
            while end < len(text):
                c = text[end]
                if c == '\\' and quote == '"':
                    escaped = not escaped
                    end += 1
                    continue
                if c == quote and not escaped:
                    break
                escaped = False
                end += 1
            else:
                error('Unclosed quoted key')
            raw = text[i+1:end]
            if quote == '"':
                token = parse_basic_string(raw)
            else:
                token = parse_literal_string(raw)
            i = end + 1
            continue
        # bare char
        if re.match(r'[A-Za-z0-9_-]', ch):
            token += ch
            i += 1
            continue
        error('Invalid character in key: %s' % ch)
    if token:
        parts.append(token)
    if not parts:
        error('Empty key')
    return parts


def parse_value(tok: str) -> Any:
    # Strip surrounding whitespace (already done in many callers)
    tok = tok.strip()
    if not tok:
        error('Empty value')
    # String
    if tok.startswith('"""'):
        # multiline basic – trim first newline if present
        body = tok[3:-3]
        if body.startswith('\n'):
            body = body[1:]
        # handle line continuation backslash (simplified: remove backslash + following whitespace)
        body = re.sub(r'\\[ \t]*\n[ \t]*', '', body)
        return parse_basic_string(body)
    if tok.startswith("'''"):
        body = tok[3:-3]
        if body.startswith('\n'):
            body = body[1:]
        return parse_literal_string(body)
    if tok.startswith('"') and tok.endswith('"'):
        return parse_basic_string(tok[1:-1])
    if tok.startswith("'") and tok.endswith("'"):
        return parse_literal_string(tok[1:-1])
    # Array
    if tok.startswith('[') and tok.endswith(']'):
        return parse_array(tok)
    # Inline table
    if tok.startswith('{') and tok.endswith('}'):
        return parse_inline_table(tok)
    # Booleans
    if tok in ('true', 'false'):
        return parse_bool(tok)
    # Numbers
    if re.match(r'^[+-]?(0x[0-9A-Fa-f_]+|0o[0-7_]+|0b[01_]+|\d[\d_]*([.]\d[\d_]*)?([eE][+-]?\d+)?|\d+)$', tok):
        return parse_number(tok)
    error('Unsupported value: %s' % tok)

# ------------------------------------------------------------
# Document building utilities
# ------------------------------------------------------------

class TOMLParser:
    def __init__(self):
        self.root: Dict[str, Any] = {}
        self.current_path: List[str] = []  # path of the table we are currently in
        self.tables_defined: set = set()   # set of tuple paths for tables (including array tables elements)
        self.array_table_counters: Dict[Tuple[str, ...], int] = {}

    def set_value(self, key_parts: List[str], value: Any, is_array_of_tables: bool = False) -> None:
        # Navigate/create dicts according to current table path
        container = self.root
        for p in self.current_path:
            container = container.setdefault(p, {})
            if not isinstance(container, dict):
                error('Attempt to use non-table as parent')
        # Resolve dotted key parts
        for i, part in enumerate(key_parts):
            if i == len(key_parts) - 1:
                # final part – assign
                if part in container:
                    error('Duplicate key: %s' % '.'.join(self.current_path + key_parts))
                container[part] = value
            else:
                # intermediate tables
                if part not in container:
                    container[part] = {}
                elif not isinstance(container[part], dict):
                    error('Key already defined as a non-table: %s' % part)
                container = container[part]

    def ensure_table(self, path: List[str], array_of_tables: bool = False) -> None:
        # Ensure a table exists at given path (creating parents). For array tables, create a new dict element.
        container = self.root
        for i, part in enumerate(path):
            if i == len(path) - 1:
                # final part
                if array_of_tables:
                    # must be a list
                    if part not in container:
                        container[part] = []
                    elif not isinstance(container[part], list):
                        error('Attempt to redefine non-array as array of tables: %s' % part)
                    # Append a new dict for this occurrence
                    new_elem: Dict[str, Any] = {}
                    container[part].append(new_elem)
                    # set current_path to this new element
                    self.current_path = path[:-1] + [part, str(len(container[part]) - 1)]
                else:
                    if part in container:
                        existing = container[part]
                        if isinstance(existing, dict):
                            # existing static table – ok, just move into it
                            pass
                        else:
                            error('Duplicate table definition: %s' % '.'.join(path))
                    else:
                        container[part] = {}
                    self.current_path = path
                return
            else:
                # intermediate part – must be a table
                if part not in container:
                    container[part] = {}
                elif not isinstance(container[part], dict):
                    error('Intermediate key not a table: %s' % part)
                container = container[part]
        # unreachable

    def parse_header(self, line: str) -> None:
        line = line.strip()
        if line.startswith('[[', 0) and line.endswith(']]'):
            inner = line[2:-2].strip()
            path = parse_key(inner)
            self.ensure_table(path, array_of_tables=True)
        elif line.startswith('[', 0) and line.endswith(']'):
            inner = line[1:-1].strip()
            path = parse_key(inner)
            self.ensure_table(path, array_of_tables=False)
        else:
            error('Invalid header line: %s' % line)

    def parse_line(self, raw_line: str) -> None:
        line = strip_comment(raw_line)
        if not line:
            return
        if line.lstrip().startswith('['):
            self.parse_header(line)
            return
        # key/value line
        if '=' not in line:
            error('Invalid line (no =): %s' % raw_line)
        key_part, value_part = line.split('=', 1)
        key_parts = parse_key(key_part.strip())
        value = parse_value(value_part.strip())
        self.set_value(key_parts, value)

    def parse(self, lines: List[str]) -> Dict[str, Any]:
        for raw in lines:
            self.parse_line(raw)
        return self.root

# ------------------------------------------------------------
# Main driver
# ------------------------------------------------------------

def main(argv: List[str]) -> None:
    if not (2 <= len(argv) <= 3):
        error('Usage: python3 tomlq.py FILE [KEYPATH]')
    filename = argv[1]
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.readlines()
    except Exception as e:
        error(f'Cannot read file: {e}', 1)
    parser = TOMLParser()
    data = parser.parse(content)
    if len(argv) == 3:
        path = argv[2].split('.') if argv[2] else []
        cur: Any = data
        for part in path:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                error('Key path not found', 2)
        json.dump(cur, sys.stdout, ensure_ascii=False)
        sys.stdout.write('\n')
    else:
        json.dump(data, sys.stdout, ensure_ascii=False)
        sys.stdout.write('\n')

if __name__ == '__main__':
    main(sys.argv)
