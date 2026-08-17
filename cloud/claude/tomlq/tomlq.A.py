#!/usr/bin/env python3
"""tomlq.py
A minimal TOML parser (subset) that outputs JSON.
Usage: python3 tomlq.py FILE [KEYPATH]
"""

import sys
import json
import re
import codecs
from collections import OrderedDict

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class ParseError(Exception):
    """Raised when the TOML input does not conform to the supported subset."""
    pass

# ---------------------------------------------------------------------------
# Helper functions for low‑level token handling
# ---------------------------------------------------------------------------

def split_key_value(line: str):
    """Return (key, value) split on the first unquoted '='.
    Leading/trailing whitespace is stripped from both sides.
    """
    i = 0
    n = len(line)
    in_str = None  # None or quote delimiter (" or ' or triple)
    while i < n:
        ch = line[i]
        if in_str:
            if in_str in ("'''", '"""'):
                if line.startswith(in_str, i):
                    in_str = None
                    i += len(in_str)
                else:
                    i += 1
            else:
                if ch == "\\":
                    i += 2
                elif ch == in_str:
                    in_str = None
                    i += 1
                else:
                    i += 1
        else:
            if ch in ('"', "'"):
                # start quoted key – triple quotes are not allowed in keys
                if line.startswith(ch * 3, i):
                    raise ParseError('Triple quotes not allowed in keys')
                in_str = ch
                i += 1
            elif ch == "#":
                # comment before the '=', ignore rest of line
                break
            elif ch == "=":
                key = line[:i].strip()
                value = line[i + 1 :].strip()
                return key, value
            else:
                i += 1
    raise ParseError('No "=" found in line')


def parse_dotted_key(s: str):
    """Parse a dotted key (bare or quoted parts) into a list of strings."""
    parts = []
    i = 0
    n = len(s)
    while i < n:
        # skip whitespace
        while i < n and s[i] in " \t":
            i += 1
        if i >= n:
            break
        if s[i] in ("\"", "'"):
            quote = s[i]
            i += 1
            start = i
            while i < n:
                if s[i] == "\\" and quote == "\"":
                    i += 2
                elif s[i] == quote:
                    break
                else:
                    i += 1
            else:
                raise ParseError('Unterminated quoted key')
            part = s[start:i]
            if quote == "\"":
                part = codecs.decode(part, "unicode_escape")
            parts.append(part)
            i += 1  # skip closing quote
        else:
            start = i
            while i < n and s[i] not in ". \t":
                i += 1
            part = s[start:i]
            parts.append(part)
        # skip whitespace after part
        while i < n and s[i] in " \t":
            i += 1
        # optional dot
        if i < n and s[i] == ".":
            i += 1
    return parts


def remove_comments(s: str) -> str:
    """Strip comments ("# …") that are not inside a string."""
    result = []
    i = 0
    n = len(s)
    in_str = None
    while i < n:
        ch = s[i]
        if in_str:
            if in_str in ("'''", '"""'):
                if s.startswith(in_str, i):
                    in_str = None
                    result.append(in_str)
                    i += len(in_str)
                else:
                    result.append(ch)
                    i += 1
            else:
                if ch == "\\":
                    result.append(s[i : i + 2])
                    i += 2
                elif ch == in_str:
                    in_str = None
                    result.append(ch)
                    i += 1
                else:
                    result.append(ch)
                    i += 1
        else:
            if ch == "#":
                # skip to end of line (preserve newline itself)
                while i < n and s[i] != "\n":
                    i += 1
                continue
            elif ch in ("\"", "'"):
                if s.startswith(ch * 3, i):
                    in_str = ch * 3
                    result.append(in_str)
                    i += 3
                else:
                    in_str = ch
                    result.append(ch)
                    i += 1
            else:
                result.append(ch)
                i += 1
    return "".join(result)


