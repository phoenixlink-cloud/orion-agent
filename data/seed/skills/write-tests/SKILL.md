---
name: write-tests
description: "Generate unit and integration tests with coverage targets"
version: "1.0.0"
author: "Orion"
tags: ["quality", "testing", "automation"]
source: "bundled"
trust_level: "verified"
---

## Test Writing Procedure

### 1. Analyze the Code Under Test
- Read the source file(s) completely
- Identify all public functions, methods, and classes
- Map input types, return types, and side effects
- Note any dependencies that need mocking

### 2. Test Categories
Write tests in this priority order:

#### A. Happy Path
- Normal inputs produce expected outputs
- One test per major code path

#### B. Edge Cases
- Empty inputs (empty string, empty list, None/null)
- Boundary values (0, -1, MAX_INT, empty collections)
- Single-element collections

#### C. Error Paths
- Invalid inputs raise appropriate exceptions
- Error messages are descriptive
- Resources are cleaned up on failure

#### D. Integration (if applicable)
- Components work together correctly
- Database queries return expected results
- API calls handle timeouts and errors

### 3. Test Structure
Follow the Arrange-Act-Assert pattern:
```
def test_<what>_<condition>_<expected>():
    # Arrange — set up test data
    # Act — call the function
    # Assert — verify the result
```

### 4. Coverage Targets
- Aim for >80% line coverage on new code
- 100% coverage on critical paths (auth, payment, data mutation)
- Every public method should have at least one test

### 5. Best Practices
- Tests should be independent (no shared mutable state)
- Use fixtures for common setup
- Prefer real assertions over mock verification where possible
- Test names should describe the scenario, not the implementation
