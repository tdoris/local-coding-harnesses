#!/usr/bin/env python3
"""
tomlq.py - Minimal TOML parser (subset) that outputs JSON.

Usage:
    python3 tomlq.py FILE [KEYPATH]

Exit codes:
    0 - success
    1 - parse error
    2 - key path not found
"""

import sys
import re
import json
from collections import OrderedDict

# ---------- Utility functions ----------

def _error(msg):
    """Print error to stderr and exit with code 1."""
    print(f"parse error: {msg}", file=sys.stderr)
    sys.exit(1)

def _keypath_error(msg):
    """Print error to stderr and exit with code 2."""
    print(msg, file=sys.stderr)
    sys.exit(2)

def _strip_comments(line):
    """Remove comments, respecting quoted strings."""
    in_single = in_double = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "'" and not in_double:
            # toggle literal string, ignore escaped quotes (none)
            if i > 0 and line[i-1] == "\\":
                pass
            else:
                in_single = not in_single
        elif ch == '"' and not in_single:
            # toggle basic string, handle escape
            if i > 0 and line[i-1] == "\\":
                pass
            else:
                in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i]
        i += 1
    return line

def _unescape_basic(s):
    """Unescape basic string escapes."""
    def repl(m):
        esc = m.group(1)
        if esc == 'b':
            return '\b'
        if esc == 't':
            return '\t'
        if esc == 'n':
            return '\n'
        if esc == 'f':
            return '\f'
        if esc == 'r':
            return '\r'
        if esc == '"':
            return '"'
        if esc == '\\':
            return '\\'
        if esc.startswith('u'):
            return chr(int(esc[1:], 16))
        if esc.startswith('U'):
            return chr(int(esc[1:], 16))
        _error(f"invalid escape \\{esc}")
    return re.sub(r'\\([btnfr"\\uU][0-9a-fA-F]{0,8})', repl, s)

def _parse_string(token):
    """Parse a TOML string token (basic or literal, single or multi-line)."""
    if token.startswith('"""'):
        # multiline basic
        if token == '"""':
            # start on next line
            return _parse_multiline_string('"""', basic=True)
        else:
            # same line content after opening triple quotes
            inner = token[3:]
            if inner.endswith('"""'):
                inner = inner[:-3]
                return _unescape_basic(inner)
            else:
                # continuation on following lines
                return _parse_multiline_string('"""', basic=True, first_line=inner)
    if token.startswith("'''"):
        # multiline literal
        if token == "'''":
            return _parse_multiline_string("'''", basic=False)
        else:
            inner = token[3:]
            if inner.endswith("'''"):
                return inner[:-3]
            else:
                return _parse_multiline_string("'''", basic=False, first_line=inner)

    # single line
    if token.startswith('"'):
        if not token.endswith('"'):
            _error("unterminated basic string")
        inner = token[1:-1]
        return _unescape_basic(inner)
    if token.startswith("'"):
        if not token.endswith("'"):
            _error("unterminated literal string")
        return token[1:-1]
    _error("invalid string token")

def _parse_multiline_string(delim, basic, first_line=''):
    """Read lines from the global iterator to finish a multiline string."""
    lines = []
    # The first line (after opening delimiter) may be empty and is trimmed if it's the first line.
    if first_line != '':
        lines.append(first_line)
    for raw in _line_iter:
        line = raw.rstrip('\n')
        if line.endswith(delim):
            # Trim the ending delimiter
            content = line[:-len(delim)]
            lines.append(content)
            break
        lines.append(line)
    else:
        _error("unterminated multiline string")

    # According to TOML spec, a newline immediately after opening delimiter is trimmed
    if lines and lines[0] == '' and first_line == '':
        lines = lines[1:]

    # Handle line ending backslash continuation
    result = []
    continuation = False
    for l in lines:
        if continuation:
            # leading whitespace after a continuation backslash is stripped
            l = l.lstrip()
        if l.endswith('\\') and not l.endswith('\\\\'):
            continuation = True
            result.append(l[:-1])
        else:
            continuation = False
            result.append(l)
    text = '\n'.join(result)
    if basic:
        return _unescape_basic(text)
    else:
        return text

