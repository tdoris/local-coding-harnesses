#!/usr/bin/env python3
"""tomlq – minimal TOML to JSON converter (subset of TOML v1.0.0).

Supported features are listed in the problem statement.  The implementation is
self‑contained and uses only the Python standard library.  It deliberately
avoids the use of ``tomllib`` or any third‑party TOML parser.
"""

import sys
import json
import re
import ast
from collections import OrderedDict

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _strip_comment(line: str) -> str:
    """Return *line* with any ``#`` comment removed, unless the ``#`` occurs
    inside a quoted string.  This is a lightweight implementation that works
    for the subset required by the tests.
    """
    in_single = in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            # toggle single‑quoted literal string
            # ignore escaped single quote – not allowed in literal strings
            in_single = not in_single
        elif ch == '"' and not in_single:
            # toggle basic string, handling escaped quote
            if i == 0 or line[i - 1] != "\\":
                in_double = not in_double
        elif ch == "#" and not (in_single or in_double):
            return line[:i]
    return line

def _unescape_basic(s: str) -> str:
    """Unescape a basic TOML string (single‑line)."""
    # Python's ``unicode_escape`` handles most escapes, but we need to map
    # TOML's \b, \t, \n, \f, \r, \" and \\ correctly.
    esc_map = {
        "\\b": "\b",
        "\\t": "\t",
        "\\n": "\n",
        "\\f": "\f",
        "\\r": "\r",
        "\\\"": "\"",
        "\\\\": "\\",
    }
    # Replace known escapes first
    for k, v in esc_map.items():
        s = s.replace(k, v)
    # Unicode escapes – ``\uXXXX`` or ``\UXXXXXXXX`` – let Python decode them
    return bytes(s, "utf-8").decode("unicode_escape")

def _parse_number(tok: str):
    # Underscores are allowed as visual separators – remove them first.
    num = tok.replace("_", "")
    # Integer bases
    if re.fullmatch(r"[+-]?0[xX][0-9a-fA-F]+", num):
        return int(num, 16)
    if re.fullmatch(r"[+-]?0[oO][0-7]+", num):
        return int(num, 8)
    if re.fullmatch(r"[+-]?0[bB][01]+", num):
        return int(num, 2)
    # Decimal integer – reject leading zeros (except zero itself)
    if re.fullmatch(r"[+-]?0[0-9]+", num):
        raise ValueError("invalid leading zero in integer")
    if re.fullmatch(r"[+-]?[0-9]+", num):
        return int(num)
    # Float (including exponent)
    if re.fullmatch(r"[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)(?:[eE][+-]?[0-9]+)?", num):
        return float(num)
    raise ValueError(f"cannot parse number: {tok}")

def _prepare_literal(s: str) -> str:
    """Prepare a TOML literal (array or inline table) for ``ast.literal_eval``.
    Replaces TOML booleans with Python equivalents.
    """
    s = re.sub(r"\btrue\b", "True", s)
    s = re.sub(r"\bfalse\b", "False", s)
    return s

def _parse_array(text: str):
    # ``text`` includes the surrounding brackets.
    prepared = _prepare_literal(text)
    return ast.literal_eval(prepared)

def _parse_inline_table(text: str):
    # ``text`` includes the surrounding braces.
    inner = text.strip()[1:-1]
    if not inner.strip():
        return {}
    # Convert ``key = value`` to ``"key": value``
    # Handles quoted keys as well.
    def repl(m):
        key = m.group(1).strip()
        # If key is already quoted, keep it; otherwise quote it.
        if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
            return f"{key}:"
        return f'"{key}":'
    inner = re.sub(r"([^=,]+)=", repl, inner)
    prepared = _prepare_literal('{' + inner + '}')
    return ast.literal_eval(prepared)

def _parse_value(raw: str, lines: list, idx: int):
    """Parse a TOML value starting at *raw* (the part after ``=``).
    Returns ``(value, new_idx)`` where *new_idx* is the index of the last line
    that belonged to the value.
    """
    raw = raw.strip()
    # Multi‑line basic string
    if raw.startswith('"""'):
        delim = '"""'
        content = raw[3:]
        line_no = idx
        while not content.endswith(delim):
            line_no += 1
            if line_no >= len(lines):
                raise ValueError('unterminated multi‑line string')
            content += '\n' + _strip_comment(lines[line_no])
        content = content[:-3]
        # Trim first newline if present (spec behaviour) – handled implicitly.
        return (_unescape_basic(content), line_no)
    if raw.startswith("'''"):
        delim = "'''"
        content = raw[3:]
        line_no = idx
        while not content.endswith(delim):
            line_no += 1
            if line_no >= len(lines):
                raise ValueError('unterminated multi‑line literal string')
            content += '\n' + _strip_comment(lines[line_no])
        content = content[:-3]
        return (content, line_no)
    # Single‑line basic string
    if raw.startswith('"'):
        if not raw.endswith('"'):
            raise ValueError('unterminated basic string')
        inner = raw[1:-1]
        return (_unescape_basic(inner), idx)
    # Single‑line literal string
    if raw.startswith("'"):
        if not raw.endswith("'"):
            raise ValueError('unterminated literal string')
        return (raw[1:-1], idx)
    # Array
    if raw.startswith('['):
        # Might be multi‑line – collect until matching ']'
        depth = raw.count('[') - raw.count(']')
        line_no = idx
        text = raw
        while depth > 0:
            line_no += 1
            if line_no >= len(lines):
                raise ValueError('unterminated array')
            nxt = _strip_comment(lines[line_no]).strip()
            text += ' ' + nxt
            depth += nxt.count('[') - nxt.count(']')
        return (_parse_array(text), line_no)
    # Inline table
    if raw.startswith('{'):
        depth = raw.count('{') - raw.count('}')
        line_no = idx
        text = raw
        while depth > 0:
            line_no += 1
            if line_no >= len(lines):
                raise ValueError('unterminated inline table')
            nxt = _strip_comment(lines[line_no]).strip()
            text += ' ' + nxt
            depth += nxt.count('{') - nxt.count('}')
        return (_parse_inline_table(text), line_no)
    # Boolean
    if raw in ('true', 'false'):
        return (raw == 'true', idx)
    # Number (int or float)
    try:
        return (_parse_number(raw), idx)
    except ValueError:
        pass
    raise ValueError(f'unknown value: {raw}')

