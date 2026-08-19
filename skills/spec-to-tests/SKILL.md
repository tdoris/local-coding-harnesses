---
name: spec-to-tests
description: Turn a written specification into a small executable test file BEFORE implementing it. Use at the start of any task that hands you a spec or prose description but no test file. Gives the work a concrete target to iterate against instead of an open-ended essay to plan around.
---

# Spec to tests

A visible test file is the single strongest predictor of finishing a task
correctly. When the task gives you one, use it. When it does not, write one
first — before the implementation, not after.

This is not ceremony. It converts an open-ended "write X" into a closed loop
you can run.

## 1. Extract concrete cases from the spec

Read the spec and list 8-12 specific input/output pairs. Cover:

- the two or three most basic cases
- each distinct feature the spec names
- every error condition the spec names (these are usually the majority of
  hidden-test failures)
- boundaries: empty input, single element, nesting, escaping

Write down actual literal values, not descriptions of values.

## 2. Write a runnable test file

Use `unittest` so it runs with no dependencies:

```python
#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile, unittest

PROG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "<prog>.py")

def run(*args):
    r = subprocess.run([sys.executable, PROG, *args],
                       capture_output=True, text=True, timeout=20)
    return r.returncode, r.stdout, r.stderr

class T(unittest.TestCase):
    def test_basic(self):
        rc, out, _ = run(...)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), {...})

if __name__ == "__main__":
    unittest.main(verbosity=1)
```

Invoke the program as a subprocess the way a user would, not by importing it —
that also proves the entry point exists.

## 3. Run it before implementing

```bash
python3 test_<prog>.py
```

Everything should fail. That is the target.

## 4. Implement until green

Re-run after each change. Fix only the program.

**Never edit a test to match the implementation.** If a test looks wrong,
re-read the spec and confirm against it before touching the test.

## 5. Keep it

Leave the test file in place. It is evidence the work was verified.
