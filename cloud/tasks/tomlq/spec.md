Write `tomlq.py`: a single-file Python 3 program (standard library only) that parses a subset of TOML and prints JSON.

Usage: `python3 tomlq.py FILE [KEYPATH]`

- Parse FILE as TOML (subset below). Print the whole document as a JSON object on stdout; if KEYPATH is given (dotted, e.g. `server.ports` or `owner.name`), print only the JSON value at that path. KEYPATH parts are split on `.`; parts are plain (no quoting needed in tests).
- Exit code 0 on success. On a TOML parse error: print a message to stderr, nothing on stdout, exit code 1. If KEYPATH does not exist: message to stderr, nothing on stdout, exit code 2.
- Output must be valid JSON (`json.dumps` is fine; formatting does not matter). Preserve document key order.
- Integers must be emitted as JSON integers, floats as JSON floats (e.g. `1` vs `1.0`), booleans as `true`/`false`, strings as JSON strings.
- You must implement the parser yourself. Do NOT import or use tomllib, toml, tomli, tomlkit or any other TOML library.

Supported subset — behaviour must match TOML v1.0.0 exactly for these features:

- Comments (`#` to end of line), blank lines, spaces/tabs around keys, `=` and values.
- Bare keys `[A-Za-z0-9_-]+`; basic quoted keys `"..."` (with escapes); literal quoted keys `'...'`; dotted keys `a.b.c` where each part is bare or quoted (whitespace around dots allowed). Dotted keys create intermediate tables.
- Key/value pairs `key = value`, one per line.
- Strings: basic `"..."` with escapes `\b \t \n \f \r \" \\ \uXXXX \UXXXXXXXX`; literal `'...'` (no escapes); multi-line basic `"""..."""` (a newline immediately after the opening delimiter is trimmed; a line-ending backslash trims all whitespace and newlines up to the next non-whitespace character; escapes as in basic strings); multi-line literal `'''...'''` (first newline trimmed, no escapes).
- Integers: decimal with optional `+`/`-` and underscores between digits (`1_000`); hex `0xDEAD_beef`, octal `0o755`, binary `0b1101` (no sign). Leading zeros in decimal are an error.
- Floats: `3.14`, `-0.01`, `5e+22`, `1e06`, `6.626e-34`, `+1.0`, underscores between digits allowed. `inf`/`nan` are not required (you may reject them).
- Booleans `true` / `false`.
- Arrays `[ ... ]`: comma-separated values, may span multiple lines, trailing comma allowed, comments and blank lines allowed inside, mixed types allowed, nesting allowed, empty `[]`.
- Inline tables `{ k = v, k2 = v2 }` on a single line, empty `{}` allowed, no trailing comma. Inline tables are closed: adding keys to them later is an error.
- Standard tables `[a.b.c]`: opens the table at that path (creating parents as needed); subsequent key/values belong to it until the next header. Headers may appear in any order and a super-table may be defined after its sub-table (`[a.b]` then `[a]`). Defining the same table header twice is an error.
- Arrays of tables `[[fruits]]`: each header appends a new table to the array at that path; a following `[fruits.physical]` refers to the last element. Using `[[x]]` where `x` is already a static array or a value is an error.
- Duplicate keys (defining a key or table that already exists as a value) is a parse error. Redefining a value as a table, or a static array as an array of tables, is an error.
- Dates and times are NOT required; you may reject them with exit code 1.
- An empty document (or comments only) parses to `{}`.
