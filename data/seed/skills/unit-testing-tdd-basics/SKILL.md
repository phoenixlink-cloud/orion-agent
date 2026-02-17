---
name: unit-testing-tdd-basics
description: "Writing effective unit tests and applying test-driven development fundamentals"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - development
  - coding
  - junior-developer
  - testing
  - tdd
---

# Unit Testing & TDD Basics

The discipline of writing automated tests to verify code correctness, catch
regressions, and enable confident refactoring. Covers test structure, assertions,
mocking, test-driven development workflow, and achieving meaningful coverage.

STEP-BY-STEP PROCEDURE

STEP 1: UNDERSTAND THE TEST PYRAMID
  Structure your test suite for fast, reliable feedback:

  UNIT TESTS (base — most tests here):
  - Test a single function, method, or class in isolation
  - No database, no network, no file I/O — use mocks for external deps
  - Run in milliseconds; entire suite completes in seconds
  - Aim for 70-80% of your total test count

  INTEGRATION TESTS (middle):
  - Test how components work together (e.g. service + database)
  - Slower than unit tests but catch wiring issues
  - Aim for 15-25% of your total test count

  END-TO-END TESTS (top — fewest):
  - Test complete user workflows through the real interface
  - Slowest and most brittle; use sparingly
  - Aim for 5-10% of your total test count

STEP 2: WRITE EFFECTIVE UNIT TESTS
  Follow the AAA pattern for every test:

  ARRANGE: Set up the test data and preconditions
  ACT:     Call the function/method being tested
  ASSERT:  Verify the result matches expectations

  Naming convention: test_<what>_<condition>_<expected_result>
  Examples:
  - test_calculate_tax_with_valid_income_returns_correct_amount
  - test_validate_email_with_empty_string_raises_value_error
  - test_fetch_user_with_unknown_id_returns_none

  Rules for good unit tests:
  - ONE assertion per test (or one logical assertion group)
  - Tests must be independent — no shared mutable state between tests
  - Tests must be deterministic — same result every time, no randomness
  - Tests must be fast — if a test takes > 1 second, it's not a unit test
  - Test behaviour, not implementation — test WHAT the function returns,
    not HOW it computes internally
  - Include edge cases: empty input, null, boundary values, error paths

STEP 3: USE MOCKS AND STUBS APPROPRIATELY
  Replace external dependencies with controlled substitutes:

  WHEN TO MOCK:
  - External APIs and network calls
  - Database queries
  - File operations
  - Time-dependent logic (freeze time)
  - Third-party services (email, payment, etc.)

  WHEN NOT TO MOCK:
  - The code under test itself
  - Simple value objects or data structures
  - Pure functions with no side effects

  Best practices:
  - Mock at the boundary, not deep inside your code
  - Verify mocks are called with expected arguments
  - Don't mock what you don't own — wrap third-party code in your own
    adapter, then mock the adapter
  - If you need more than 3 mocks for one test, the code under test
    probably has too many dependencies — refactor the production code

STEP 4: PRACTICE TEST-DRIVEN DEVELOPMENT (TDD)
  The Red-Green-Refactor cycle:

  RED:    Write a test that fails (because the feature doesn't exist yet)
  GREEN:  Write the MINIMUM code to make the test pass
  REFACTOR: Clean up the code while keeping all tests green

  TDD workflow:
  1. Read the requirement or user story
  2. Write one test for the simplest case
  3. Run it — confirm it fails (red)
  4. Write just enough production code to pass
  5. Run all tests — confirm they pass (green)
  6. Refactor if needed (extract, rename, simplify)
  7. Run all tests again — confirm still green
  8. Write the next test (next case, edge case, error case)
  9. Repeat until the feature is complete

  Benefits of TDD:
  - You never write code without a test
  - You design the API from the caller's perspective first
  - You avoid over-engineering (you only write what's needed)
  - You always have a safety net for refactoring

STEP 5: MEASURE AND IMPROVE COVERAGE
  Coverage measures which lines/branches your tests execute:

  - Line coverage: What percentage of lines are executed by tests?
  - Branch coverage: Are both if and else paths tested?
  - Aim for 80%+ line coverage on new code
  - 100% coverage does NOT mean bug-free — it means all paths are exercised
  - Missing coverage reveals untested code paths — prioritise those
  - Use coverage reports to find dead code (0% coverage = possibly unused)

  Do NOT chase 100% coverage by writing meaningless tests. Focus on:
  - Business logic (calculations, validations, transformations)
  - Error handling paths
  - Edge cases and boundary conditions
  - Recently changed code

TOOLS & RESOURCES
- Python: pytest, unittest, coverage.py, pytest-cov, pytest-mock
- JavaScript: Jest, Vitest, Mocha, Istanbul (coverage)
- General: IDE test runners, CI test automation, coverage badges
- Reference: "Test-Driven Development" by Kent Beck
- Reference: "Working Effectively with Legacy Code" by Michael Feathers

QUALITY STANDARDS
- All new code has accompanying unit tests
- Tests follow AAA pattern with descriptive names
- Test suite runs in < 30 seconds for unit tests
- No flaky tests — tests pass 100% of the time or are fixed immediately
- Coverage >= 80% on new code; coverage never decreases on a PR
- Mocks are used only for external boundaries, not internal logic
- Every bug fix includes a regression test
