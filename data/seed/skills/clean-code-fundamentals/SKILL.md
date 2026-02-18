---
name: clean-code-fundamentals
description: "Writing readable, maintainable, and well-structured code following industry best practices"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - development
  - coding
  - junior-developer
  - clean-code
  - best-practices
---

# Clean Code Fundamentals

The ability to write code that is readable, maintainable, and follows established
conventions. This covers naming, structure, formatting, SOLID principles at an
introductory level, and avoiding common anti-patterns that lead to technical debt.

STEP-BY-STEP PROCEDURE

STEP 1: NAMING CONVENTIONS
  Variables, functions, classes, and files must communicate intent:
  - Variables: Use nouns that describe what the value IS
    BAD:  d, temp, data, x, val
    GOOD: elapsed_days, user_email, invoice_total, retry_count
  - Functions: Use verbs that describe what the function DOES
    BAD:  process(), handle(), do_thing()
    GOOD: calculate_tax(), validate_email(), fetch_user_by_id()
  - Booleans: Use is_, has_, can_, should_ prefixes
    GOOD: is_active, has_permission, can_edit, should_retry
  - Classes: Use PascalCase nouns describing the entity
    GOOD: InvoiceProcessor, UserRepository, EmailNotifier
  - Constants: Use UPPER_SNAKE_CASE
    GOOD: MAX_RETRY_COUNT, DEFAULT_TIMEOUT_SECONDS, API_BASE_URL
  - Avoid abbreviations unless universally understood (e.g. URL, HTTP, ID)
  - Name length should be proportional to scope size

STEP 2: FUNCTION DESIGN
  Write small, focused functions:
  - Single Responsibility: Each function does ONE thing well
  - Length: Aim for < 20 lines; if longer, consider splitting
  - Parameters: Ideally 0-3; if more, use an options object or dataclass
  - Return early: Use guard clauses to handle edge cases at the top
    instead of deeply nested if/else blocks
  - Avoid side effects: A function named get_user() should not also
    modify a database — name it update_and_get_user() if it does both
  - DRY (Don't Repeat Yourself): If you copy-paste code, extract it
    into a shared function. But don't over-abstract — Rule of Three
    (wait until you've duplicated 3 times before extracting)

STEP 3: CODE STRUCTURE & FORMATTING
  Consistency is more important than any specific style:
  - Follow the project's existing style guide (PEP 8 for Python,
    StandardJS, Google style guides, etc.)
  - Use an auto-formatter (Black, Prettier, gofmt) — don't argue about
    formatting; automate it
  - Use a linter (Ruff, ESLint, Clippy) — fix all warnings before committing
  - Organise imports: stdlib first, third-party second, local third
  - Group related code together; separate groups with blank lines
  - Keep files focused: one class or one cohesive set of functions per file
  - File length: If > 300 lines, consider splitting by responsibility

STEP 4: COMMENTS & DOCUMENTATION
  Code should be self-documenting; comments explain WHY, not WHAT:
  - BAD:  # increment counter  (the code already says that)
    counter += 1
  - GOOD: # Retry up to 3 times because the upstream API is flaky
    counter += 1
  - Write docstrings for all public functions and classes
  - Document non-obvious business rules or workarounds
  - TODO comments: Include your name/ticket and a brief explanation
    GOOD: # TODO(JSmith/JIRA-1234): Replace with batch API once available
  - Delete commented-out code — that's what version control is for

STEP 5: SOLID PRINCIPLES (INTRODUCTORY)
  S — Single Responsibility Principle:
    Each class/module has ONE reason to change.
    If a class handles both database queries AND email sending, split it.

  O — Open/Closed Principle:
    Open for extension, closed for modification.
    Use interfaces/abstract classes so new behaviour doesn't require
    editing existing working code.

  L — Liskov Substitution Principle:
    Subclasses must be usable wherever their parent class is expected.
    If it breaks when you swap in a subclass, your inheritance is wrong.

  I — Interface Segregation:
    Don't force classes to implement methods they don't use.
    Many small, specific interfaces > one large general interface.

  D — Dependency Inversion:
    Depend on abstractions, not concretions.
    Pass dependencies IN (constructor injection) rather than creating
    them inside the class. This makes testing much easier.

STEP 6: COMMON ANTI-PATTERNS TO AVOID
  - Magic numbers: Use named constants instead of raw values
    BAD:  if retries > 3:
    GOOD: if retries > MAX_RETRIES:
  - God class/function: One giant thing that does everything — split it
  - Deep nesting: More than 3 levels of indentation = refactor opportunity
  - Boolean parameters: def create_user(name, is_admin=False, is_active=True,
    send_email=True) — use an enum or config object instead
  - Catch-all exception handling: Never swallow errors silently
    BAD:  except Exception: pass
    GOOD: except ValueError as e: logger.warning("Invalid input: %s", e)
  - Premature optimisation: Make it work, make it right, THEN make it fast

TOOLS & RESOURCES
- Linters: Ruff (Python), ESLint (JS/TS), Clippy (Rust), golangci-lint (Go)
- Formatters: Black (Python), Prettier (JS/TS/CSS), gofmt (Go)
- Reference: "Clean Code" by Robert C. Martin
- Reference: "The Pragmatic Programmer" by Hunt & Thomas
- IDE features: Use refactoring tools (rename, extract method, inline)

QUALITY STANDARDS
- All code passes linter with zero warnings before commit
- Functions < 20 lines on average; outliers justified with a comment
- No commented-out code in committed files
- All public functions and classes have docstrings
- No magic numbers — all constants are named
- Naming: Another developer can understand the purpose without reading the implementation
- Code review feedback on readability decreases over time
