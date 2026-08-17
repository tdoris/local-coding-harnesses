#!/usr/bin/env python3
"""tomlq.py - parse a subset of TOML (v1.0.0) and print it as JSON.

Usage: python3 tomlq.py FILE [KEYPATH]

Exit codes: 0 success, 1 TOML parse error, 2 keypath not found.
Standard library only; the TOML parser is implemented from scratch here.
"""

import json
import sys


class TomlError(Exception):
    def __init__(self, msg, line):
        super().__init__(msg)
        self.line = line

    def __str__(self):
        return f"line {self.line}: {self.args[0]}"


class Table(dict):
    """A TOML table.

    `defined` is True when the table was the direct target of a table header
    (it may not be redefined by a later header, but may be a super-table of an
    earlier sub-table header that is later defined).
    `by_dotted` is True when it was created as an intermediate table by a
    dotted key (it may not be redefined by a later header).
    """
    def __init__(self, defined=False, by_dotted=False):
        super().__init__()
        self.defined = defined
        self.by_dotted = by_dotted


class InlineTable(Table):
    """A dict that is a closed inline table (may not be extended)."""
    def __init__(self):
        super().__init__(defined=True)


class ArrayOfTables(list):
    """A list created by [[...]] headers."""


def _hexdigits(s, i, count, what, line):
    out = []
    for _ in range(count):
        c = s[i] if i < len(s) else ''
        if c.isalnum() and c.lower() in '0123456789abcdef':
            out.append(c.lower())
            i += 1
        else:
            raise TomlError(f"invalid escape (bad \\{what} sequence)", line)
    return chr(int(''.join(out), 16)), i


