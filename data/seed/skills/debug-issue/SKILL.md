---
name: debug-issue
description: "Systematic debugging methodology for isolating and fixing bugs"
version: "1.0.0"
author: "Orion"
tags: ["general", "debugging", "troubleshooting"]
source: "bundled"
trust_level: "verified"
---

## Systematic Debugging Procedure

### 1. Reproduce
- Confirm the bug exists — run the failing scenario
- Note exact error messages, stack traces, and log output
- Identify the minimum steps to reproduce

### 2. Isolate
- Narrow down to the specific file and function
- Add targeted logging or print statements
- Check recent changes (`git log`, `git diff`) for likely culprits
- Use binary search on commits if the regression timing is unclear

### 3. Understand Root Cause
- Read the code around the failure point carefully
- Trace the data flow from input to failure
- Check assumptions: types, null values, state, timing
- Distinguish symptom from root cause — fix the cause, not the symptom

### 4. Fix
- Make the minimal change that addresses the root cause
- Prefer upstream fixes over downstream workarounds
- Ensure the fix handles edge cases discovered during investigation

### 5. Verify
- Run the original reproduction steps — bug should be gone
- Run the full test suite — no regressions
- Add a regression test that would have caught this bug

### 6. Document
- Write a clear commit message explaining what was broken and why
- If the bug was subtle, add a code comment at the fix site
- Update any related documentation if behaviour changed