def update_state_on_line(line: str, state: dict):
    """Update bracket/brace counters and string state while scanning a line.
    Stops scanning at an unquoted "#" (comment).
    """
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if state["in_str"]:
            delim = state["in_str"]
            if delim in ("'''", '"""'):
                if line.startswith(delim, i):
                    state["in_str"] = None
                    i += len(delim)
                else:
                    i += 1
            else:
                if ch == "\\":
                    i += 2
                elif ch == delim:
                    state["in_str"] = None
                    i += 1
                else:
                    i += 1
        else:
            if ch == "#":
                break  # comment – ignore rest of line
            elif ch in ("\"", "'"):
                if line.startswith(ch * 3, i):
                    state["in_str"] = ch * 3
                    i += 3
                else:
                    state["in_str"] = ch
                    i += 1
            elif ch == "[":
                state["bracket"] += 1
                i += 1
            elif ch == "]":
                state["bracket"] -= 1
                i += 1
            elif ch == "{":
                state["brace"] += 1
                i += 1
            elif ch == "}":
                state["brace"] -= 1
                i += 1
            else:
                i += 1

# ---------------------------------------------------------------------------
# Value parsers
# ---------------------------------------------------------------------------

def parse_number(tok: str):
    s = tok.replace("_", "")
    low = s.lower()
    if low.startswith("0x"):
        return int(s, 16)
    if low.startswith("0o"):
        return int(s, 8)
    if low.startswith("0b"):
        return int(s, 2)
    # decimal integer or float
    if any(c in s for c in ".eE"):
        # float
        try:
            return float(s)
        except ValueError:
            raise ParseError(f'Invalid float literal: {tok}')
    # integer – leading zero not allowed (except "0")
    if len(s) > 1 and s[0] == "0" and s[1].isdigit():
        raise ParseError(f'Leading zeros are not allowed: {tok}')
    try:
        return int(s)
    except ValueError:
        raise ParseError(f'Invalid integer literal: {tok}')


def parse_basic_string(s: str) -> str:
    # single‑line or multi‑line basic string (already stripped delimiters)
    inner = s
    # line continuation handling – backslash newline + optional whitespace
    inner = re.sub(r"\\\n[ \t]*", "", inner)
    # unescape using unicode_escape (covers \b \t \n \f \r \" \\ \uXXXX \UXXXXXXXX)
    return codecs.decode(inner, "unicode_escape")


def parse_string(tok: str):
    if tok.startswith('"""'):
        if not tok.endswith('"""'):
            raise ParseError('Unterminated multi‑line basic string')
        inner = tok[3:-3]
        if inner.startswith('\n'):
            inner = inner[1:]
        return parse_basic_string(inner)
    if tok.startswith("'''"):
        if not tok.endswith("'''"):
            raise ParseError('Unterminated multi‑line literal string')
        inner = tok[3:-3]
        if inner.startswith('\n'):
            inner = inner[1:]
        return inner
    if tok.startswith('"'):
        if not tok.endswith('"'):
            raise ParseError('Unterminated basic string')
        inner = tok[1:-1]
        return parse_basic_string(inner)
    if tok.startswith("'"):
        if not tok.endswith("'"):
            raise ParseError('Unterminated literal string')
        return tok[1:-1]
    raise ParseError('Invalid string literal')


def split_items(inner: str, allow_trailing: bool = True):
    """Split a comma‑separated list respecting nesting and strings."""
    items = []
    cur = []
    state = {"in_str": None, "bracket": 0, "brace": 0}
    i = 0
    n = len(inner)
    while i < n:
        ch = inner[i]
        if state["in_str"]:
            delim = state["in_str"]
            if delim in ("'''", '"""'):
                if inner.startswith(delim, i):
                    state["in_str"] = None
                    cur.append(delim)
                    i += len(delim)
                else:
                    cur.append(ch)
                    i += 1
            else:
                if ch == "\\":
                    cur.append(inner[i : i + 2])
                    i += 2
                elif ch == delim:
                    state["in_str"] = None
                    cur.append(ch)
                    i += 1
                else:
                    cur.append(ch)
                    i += 1
        else:
            if ch == "#":
                # ignore comment till end of line
                while i < n and inner[i] != "\n":
                    i += 1
                continue
            elif ch in ("'", '"'):
                if inner.startswith(ch * 3, i):
                    state["in_str"] = ch * 3
                    cur.append(ch * 3)
                    i += 3
                else:
                    state["in_str"] = ch
                    cur.append(ch)
                    i += 1
            elif ch == "[":
                state["bracket"] += 1
                cur.append(ch)
                i += 1
            elif ch == "]":
                state["bracket"] -= 1
                cur.append(ch)
                i += 1
            elif ch == "{":
                state["brace"] += 1
                cur.append(ch)
                i += 1
            elif ch == "}":
                state["brace"] -= 1
                cur.append(ch)
                i += 1
            elif ch == "," and state["bracket"] == 0 and state["brace"] == 0:
                items.append("".join(cur).strip())
                cur = []
                i += 1
                # skip whitespace after comma
                while i < n and inner[i] in " \t\r\n":
                    i += 1
                continue
            else:
                cur.append(ch)
                i += 1
    # final item (allow empty if trailing comma and allow_trailing is True)
    final = "".join(cur).strip()
    if final:
        items.append(final)
    elif not allow_trailing:
        # nothing after last comma – treat as error later if needed
        pass
    return items


