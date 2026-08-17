#!/usr/bin/env python3
"""tomlq: parse a subset of TOML and print JSON.

Usage: python3 tomlq.py FILE [KEYPATH]
"""
import json
import sys


class ParseError(Exception):
    pass


class InlineTable(dict):
    pass


class ArrayOfTables(list):
    pass


class Parser:
    ESCAPES = {
        'b': '\b', 't': '\t', 'n': '\n', 'f': '\f',
        'r': '\r', '"': '"', '\\': '\\',
    }

    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.root = {}
        self.current = self.root
        # (id(parent table), key) pairs that were explicitly defined (by a
        # header, a value, a dotted key, or an array-of-tables header).
        self.explicit = set()

    # ---------------- low level helpers ----------------

    def err(self, msg, pos=None):
        if pos is None:
            pos = self.pos
        line = self.text.count('\n', 0, pos) + 1
        raise ParseError('line %d: %s' % (line, msg))

    def skip_ws(self):
        while self.pos < len(self.text) and self.text[self.pos] in ' \t':
            self.pos += 1

    def skip_ws_comments_newlines(self):
        while self.pos < len(self.text):
            c = self.text[self.pos]
            if c in ' \t\n':
                self.pos += 1
            elif c == '#':
                while self.pos < len(self.text) and self.text[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    def at(self, s):
        return self.text.startswith(s, self.pos)

    def consume(self, s):
        if self.at(s):
            self.pos += len(s)
        else:
            self.err('expected %r' % s)

    # ---------------- strings ----------------

    def parse_hex_escape(self, n):
        if self.pos + n > len(self.text):
            self.err('truncated unicode escape')
        h = self.text[self.pos:self.pos + n]
        if not all(c in '0123456789abcdefABCDEF' for c in h):
            self.err('invalid unicode escape')
        cp = int(h, 16)
        if cp >= 0x110000 or 0xD800 <= cp <= 0xDFFF:
            self.err('escaped character is not a Unicode scalar value')
        self.pos += n
        return chr(cp)

    def parse_escapes(self):
        # pos is at the backslash
        self.pos += 1
        c = self.text[self.pos] if self.pos < len(self.text) else ''
        if c in self.ESCAPES:
            self.pos += 1
            return self.ESCAPES[c]
        if c == 'u':
            self.pos += 1
            return self.parse_hex_escape(4)
        if c == 'U':
            self.pos += 1
            return self.parse_hex_escape(8)
        self.err('invalid escape sequence')

    def parse_basic_string(self):
        self.pos += 1  # opening quote
        out = []
        while True:
            if self.pos >= len(self.text):
                self.err('unterminated string', self.pos - 1)
            c = self.text[self.pos]
            if c == '"':
                self.pos += 1
                return ''.join(out)
            if c == '\n':
                self.err('newlines are not allowed in basic strings')
            if c == '\\':
                out.append(self.parse_escapes())
            else:
                out.append(c)
                self.pos += 1

    def parse_literal_string(self):
        self.pos += 1
        out = []
        while True:
            if self.pos >= len(self.text):
                self.err('unterminated string', self.pos - 1)
            c = self.text[self.pos]
            if c == "'":
                self.pos += 1
                return ''.join(out)
            if c == '\n':
                self.err("newlines are not allowed in literal strings")
            out.append(c)
            self.pos += 1

    def _ml_trim(self, start):
        # trim first newline immediately after the opening delimiter
        if self.text.startswith('\n', start):
            return start + 1
        return start

    def parse_ml_basic(self):
        self.pos += 3  # """
        i = self._ml_trim(self.pos)
        out = []
        while True:
            if i >= len(self.text):
                self.err('unterminated multi-line basic string')
            c = self.text[i]
            if c == '\\':
                nxt = self.text[i + 1] if i + 1 < len(self.text) else ''
                if nxt in self.ESCAPES or nxt in ('u', 'U'):
                    # normal escape
                    save = self.pos
                    self.pos = i
                    out.append(self.parse_escapes())
                    i = self.pos
                    continue
                if nxt in ' \t\n\r':
                    # line-ending backslash: trim all whitespace incl. newlines
                    j = i + 1
                    while j < len(self.text) and self.text[j] in ' \t\n\r':
                        j += 1
                    i = j
                    continue
                self.err('invalid escape sequence', i)
            if c == '"':
                run = 0
                k = i
                while k < len(self.text) and self.text[k] == '"':
                    run += 1
                    k += 1
                if run >= 3:
                    # first three quotes close; any extras are content
                    out.append('"' * (run - 3))
                    self.pos = k
                    return ''.join(out)
                out.append('"' * run)
                i = k
                continue
            out.append(c)
            i += 1

    def parse_ml_literal(self):
        self.pos += 3  # '''
        i = self._ml_trim(self.pos)
        out = []
        while True:
            if i >= len(self.text):
                self.err('unterminated multi-line literal string')
            if self.text[i] == "'":
                run = 0
                k = i
                while k < len(self.text) and self.text[k] == "'":
                    run += 1
                    k += 1
                if run >= 3:
                    out.append("'" * (run - 3))
                    self.pos = k
                    return ''.join(out)
                out.append("'" * run)
                i = k
                continue
            j = self.text.find("'", i)
            if j < 0:
                self.err('unterminated multi-line literal string')
            out.append(self.text[i:j])
            i = j

    def parse_string_value(self):
        if self.at('"""'):
            return self.parse_ml_basic()
        if self.at("'''"):
            return self.parse_ml_literal()
        if self.text[self.pos] == '"':
            return self.parse_basic_string()
        return self.parse_literal_string()

    # ---------------- keys ----------------

    def parse_key_part(self):
        self.skip_ws()
        c = self.text[self.pos] if self.pos < len(self.text) else ''
        if c == '"':
            if self.at('"""'):
                self.err('multi-line strings are not allowed in keys')
            return self.parse_basic_string()
        if c == "'":
            if self.at("'''"):
                self.err('multi-line strings are not allowed in keys')
            return self.parse_literal_string()
        start = self.pos
        while self.pos < len(self.text) and (
                self.text[self.pos].isalnum()
                or self.text[self.pos] in '_-'):
            self.pos += 1
        if self.pos == start:
            self.err('invalid key')
        return self.text[start:self.pos]

    def parse_key(self):
        self.skip_ws()
        parts = [self.parse_key_part()]
        while True:
            self.skip_ws()
            if self.pos < len(self.text) and self.text[self.pos] == '.':
                self.pos += 1
                parts.append(self.parse_key_part())
            else:
                break
        return parts

    # ---------------- numbers ----------------

    @staticmethod
    def _is_digit(c):
        return '0' <= c <= '9'

    def _check_digit(self, c, base):
        if '0' <= c <= '9':
            d = ord(c) - 48
        elif base >= 11 and 'a' <= c <= 'f':
            d = ord(c) - 87
        elif base >= 11 and 'A' <= c <= 'F':
            d = ord(c) - 55
        else:
            self.err('invalid digit for base %d' % base)
        if d >= base:
            self.err('digit out of range for base %d' % base)

    def _consume_radix_digits(self, i, base):
        if i >= len(self.text):
            self.err('expected digit')
        self._check_digit(self.text[i], base)
        i += 1
        while i < len(self.text) and (self.text[i] == '_' or self.text[i].isalnum()):
            if self.text[i] == '_':
                if i + 1 >= len(self.text) or not self.text[i + 1].isalnum():
                    self.err('misplaced underscore', i)
                self._check_digit(self.text[i + 1], base)
                i += 2
            else:
                self._check_digit(self.text[i], base)
                i += 1
        return i

    def parse_number(self):
        i = self.pos
        if self.text[i] in '+-':
            i += 1
        if i >= len(self.text):
            self.err('expected value')
        c = self.text[i]
        if not ('0' <= c <= '9'):
            self.err('expected value, got %r' % c)
        # radix forms (unsigned)
        if c == '0' and i + 1 < len(self.text) and self.text[i + 1] in 'xob':
            base = {'x': 16, 'o': 8, 'b': 2}[self.text[i + 1]]
            j = self._consume_radix_digits(i + 2, base)
            digits = self.text[i + 2:j].replace('_', '')
            self.pos = j
            return int(digits, base)
        # decimal integer or float
        if c == '0' and i + 1 < len(self.text) and self._is_digit(self.text[i + 1]):
            self.err('leading zeros are not allowed', i)
        i += 1
        i = self._consume_decimal_digits(i)
        is_float = False
        if i < len(self.text) and self.text[i] == '.':
            if i + 1 >= len(self.text) or not self._is_digit(self.text[i + 1]):
                self.err('expected digits after decimal point', i)
            is_float = True
            i = self._consume_decimal_digits(i + 1)
        if i < len(self.text) and self.text[i] in 'eE':
            is_float = True
            i += 1
            if i < len(self.text) and self.text[i] in '+-':
                i += 1
            if i >= len(self.text) or not self._is_digit(self.text[i]):
                self.err('expected digits in exponent')
            i = self._consume_decimal_digits(i)
        literal = self.text[self.pos:i]
        self.pos = i
        if is_float:
            return float(literal.replace('_', ''))
        return int(literal.replace('_', ''))

    def _consume_decimal_digits(self, i):
        # consumes a run of digits with single underscores between; assumes at
        # least one digit has already been consumed before position i
        while i < len(self.text) and (self.text[i] == '_' or self._is_digit(self.text[i])):
            if self.text[i] == '_':
                if i + 1 >= len(self.text) or not self._is_digit(self.text[i + 1]):
                    self.err('misplaced underscore', i)
                i += 2
            else:
                i += 1
        return i

    # ---------------- values ----------------

    def parse_value(self):
        c = self.text[self.pos]
        if c == '"' or c == "'":
            return self.parse_string_value()
        if c == '[':
            return self.parse_array()
        if c == '{':
            return self.parse_inline_table()
        if c == 't' and self.at('true'):
            self.pos += 4
            return True
        if c == 'f' and self.at('false'):
            self.pos += 5
            return False
        if c in '+-0123456789':
            return self.parse_number()
        self.err('expected value, got %r' % c)

    def parse_array(self):
        self.pos += 1  # [
        arr = []
        while True:
            self.skip_ws_comments_newlines()
            if self.pos >= len(self.text):
                self.err('unterminated array')
            if self.text[self.pos] == ']':
                self.pos += 1
                return arr
            arr.append(self.parse_value())
            self.skip_ws_comments_newlines()
            if self.pos >= len(self.text):
                self.err('unterminated array')
            c = self.text[self.pos]
            if c == ',':
                self.pos += 1
            elif c == ']':
                self.pos += 1
                return arr
            else:
                self.err("expected ',' or ']' in array")

    def parse_inline_table(self):
        self.pos += 1  # {
        table = InlineTable()
        while True:
            self.skip_ws()
            if self.pos >= len(self.text):
                self.err('unterminated inline table')
            if self.text[self.pos] == '\n':
                self.err('newlines are not allowed in inline tables')
            if self.text[self.pos] == '}':
                self.pos += 1
                return table
            parts = self.parse_key()
            self.skip_ws()
            self.consume('=')
            self.skip_ws()
            value = self.parse_value()
            self._store(table, parts, value)
            self.skip_ws()
            if self.pos >= len(self.text):
                self.err('unterminated inline table')
            c = self.text[self.pos]
            if c == ',':
                self.pos += 1
            elif c == '}':
                self.pos += 1
                return table
            else:
                self.err("expected ',' or '}' in inline table")
            # no trailing comma: after a comma a key must follow
            self.skip_ws()
            if self.pos >= len(self.text) or self.text[self.pos] == '}':
                self.err('trailing comma is not allowed in inline tables')

    # ---------------- tables / insertion ----------------

    def _store(self, table, parts, value):
        cur = table
        for part in parts[:-1]:
            if part not in cur:
                cur[part] = {}
            v = cur[part]
            if isinstance(v, ArrayOfTables):
                cur = v[-1]
                if not isinstance(cur, dict) or isinstance(cur, InlineTable):
                    self.err('cannot extend array of tables', self.pos)
            elif isinstance(v, InlineTable):
                self.err('duplicate key %r' % part, self.pos)
            elif type(v) is dict:
                cur = v
            else:
                self.err('cannot redefine %r as a table' % part, self.pos)
        last = parts[-1]
        if last in cur:
            self.err('duplicate key %r' % last, self.pos)
        cur[last] = value
        return cur

    def _resolve(self, parts, aot):
        cur = self.root
        for part in parts[:-1]:
            if part not in cur:
                cur[part] = {}
            v = cur[part]
            if isinstance(v, ArrayOfTables):
                cur = v[-1]
                if not isinstance(cur, dict) or isinstance(cur, InlineTable):
                    self.err('invalid table header', self.pos)
            elif type(v) is dict:
                cur = v
            else:
                self.err('cannot redefine %r as a table' % part, self.pos)
        last = parts[-1]
        marker = (id(cur), last)
        if aot:
            if last in cur:
                v = cur[last]
                if isinstance(v, ArrayOfTables):
                    newt = {}
                    v.append(newt)
                    return newt
                self.err('duplicate key %r' % last, self.pos)
            self.explicit.add(marker)
            newt = {}
            cur[last] = ArrayOfTables([newt])
            return newt
        # static table header
        if marker in self.explicit:
            self.err('duplicate table header for %r' % last, self.pos)
        self.explicit.add(marker)
        if last in cur:
            if type(cur[last]) is dict:
                return cur[last]  # super-table defined after sub-table, or implicit
            self.err('duplicate key %r' % last, self.pos)
        newt = {}
        cur[last] = newt
        return newt

    # ---------------- headers / main loop ----------------

    def parse_header(self):
        aot = False
        self.consume('[')
        if self.at('['):
            aot = True
            self.pos += 1
        self.skip_ws()
        parts = self.parse_key()
        self.skip_ws()
        self.consume(']')
        if aot:
            self.consume(']')
        # header must end the line (a comment is allowed)
        self.skip_ws()
        if self.pos < len(self.text) and self.text[self.pos] == '#':
            while self.pos < len(self.text) and self.text[self.pos] != '\n':
                self.pos += 1
        self.skip_ws()
        if self.pos < len(self.text) and self.text[self.pos] != '\n':
            self.err('expected newline after table header')
        self.current = self._resolve(parts, aot)

    def parse_key_value(self):
        parts = self.parse_key()
        self.skip_ws()
        self.consume('=')
        self.skip_ws()
        value = self.parse_value()
        parent = self._store(self.current, parts, value)
        self.explicit.add((id(parent), parts[-1]))
        # end of line (comment allowed)
        self.skip_ws()
        if self.pos < len(self.text) and self.text[self.pos] == '#':
            while self.pos < len(self.text) and self.text[self.pos] != '\n':
                self.pos += 1
        self.skip_ws()
        if self.pos < len(self.text) and self.text[self.pos] != '\n':
            self.err('unexpected character after value')

    def parse(self):
        while True:
            self.skip_ws_comments_newlines()
            if self.pos >= len(self.text):
                break
            c = self.text[self.pos]
            if c == '[':
                self.parse_header()
            elif c in ' \t\n#':
                self.err('unexpected character', self.pos)
            else:
                self.parse_key_value()
        return self.root


def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print('usage: python3 tomlq.py FILE [KEYPATH]', file=sys.stderr)
        sys.exit(1)
    path = sys.argv[1]
    keypath = sys.argv[2] if len(sys.argv) == 3 else None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read().replace('\r\n', '\n').replace('\r', '\n')
    except OSError as e:
        print('tomlq: cannot read %s: %s' % (path, e), file=sys.stderr)
        sys.exit(1)
    try:
        doc = Parser(text).parse()
    except ParseError as e:
        print('tomlq: %s' % e, file=sys.stderr)
        sys.exit(1)
    if keypath is not None:
        node = doc
        for part in keypath.split('.'):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                print('tomlq: no such key: %s' % keypath, file=sys.stderr)
                sys.exit(2)
    sys.stdout.write(json.dumps(doc if keypath is None else node,
                               ensure_ascii=False) + '\n')
    sys.exit(0)


if __name__ == '__main__':
    main()
