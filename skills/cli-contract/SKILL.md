---
name: cli-contract
description: Verify a command-line program actually runs and writes output before declaring it done. Use whenever you create or edit a program that is invoked from a shell — especially a single-file CLI tool judged on its stdout and exit code. Catches the case where a syntactically valid module ships with no entry point and silently produces nothing.
---

# CLI contract

A program that imports cleanly is not a program that works. The most common
way a finished-looking file scores zero is that it defines its classes and
functions and then never runs them: no `if __name__ == "__main__"`, no
`sys.argv` handling, no `print`. It exits 0 and writes nothing.

Never declare a CLI task complete without executing the contract below.

## 1. Find the documented invocation

Re-read the spec and write down the exact command line it promises, e.g.

```
python3 tomlq.py <file.toml> [keypath]
python3 jpatch.py <doc.json> <patch.json>
```

If the spec shows example invocations, those are the contract. Use them verbatim.

## 2. Prove there is an entry point

```bash
grep -nE '__main__|sys\.argv' <prog>.py
```

Zero matches means the program cannot be invoked. Fix it before anything else.

## 3. Run it on a real input and require non-empty output

Create a small valid input, then:

```bash
out=$(python3 <prog>.py <input> 2>/dev/null); rc=$?
printf 'exit=%s bytes=%s\n' "$rc" "${#out}"
```

**Hard rule:** on a valid input, `exit=0` with `bytes=0` is a failure, not a
success. Fix the program and re-run until it prints something.

## 4. Check the output is the right shape

If the spec says JSON on stdout, pipe it through a parser rather than eyeballing:

```bash
python3 <prog>.py <input> | python3 -c 'import json,sys; json.load(sys.stdin); print("valid json")'
```

## 5. Check the failure path

Run it on input the spec says is invalid. A tool judged on exit codes must
return non-zero there and must not print a traceback as its normal output.

## Done means

All of: entry point present, valid input produces non-empty correctly-shaped
stdout with exit 0, invalid input produces a non-zero exit. Only then say the
task is complete.
