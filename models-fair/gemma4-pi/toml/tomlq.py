import sys
import json
import re

class TOMLParseError(Exception):
    pass

class TOMLScanner:
    def __init__(self, text):
        self.text = text
        self.pos = 0

    def peek(self, n=1):
        return self.text[self.pos:self.pos+n]

    def consume(self, n=1):
        res = self.text[self.pos:self.pos+n]
        self.pos += n
        return res

    def skip_whitespace_and_comments(self):
        while self.pos < len(self.text):
            if self.text[self.pos].isspace():
                self.pos += 1
            elif self.text[self.pos] == '#':
                while self.pos < len(self.text) and self.text[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    def next_token(self):
        self.skip_whitespace_and_comments()
        if self.pos >= len(self.text):
            return None

        char = self.text[self.pos]

        # Strings
        if char == '"':
            return self.scan_basic_string()
        elif char == "'":
            return self.scan_literal_string()
        elif char == '"' and self.peek(3) == '"""':
            return self.scan_multiline_basic_string()
        elif char == "'" and self.peek(3) == "'''":
            return self.scan_multiline_literal_string()
        
        # Numbers, Booleans, Identifiers, Punctuation
        # We'll use a regex for the rest to simplify
        remaining = self.text[self.pos:]
        
        # Check for [[ or ]] or [ or ] or { or } or = or , or .
        match = re.match(r'(\[\[|\]\]|\[|\]|\{|\}|=|,| \.)', remaining)
        # Wait, the dot might be part of a key. Let's refine.
        
        # Let's use a simpler approach for non-string tokens:
        # Match the largest possible token from a set of patterns.
        patterns = [
            ('BOOL', r'true|false'),
            ('FLOAT', r'[+-]?\d[0-9_]*(?:\.\d[0-9_]*)?(?:[eE][+-]?\d[0-9_]*)?'),
            ('INT', r'[+-]?0[xX][0-9a-fA-F_]+|[+-]?0[oO][0-7_]+|[+-]?0[bB][01_]+|[+-]?\d[0-9_]*'),
            ('KEY', r'[A-Za-textrm0-9_-]+'), # This is a bit loose
            ('PUNCT', r'[\[\]\{\}=,.]'),
        ]
        # Actually, the regex approach is tricky because of the order.
        # Let's use a simpler scanner.
        
        # Let's try regex for everything else.
        # We need to be careful with the order.
        
        # Check for tokens:
        for type, pattern in [
            ('BOOL', r'true|false'),
            ('FLOAT', r'[+-]?\d[0-9_]*\.\d[0-9_]*(?:[eE][+-]?\d[0-9_]*)?'), # Must have a dot
            ('FLOAT_SCI', r'[+-]?\d[0-9_]*[eE][+-]?\d[0-9_]*'),
            ('INT', r'[+-]?0[xX][0-9a-fA-F_]+|[+-]?0[oO][0-7_]+|[+-]?0[bB][01_]+|[+-]?\d[0-9_]*'),
            ('PUNCT', r'\[\[|\]\]|\[|\]|\{|\}|=|,| \.'), # Added space before dot to avoid matching keys
            ('KEY', r'[A-Za-z0-9_-]+'),
        ]:
            match = re.match(pattern, remaining)
            if match:
                token_val = match.group(0)
                # Validate INT (no leading zeros unless 0x, 0o, 0b)
                if type == 'INT' and len(token_val) > 1 and token_val[0] in '+-' and token_val[1] == '0' and len(token_val) > 2 and token_val[2] not in 'xo b':
                     # This is tricky. Let's let the parser handle the 'leading zero' error.
                     pass
                
                # Wait, if it's a FLOAT, we should check it. 
                # Let's just return the token and let the parser handle types.
                self.pos += len(token_val)
                return (type, token_val)

        # If nothing matches, it might be a single character punctuation
        char = self.text[self.pos]
        if char in '[]{}=,.':
            self.pos += 1
            return ('PUNCT', char)
        
        # If we are here, we might have a key that regex missed
        # Let's use a more robust way.
        raise TOMLParseError(f"Unexpected character at {self.pos}: {char}")

    def scan_basic_string(self):
        # Starts with "
        self.pos += 1 # skip "
        res = []
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char == '"':
                self.pos += 1
                return ('STRING', "".join(res))
            elif char == '\\':
                self.pos += 1
                esc = self.text[self.pos]
                if esc == '"': res.append('"')
                elif esc == '\\': res.append('\\')
                elif esc == 'b': res.append('\b')
                elif esc == 'f': res.append('\f')
                elif esc == 'n': res.append('\n')
                elif esc == 'r': res.append('\r')
                elif esc == 't': res.append('\t')
                elif esc == 'u':
                    # \uXXXX
                    self.pos += 4
                    hex_val = self.text[self.pos-4:self.pos]
                    res.append(chr(int(hex_val, 16)))
                elif esc == 'U':
                    # \UXXXXXXXX
                    self.pos += 8
                    hex_val = self.text[self.pos-8:self.pos]
                    res.append(chr(int(hex_val, 16)))
                else:
                    res.append(esc) # Should not happen in valid TOML
                self.pos += 1
            else:
                res.append(char)
                self.pos += 1
        raise TOMLParseError("Unterminated basic string")

    def scan_literal_string(self):
        # Starts with '
        self.pos += 1 # skip '
        start = self.pos
        while self.pos < len(self.token_text_if_needed_but_i_dont_have_it): # wait
            pass
        # I need to fix the scanner. Let's rewrite it.
        pass

# Rewriting the scanner and parser from scratch.