def _parse_number(tok):
    """Parse integer or float with underscores, respecting bases."""
    # Detect base prefixes
    if tok.startswith(('+', '-')):
        sign = tok[0]
        rest = tok[1:]
    else:
        sign = ''
        rest = tok

    if '_' in rest:
        rest = rest.replace('_', '')

    # Hex, octal, binary integers
    if rest.startswith('0x') or rest.startswith('0X'):
        try:
            return int(sign + rest, 0)
        except ValueError:
            _error(f"invalid hex integer {tok}")
    if rest.startswith('0o') or rest.startswith('0O'):
        try:
            return int(sign + rest, 0)
        except ValueError:
            _error(f"invalid octal integer {tok}")
    if rest.startswith('0b') or rest.startswith('0B'):
        try:
            return int(sign + rest, 0)
        except ValueError:
            _error(f"invalid binary integer {tok}")

    # Float detection (contains . or e/E)
    if '.' in rest or 'e' in rest.lower():
        try:
            return float(sign + rest)
        except ValueError:
            _error(f"invalid float {tok}")

    # Decimal integer – leading zeros not allowed (except zero itself)
    if len(rest) > 1 and rest.startswith('0'):
        _error(f"invalid decimal integer with leading zero {tok}")

    try:
        return int(sign + rest)
    except ValueError:
        _error(f"invalid integer {tok}")

def _parse_bool(tok):
    if tok == 'true':
        return True
    if tok == 'false':
        return False
    _error(f"invalid boolean {tok}")

def _parse_array(tok):
    """Parse a TOML array, possibly spanning multiple lines."""
    # Token starts with '[' and may end with ']'
    content = tok.strip()
    if content == '[]':
        return []
    # Remove outer brackets and parse inner using a small recursive descent
    # We'll collect tokens from the iterator until matching closing bracket
    inner = ''
    depth = 0
    # If the opening line has more after '['
    pos = content.find('[')
    inner = content[pos+1:]
    if ']' in inner:
        # single line array
        idx = inner.rfind(']')
        inner = inner[:idx]
        return _parse_array_items(inner)
    # multiline
    depth = 1
    for raw in _line_iter:
        line = _strip_comments(raw).strip()
        if not line:
            continue
        for ch in line:
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    # end of array
                    before = line[:line.rfind(']')]
                    inner += ' ' + before
                    return _parse_array_items(inner)
        inner += ' ' + line
    _error("unterminated array")

def _parse_array_items(s):
    """Parse comma‑separated values in an array string s."""
    items = []
    token = ''
    in_str = False
    str_delim = ''
    i = 0
    while i < len(s):
        ch = s[i]
        if in_str:
            token += ch
            if ch == str_delim and s[i-1] != '\\':
                in_str = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = True
            str_delim = ch
            token += ch
            i += 1
            continue
        if ch == ',':
            if token.strip():
                items.append(_parse_value(token.strip()))
                token = ''
            i += 1
            continue
        if ch.isspace():
            i += 1
            continue
        token += ch
        i += 1
    if token.strip():
        items.append(_parse_value(token.strip()))
    return items

def _parse_inline_table(tok):
    """Parse an inline table { a = 1, b = "x" }."""
    content = tok.strip()
    if not (content.startswith('{') and content.endswith('}')):
        _error("invalid inline table")
    inner = content[1:-1].strip()
    if not inner:
        return {}
    table = OrderedDict()
    # split on commas not inside strings
    parts = []
    token = ''
    in_str = False
    delim = ''
    for ch in inner:
        if in_str:
            token += ch
            if ch == delim and token[-2] != '\\':
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            delim = ch
            token += ch
            continue
        if ch == ',':
            parts.append(token.strip())
            token = ''
            continue
        token += ch
    if token.strip():
        parts.append(token.strip())
    for part in parts:
        if '=' not in part:
            _error("invalid inline table entry")
        k, v = part.split('=', 1)
        key = _parse_key(k.strip())
        value = _parse_value(v.strip())
        if key in table:
            _error(f"duplicate key {key} in inline table")
        table[key] = value
    return table

def _parse_key(raw):
    """Parse a bare or quoted key."""
    raw = raw.strip()
    if raw.startswith('"'):
        return _parse_string(raw)
    if raw.startswith("'"):
        return _parse_string(raw)
    # bare key validation
    if not re.fullmatch(r"[A-Za-z0-9_-]+", raw):
        _error(f"invalid bare key {raw}")
    return raw

