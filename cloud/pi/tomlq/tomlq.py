#!/usr/bin/env python3
"""tomlq - minimal TOML subset parser to JSON.
Usage: python3 tomlq.py FILE [KEYPATH]
"""
import sys, json, re
from collections import OrderedDict

# Helper functions

def err(msg, code):
    sys.stderr.write(msg + "\n")
    sys.exit(code)

# Tokenizer for values (strings, numbers, bool, array, inline table)

def tokenize_value(s):
    # returns list of tokens preserving order, simple split by whitespace except inside strings/brackets/braces
    tokens = []
    i = 0
    N = len(s)
    while i < N:
        c = s[i]
        if c in ' \t\n\r':
            i += 1
            continue
        if c in '[]{}:,=':
            tokens.append(c)
            i += 1
            continue
        if c == '"' or c == "'":
            # string literal (including multiline triple quotes)
            delim = c
            if s[i:i+3] == delim*3:
                end = s.find(delim*3, i+3)
                if end == -1:
                    err('unterminated multiline string', 1)
                val = s[i+3:end]
                i = end + 3
                tokens.append(('string', val, delim*3))
            else:
                i += 1
                start = i
                while i < N:
                    if s[i] == '\\':
                        i += 2
                        continue
                    if s[i] == delim:
                        break
                    i += 1
                else:
                    err('unterminated string', 1)
                val = s[start:i]
                i += 1
                tokens.append(('string', val, delim))
            continue
        # identifier / number / boolean
        m = re.match(r'[A-Za-z_\-][A-Za-z0-9_\-]*', s[i:])
        if m:
            txt = m.group(0)
            tokens.append(txt)
            i += len(txt)
            continue
        # number (including possible sign and underscores)
        m = re.match(r'[+-]?(?:0[xX][0-9A-Fa-f_]+|0[oO][0-7_]+|0[bB][01_]+|\d[\d_]*\.?[\d_]*([eE][+-]?\d[\d_]*)?)', s[i:])
        if m:
            txt = m.group(0)
            tokens.append(txt)
            i += len(txt)
            continue
        err(f'unexpected character {c!r} in value', 1)
    return tokens

def parse_string(tok):
    typ, raw, delim = tok
    if delim in ("'", "'''"):
        # literal string, no escapes
        return raw
    # basic string, need to process escapes
    esc_map = {'b':'\b','t':'\t','n':'\n','f':'\f','r':'\r','"':'\"','\\':'\\'}
    i = 0
    res = ''
    while i < len(raw):
        if raw[i] == '\\':
            i += 1
            if i >= len(raw):
                err('invalid escape at end of string',1)
            ch = raw[i]
            if ch in esc_map:
                res += esc_map[ch]
                i += 1
                continue
            if ch == 'u':
                hex4 = raw[i+1:i+5]
                if len(hex4)!=4 or not re.fullmatch(r'[0-9A-Fa-f]{4}',hex4):
                    err('invalid \u escape',1)
                res += chr(int(hex4,16))
                i += 5
                continue
            if ch == 'U':
                hex8 = raw[i+1:i+9]
                if len(hex8)!=8 or not re.fullmatch(r'[0-9A-Fa-f]{8}',hex8):
                    err('invalid \U escape',1)
                res += chr(int(hex8,16))
                i += 9
                continue
            # other escapes not supported
            err(f'unsupported escape \\{ch}',1)
        else:
            res += raw[i]
            i += 1
    return res

def parse_number(txt):
    if '_' in txt:
        txt = txt.replace('_','')
    if txt.startswith('+'):
        txt = txt[1:]
    if txt.lower().startswith('0x'):
        return int(txt,16)
    if txt.lower().startswith('0o'):
        return int(txt,8)
    if txt.lower().startswith('0b'):
        return int(txt,2)
    # float detection
    if any(c in txt for c in '.eE'):
        return float(txt)
    # decimal int cannot have leading zeros (except zero itself)
    if txt.startswith('0') and txt != '0':
        err('invalid leading zero in integer',1)
    return int(txt)

def parse_value(tokens, idx=0):
    # returns (value, new_idx)
    if idx >= len(tokens):
        err('unexpected end of value',1)
    tok = tokens[idx]
    # string token
    if isinstance(tok, tuple) and tok[0]=='string':
        return parse_string(tok), idx+1
    # bool
    if tok in ('true','false'):
        return tok=='true', idx+1
    # array
    if tok == '[':
        arr = []
        i = idx+1
        while True:
            # allow trailing commas and comments handled earlier
            # skip commas
            while i < len(tokens) and tokens[i]==',':
                i+=1
            if i < len(tokens) and tokens[i]==']':
                i+=1
                break
            val, i = parse_value(tokens,i)
            arr.append(val)
            # after a value, expect ',' or ']'
            while i < len(tokens) and tokens[i]==',':
                i+=1
                # allow trailing comma before closing
                if i < len(tokens) and tokens[i]==']':
                    i+=1
                    return arr,i
            if i < len(tokens) and tokens[i]==']':
                i+=1
                break
        return arr,i
    # inline table
    if tok == '{':
        table = OrderedDict()
        i = idx+1
        while True:
            if i < len(tokens) and tokens[i]=='}':
                i+=1
                break
            # key
            key_tok = tokens[i]
            if isinstance(key_tok, tuple):
                err('invalid key in inline table',1)
            key = key_tok
            i+=1
            if tokens[i] != '=':
                err('expected = in inline table',1)
            i+=1
            val, i = parse_value(tokens,i)
            if key in table:
                err('duplicate key in inline table',1)
            table[key]=val
            if i < len(tokens) and tokens[i]==',':
                i+=1
                continue
            if i < len(tokens) and tokens[i]=='}':
                i+=1
                break
            err('invalid inline table syntax',1)
        return table,i
    # number or identifier (could be boolean handled earlier)
    if isinstance(tok,str):
        # check if numeric
        if re.fullmatch(r'[+-]?(?:0[xX][0-9A-Fa-f_]+|0[oO][0-7_]+|0[bB][01_]+|\d[\d_]*\.?[\d_]*([eE][+-]?\d[\d_]*)?)',tok):
            return parse_number(tok), idx+1
        # otherwise treat as error (dates not supported)
        err('unsupported value token '+tok,1)
    err('unexpected token',1)

