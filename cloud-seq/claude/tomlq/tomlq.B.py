#!/usr/bin/env python3
"""tomlq.py – Minimal TOML parser for a subset of TOML v1.0.0.

Implements the features required by the test suite in this repository.
Only the Python standard library is used.
"""

import sys
import json
from typing import Any, List, Dict, Tuple, Set


class TomlParseError(Exception):
    pass


class TomlParser:
    def __init__(self, text: str):
        self.text = text
        self.idx = 0
        self.length = len(text)
        self.root: Dict[str, Any] = {}
        # current table where key/value pairs are added
        self.current_table = self.root
        # Explicitly defined table headers (to detect duplicates)
        self.explicit_tables: Set[Tuple[str, ...]] = set()
        # Paths that originated from inline tables and may not be extended
        self.locked_paths: Set[Tuple[str, ...]] = set()
        # Mapping of array‑of‑tables path → last element dict (for sub‑table headers)
        self.last_array_elem: Dict[Tuple[str, ...], Dict[str, Any]] = {}

    # ---------------------------------------------------------------------
    # Helpers for reading the input
    # ---------------------------------------------------------------------
    def eof(self) -> bool:
        return self.idx >= self.length

    def peek(self, n: int = 1) -> str:
        if self.idx + n > self.length:
            return ""
        return self.text[self.idx : self.idx + n]

    def advance(self, n: int = 1) -> None:
        self.idx += n

    def error(self, msg: str) -> TomlParseError:
        # Provide a simple location hint for debugging
        line = self.text.count("\n", 0, self.idx) + 1
        col = self.idx - self.text.rfind("\n", 0, self.idx)
        return TomlParseError(f"Line {line}, col {col}: {msg}")

    # ---------------------------------------------------------------------
    # Whitespace / comment handling
    # ---------------------------------------------------------------------
    def skip_ws_and_comments(self) -> None:
        while not self.eof():
            ch = self.text[self.idx]
            if ch in " \t\r\n":
                self.idx += 1
                continue
            if ch == "#":
                # skip to end of line
                while not self.eof() and self.text[self.idx] != "\n":
                    self.idx += 1
                continue
            break

    def skip_spaces(self) -> None:
        while not self.eof() and self.text[self.idx] in " \t":
            self.idx += 1

    # ---------------------------------------------------------------------
    # Public entry point
    # ---------------------------------------------------------------------
    def parse(self) -> Dict[str, Any]:
        while True:
            self.skip_ws_and_comments()
            if self.eof():
                break
            if self.peek() == "[":
                if self.peek(2) == "[[":
                    self.advance(2)  # consume '[['
                    self.skip_ws_and_comments()
                    parts = self.parse_key()
                    self.skip_ws_and_comments()
                    if self.peek(2) != "]]":
                        raise self.error("Expected ']]' to close array of tables header")
                    self.advance(2)
                    self.handle_array_of_tables(parts)
                else:
                    self.advance()  # consume '['
                    self.skip_ws_and_comments()
                    parts = self.parse_key()
                    self.skip_ws_and_comments()
                    if self.peek() != "]":
                        raise self.error("Expected ']' to close table header")
                    self.advance()
                    self.handle_table(parts)
            else:
                self.handle_key_value()
        return self.root

    # ---------------------------------------------------------------------
    # Table handling
    # ---------------------------------------------------------------------
    def resolve_path(self, parts: List[str], create: bool = True) -> Tuple[Dict[str, Any], List[str]]:
        """Resolve a dotted path to a dict.

        Returns a tuple (container, remaining_parts) where *container* is the dict
        that holds the final part and *remaining_parts* is a list of the parts that
        have not yet been resolved (used for creating new tables).
        """
        current: Any = self.root
        i = 0
        while i < len(parts):
            if isinstance(current, list):
                # we are inside an array of tables – use its last element
                if not current:
                    raise self.error("Array of tables is empty when resolving path")
                current = current[-1]
                # do not advance i, stay on same part (it refers to a key inside the table)
                continue
            if not isinstance(current, dict):
                raise self.error("Expected a table while resolving path")
            part = parts[i]
            # If this is the final part, return the container and the remaining part
            if i == len(parts) - 1:
                return current, [part]
            # Intermediate part
            if part not in current:
                if create:
                    current[part] = {}
                else:
                    raise self.error(f"Missing intermediate table '{part}'")
                current = current[part]
                i += 1
                continue
            # Part exists
            if isinstance(current[part], list):
                # Descend into the last table of the array
                if not current[part]:
                    raise self.error("Array of tables is empty when resolving path")
                current = current[part][-1]
                i += 1
                continue
            if isinstance(current[part], dict):
                current = current[part]
                i += 1
                continue
            # Existing key is a non‑table scalar – error
            raise self.error(f"Path '{'.'.join(parts[: i + 1])}' is not a table")
        # Should never reach here
        raise self.error("Invalid path resolution logic")

    def handle_table(self, parts: List[str]) -> None:
        # Detect duplicate explicit table header
        path_tuple = tuple(parts)
        if path_tuple in self.explicit_tables:
            raise self.error(f"Duplicate table header [{'.'.join(parts)}]")
        self.explicit_tables.add(path_tuple)
        # Resolve or create the table (parents may be implicit)
        container, last = self.resolve_path(parts, create=True)
        # Ensure the final component exists and is a dict
        final = last[0]
        if final in container:
            if not isinstance(container[final], dict):
                raise self.error(f"Table name '{final}' collides with a non‑table value")
        else:
            container[final] = {}
        self.current_table = container[final]

    def handle_array_of_tables(self, parts: List[str]) -> None:
        if not parts:
            raise self.error("Empty array of tables header")
        parent_parts = parts[:-1]
        array_key = parts[-1]
        # Resolve the container where this array-of-tables should live
        if parent_parts:
            # Resolve to the dict that holds the parent array (e.g., 'fruits')
            container, last = self.resolve_path(parent_parts, create=True)
            parent_array_name = last[0]
            if parent_array_name not in container:
                container[parent_array_name] = []
            elif not isinstance(container[parent_array_name], list):
                raise self.error(f"Key '{parent_array_name}' already exists and is not an array of tables")
            # The parent array must have at least one element to attach the sub‑table
            if not container[parent_array_name]:
                raise self.error(f"Array '{parent_array_name}' has no elements to attach '{array_key}'")
            parent_container = container[parent_array_name][-1]
        else:
            parent_container = self.root
        # Initialise the array if necessary under the parent container
        if array_key in parent_container:
            if not isinstance(parent_container[array_key], list):
                raise self.error(f"Key '{array_key}' already exists and is not an array of tables")
        else:
            parent_container[array_key] = []
        # Append a new dict element to the array
        new_elem: Dict[str, Any] = {}
        parent_container[array_key].append(new_elem)
        # Remember the last element for subsequent sub‑table headers
        self.last_array_elem[tuple(parts)] = new_elem
        self.current_table = new_elem

    # ---------------------------------------------------------------------
    # Key/value handling
    # ---------------------------------------------------------------------
    def handle_key_value(self) -> None:
        # Parse the (possibly dotted) key
        key_parts = self.parse_key()
        self.skip_ws_and_comments()
        if self.eof() or self.text[self.idx] != "=":
            raise self.error("Expected '=' after key")
        self.advance()  # consume '='
        self.skip_ws_and_comments()
        value = self.parse_value()
        # ---- enforce single pair per line --------------------------------
        # After a value we may have spaces/tabs, optional comment, then a newline or EOF.
        # Any other token on the same physical line is an error.
        saved_idx = self.idx
        self.skip_spaces()
        if not self.eof():
            if self.peek() == "#":
                # consume comment up to newline
                while not self.eof() and self.peek() != "\n":
                    self.advance()
                # after comment, skip any spaces before newline
                self.skip_spaces()
            if self.peek() not in "\n\r":
                raise self.error("Multiple key/value pairs on the same line are not allowed")
        # If we stopped at a newline or EOF, move past the newline(s) for the next loop.
        while not self.eof() and self.text[self.idx] in "\r\n":
            self.idx += 1
        # -------------------------------------------------------------------

        # Insert value respecting dotted keys
        self.insert_key_path(key_parts, value)

    def insert_key_path(self, parts: List[str], value: Any) -> None:
        # Follow/create intermediate tables
        container = self.current_table
        for i, part in enumerate(parts):
            # Guard against extending inline tables
            prefix = tuple(parts[: i + 1])
            if prefix in self.locked_paths:
                raise self.error(f"Cannot extend inline table at '{'.'.join(prefix)}'")
            if i == len(parts) - 1:
                # final part – insert the value
                if part in container:
                    raise self.error(f"Duplicate key '{part}'")
                container[part] = value
                # If the value is an inline table (a dict) we lock its path
                if isinstance(value, dict) and self.is_inline_table(value):
                    self.locked_paths.add(tuple(parts))
                return
            # intermediate part – must be a table (dict)
            if part not in container:
                container[part] = {}
            elif not isinstance(container[part], dict):
                raise self.error(f"Key '{part}' already has a non‑table value")
            container = container[part]

    # ---------------------------------------------------------------------
    # Key parsing (bare or quoted)
    # ---------------------------------------------------------------------
    def parse_key(self) -> List[str]:
        parts: List[str] = []
        while True:
            part = self.parse_key_part()
            parts.append(part)
            self.skip_ws_and_comments()
            if self.peek() == ".":
                self.advance()
                self.skip_ws_and_comments()
                continue
            break
        return parts

    def parse_key_part(self) -> str:
        if self.eof():
            raise self.error("Unexpected EOF while parsing key")
        ch = self.peek()
        if ch == '"':
            return self.parse_basic_string()
        if ch == "'":
            return self.parse_literal_string()
        # Bare key – must match [A-Za-z0-9_-]+
        start = self.idx
        while not self.eof():
            c = self.text[self.idx]
            if c.isalnum() or c in "_-":
                self.idx += 1
                continue
            break
        if self.idx == start:
            raise self.error("Invalid bare key")
        return self.text[start:self.idx]

    # ---------------------------------------------------------------------
    # Value parsing
    # ---------------------------------------------------------------------
    def parse_value(self) -> Any:
        self.skip_ws_and_comments()
        if self.eof():
            raise self.error("Unexpected EOF while parsing value")
        ch = self.peek()
        if ch == '"':
            return self.parse_basic_string()
        if ch == "'":
            return self.parse_literal_string()
        if ch == '[':
            return self.parse_array()
        if ch == '{':
            return self.parse_inline_table()
        # Booleans
        if self.text.startswith("true", self.idx):
            after = self.idx + 4
            if after == self.length or not self.text[after].isalnum():
                self.idx = after
                return True
        if self.text.startswith("false", self.idx):
            after = self.idx + 5
            if after == self.length or not self.text[after].isalnum():
                self.idx = after
                return False
        # Numbers (int or float)
        return self.parse_number()

    # ---------------------------------------------------------------------
    # String parsing (basic and literal, single‑ and multi‑line)
    # ---------------------------------------------------------------------
    def parse_basic_string(self) -> str:
        # Determine if this is a triple‑quoted string
        if self.peek(3) == '"""':
            self.advance(3)
            multiline = True
            # Trim first newline if present
            if not self.eof() and self.peek() == '\n':
                self.advance()
        else:
            if self.peek() != '"':
                raise self.error("Expected '\"' to start a basic string")
            self.advance()
            multiline = False
        result: List[str] = []
        while True:
            if self.eof():
                raise self.error("Unterminated basic string")
            if multiline and self.peek(3) == '"""':
                self.advance(3)
                break
            if not multiline and self.peek() == '"':
                self.advance()
                break
            ch = self.peek()
            if ch == '\\':
                # Escape handling or line‑continuation
                self.advance()
                if self.eof():
                    raise self.error("Unterminated escape sequence in string")
                esc = self.peek()
                if esc == '\n':
                    # line‑continuation – skip newline and following whitespace
                    self.advance()
                    while not self.eof() and self.peek() in ' \t\r\n':
                        self.advance()
                    continue
                if esc == 'b':
                    result.append('\b')
                elif esc == 't':
                    result.append('\t')
                elif esc == 'n':
                    result.append('\n')
                elif esc == 'f':
                    result.append('\f')
                elif esc == 'r':
                    result.append('\r')
                elif esc == '"':
                    result.append('"')
                elif esc == '\\':
                    result.append('\\')
                elif esc == 'u':
                    self.advance()
                    hex_digits = self.text[self.idx : self.idx + 4]
                    if len(hex_digits) != 4 or any(c not in "0123456789abcdefABCDEF" for c in hex_digits):
                        raise self.error("Invalid \\u escape sequence")
                    result.append(chr(int(hex_digits, 16)))
                    self.advance(4)
                    continue
                elif esc == 'U':
                    self.advance()
                    hex_digits = self.text[self.idx : self.idx + 8]
                    if len(hex_digits) != 8 or any(c not in "0123456789abcdefABCDEF" for c in hex_digits):
                        raise self.error("Invalid \\U escape sequence")
                    result.append(chr(int(hex_digits, 16)))
                    self.advance(8)
                    continue
                else:
                    raise self.error(f"Invalid escape character '\\{esc}' in string")
                self.advance()
            else:
                result.append(ch)
                self.advance()
        return ''.join(result)

    def parse_literal_string(self) -> str:
        # Triple‑quoted literal string?
        if self.peek(3) == "'''":
            self.advance(3)
            multiline = True
            if not self.eof() and self.peek() == '\n':
                self.advance()
        else:
            if self.peek() != "'":
                raise self.error("Expected \"'\" to start a literal string")
            self.advance()
            multiline = False
        result: List[str] = []
        while True:
            if self.eof():
                raise self.error("Unterminated literal string")
            if multiline and self.peek(3) == "'''":
                self.advance(3)
                break
            if not multiline and self.peek() == "'":
                self.advance()
                break
            # No escape processing – take character verbatim
            result.append(self.peek())
            self.advance()
        return ''.join(result)

    # ---------------------------------------------------------------------
    # Array parsing
    # ---------------------------------------------------------------------
    def parse_array(self) -> List[Any]:
        self.advance()  # consume '['
        arr: List[Any] = []
        while True:
            self.skip_ws_and_comments()
            if self.eof():
                raise self.error("Unterminated array")
            if self.peek() == ']':
                self.advance()
                break
            value = self.parse_value()
            arr.append(value)
            self.skip_ws_and_comments()
            if self.peek() == ',':
                self.advance()
                continue
            if self.peek() == ']':
                self.advance()
                break
            raise self.error("Expected ',' or ']' in array")
        return arr

    # ---------------------------------------------------------------------
    # Inline table parsing
    # ---------------------------------------------------------------------
    def parse_inline_table(self) -> Dict[str, Any]:
        self.advance()  # consume '{'
        table: Dict[str, Any] = {}
        first = True
        while True:
            self.skip_ws_and_comments()
            if self.eof():
                raise self.error("Unterminated inline table")
            if self.peek() == '}':
                self.advance()
                break
            if not first:
                if self.peek() != ',':
                    raise self.error("Expected ',' between inline table items")
                self.advance()
                self.skip_ws_and_comments()
            first = False
            # Inline table keys may be dotted.
            key_parts = self.parse_key()
            # Resolve target dict within the inline table.
            target = table
            for i, part in enumerate(key_parts):
                if i == len(key_parts) - 1:
                    final_key = part
                else:
                    if part not in target:
                        target[part] = {}
                    elif not isinstance(target[part], dict):
                        raise self.error(f"Invalid dotted key in inline table: '{part}' conflicts with existing non-table value")
                    target = target[part]
            self.skip_ws_and_comments()
            if self.eof() or self.peek() != '=':
                raise self.error("Expected '=' after key in inline table")
            self.advance()
            self.skip_ws_and_comments()
            val = self.parse_value()
            if final_key in target:
                raise self.error(f"Duplicate key '{final_key}' in inline table")
            target[final_key] = val
        return table

    # ---------------------------------------------------------------------
    # Number parsing
    # ---------------------------------------------------------------------
    def parse_number(self) -> Any:
        start = self.idx
        # Optional sign for decimal numbers
        sign = ''
        if self.peek() in '+-':
            sign = self.peek()
            self.advance()
        # Look ahead to decide which kind of number we have
        if self.peek(2).lower() == '0x':
            # Hexadecimal integer
            self.advance(2)  # consume '0x'
            digits_start = self.idx
            while not self.eof() and (self.peek().isalnum() or self.peek() == '_'):
                self.idx += 1
            raw = self.text[digits_start:self.idx].replace('_', '')
            if not raw:
                raise self.error("Invalid hexadecimal integer")
            try:
                return int(raw, 16)
            except ValueError:
                raise self.error("Invalid hexadecimal integer")
        if self.peek(2).lower() == '0o':
            self.advance(2)
            digits_start = self.idx
            while not self.eof() and (self.peek().isdigit() or self.peek() == '_'):
                self.idx += 1
            raw = self.text[digits_start:self.idx].replace('_', '')
            if not raw:
                raise self.error("Invalid octal integer")
            return int(raw, 8)
        if self.peek(2).lower() == '0b':
            self.advance(2)
            digits_start = self.idx
            while not self.eof() and (self.peek() in '01' or self.peek() == '_'):
                self.idx += 1
            raw = self.text[digits_start:self.idx].replace('_', '')
            if not raw:
                raise self.error("Invalid binary integer")
            return int(raw, 2)
        # Decimal integer or float
        has_dot = False
        has_exp = False
        while not self.eof() and (self.peek().isdigit() or self.peek() == '_' or self.peek() in '.eE'):
            ch = self.peek()
            if ch == '.':
                if has_dot:
                    raise self.error("Multiple decimal points in number")
                has_dot = True
                self.advance()
            elif ch in 'eE':
                if has_exp:
                    raise self.error("Multiple exponent markers in number")
                has_exp = True
                self.advance()
                # exponent may have its own sign
                if not self.eof() and self.peek() in '+-':
                    self.advance()
            else:
                self.advance()
        raw = self.text[start:self.idx].replace('_', '')
        # Determine if float
        if ('.' in raw) or ('e' in raw) or ('E' in raw):
            try:
                return float(raw)
            except ValueError:
                raise self.error(f"Invalid float literal '{raw}'")
        # Integer – enforce no leading zeros (except a single zero)
        if raw.startswith(('+', '-')):
            sign_char = raw[0]
            num_body = raw[1:]
        else:
            sign_char = ''
            num_body = raw
        if len(num_body) > 1 and num_body[0] == '0' and not all(c == '_' for c in num_body[1:]):
            raise self.error("Leading zeros are not allowed in decimal integers")
        try:
            return int(sign + num_body)
        except ValueError:
            raise self.error(f"Invalid integer literal '{raw}'")

    # ---------------------------------------------------------------------
    # Helper to identify inline tables (used for locking paths)
    # ---------------------------------------------------------------------
    def is_inline_table(self, value: Any) -> bool:
        # Inline tables are dicts that originated from parse_inline_table.
        # By construction we only lock the top‑level dict supplied directly.
        return isinstance(value, dict)


def main() -> None:
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python3 tomlq.py FILE [KEYPATH]", file=sys.stderr)
        sys.exit(1)
    path = sys.argv[1]
    keypath = sys.argv[2] if len(sys.argv) == 3 else None
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        parser = TomlParser(text)
        document = parser.parse()
        # Resolve optional keypath
        if keypath is not None:
            parts = keypath.split('.')
            cur: Any = document
            for p in parts:
                if not isinstance(cur, dict) or p not in cur:
                    print(f"Key path '{keypath}' not found", file=sys.stderr)
                    sys.exit(2)
                cur = cur[p]
            result = cur
        else:
            result = document
        json.dump(result, sys.stdout, ensure_ascii=False)
        sys.stdout.write('\n')
        sys.exit(0)
    except TomlParseError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Any unexpected error is treated as a parse failure.
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
