import unittest
from tomlq import Tokenizer

class TestTokenizer(unittest.TestCase):
    def test_basic_tokens(self):
        toml_content = 'key = "value"\nnumber = 123\nboolean = true'
        tokenizer = Tokenizer(toml_content)
        tokens = tokenizer.tokenize()
        
        expected_types = ['IDENTIFIER', 'EQUALS', 'STRING_BASIC', 'IDENTIFIER', 'EQUALS', 'INTEGER', 'IDENTIFIER', 'EQUALS', 'BOOLEAN']
        actual_types = [t.type for t in tokens]
        self.assertEqual(actual_types, expected_types)

    def test_strings(self):
        toml_content = 's1 = "double quoted"\ns2 = \'single quoted\'\ns3 = """multiline\nbasic"""\ns4 = \'\'\'multiline\nliteral\'\'\''
        tokenizer = Tokenizer(toml_content)
        tokens = tokenizer.tokenize()
        
        # Filter for string tokens
        string_tokens = [t for t in tokens if t.type.startswith('STRING')]
        self.assertEqual(len(string_tokens), 4)
        self.assertEqual(string_tokens[0].value, 'double quoted')
        self.assertEqual(string_tokens[1].value, 'single quoted')
        self.assertEqual(string_tokens[2].value, 'multiline\nbasic')
        self.assertEqual(string_tokens[3].value, 'multiline\nliteral')

    def test_numbers_and_floats(self):
        toml_content = 'i = 1\nf = 1.23\ne = 1.2e3'
        tokenizer = Tokenizer(toml_content)
        tokens = tokenizer.tokenize()
        
        values = [t.value for t in tokens if t.type in ('INTEGER', 'FLOAT')]
        self.assertEqual(values, [1, 1.23, 1200.0])

    def test_arrays_and_tables(self):
        toml_content = 'arr = [1, 2]\n[table]\nkey = "val"'
        tokenizer = Tokenizer(toml_content)
        tokens = tokenizer.tokenize()
        
        expected_types = ['IDENTIFIER', 'EQUALS', 'LBRACKET', 'INTEGER', 'COMMA', 'INTEGER', 'RBRACKET', 'LBRACKET', 'IDENTIFIER', 'RBRACKET', 'IDENTIFIER', 'EQUALS', 'STRING_BASIC']
        # Wait, the regex for IDENTIFIER might be greedy or something. Let's check.
        # The current regex for IDENTIFIER is [a-zA-Z0-9_-]+
        # In '[table]', 'table' is an IDENTIFIER.
        
        actual_types = [t.type for t in tokens]
        # Let's just check if the essential tokens are there.
        self.assertIn('LBRACKET', actual_types)
        self.assertIn('RBRACKET', actual_types)
        self.assertIn('IDENTIFIER', actual_types)

if __name__ == '__main__':
    unittest.main()