class Parser:
    BARE_KEY = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_')

    def __init__(self, text):
        self.t = text
        self.n = len(text)
        self.pos = 0

    # ---------- helpers ----------

    def line_of(self, pos):
        return self.t.count('\n', 0, pos) + 1

    def err(self, msg, pos=None):
        p = self.pos if pos is None else pos
        raise TomlError(msg, self.line_of(p))

    def at_eof(self):
        return self.pos >= self.n

    def peek(self, k=0):
        i = self.pos + k
        return self.t[i] if i < self.n else ''

    def skip_ws_inline(self):
        """Spaces and tabs only (not newlines, not comments)."""
        while self.pos < self.n and self.t[self.pos] in ' \t':
            self.pos += 1

    def skip_ws(self):
        """Whitespace plus whole-line comments (top-level context)."""
        while self.pos < self.n:
            c = self.t[self.pos]
            if c in ' \t\r\n':
                self.pos += 1
            elif c == '#':
                while self.pos < self.n and self.t[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    # ---------- keys ----------

    def parse_key_part(self):
        c = self.peek()
        if c == '"':
            return self.parse_basic_string()
        if c == "'":
            return self.parse_literal_string()
        start = self.pos
        while self.pos < self.n and self.t[self.pos] in self.BARE_KEY:
            self.pos += 1
        if self.pos == start:
            self.err("expected a key (bare key or quoted key)")
        return self.t[start:self.pos]

    def parse_key(self):
        parts = [self.parse_key_part()]
        while True:
            save = self.pos
            self.skip_ws_inline()
            if self.peek() == '.':
                self.pos += 1
                self.skip_ws_inline()
                parts.append(self.parse_key_part())
            else:
                self.pos = save
                break
        return parts

    # ---------- strings ----------

    def parse_basic_string(self):
        start = self.pos
        self.pos += 1
        if self.t.startswith('""', self.pos):
            return self.parse_multiline_basic(start)
        out = []
        while True:
            c = self.peek()
            if c == '':
                self.err("unterminated basic string", start)
            if c == '\n':
                self.err("newline in basic string", start)
            if c == '"':
                self.pos += 1
                return ''.join(out)
            if c == '\\':
                e, self.pos = self.parse_escape(self.pos + 1)
                out.append(e)
            else:
                out.append(c)
                self.pos += 1

    def parse_literal_string(self):
        start = self.pos
        self.pos += 1
        if self.t.startswith("''", self.pos):
            return self.parse_multiline_literal(start)
        end = self.t.find("'", self.pos)
        if end == -1:
            self.err("unterminated literal string", start)
        for c in self.t[self.pos:end]:
            if c == '\n':
                self.err("newline in literal string", start)
        s = self.t[self.pos:end]
        self.pos = end + 1
        return s

    def parse_multiline_basic(self, start):
        self.pos += 2  # consume the remaining two quotes of the opener
        out = []
        if self.peek() == '\r':
            self.pos += 1
        if self.peek() == '\n':
            self.pos += 1  # trim first line-ending newline
        while True:
            c = self.peek()
            if c == '':
                self.err("unterminated multi-line basic string", start)
            if self.t.startswith('"""', self.pos):
                self.pos += 3
                return ''.join(out)
            if c == '\\':
                if self.peek(1) in ' \t\r\n' and not self.t.startswith('"""', self.pos + 1):
                    # line-ending backslash: trim all following ws/newlines
                    j = self.pos + 1
                    while j < self.n and self.t[j] in ' \t\r\n':
                        j += 1
                    if self.t.startswith('"""', j):
                        self.pos = j
                        return ''.join(out)
                    self.pos = j
                    continue
                e, self.pos = self.parse_escape(self.pos + 1)
                out.append(e)
            else:
                out.append(c)
                self.pos += 1

    def parse_multiline_literal(self, start):
        self.pos += 2  # consume the remaining two quotes of the opener
        if self.peek() == '\r':
            self.pos += 1
        if self.peek() == '\n':
            self.pos += 1  # trim first line-ending newline
        end = self.t.find("'''", self.pos)
        if end == -1:
            self.err("unterminated multi-line literal string", start)
        s = self.t[self.pos:end]
        self.pos = end + 3
        return s

    def parse_escape(self, i):
        t, n, p = self.t, self.n, self.line_of(i)
        c = t[i] if i < n else ''
        simple = {'b': '\b', 't': '\t', 'n': '\n', 'f': '\f', 'r': '\r',
                  '"': '"', '\\': '\\'}
        if c in simple:
            return simple[c], i + 1
        if c == 'u':
            return _hexdigits(t, i + 1, 4, 'u', p)
        if c == 'U':
            return _hexdigits(t, i + 1, 8, 'U', p)
        raise TomlError(f"invalid escape character \\{c}", p)

    # ---------- numbers ----------

    def _check_underscores(self, seg, start):
        if '_' in seg and (
                seg.startswith('_') or seg.endswith('_') or '__' in seg):
            self.err("underscores must appear between digits", start)

    def parse_number(self):
        t, n = self.t, self.n
        start = self.pos
        i = self.pos
        sign = 1
        signed = False
        c = t[i] if i < n else ''
        if c == '+':
            signed = True
            i += 1
        elif c == '-':
            signed = True
            sign = -1
            i += 1
        c = t[i] if i < n else ''

        if c == '0' and i + 1 < n and t[i + 1] in 'xob':
            if signed:
                self.err("signs are not allowed on hex, octal or binary numbers",
                         start)
            base = {'x': 16, 'o': 8, 'b': 2}[t[i + 1]]
            j = i + 2
            digits = []
            while j < n:
                ch = t[j]
                if ch == '_':
                    j += 1
                    continue
                if ch.isalnum() and ch.lower() in '0123456789abcdef' and int(ch, 36) < base:
                    digits.append(ch)
                    j += 1
                else:
                    break
            if not digits:
                self.err("expected at least one digit", start)
            self._check_underscores(t[i + 2:j], start)
            self.pos = j
            return int(''.join(digits), base)

        # decimal integer or float
        j = i
        int_digits = []
        while j < n:
            ch = t[j]
            if ch == '_':
                j += 1
                continue
            if ch.isdigit():
                int_digits.append(ch)
                j += 1
            else:
                break
        if not int_digits:
            self.err("expected a number", start)
        self._check_underscores(t[i:j], start)
        if int_digits[0] == '0' and len(int_digits) > 1:
            self.err("invalid decimal integer (leading zeros not allowed)", start)
        is_float = False
        if j < n and t[j] == '.':
            is_float = True
            k = j + 1
            frac = []
            while k < n:
                ch = t[k]
                if ch == '_':
                    k += 1
                    continue
                if ch.isdigit():
                    frac.append(ch)
                    k += 1
                else:
                    break
            if not frac:
                self.err("expected at least one digit after decimal point", start)
            self._check_underscores(t[j + 1:k], start)
            j = k
        if j < n and t[j] in 'eE':
            is_float = True
            k = j + 1
            if k < n and t[k] in '+-':
                k += 1
            kstart = k
            exp = []
            while k < n:
                ch = t[k]
                if ch == '_':
                    k += 1
                    continue
                if ch.isdigit():
                    exp.append(ch)
                    k += 1
                else:
                    break
            if not exp:
                self.err("expected at least one digit in exponent", start)
            self._check_underscores(t[kstart:k], start)
            j = k
        self.pos = j
        if is_float:
            return float(self.t[start:j])  # slice already includes the sign
        return sign * int(''.join(int_digits))

    # ---------- values ----------

    def parse_value(self):
        c = self.peek()
        if c == '"':
            return self.parse_basic_string()
        if c == "'":
            return self.parse_literal_string()
        if c == '[':
            return self.parse_array()
        if c == '{':
            return self.parse_inline_table()
        if c in '+-' or c.isdigit():
            return self.parse_number()
        if c == 't':
            if self.t.startswith('true', self.pos):
                self.pos += 4
                return True
        if c == 'f':
            if self.t.startswith('false', self.pos):
                self.pos += 5
                return False
        self.err("invalid value")

    def parse_array(self):
        start = self.pos
        self.pos += 1  # '['
        items = []
        while True:
            self.skip_ws()
            if self.at_eof():
                self.err("unterminated array", start)
            if self.peek() == ']':
                self.pos += 1
                return items
            items.append(self.parse_value())
            self.skip_ws()
            c = self.peek()
            if c == ',':
                self.pos += 1
            elif c == ']':
                self.pos += 1
                return items
            else:
                self.err("expected ',' or ']' in array")

    def parse_inline_table(self):
        start = self.pos
        self.pos += 1  # '{'
        table = InlineTable()
        self.skip_ws_inline()
        if self.peek() == '}':
            self.pos += 1
            return table
        while True:
            self.skip_ws_inline()
            parts = self.parse_key()
            self.skip_ws_inline()
            if self.peek() != '=':
                self.err("expected '=' after key in inline table")
            self.pos += 1
            self.skip_ws_inline()
            val = self.parse_value()
            self.put(table, parts, val, "inline table")
            self.skip_ws_inline()
            c = self.peek()
            if c == ',':
                self.pos += 1
            elif c == '}':
                self.pos += 1
                return table
            else:
                self.err("expected ',' or '}' in inline table")

    # ---------- assignment / structure ----------

    def put(self, table, parts, value, context):
        """Assign value at dotted path inside table (dotted-key context)."""
        cur = table
        for p in parts[:-1]:
            nxt = cur.get(p)
            if nxt is None:
                nxt = Table(by_dotted=True)
                cur[p] = nxt
            if isinstance(nxt, (ArrayOfTables, list)):
                self.err(
                    f"key {p!r} already exists as a value and cannot be extended",
                    self.pos)
            if isinstance(nxt, InlineTable):
                self.err("inline tables are closed and cannot be extended", self.pos)
            if isinstance(nxt, Table):
                if nxt.defined:
                    self.err(
                        "dotted keys must not extend a table defined by a header",
                        self.pos)
            else:
                self.err(
                    f"key {p!r} already exists as a value and cannot be extended",
                    self.pos)
            cur = nxt
        last = parts[-1]
        if last in cur:
            self.err(f"key {last!r} already exists (duplicate key)", self.pos)
        cur[last] = value

    def lookup_header(self, parts, aot):
        """Return (container_dict, last_key) where the (array of) table lives."""
        cur = self.root
        for p in parts[:-1]:
            nxt = cur.get(p)
            if nxt is None:
                nxt = Table()  # implicit super-table
                cur[p] = nxt
            if isinstance(nxt, ArrayOfTables):
                if not nxt:
                    self.err(f"no element in array of tables for key {p!r}", self.pos)
                nxt = nxt[-1]
            if isinstance(nxt, (InlineTable, list)) or not isinstance(nxt, dict):
                self.err(f"key {p!r} already exists as a value and cannot be extended",
                         self.pos)
            if isinstance(nxt, Table) and nxt.by_dotted:
                # a table created by a dotted key may not be redefined by a
                # header (duplicated table definition)
                self.err(f"table {p!r} already defined (duplicate table)", self.pos)
            cur = nxt
        return cur, parts[-1]

    def parse(self):
        root = Table(defined=False)
        self.root = root
        current = root
        while True:
            self.skip_ws()
            if self.at_eof():
                break
            if self.peek() == '[':
                self.pos += 1
                self.skip_ws_inline()
                if self.peek() == '[':
                    aot = True
                    self.pos += 1
                    self.skip_ws_inline()
                else:
                    aot = False
                parts = self.parse_key()
                self.skip_ws_inline()
                if aot:
                    if self.peek() != ']':
                        self.err("expected ']]' to close array-of-tables header")
                    self.pos += 1
                    self.skip_ws_inline()
                    if self.peek() != ']':
                        self.err("expected ']]' to close array-of-tables header")
                else:
                    if self.peek() != ']':
                        self.err("expected ']' to close table header")
                self.pos += 1
                # after the header, only ws/comments may follow
                while self.pos < self.n and self.t[self.pos] in ' \t':
                    self.pos += 1
                if self.pos < self.n and self.t[self.pos] != '\n' and self.t[self.pos] != '#':
                    self.err("unexpected content after table header")
                container, last = self.lookup_header(parts, aot)
                if aot:
                    existing = container.get(last)
                    if existing is None:
                        elem = Table(defined=True)
                        container[last] = arr = ArrayOfTables()
                        arr.append(elem)
                        current = elem
                    elif isinstance(existing, ArrayOfTables):
                        elem = Table(defined=True)
                        existing.append(elem)
                        current = elem
                    else:
                        self.err(
                            f"key {last!r} already exists as a value or static table",
                            self.pos)
                else:
                    existing = container.get(last)
                    if existing is None:
                        elem = Table(defined=True)
                        container[last] = elem
                        current = elem
                    elif isinstance(existing, Table) and not existing.defined \
                            and not existing.by_dotted:
                        # super-table after sub-table: defining a super-table
                        # that was created implicitly is permitted
                        existing.defined = True
                        current = existing
                    else:
                        self.err(
                            f"table {last!r} already defined (duplicate table)",
                            self.pos)
            else:
                parts = self.parse_key()
                self.skip_ws_inline()
                if self.peek() != '=':
                    self.err("expected '=' after key")
                self.pos += 1
                self.skip_ws_inline()
                val = self.parse_value()
                self.put(current, parts, val, "table")
                # after the value, only ws/comments may follow
                while self.pos < self.n and self.t[self.pos] in ' \t':
                    self.pos += 1
                if self.pos < self.n:
                    c = self.t[self.pos]
                    if c not in '\n#':
                        self.err("unexpected content after value")
        return self.root


def main(argv):
    if len(argv) < 2 or len(argv) > 3:
        print("usage: tomlq.py FILE [KEYPATH]", file=sys.stderr)
        return 1
    path = argv[1]
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except UnicodeDecodeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    parser = Parser(text)
    try:
        doc = parser.parse()
    except TomlError as e:
        print(f"tomlq: {e}", file=sys.stderr)
        return 1
    except RecursionError:
        print("tomlq: nested structure too deep", file=sys.stderr)
        return 1

    target = doc
    if len(argv) == 3:
        for part in argv[2].split('.'):
            if isinstance(target, dict) and part in target:
                target = target[part]
            elif (isinstance(target, list)
                  and part.lstrip('-').isdigit()
                  and -len(target) <= int(part) < len(target)):
                target = target[int(part)]
            else:
                print(f"tomlq: keypath '{argv[2]}' not found "
                      f"(missing part: {part!r})", file=sys.stderr)
                return 2

    print(json.dumps(target))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
