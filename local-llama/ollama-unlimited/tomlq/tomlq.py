#!/usr/bin/env python3
"""tomlq: parse a subset of TOML (v1.0.0 semantics) and print JSON.

Usage: python3 tomlq.py FILE [KEYPATH]
Exit codes: 0 ok, 1 parse error, 2 keypath not found.
"""
import json
import re
import sys


class TomlError(Exception):
    pass


class InlineTable(dict):
    """A dict created from an inline table; closed (cannot be extended)."""


_WS = ' \t\r\n'
_ESCAPES = {'b': '\b', 't': '\t', 'n': '\n', 'f': '\f', 'r': '\r',
            '"': '"', '\\': '\\'}
_BARE_KEY = re.compile(r'[A-Za-z0-9_-]+')
_SCALAR = re.compile(r'[A-Za-z0-9_+.\-]+')
_HEXDIGIT = re.compile(r'[0-9a-fA-F]+$')
_DECINT = re.compile(r'[0-9_]+$')
_FLOAT = re.compile(r'[0-9]+(\.[0-9]*)?([eE][+-]?[0-9]+)?$')


def _unders_ok(s, digit=lambda c: c.isdigit()):
    """Underscores allowed only strictly between two digit characters."""
    if not s or s[0] == '_' or s[-1] == '_' or '__' in s:
        return False
    for i, c in enumerate(s):
        if c == '_' and not (digit(s[i - 1]) and digit(s[i + 1])):
            return False
    return True


def parse_scalar(tok):
    if tok == 'true':
        return True
    if tok == 'false':
        return False
    t = tok
    sign = 1
    if t and t[0] in '+-':
        sign = -1 if t[0] == '-' else 1
        t = t[1:]
    if sign > 0:
        for prefix, digits, isd in (
                ('0x', HEXDIGIT_RE, lambda c: c in '0123456789abcdefABCDEF'),
                ('0o', OCTDIGIT_RE, lambda c: c in '01234567'),
                ('0b', BINDIGIT_RE, lambda c: c in '01')):
            if t.startswith(prefix):
                body = t[len(prefix):]
                if not body or not _unders_ok(body, isd) \
                        or not digits.match(body.replace('_', '')):
                    raise TomlError('invalid integer: %r' % tok)
                return int(body.replace('_', ''), {'0x': 16, '0o': 8,
                                                   '0b': 2}[prefix])
    if _DECINT.match(t):
        if not _unders_ok(t):
            raise TomlError('invalid integer: %r' % tok)
        s = t.replace('_', '')
        if len(s) > 1 and s[0] == '0':
            raise TomlError('invalid decimal integer (leading zero): %r' % tok)
        return sign * int(s)
    if '.' in t or 'e' in t or 'E' in t:
        if not _unders_ok(t):
            raise TomlError('invalid float: %r' % tok)
        u = t.replace('_', '')
        if _FLOAT.match(u):
            return sign * float(u)
    raise TomlError('invalid value: %r' % tok)


HEXDIGIT_RE = re.compile(r'[0-9a-fA-F]+$')
OCTDIGIT_RE = re.compile(r'[0-7]+$')
BINDIGIT_RE = re.compile(r'[01]+$')


