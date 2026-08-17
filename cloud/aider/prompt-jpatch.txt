Write `jpatch.py`: a single-file Python 3 program (standard library only) that applies a JSON Patch (RFC 6902) to a JSON document.

Usage: `python3 jpatch.py DOC.json PATCH.json`

- Read the document and the patch (a JSON array of operation objects), apply the operations in order, print the resulting document as JSON on stdout, exit 0.
- Any error: print a message to stderr, print nothing on stdout, exit 1. Errors include: the patch is not an array; an operation is not an object or lacks a required member (`op`, `path`; `value` for add/replace/test; `from` for move/copy); unknown `op`; a JSON Pointer that is malformed (must be `""` or start with `/`) or does not resolve where the operation requires it to exist (remove/replace/test, `from` of move/copy, and the parent of an add target); an array index that is out of range or not a canonical decimal (no leading zeros, no sign; `-` means end-of-array and is valid only as an add target); a failed `test`; moving a location into one of its own children. Application is atomic: on any error nothing is printed.
- JSON Pointer per RFC 6901: `~1` decodes to `/` and `~0` to `~` (decode `~1` before `~0`); `""` is the whole document; `/` is the key `""`.
- Semantics per RFC 6902: `add` inserts into arrays (shifting later elements; index equal to length or `-` appends) or sets an object member (a new member is appended at the end of the object; an existing member is replaced); `remove`/`replace` require the target to exist; `move` = remove from `from` then add at `path`; `copy` = add a deep copy of the value at `from`; `test` compares by JSON equality: objects irrespective of key order, arrays in order, numbers by numeric value (1 == 1.0), strings/booleans/null by exact type. Unrecognised members of an operation object are ignored.
- Preserve object key order in the output.
- Do not use `jsonpatch`, `jsonpointer` or any similar library.

The file `test_jpatch.py` in the current directory is the acceptance test: `python3 test_jpatch.py` must pass. Do not modify the test file.