def parse_array(tok: str):
    if not (tok.startswith('[') and tok.endswith(']')):
        raise ParseError('Invalid array')
    inner = tok[1:-1]
    if not inner.strip():
        return []
    raw_items = split_items(inner, allow_trailing=True)
    return [parse_toml_value(item) for item in raw_items]


def parse_inline_table(tok: str):
    if not (tok.startswith('{') and tok.endswith('}')):
        raise ParseError('Invalid inline table')
    inner = tok[1:-1].strip()
    if not inner:
        return {}
    raw_pairs = split_items(inner, allow_trailing=False)
    table = {}
    for pair in raw_pairs:
        k, v = split_key_value(pair)
        k_parts = parse_dotted_key(k)
        if len(k_parts) != 1:
            raise ParseError('Dotted keys are not allowed inside inline tables')
        key = k_parts[0]
        if key in table:
            raise ParseError(f'Duplicate key {key} in inline table')
        table[key] = parse_toml_value(v)
    return table


def parse_toml_value(tok: str):
    # Strip comments that are outside strings first
    cleaned = remove_comments(tok).strip()
    if not cleaned:
        raise ParseError('Empty value')
    # Dispatch based on leading character
    if cleaned[0] in ('"', "'"):
        return parse_string(cleaned)
    if cleaned.startswith('['):
        return parse_array(cleaned)
    if cleaned.startswith('{'):
        return parse_inline_table(cleaned)
    if cleaned in ('true', 'false'):
        return cleaned == 'true'
    # Numbers – try integer / float
    return parse_number(cleaned)

# ---------------------------------------------------------------------------
# Core parser class
# ---------------------------------------------------------------------------