class Parser:
    def __init__(self, text):
        self.s = text
        self.n = len(text)
        self.i = 0
        self.root = {}
        self.ctx = []          # current table path (str keys + int indices)
        self.explicit = set()  # ids() of dicts opened by [header]
        self.aot = set()       # paths opened by [[header]]

    # ---- helpers -------------------------------------------------------
    def line(self):
        return 1 + self.s.count('\n', 0, self.i)

    def err(self, msg):
        raise TomlError('line %d: %s' % (self.line(), msg))

    def peek(self):
        return self.s[self.i] if self.i < self.n else ''

    def skip_space(self):
        while self.i < self.n and self.s[self.i] in ' \t':
            self.i += 1

    def skip_ambient(self):
        """Skip whitespace (incl. newlines) and comments."""
        while self.i < self.n:
            c = self.s[self.i]
            if c in _WS:
                self.i += 1
            elif c == '#':
                while self.i < self.n and self.s[self.i] != '\n':
                    self.i += 1
            else:
                break

    def end_of_line(self):
        """After a header/value: rest of line must be comment or newline."""
        while self.i < self.n and self.s[self.i] in ' \t':
            self.i += 1
        if self.i < self.n and self.s[self.i] == '#':
            while self.i < self.n and self.s[self.i] != '\n':
                self.i += 1
        if self.i < self.n:
            c = self.s[self.i]
            if c != '\n' and c != '\r':
                self.err('unexpected content after value or header')

    # ---- keys ----------------------------------------------------------
    def parse_key_part(self):
        self.skip_space()
        c = self.peek()
        if c == '"':
            return self.parse_basic_string()
        if c == "'":
            return self.parse_literal_string()
        m = _BARE_KEY.match(self.s, self.i)
        if not m:
            self.err('invalid key')
        self.i = m.end()
        return m.group(0)

    def parse_dotted_key(self):
        parts = []
        while True:
            parts.append(self.parse_key_part())
            self.skip_space()
            if self.peek() == '.':
                self.i += 1
            else:
                return parts

    # ---- strings -------------------------------------------------------
    def parse_escape(self, out):
        """self.i at backslash; parse one escape into out."""
        ch = self.s[self.i + 1] if self.i + 1 < self.n else ''
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
            self.i += 2
            return
        if ch in 'uU':
            w = 4 if ch == 'u' else 8
            h = self.s[self.i + 2:self.i + 2 + w]
            if len(h) != w or not _HEXDIGIT.match(h):
                self.err('invalid \\%s escape' % ch)
            out.append(chr(int(h, 16)))
            self.i += 2 + w
            return
        self.err('invalid escape sequence')

    def parse_basic_string(self):
        if self.s.startswith('"""', self.i):
            return self.parse_ml_basic()
        self.i += 1
        out = []
        while True:
            if self.i >= self.n:
                self.err('unterminated basic string')
            c = self.s[self.i]
            if c == '\n':
                self.err('newline in basic string')
            if c == '"':
                self.i += 1
                return ''.join(out)
            if c == '\\':
                self.parse_escape(out)
                continue
            out.append(c)
            self.i += 1

    def parse_ml_basic(self):
        self.i += 3
        if self.s.startswith('\r\n', self.i):
            self.i += 2
        elif self.s[self.i:self.i + 1] == '\n':
            self.i += 1
        out = []
        while True:
            if self.i >= self.n:
                self.err('unterminated multi-line basic string')
            c = self.s[self.i]
            if c == '"':
                j = self.i
                while j < self.n and self.s[j] == '"' and j - self.i < 3:
                    j += 1
                if j - self.i == 3:
                    self.i = j
                    return ''.join(out)
                out.append('"' * (j - self.i))
                self.i = j
            elif c == '\\' and self.i + 1 < self.n and self.s[self.i + 1] in _WS:
                # line-continuation backslash: trim all following whitespace
                self.i += 1
                while self.i < self.n and self.s[self.i] in _WS:
                    self.i += 1
            elif c == '\\':
                self.parse_escape(out)
            else:
                out.append(c)
                self.i += 1

    def parse_literal_string(self):
        if self.s.startswith("'''", self.i):
            return self.parse_ml_literal()
        self.i += 1
        out = []
        while True:
            if self.i >= self.n:
                self.err('unterminated literal string')
            c = self.s[self.i]
            if c == '\n' or c == '\r':
                self.err('newline in literal string')
            if c == "'":
                self.i += 1
                return ''.join(out)
            out.append(c)
            self.i += 1

    def parse_ml_literal(self):
        self.i += 3
        if self.s.startswith('\r\n', self.i):
            self.i += 2
        elif self.s[self.i:self.i + 1] == '\n':
            self.i += 1
        out = []
        while True:
            if self.i >= self.n:
                self.err('unterminated multi-line literal string')
            c = self.s[self.i]
            if c == "'":
                j = self.i
                while j < self.n and self.s[j] == "'" and j - self.i < 3:
                    j += 1
                if j - self.i == 3:
                    self.i = j
                    return ''.join(out)
                out.append("'" * (j - self.i))
                self.i = j
            else:
                out.append(c)
                self.i += 1

    # ---- values --------------------------------------------------------
    def parse_value(self):
        self.skip_space()
        if self.i >= self.n:
            self.err('missing value')
        c = self.peek()
        if c == '"':
            return self.parse_basic_string()
        if c == "'":
            return self.parse_literal_string()
        if c == '[':
            return self.parse_array()
        if c == '{':
            return self.parse_inline_table()
        m = _SCALAR.match(self.s, self.i)
        if not m:
            self.err('invalid value')
        tok = m.group(0)
        self.i = m.end()
        return parse_scalar(tok)

    def parse_array(self):
        self.i += 1  # '['
        arr = []
        while True:
            self.skip_ambient()
            if self.i >= self.n:
                self.err('unterminated array')
            c = self.peek()
            if c == ']':
                self.i += 1
                return arr
            v = self.parse_value()
            arr.append(v)
            self.skip_ambient()
            if self.i >= self.n:
                self.err('unterminated array')
            c = self.peek()
            if c == ',':
                self.i += 1
            elif c == ']':
                self.i += 1
                return arr
            else:
                self.err('expected "," or "]" in array')

    def _insert_dotted(self, d, parts, value):
        cur = d
        for p in parts[:-1]:
            if p not in cur:
                cur[p] = {}
            if not isinstance(cur[p], dict):
                self.err('cannot extend non-table with dotted key %r' % p)
            cur = cur[p]
        last = parts[-1]
        if last in cur:
            self.err('duplicate key %r in inline table' % last)
        cur[last] = value

    def parse_inline_table(self):
        self.i += 1  # '{'
        d = InlineTable()
        self.skip_space()
        if self.peek() == '}':
            self.i += 1
            return d
        while True:
            self.skip_space()
            if self.i >= self.n:
                self.err('unterminated inline table')
            if self.peek() in '\r\n':
                self.err('newline in inline table')
            parts = self.parse_dotted_key()
            self.skip_space()
            if self.peek() != '=':
                self.err('expected "=" in inline table')
            self.i += 1
            self.skip_space()
            v = self.parse_value()
            self._insert_dotted(d, parts, v)
            self.skip_space()
            if self.i >= self.n:
                self.err('unterminated inline table')
            c = self.peek()
            if c == '}':
                self.i += 1
                return d
            if c == ',':
                self.i += 1
                continue
            self.err('expected "," or "}" in inline table')

    # ---- document structure --------------------------------------------
    def assign(self, parts, value):
        path = list(self.ctx) + list(parts)
        cur = self.root
        for idx, p in enumerate(path[:-1]):
            if isinstance(p, int):
                if not (isinstance(cur, list) and 0 <= p < len(cur)):
                    self.err('invalid table path')
                cur = cur[p]
            else:
                if not isinstance(cur, dict) or p not in cur:
                    if not isinstance(cur, dict):
                        self.err('cannot define key inside non-table')
                    cur[p] = {}
                nxt = cur[p]
                if isinstance(nxt, list):
                    if idx + 1 < len(path) and isinstance(path[idx + 1], int):
                        cur = nxt
                    elif tuple(path[:idx + 1]) in self.aot:
                        cur = nxt[-1]
                    else:
                        self.err('cannot redefine %r as a table' % p)
                elif not isinstance(nxt, dict):
                    self.err('cannot redefine %r as a table' % p)
                else:
                    cur = nxt
        if isinstance(cur, InlineTable):
            self.err('cannot add keys to a closed inline table')
        last = path[-1]
        if isinstance(last, int):
            if not (isinstance(cur, list) and last < len(cur)):
                self.err('invalid table path')
            cur[last] = value
        else:
            if not isinstance(cur, dict):
                self.err('cannot assign to non-table')
            if last in cur:
                self.err('duplicate key %r' % last)
            cur[last] = value
        if isinstance(value, InlineTable):
            pass  # closure enforced via InlineTable type

    def open_table(self, parts, aot):
        path = []
        cur = self.root
        for p in parts[:-1]:
            path.append(p)
            if not isinstance(cur, dict):
                self.err('cannot define table inside non-table')
            if p in cur:
                nxt = cur[p]
                if isinstance(nxt, list) and tuple(path) in self.aot:
                    cur = nxt[-1]
                    continue
                if not isinstance(nxt, dict):
                    self.err('cannot redefine %r as a table' % p)
                if isinstance(nxt, InlineTable):
                    self.err('cannot open a closed inline table')
                cur = nxt
            else:
                cur[p] = {}
                cur = cur[p]
        last = parts[-1]
        path.append(last)
        tp = tuple(path)
        if aot:
            if not isinstance(cur, dict):
                self.err('cannot define array of tables inside non-table')
            if last in cur:
                v = cur[last]
                if tp in self.aot and isinstance(v, list):
                    new = {}
                    v.append(new)
                    self.ctx = list(path) + [len(v) - 1]
                else:
                    self.err('cannot redefine %r as an array of tables' % last)
            else:
                cur[last] = [{}]
                self.aot.add(tp)
                self.ctx = list(path) + [0]
        else:
            if last in cur:
                v = cur[last]
                if isinstance(v, list):
                    self.err('cannot redefine array %r as a table' % last)
                if not isinstance(v, dict):
                    self.err('cannot redefine %r as a table' % last)
                if isinstance(v, InlineTable):
                    self.err('cannot open a closed inline table')
                if id(v) in self.explicit:
                    self.err('duplicate table header [%s]' % '.'.join(parts))
            else:
                if not isinstance(cur, dict):
                    self.err('cannot define table inside non-table')
                cur[last] = {}
            self.ctx = list(path)
            self.explicit.add(id(cur[parts[-1]]))

    # ---- top level -------------------------------------------------------
    def parse_header(self, aot):
        parts = self.parse_dotted_key()
        self.skip_space()
        if aot:
            if not self.s.startswith(']]', self.i):
                self.err('expected "]]" in array-of-tables header')
            self.i += 2
        else:
            if self.peek() != ']':
                self.err('expected "]" in table header')
            self.i += 1
        self.end_of_line()
        self.open_table(parts, aot)

    def parse_keyvalue(self):
        parts = self.parse_dotted_key()
        self.skip_space()
        if self.peek() != '=':
            self.err('expected "=" after key')
        self.i += 1
        self.skip_space()
        v = self.parse_value()
        self.end_of_line()
        self.assign(parts, v)

    def parse_document(self):
        while True:
            self.skip_ambient()
            if self.i >= self.n:
                break
            c = self.peek()
            if c == '[':
                if self.s.startswith('[[' , self.i):
                    self.i += 2
                    self.parse_header(aot=True)
                else:
                    self.i += 1
                    self.parse_header(aot=False)
            else:
                self.parse_keyvalue()
        return self.root


def main():
    args = sys.argv[1:]
    if not args or len(args) > 2:
        print('usage: tomlq.py FILE [KEYPATH]', file=sys.stderr)
        return 1
    try:
        with open(args[0], encoding='utf-8') as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print('tomlq: cannot read %s: %s' % (args[0], e), file=sys.stderr)
        return 1
    try:
        doc = Parser(text).parse_document()
    except TomlError as e:
        print('tomlq: %s' % e, file=sys.stderr)
        return 1
    result = doc
    if len(args) == 2:
        keypath = args[1]
        for part in keypath.split('.'):
            if isinstance(result, dict) and part in result:
                result = result[part]
            elif (isinstance(result, list) and part.isdigit()
                    and 0 <= int(part) < len(result)):
                result = result[int(part)]
            else:
                print('tomlq: key path %r not found' % keypath, file=sys.stderr)
                return 2
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