def _parse_dotted_key(line):
    """Parse a dotted key string into list of components."""
    parts = []
    buf = ''
    in_str = False
    delim = ''
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            buf += ch
            if ch == delim and line[i-1] != '\\':
                in_str = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = True
            delim = ch
            buf += ch
            i += 1
            continue
        if ch == '.':
            parts.append(_parse_key(buf.strip()))
            buf = ''
            i += 1
            continue
        if ch.isspace():
            i += 1
            continue
        buf += ch
        i += 1
    if buf:
        parts.append(_parse_key(buf.strip()))
    return parts

def _assign_path(root, path, value, is_table=False):
    """Assign value into nested dicts according to path."""
    cur = root
    for i, part in enumerate(path):
        if i == len(path) - 1:
            # final element
            if is_table:
                if part in cur:
                    if not isinstance(cur[part], dict):
                        _error(f"cannot redefine non-table key {part}")
                else:
                    cur[part] = OrderedDict()
                return cur[part]
            else:
                if part in cur:
                    _error(f"duplicate key {part}")
                cur[part] = value
                return
        # intermediate tables
        if part not in cur:
            cur[part] = OrderedDict()
        elif not isinstance(cur[part], dict):
            _error(f"key {part} already has a non-table value")
        cur = cur[part]

def _parse_value(tok):
    """Parse an individual value token."""
    # String?
    if tok.startswith(('"""', "'''", '"', "'")):
        return _parse_string(tok)
    # Inline table?
    if tok.startswith('{'):
        return _parse_inline_table(tok)
    # Array?
    if tok.startswith('['):
        return _parse_array(tok)
    # Bool
    if tok in ('true', 'false'):
        return _parse_bool(tok)
    # Number (int or float)
    # Attempt numeric parsing; on failure treat as error
    try:
        return _parse_number(tok)
    except SystemExit:
        raise
    except Exception:
        _error(f"invalid value {tok}")

# ---------- Parsing entry point ----------

def parse_toml(text):
    """Parse TOML text (subset) into an ordered dict."""
    global _line_iter
    _line_iter = iter(text.splitlines(keepends=True))
    document = OrderedDict()
    current_table = document
    for raw_line in _line_iter:
        line = _strip_comments(raw_line).strip()
        if not line:
            continue
        if line.startswith('['):
            # Table or array of tables
            if line.startswith('[[') and line.endswith(']]'):
                # array of tables
                path = _parse_dotted_key(line[2:-2])
                # navigate to the parent of the last component
                cur = document
                for part in path[:-1]:
                    if part not in cur:
                        cur[part] = OrderedDict()
                    elif not isinstance(cur[part], dict):
                        _error(f"cannot redefine non-table key {part}")
                    cur = cur[part]
                last = path[-1]
                if last not in cur:
                    cur[last] = []
                elif not isinstance(cur[last], list):
                    _error(f"cannot redefine static table {'.'.join(path)} as array of tables")
                new_elem = OrderedDict()
                cur[last].append(new_elem)
                current_table = new_elem
            elif line.startswith('[') and line.endswith(']'):
                path = _parse_dotted_key(line[1:-1])
                tbl = _assign_path(document, path, None, is_table=True)
                current_table = tbl
            else:
                _error(f"malformed table header {line}")
        else:
            # key/value line
            if '=' not in line:
                _error(f"expected = in line: {line}")
            left, right = line.split('=', 1)
            key_parts = _parse_dotted_key(left)
            value = _parse_value(right.strip())
            # assign
            target = current_table
            # If dotted key creates sub‑tables deeper than current_table, we need to walk.
            for i, part in enumerate(key_parts):
                if i == len(key_parts) - 1:
                    if part in target:
                        _error(f"duplicate key {part}")
                    target[part] = value
                else:
                    if part not in target:
                        target[part] = OrderedDict()
                    elif not isinstance(target[part], dict):
                        _error(f"key {part} already has a non-table value")
                    target = target[part]
    return document

# ---------- Main driver ----------

def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python3 tomlq.py FILE [KEYPATH]", file=sys.stderr)
        sys.exit(1)

    filename = sys.argv[1]
    keypath = sys.argv[2] if len(sys.argv) == 3 else None

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"error reading file: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        data = parse_toml(content)
    except SystemExit as e:
        # already printed error and set code
        sys.exit(e.code)

    if keypath:
        parts = keypath.split('.')
        cur = data
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                _keypath_error(f"key path '{keypath}' not found")
        print(json.dumps(cur, ensure_ascii=False))
    else:
        print(json.dumps(data, ensure_ascii=False))

if __name__ == "__main__":
    main()
