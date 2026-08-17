import sys
import json
import re

class TOMLParseError(Exception):
    def __init__(self, message, code=1):
        self.message = message
        self.code = code
        super().__init__(self.message)

class TOMLScanner:
    def __init__(self, text):
        self.text = text
        self.pos = 0

    def error(self, message):
        raise TOMLParseError(message)

    def peek(self, n=1):
        return self.text[self.pos:self.pos+n]

    def skip_whitespace(self):
        while self.pos < len(self.text):
            if self.text[self.pos].isspace():
                self.pos += 1
            elif self.text[self.pos] == '#':
                while self.pos < len(self.text) and self.text[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    def next_token(self):
        self.skip_whitespace()
        if self.pos >= len(self.text):
            return ('EOF', None)

        char = self.text[self.pos]

        # String handling
        if char == '"':
            return ('STRING', self.scan_basic_string())
        if char == "'":
            return ('STRING', self.scan_literal_char_string())
        if self.text.startswith('"""', self.pos):
            return ('STRING', self.scan_multiline_string(True))
        if self.text.startswith("'''", self.pos):
            return ('STRING', self.scan_multiline_string(False))

        # Array/Table delimiters
        if self.text.startswith('[[', self.pos):
            self.pos += 2
            return ('TABLE_ARRAY_START', '[[')
        if char == '[':
            self.pos += 1
            return ('TABLE_START', '[')
        if char == ']':
            self.pos += 1
            return ('RBRACKET', ']')
        if char == '{':
            self.pos += 1
            return ('LBRACE', '{')
        if char == '}':
            self.pos += 1
            return ('RBRACE', '}')
        if char == '=':
            self.pos += 1
            return ('EQUALS', '=')
        if char == ',':
            self.pos += 1
            return ('COMMA', ',')
        if char == '.':
            self.pos += 1
            return ('DOT', '.')

        # Numbers and Booleans and Keys
        start = self.pos
        while self.pos < len(self.text) and (self.text[self.pos].isalnum() or self.text[self.pos] in '_-.'):
            # Note: we include '.' because keys can be dotted, but we handle them as separate tokens
            # Actually, let's stop at non-alphanumeric
            if not (self.text[self.pos].isalnum() or self.text[self.pos] in '_-'):
                break
            self.pos += 1
        
        atom = self.text[start:self.pos]
        if not atom:
            self.error("Unexpected character: " + char)
            
        if atom == 'true': return ('BOOL', True)
        if atom == 'false': return ('BOOL', False)
        
        # Number parsing
        try:
            # Remove underscores for number parsing
            clean_atom = atom.replace('_', '')
            if clean_atom.startswith(('0x', '0o', '0b')):
                if clean_atom.startswith('0x'):
                    return ('INT', int(clean_atom, 16))
                if clean_atom.startswith('0o'):
                    return ('INT', int(clean_atom, 8))
                if clean_atom.startswith('0b'):
                    return ('INT', int(clean_atom, 2))
            if '.' in clean_atom or 'e' in clean_atom.lower():
                return ('FLOAT', float(clean_atom))
            if clean_atom.startswith('0') and len(clean_atom) > 1 and not clean_atom.startswith(('0x', '0o', '0b')):
                # Check for leading zero error in decimal
                self.error("Leading zeros in decimal are not allowed")
            return ('INT', int(clean_atom))
        except ValueError:
            # If it's not a number, it's a key/identifier
            return ('KEY', atom)

    def scan_basic_string(self):
        start = self.pos
        self.pos += 1  # skip "
        while self.pos < len(self.text):
            if self.text[self.pos] == '"':
                self.pos += 1
                return self.text[start:self.pos]
            if self.text[self.pos] == '\\':
                self.pos += 2
            else:
                self.pos += 1
        self.error("Unterminated basic string")

    def scan_literal_char_string(self):
        start = self.pos
        self.pos += 1  # skip '
        while self.append_to_pos_if_found(self.text, self.pos, "'"):
            self.pos += 1
        if self.pos >= len(self.text):
            self.error("Unterminated literal string")
        return self.text[start:self.pos]

    def append_to_pos_if_found(self, text, pos, char):
        # Helper for scanning
        return False # placeholder

    # Let's rewrite the scanner properly. 
    # The above is too messy. I will use a simpler approach.
    
# Rewriting...
