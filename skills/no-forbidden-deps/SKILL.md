---
name: no-forbidden-deps
description: Check the implementation does not use a library the spec forbids. Use when a spec says stdlib-only, "written from scratch", "do not use X", or names a reference library that solves the task for you. Catches the case where a task to reimplement something is quietly satisfied by importing the thing it was meant to replace.
---

# No forbidden dependencies

When a task says "write a TOML parser from scratch, `tomllib` is forbidden",
importing `tomllib` passes your own smoke tests and fails the actual grading.
This is an easy mistake to make late in a task, when a stubborn edge case is
the only thing left.

Graders check for this. Run the check yourself first.

## 1. Extract the forbidden set from the spec

Look for: "do not use", "forbidden", "without using", "from scratch",
"standard library only", "no third-party", or any named reference
implementation. Write the list down explicitly.

Also treat as forbidden any library that would trivially solve the whole
task, even if unnamed — that is usually the intent.

## 2. Grep the source

```bash
grep -nE '^\s*(import|from)\s+' <prog>.py
```

Read every line of that output against your forbidden list. Do not skim: a
single `import tomllib` inside a fallback branch is enough to fail.

## 3. Check the indirect routes

A forbidden library can arrive without an import statement:

```bash
grep -nE '__import__|importlib|subprocess|os\.system|eval\(|exec\(' <prog>.py
```

Shelling out to a CLI that wraps the forbidden library counts as using it.

## 4. Check for a stray dependency

If the spec says stdlib-only, every import must resolve in a bare interpreter:

```bash
python3 -c "
import ast,sys
mods={n.module.split('.')[0] if isinstance(n,ast.ImportFrom) and n.module else
      (n.names[0].name.split('.')[0] if isinstance(n,ast.Import) else None)
      for n in ast.walk(ast.parse(open('<prog>.py').read()))
      if isinstance(n,(ast.Import,ast.ImportFrom))}
print(sorted(m for m in mods if m))"
```

Confirm each name is in the standard library.

## Done means

You have read the actual import list, compared it against an explicit
forbidden set, and checked the indirect routes. If a forbidden import is the
only way you can pass a case, the correct move is to implement that case, not
to keep the import.
