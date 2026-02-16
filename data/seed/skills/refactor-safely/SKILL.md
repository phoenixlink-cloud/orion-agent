---
name: refactor-safely
description: "Safe refactoring with test verification at every step"
version: "1.0.0"
author: "Orion"
tags: ["general", "refactoring", "quality"]
source: "bundled"
trust_level: "verified"
---

## Safe Refactoring Procedure

### 1. Pre-flight
- Ensure all tests pass BEFORE starting any refactoring
- Create a git savepoint (commit or stash current state)
- Identify the specific code smell or improvement target

### 2. Refactoring Types (in order of risk)

#### Low Risk
- **Rename** — variable, function, class, file
- **Extract function** — move a block into its own function
- **Extract constant** — replace magic numbers/strings with named constants
- **Remove dead code** — delete unused functions, imports, variables

#### Medium Risk
- **Move function** — relocate to a more appropriate module
- **Inline function** — replace trivial wrapper with the wrapped call
- **Change signature** — add/remove parameters (update all callers)
- **Replace conditional with polymorphism**

#### High Risk
- **Extract class/module** — split a large file into smaller ones
- **Change data structure** — modify how data is stored/passed
- **Replace algorithm** — swap implementation with a better approach

### 3. The Refactoring Loop
For EACH individual change:
1. Make ONE refactoring move
2. Run all tests immediately
3. If tests pass → commit with descriptive message
4. If tests fail → revert and try a smaller step
5. Repeat

### 4. Post-refactoring
- Run full test suite one final time
- Check that no functionality was accidentally changed
- Review the diff to ensure only intended changes were made
- Update documentation if public APIs changed
