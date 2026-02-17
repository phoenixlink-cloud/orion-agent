---
name: debugging-troubleshooting-fundamentals
description: "Systematic approach to identifying, isolating, and resolving software bugs"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - development
  - coding
  - junior-developer
  - debugging
  - troubleshooting
---

# Debugging & Troubleshooting Fundamentals

A structured methodology for diagnosing and fixing software defects. This covers
reproducing issues, isolating root causes, using debugging tools effectively,
and building habits that prevent bugs from recurring.

STEP-BY-STEP PROCEDURE

STEP 1: REPRODUCE THE BUG
  Before fixing anything, you MUST be able to reproduce the issue reliably:
  - Read the bug report carefully: What was expected? What happened instead?
  - Identify the exact steps to reproduce (STR)
  - Note the environment: OS, browser, language version, dependencies
  - If intermittent, identify conditions that increase likelihood
  - Write down the reproduction steps — you'll need them later for testing
  - If you cannot reproduce it, ask for more details before investigating

STEP 2: ISOLATE THE PROBLEM
  Narrow down WHERE the bug lives:
  - Binary search: Comment out / disable half the code path, check if the
    bug persists, then narrow to the half that contains it. Repeat.
  - Check recent changes: Use version control log to see what changed
    near the affected code since it last worked
  - Simplify inputs: Use the minimum input that triggers the bug
  - Check boundaries: Off-by-one errors, null/empty inputs, negative
    values, very large inputs, special characters, timezone edge cases
  - Read error messages carefully — the stack trace tells you exactly
    where the failure occurred. Start from the BOTTOM of the trace.

STEP 3: UNDERSTAND BEFORE YOU FIX
  Resist the urge to change code until you understand the root cause:
  - Add logging at key points to trace the actual data flow
  - Use a debugger: Set breakpoints, step through line by line,
    inspect variable values at each stage
  - Draw the expected flow vs the actual flow
  - Ask: "Why does this value have this state at this point?"
  - Check assumptions: Is the data type what you expect? Is the function
    being called with the arguments you expect? Is it being called at all?
  - Common root causes:
    * Wrong variable scope (using stale or shadowed variable)
    * Off-by-one in loops or slicing
    * Null/undefined reference where a value was expected
    * Race condition in async code
    * Incorrect type coercion (string "0" treated as truthy)
    * Stale cache or memoised value
    * Environment difference (dev vs staging vs production)

STEP 4: IMPLEMENT THE FIX
  Make the minimum change that fixes the root cause:
  - Fix the ROOT CAUSE, not the symptom. If a variable is null because
    it wasn't initialised, don't just add a null check — initialise it.
  - Keep the fix focused: One bug = one fix = one commit
  - Write a test that FAILS before your fix and PASSES after
  - Check for similar patterns elsewhere in the codebase — the same
    bug class may exist in other places
  - Run the full test suite to ensure you haven't broken anything else

STEP 5: VERIFY THE FIX
  Confirm the fix works AND nothing else broke:
  - Re-run your reproduction steps — the bug should be gone
  - Run related test suites: unit, integration, and any end-to-end tests
  - Test edge cases around the fix
  - If the bug was reported by someone else, ask them to verify
  - Check: Did your fix introduce any new warnings or deprecations?

STEP 6: DOCUMENT AND LEARN
  Capture knowledge for the team and your future self:
  - Write a clear commit message: What was the bug? What caused it?
    What was the fix? Reference the ticket/issue number.
  - If the root cause was non-obvious, add a brief code comment
  - Update documentation if the bug revealed a misunderstanding
  - Retrospective: Could this class of bug be prevented?
    * Better type checking (TypeScript, mypy, type hints)?
    * A linter rule?
    * Better input validation?
    * More comprehensive tests?

DEBUGGING TOOLS BY LANGUAGE
  Python: pdb / breakpoint(), logging module, pytest --pdb, rich.traceback
  JavaScript: browser DevTools, console.log/debug/trace, Node --inspect
  General: IDE debuggers (VS Code, PyCharm, IntelliJ), print/log statements
  Network: browser Network tab, Postman, curl with verbose flags
  Database: query logs, EXPLAIN plans, pgAdmin / DBeaver

COMMON DEBUGGING MISTAKES TO AVOID
- Changing multiple things at once — change ONE thing, test, then change the next
- Fixing the symptom instead of the root cause
- Not writing a regression test for the bug
- Assuming the bug is in someone else's code (check yours first)
- Debugging production without reproducing locally first
- Ignoring compiler/linter warnings — they often point to the problem

QUALITY STANDARDS
- Every bug fix includes a regression test
- Commit messages reference the issue/ticket number
- Reproduction steps documented before investigation begins
- Root cause identified and documented, not just the symptom
- No "shotgun debugging" — changes are deliberate and minimal
- Fix verified by re-running original reproduction steps
