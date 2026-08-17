---
name: verify-before-finishing
description: |
  Trigger the model to ALWAYS run verification before ending any turn where it created or edited a program, especially for Python CLI tools or any task that ships a runnable file.
---

**Verification Skill**

1. **Syntax check** for each source file you wrote or edited:
   ```bash
   python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" <file>
   ```
   - If the command fails, read the error output, fix the file, and repeat until it succeeds.

2. **Run tests** if any `test_*.py` files exist in the working directory:
   - Execute each test file with `python3 <testfile>`.
   - If any test fails, read the failure report, modify only the program (not the test), and re‑run until all tests pass.

3. **Run the program** when no test files are present:
   - Execute the main script (or entry point) on 2‑3 representative inputs.
   - Verify it produces output, exits with status 0, and behaves as expected.

4. **Declare completion** only after the above checks have all succeeded in the current turn. Do **not** claim "done" or "all tests pass" without having performed the verification steps.
