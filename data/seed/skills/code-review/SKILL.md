---
name: code-review
description: "Structured code review with security checklist and quality gates"
version: "1.0.0"
author: "Orion"
tags: ["quality", "review", "security"]
source: "bundled"
trust_level: "verified"
---

## Code Review Procedure

### 1. Context Gathering
- Read the files to be reviewed in full
- Understand the purpose of the change (bug fix, feature, refactor)
- Identify the programming language and framework

### 2. Correctness Check
- Does the code do what the commit message / PR description says?
- Are edge cases handled (null, empty, overflow, concurrency)?
- Are error paths handled gracefully (try/catch, Result types)?

### 3. Security Checklist
- [ ] No hardcoded secrets, API keys, or passwords
- [ ] User input is validated and sanitized
- [ ] SQL queries use parameterized statements (no string concatenation)
- [ ] File paths are validated against traversal attacks
- [ ] Authentication and authorization checks are present where needed
- [ ] Sensitive data is not logged or exposed in error messages

### 4. Quality Gates
- [ ] Code follows the project's style guide
- [ ] Functions are reasonably sized (<50 lines preferred)
- [ ] Variable and function names are descriptive
- [ ] No dead code or commented-out blocks
- [ ] DRY — no unnecessary duplication
- [ ] Tests cover the new or changed code

### 5. Performance
- Are there any obvious N+1 queries or unnecessary loops?
- Are large datasets paginated or streamed?
- Are expensive operations cached where appropriate?

### 6. Output Format
Provide feedback as:
- **APPROVE** — no issues found
- **REQUEST CHANGES** — list specific issues with file:line references
- **COMMENT** — suggestions that are not blocking
