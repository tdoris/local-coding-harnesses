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

class _InlineTable(dict):
    """Marker dict for inline tables (immutable)."""
    pass

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
    """Unescape basic string escapes, rejecting invalid ones."""
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
    # Replace valid escapes
    result = re.sub(r'\\([btnfr"\\uU][0-9a-fA-F]{0,8})', repl, s)
    # Detect any leftover backslashes indicating invalid escapes
    if re.search(r'\\(?![btnfr"\\uU])', result):
        _error("invalid escape sequence")
    return result

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
    """Read lines from the global iterator to finish a multiline string, handling backslash continuation."""
    lines = []
    if first_line != '':
        lines.append(first_line)
    for raw in _line_iter:
        line = raw.rstrip('\n')
        if line.endswith(delim):
            lines.append(line[:-len(delim)])
            break
        lines.append(line)
    else:
        _error("unterminated multiline string")

    # Trim first newline if the opening delimiter is immediately followed by a newline
    if lines and lines[0] == '' and first_line == '':
        lines = lines[1:]

    # Build the final string respecting backslash continuations (which remove the newline and following whitespace)
    text = ''
    continuation = False
    for l in lines:
        if continuation:
            l = l.lstrip()
        if l.endswith('\\') and not l.endswith('\\\\'):
            continuation = True
            text += l[:-1]
        else:
            continuation = False
            if text:
                text += '\n' + l
            else:
                text = l
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
    # Gather characters until the matching closing ']'
    txt = tok
    depth = txt.count('[') - txt.count(']')
    inner_parts = []
    # If the token contains the closing bracket on the same line, handle directly
    if depth == 0:
        # strip outer brackets
        inner = txt.strip()[1:-1]
        return _parse_array_items(inner)
    # Multi‑line array: keep reading lines until depth returns to zero
    while depth > 0:
        raw = next(_line_iter, None)
        if raw is None:
            _error("unterminated array")
        line = _strip_comments(raw).strip()
        if not line:
            continue
        for ch in line:
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
        inner_parts.append(line)
    # Join the collected parts and strip the outer brackets
    inner_text = ' '.join(inner_parts)
    # Remove the first '[' and the last ']' that balanced the depth
    first_bracket = inner_text.find('[')
    last_bracket = inner_text.rfind(']')
    inner = inner_text[first_bracket+1:last_bracket]
    return _parse_array_items(inner)

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
    """Parse an inline table, supporting dotted keys."""
    content = tok.strip()
    if not (content.startswith('{') and content.endswith('}')):
        _error("invalid inline table")
    inner = content[1:-1].strip()
    if not inner:
        return _InlineTable()
    table = _InlineTable()
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
        # Dotted keys inside an inline table are allowed
        key_parts = _parse_dotted_key(k.strip())
        value = _parse_value(v.strip())
        cur = table
        for i, kp in enumerate(key_parts):
            if i == len(key_parts) - 1:
                if kp in cur:
                    _error(f"duplicate key {kp} in inline table")
                cur[kp] = value
            else:
                if kp not in cur:
                    cur[kp] = OrderedDict()
                elif not isinstance(cur[kp], dict):
                    _error(f"key {kp} already has a non-table value")
                cur = cur[kp]
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
    """Parse a dotted key string into list of components, rejecting whitespace in bare keys."""
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
            if not buf:
                _error("empty key component")
            parts.append(_parse_key(buf.strip()))
            buf = ''
            i += 1
            continue
        if ch.isspace():
            # whitespace allowed around dots but not inside a key component
            if buf:
                _error("invalid whitespace in key")
            i += 1
            continue
        buf += ch
        i += 1
    if not buf:
        _error("empty key component")
    parts.append(_parse_key(buf.strip()))
    return parts

def _assign_path(root, path, value, is_table=False):
    """Assign value into nested dicts according to path, with duplicate table detection."""
    cur = root
    for i, part in enumerate(path):
        if i == len(path) - 1:
            if is_table:
                if part in cur:
                    if isinstance(cur[part], list):
                        _error(f"cannot redefine array of tables as a single table {part}")
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
                # array of tables (supports nested paths)
                path = _parse_dotted_key(line[2:-2])
                cur = document
                # walk all but the last component, handling intermediate lists
                for part in path[:-1]:
                    if isinstance(cur, list):
                        if not cur:
                            _error(f"cannot extend empty array for key {part}")
                        cur = cur[-1]
                    if part not in cur:
                        cur[part] = OrderedDict()
                    elif not isinstance(cur[part], dict):
                        _error(f"cannot redefine non-table key {part}")
                    cur = cur[part]
                last = path[-1]
                # ensure the final component is a list of tables
                if isinstance(cur, list):
                    if not cur:
                        _error(f"cannot create array of tables on empty array for {last}")
                    cur = cur[-1]
                if last not in cur:
                    cur[last] = []
                elif not isinstance(cur[last], list):
                    _error(f"cannot redefine static table {'.'.join(path)} as array of tables")
                new_elem = OrderedDict()
                cur[last].append(new_elem)
                current_table = new_elem
            elif line.startswith('[') and line.endswith(']'):
                # Standard table (or super‑table). Resolve path, handling arrays of tables.
                path = _parse_dotted_key(line[1:-1])
                cur = document
                for idx, part in enumerate(path):
                    if isinstance(cur, list):
                        if not cur:
                            _error(f"cannot refer to table in empty array at {'.'.join(path[:idx])}")
                        cur = cur[-1]  # last element of the array
                    if idx == len(path) - 1:
                        # final component: ensure it's a table dict
                        if part not in cur:
                            cur[part] = OrderedDict()
                        elif not isinstance(cur[part], dict):
                            _error(f"cannot redefine non-table key {part}")
                        current_table = cur[part]
                    else:
                        if part not in cur:
                            cur[part] = OrderedDict()
                        elif not isinstance(cur[part], dict):
                            _error(f"key {part} already has a non-table value")
                        cur = cur[part]
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
                    # Disallow extending an inline table
                    if isinstance(target, _InlineTable):
                        _error(f"cannot extend inline table {part}")
                    if isinstance(target.get(part), _InlineTable):
                        _error(f"cannot extend inline table {part}")
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
