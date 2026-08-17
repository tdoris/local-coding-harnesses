
class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.data = {}
        self.current_table = self.data

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consume(self, expected_type=None):
        token = self.peek()
        if not token:
            raise TOMLParseError("Unexpected end of input", 0, 0)
        if expected_type and token.type != expected_type:
            raise TOMLParseError(f"Expected {expected_type} but found {token.type}", token.line, token.col)
        self.pos += 1
        return token

    def parse(self):
        while self.pos < len(self.tokens):
            token = self.peek()
            if token.type == 'LBRACKET':
                self._parse_table()
            elif token.type == 'IDENTIFIER':
                self._parse_assignment()
            else:
                # Skip unexpected tokens at top level, but in a real parser we'd error
                self.pos += 1
        return self.data

    def _parse_table(self):
        self.consume('LBRACKET')
        name_parts = []
        while self.peek() and self.peek().type != 'RBRACKET':
            token = self.consume()
            if token.type == 'IDENTIFIER':
                name_parts.append(token.value)
            elif token.type == 'DOT':
                continue
            else:
                raise TOMLParseError(f"Unexpected token in table name: {token.type}", token.line, token.col)
        self.consume('RBRACKET')
        
        # Navigate to the table
        self.current_table = self._get_nested_dict(name_parts)

    def _parse_assignment(self):
        key_parts = []
        while self.peek() and self.peek().type in ('IDENTIFIER', 'DOT'):
            token = self.consume()
            if token.type == 'IDENTIFIER':
                key_parts.append(token.value)
            elif token.type == 'DOT':
                continue
        
        self.consume('EQUALS')
        value = self._parse_value()
        
        # Assign value to the nested dict
        target = self._get_nested_dict(key_parts)
        target[key_parts[-1]] = value

    def _get_nested_dict(self, parts):
        curr = self.data
        for part in parts:
            if part not in curr:
                curr[part] = {}
            curr = curr[part]
        return curr

    def _parse_value(self):
        token = self.consume()
        if token.type in ('STRING_BASIC', 'STRING_LITERAL', 'STRING_MULTILINE_BASIC', 'STRING_MULTILINE_LITERAL', 'INTEGER', 'FLOAT', 'BOOLEAN'):
            return token.value
        elif token.type == 'LBRACKET':
            return self._parse_array()
    def _parse_inline_table(self):
        self.consume('LBRACE')
        table = {}
        while self.peek() and self.peek().type != 'RBRACE':
            key_parts = []
            while self.peek() and self.peek().type in ('IDENTIFIER', 'DOT'):
                token = self.consume()
                if token.type == 'IDENTIFIER':
                    key_parts.append(token.value)
                elif token.type == 'DOT':
                    continue
            
            self.consume('EQUALS')
            value = self._parse_value()
            
            target = self._get_nested_dict(key_parts)
            target[key_parts[-1]] = value
            
            if self.peek() and self.peek().type == 'COMMA':
                self.consume('COMMA')
                
        self.consume('RBRACE')
        return table
    def _parse_value(self):
        token = self.consume()
        if token.type in ('STRING_BASIC', 'STRING_LITERAL', 'STRING_MULTILINE_BASIC', 'STRING_MULTILINE_LITERAL', 'INTEGER', 'FLOAT', 'BOOLEAN'):
            return token.value
        elif token.type == 'LBRACKET':
            return self._parse_array()
        elif token.type == 'LBRACE':
            return self._parse_inline_table()
        else:
            raise TOMLParseError(f"Unexpected value type: {token.type}", token.line, token.col)

    def _parse_array(self):
        self.consume('LBRACKET')
        arr = []
        while self.peek() and self.peek().type != 'RBRACKET':
            arr.append(self._parse_value())
            if self.peek() and self.peek().type == 'COMMA':
                self.consume('COMMA')
        self.consume('RBRACKET')
        return arr
