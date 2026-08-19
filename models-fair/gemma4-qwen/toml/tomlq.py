import sys
import json
import re

def error(msg, code=1):
    sys.stderr.write(f"Error: {msg}\n")
    sys.exit(code)

class TOMLParser:
    def __init__(self, text):
        self.text = text
        self.tokens = []
        self.pos = 0
        self.root = {}

    def tokenize(self):
        token_pattern = re.compile(r'''
            (?P<ML_BASIC>"""(?:(?!\b\"\"\").)*""") |
            (?P<ML_LITERAL>''' + r"'''(?:(?!''').)*'''" + r""") |
            (?P<BASIC_STRING>"(?:[^"\\]|\\.)*") |
            (?P<LITERAL_STRING>'(?:[^'\\]|\\.)*') |
            (?P<FLOAT>[+-]?\d+\.\d+(?:[eE][+-]?\d+)?|[+-]?\d+[eE][+-]?\d+?) |
            (?P<INT>0[xob][0-9a-fA-F_]+|[+-]?\d+[0-9_]*) |
            (?P<BOOL>true|false) |
            (?P<SYM>\[\[|\]\]|[\[\]\{\}=,.]) |
            (?P<BARE_KEY>[A-Za-z0-9_-]+) |
            (?P<WHITESPACE>\s+) |
            (?P<COMMENT>#.*)
        ''', re.VERBOSE | re.DOTALL)

        for match in token_pattern.finditer(self.text):
            kind = match.lastgroup
            if kind and kind not in ('WHITESPACE', 'COMMENT'):
                self.tokens.append((kind, match.group(0)))

    def parse(self):
        # To be implemented
        return self.root

def main():
    args = sys.argv[1:]
    
    if not args:
        try:
            text = sys.stdin.read()
        except EOFError:
            return
    else:
        file_path = args[0]
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except FileNotFoundError:
            error(f"File not found: {file_path}", 1)
            return
        except Exception as e:
            error(f"Error reading file: {e}", 1)
            return

    keypath = args[1] if len(args) > 1 else None

    try:
        parser = TOMLParser(text)
        parser.tokenize()
        data = parser.parse()
        
        if keypath:
            parts = keypath.split('.')
            current = data
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    error(f"Keypath not found: {keypath}", 2)
            print(json.dumps(current, indent=2))
        else:
            print(json.dumps(data, indent=2))
            
    except Exception as e:
        error(f"Parse error: {e}", 1)

if __name__ == "__main__":
    main()
