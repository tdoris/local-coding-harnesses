---
name: error-path-coverage
description: Enumerate and test the error and edge cases a spec names, not just the happy path. Use before declaring a parser, patcher, validator, or any input-handling tool complete. Hidden test suites are weighted toward malformed input, and a tool that handles only well-formed input typically loses most of those points.
---

# Error path coverage

Happy-path code is the easy half. Graded suites concentrate on the other half:
malformed input, out-of-range access, missing members, and boundary values. A
tool that works perfectly on valid input and crashes on invalid input scores
far below what its author expects.

## 1. Enumerate from the spec

Re-read the spec and list every condition it describes as an error. The spec
usually names them explicitly — those are exactly what gets tested. Write the
list down.

## 2. Add the standard classes it did not name

Most input-handling tasks are tested on some subset of:

- **Out of range** — index past the end of a sequence
- **Negative or malformed index** — `-1`, `01`, `1.0`, `+1`, empty
- **Missing member** — operating on a key or path that does not exist
- **Root operations** — acting on the whole document rather than a child
- **Type mismatch** — indexing an object as an array, or the reverse
- **Empty input** — empty document, empty list of operations, empty file
- **Escaping** — quotes, backslashes, unicode, newlines inside strings
- **Duplicates** — the same key defined twice
- **Atomicity** — when one operation in a sequence fails, does the whole thing
  roll back, or is a partial mutation left behind?

## 3. Decide the contract for each

For every case, state what should happen: which exit code, whether anything
goes to stdout, whether a message goes to stderr. Get this from the spec — do
not invent it. A wrong-but-consistent choice still fails.

## 4. Test them

Add each case to the test file and run it. Error cases are cheap to write and
are usually where the remaining points are.

## 5. Check the failure mode is clean

An uncaught traceback is almost never the specified behaviour. Confirm errors
exit non-zero and do not print a Python traceback as their output.

## Done means

Every error condition the spec names has a test, the standard classes above
have been considered, and each produces the exit code and output the spec
requires.