# Main parser

def parse_toml(text):
    # Remove comments respecting strings
    lines = text.splitlines()
    cleaned = []
    in_ml_str = False
    ml_delim = None
    for line in lines:
        i=0
        out=''
        while i < len(line):
            if not in_ml_str and line[i] in ('"',"'"):
                # check for triple quote start
                if line[i:i+3] == line[i]*3:
                    ml_delim = line[i]*3
                    in_ml_str = True
                    out+=ml_delim
                    i+=3
                    continue
                # single quote start
                delim=line[i]
                out+=delim
                i+=1
                # consume until matching delim
                while i < len(line):
                    if line[i]=='\\':
                        out+=line[i:i+2]
                        i+=2
                        continue
                    if line[i]==delim:
                        out+=delim
                        i+=1
                        break
                    out+=line[i]
                    i+=1
                continue
            if in_ml_str:
                # inside multiline string, just copy and look for end delim
                if line[i:i+len(ml_delim)]==ml_delim:
                    out+=ml_delim
                    i+=len(ml_delim)
                    in_ml_str=False
                    ml_delim=None
                else:
                    out+=line[i]
                    i+=1
                continue
            if line[i]=='#':
                # comment start, ignore rest
                break
            out+=line[i]
            i+=1
        cleaned.append(out)
    # Now process cleaned lines
    data = OrderedDict()
    cur_path = []
    array_of_tables_stack = []  # list of (path, list)
    for raw_line in cleaned:
        line = raw_line.strip()
        if not line:
            continue
        # Header?
        if line.startswith('['):
            if not line.endswith(']'):
                err('malformed header',1)
            hdr = line.strip('[]')
            is_array = False
            if hdr.startswith('[') and hdr.endswith(']'):
                # array of tables [[...]]
                is_array=True
                hdr = hdr[1:-1]
            # split dotted keys
            parts = []
            for part in re.split(r'\s*\.\s*', hdr):
                # handle quoted parts
                if part.startswith('"') or part.startswith('\''):
                    # use simple unquote (strip quotes)
                    if part[0]==part[-1] and part[0] in ('"','\''):
                        part=part[1:-1]
                parts.append(part)
            # navigate/create tables
            cur = data
            for i,p in enumerate(parts):
                if i==len(parts)-1:
                    # last part is the table we are entering
                    if is_array:
                        # ensure array exists
                        if p not in cur:
                            cur[p]=[]
                        elif not isinstance(cur[p],list):
                            err('array of tables but existing non-array',1)
                        # append new dict
                        cur[p].append(OrderedDict())
                        cur_path = parts[:i+1]  # path includes the array name
                        # set cur to the newly appended dict
                        cur = cur[p][-1]
                        # store for later sub-table references (they refer to last element)
                    else:
                        if p in cur:
                            if isinstance(cur[p],dict):
                                # existing table, ok (cannot redefine)
                                cur = cur[p]
                            else:
                                err('table name collides with existing value',1)
                        else:
                            cur[p]=OrderedDict()
                            cur = cur[p]
                    # set current path for subsequent keys
                else:
                    # intermediate tables
                    if p not in cur:
                        cur[p]=OrderedDict()
                    elif not isinstance(cur[p],dict):
                        err('intermediate key collides with value',1)
                    cur = cur[p]
            continue
        # Key/value line
        if '=' not in line:
            err('expected = in line',1)
        key_part, value_part = line.split('=',1)
        key_part = key_part.strip()
        value_part = value_part.strip()
        # parse dotted key
        key_parts = []
        for sub in re.split(r'\s*\.\s*', key_part):
            if sub.startswith('"') or sub.startswith('\''):
                if sub[0]==sub[-1] and sub[0] in ('"','\''):
                    sub = sub[1:-1]
            key_parts.append(sub)
        # tokenize value
        tokens = tokenize_value(value_part)
        val, nxt = parse_value(tokens)
        if nxt != len(tokens):
            err('extra tokens after value',1)
        # assign
        cur = data
        for p in cur_path:
            cur = cur[p]
        for i,k in enumerate(key_parts):
            if i==len(key_parts)-1:
                if k in cur:
                    err('duplicate key',1)
                cur[k]=val
            else:
                if k not in cur:
                    cur[k]=OrderedDict()
                elif not isinstance(cur[k],dict):
                    err('intermediate key collides with value',1)
                cur=cur[k]
    return data

def get_path(data, path):
    cur=data
    for p in path:
        if isinstance(cur,dict) and p in cur:
            cur=cur[p]
        else:
            err('key path not found',2)
    return cur

def main():
    if len(sys.argv)<2:
        err('usage: tomlq.py FILE [KEYPATH]',1)
    fname=sys.argv[1]
    try:
        txt=open(fname,encoding='utf-8').read()
    except Exception as e:
        err(str(e),1)
    data=parse_toml(txt)
    if len(sys.argv)>=3:
        path=sys.argv[2].split('.') if sys.argv[2] else []
        out=get_path(data,path)
    else:
        out=data
    json.dump(out,sys.stdout,ensure_ascii=False)
    sys.stdout.write('\n')

if __name__=='__main__':
    main()