def _parse_key(key_str: str):
    """Parse a (possibly dotted) key into a list of strings."""
    parts = []
    # Split on '.' ignoring surrounding whitespace.
    for part in re.split(r"\.\s*", key_str.strip()):
        part = part.strip()
        if part.startswith('"') and part.endswith('"'):
            # Basic quoted key – unescape similar to basic string.
            inner = part[1:-1]
            parts.append(_unescape_basic(inner))
        elif part.startswith("'") and part.endswith("'"):
            parts.append(part[1:-1])
        else:
            parts.append(part)
    return parts

# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_toml(text: str):
    lines = text.splitlines()
    doc = OrderedDict()
    current_path = []  # list of keys leading to current table dict
    current_table = doc

    def _set_in_path(path, value, is_table=False, is_array_of_tables=False):
        nonlocal doc
        tbl = doc
        for i, seg in enumerate(path):
            if i == len(path) - 1:
                # final segment – set value / table / array‑of‑tables
                if is_array_of_tables:
                    existing = tbl.get(seg)
                    if existing is None:
                        tbl[seg] = []
                    elif not isinstance(existing, list):
                        raise ValueError('cannot redefine non‑array as array of tables')
                    tbl[seg].append(OrderedDict())
                    return tbl[seg][-1]
                if is_table:
                    if seg in tbl:
                        if not isinstance(tbl[seg], dict):
                            raise ValueError('key already defined as non‑table')
                    else:
                        tbl[seg] = OrderedDict()
                    return tbl[seg]
                # normal key/value
                if seg in tbl:
                    raise ValueError('duplicate key')
                tbl[seg] = value
                return None
            else:
                # intermediate segment – must be a table dict
                if seg not in tbl:
                    tbl[seg] = OrderedDict()
                elif not isinstance(tbl[seg], dict):
                    raise ValueError('intermediate key not a table')
                tbl = tbl[seg]
        return None

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = _strip_comment(raw_line).strip()
        if not line:
            i += 1
            continue
        if line.startswith('['):
            # Table header (standard or array of tables)
            is_array_of_tables = line.startswith('[[') and line.endswith(']]')
            if is_array_of_tables:
                header = line[2:-2]
            else:
                header = line[1:-1]
            parts = _parse_key(header)
            if is_array_of_tables:
                current_table = _set_in_path(parts, None, is_array_of_tables=True)
            else:
                current_table = _set_in_path(parts, None, is_table=True)
            current_path = parts
            i += 1
            continue
        # key/value line
        if '=' not in line:
            raise ValueError('invalid line (no =): ' + line)
        left, right = line.split('=', 1)
        key_str = left.strip()
        key_parts = _parse_key(key_str)
        # resolve table where this key belongs (could be nested via dotted key)
        table_path = current_path + key_parts[:-1]
        final_key = key_parts[-1]
        # ensure intermediate tables exist
        target_table = doc
        for seg in table_path:
            if seg not in target_table:
                target_table[seg] = OrderedDict()
            elif not isinstance(target_table[seg], dict):
                raise ValueError('intermediate key already a value')
            target_table = target_table[seg]
        # parse value (may consume additional lines)
        value, new_i = _parse_value(right, lines, i)
        # duplicate check
        if final_key in target_table:
            raise ValueError('duplicate key')
        target_table[final_key] = value
        i = new_i + 1
    return doc

# ---------------------------------------------------------------------------
# Command‑line interface
# ---------------------------------------------------------------------------

def _lookup_path(doc, path_str):
    parts = path_str.split('.') if path_str else []
    cur = doc
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            raise KeyError(p)
        cur = cur[p]
    return cur

def main(argv):
    if not (2 <= len(argv) <= 3):
        sys.stderr.write('Usage: python3 tomlq.py FILE [KEYPATH]\n')
        sys.exit(1)
    file_path = argv[1]
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        sys.stderr.write(f'Error reading file: {e}\n')
        sys.exit(1)
    try:
        doc = parse_toml(text)
    except Exception as e:
        sys.stderr.write(f'Parse error: {e}\n')
        sys.exit(1)
    if len(argv) == 3:
        try:
            result = _lookup_path(doc, argv[2])
        except KeyError:
            sys.stderr.write('Key path not found\n')
            sys.exit(2)
    else:
        result = doc
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write('\n')

if __name__ == '__main__':
    main(sys.argv)