class TomlParser:
    def __init__(self, lines):
        self.lines = lines  # list of raw lines (including trailing newline)
        self.root = OrderedDict()
        self.current_table = self.root
        self.line_idx = 0  # index of the line currently being processed

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------
    def parse(self):
        i = 0
        while i < len(self.lines):
            raw = self.lines[i]
            stripped = raw.lstrip()
            # skip blank / comment lines
            if not stripped or stripped.startswith('#'):
                i += 1
                continue
            if stripped.startswith('['):
                # table header
                self._handle_table_header(stripped)
                i += 1
                continue
            # key/value line
            key, first_val = split_key_value(raw)
            self.line_idx = i
            full_val = self._collect_full_value(first_val)
            py_val = parse_toml_value(full_val)
            key_parts = parse_dotted_key(key)
            self._assign(key_parts, py_val)
            # advance to line after the value (self.line_idx now points to last line of multi‑line value)
            i = self.line_idx + 1
        return self.root

    # -----------------------------------------------------------------------
    # Helpers for table handling
    # -----------------------------------------------------------------------
    def _handle_table_header(self, line: str):
        line = line.strip()
        is_array = line.startswith('[[']
        if is_array:
            if not line.endswith(']]'):
                raise ParseError('Malformed array of tables header')
            inner = line[2:-2].strip()
        else:
            if not (line.startswith('[') and line.endswith(']')):
                raise ParseError('Malformed table header')
            inner = line[1:-1].strip()
        parts = parse_dotted_key(inner)
        self._set_current_table(parts, is_array)

    def _set_current_table(self, parts, is_array):
        cur = self.root
        for idx, part in enumerate(parts):
            # if cur is a list (array of tables) -> use its last element
            if isinstance(cur, list):
                if not cur:
                    raise ParseError('Array of tables is empty while navigating')
                cur = cur[-1]
            if idx == len(parts) - 1:
                # final component
                if is_array:
                    # array of tables – always append a new dict
                    if part not in cur:
                        cur[part] = []
                    elif not isinstance(cur[part], list):
                        raise ParseError(f'Key {part} already defined and not an array')
                    cur[part].append(OrderedDict())
                    self.current_table = cur[part][-1]
                else:
                    # plain table – must not exist already
                    if part in cur:
                        raise ParseError(f'Duplicate table definition: {".".join(parts)}')
                    cur[part] = OrderedDict()
                    self.current_table = cur[part]
            else:
                # intermediate component – ensure a dict exists (or drill into array element)
                if isinstance(cur, list):
                    # already handled at top of loop – should not happen here
                    pass
                if part not in cur:
                    cur[part] = OrderedDict()
                elif isinstance(cur[part], dict):
                    pass
                elif isinstance(cur[part], list):
                    if not cur[part]:
                        raise ParseError(f'Array of tables {part} is empty')
                    # descend into the last table of the array for further nesting
                    cur = cur[part][-1]
                    continue
                else:
                    raise ParseError(f'Key {part} conflicts with existing value')
                cur = cur[part]

    # -----------------------------------------------------------------------
    # Helpers for key/value handling
    # -----------------------------------------------------------------------
    def _collect_full_value(self, first_part: str) -> str:
        # Collect the complete value, possibly spanning multiple lines.
        parts = [first_part]
        state = {"in_str": None, "bracket": 0, "brace": 0}
        update_state_on_line(first_part, state)
        # continue reading until value is closed and not inside a string
        while (state["in_str"] or state["bracket"] > 0 or state["brace"] > 0) or not "".join(parts).strip():
            self.line_idx += 1
            if self.line_idx >= len(self.lines):
                raise ParseError('Unexpected EOF while parsing multi‑line value')
            nxt = self.lines[self.line_idx]
            parts.append('\n' + nxt.rstrip('\n'))
            update_state_on_line(nxt, state)
        return "".join(parts)

    def _assign(self, key_parts, value):
        parent, final = self._resolve_path(self.root, key_parts, create=True)
        if final in parent:
            raise ParseError(f'Duplicate key: {final}')
        parent[final] = value

    def _resolve_path(self, root, parts, create=False):
        cur = root
        for idx, part in enumerate(parts):
            if isinstance(cur, list):
                if not cur:
                    raise ParseError('Array of tables is empty while resolving key path')
                cur = cur[-1]
            if idx == len(parts) - 1:
                return cur, part
            # intermediate component
            if part not in cur:
                if create:
                    cur[part] = OrderedDict()
                else:
                    raise ParseError(f'Missing intermediate table {part}')
            elif isinstance(cur[part], dict):
                pass
            elif isinstance(cur[part], list):
                if not cur[part]:
                    raise ParseError(f'Array of tables {part} is empty')
                cur = cur[part][-1]
                continue
            else:
                raise ParseError(f'Key {part} conflicts with existing value')
            cur = cur[part]
        raise ParseError('Unreachable')

# ---------------------------------------------------------------------------
# Utilities for key‑path lookup after parsing
# ---------------------------------------------------------------------------

def lookup_keypath(data, path):
    parts = path.split('.')
    cur = data
    for part in parts:
        if isinstance(cur, dict):
            cur = cur[part]
        else:
            raise KeyError
    return cur

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        sys.stderr.write('Usage: python3 tomlq.py FILE [KEYPATH]\n')
        sys.exit(1)
    filename = sys.argv[1]
    keypath = sys.argv[2] if len(sys.argv) == 3 else None
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        parser = TomlParser(lines)
        data = parser.parse()
        if keypath:
            try:
                result = lookup_keypath(data, keypath)
            except Exception:
                sys.stderr.write(f'Key path "{keypath}" not found\n')
                sys.exit(2)
        else:
            result = data
        json.dump(result, sys.stdout, ensure_ascii=False)
        sys.stdout.write('\n')
        sys.exit(0)
    except FileNotFoundError:
        sys.stderr.write(f'File not found: {filename}\n')
        sys.exit(1)
    except ParseError as e:
        sys.stderr.write(f'Parse error: {e}\n')
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f'Unexpected error: {e}\n')
        sys.exit(1)

if __name__ == '__main__':
    main()
