---
name: technical-debt-refactoring-strategy
description: "Identifying, prioritising, and systematically reducing technical debt through strategic refactoring"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - development
  - coding
  - senior-developer
  - refactoring
  - technical-debt
---

# Technical Debt & Refactoring Strategy

The discipline of identifying, quantifying, and systematically reducing technical
debt while maintaining delivery velocity. Covers debt classification, prioritisation
frameworks, safe refactoring techniques, and communicating debt impact to stakeholders.

STEP-BY-STEP PROCEDURE

STEP 1: IDENTIFY TECHNICAL DEBT
  Debt comes in many forms — learn to recognise them all:

  CODE DEBT:
  - Duplicated logic across modules
  - God classes or functions (> 500 lines, multiple responsibilities)
  - Deep nesting (> 3 levels of indentation)
  - Inconsistent patterns (3 different ways to do the same thing)
  - Missing or outdated type annotations
  - Suppressed linter warnings without justification

  ARCHITECTURAL DEBT:
  - Circular dependencies between modules
  - Business logic in the wrong layer (SQL in controllers, UI logic in models)
  - Tight coupling between components that should be independent
  - Missing abstraction boundaries (one change ripples everywhere)
  - Over-engineering: Abstractions that add complexity without benefit

  TEST DEBT:
  - Low coverage in critical business logic (< 60%)
  - Flaky tests that pass intermittently
  - Missing integration tests for key workflows
  - Tests that test implementation rather than behaviour
  - No tests for error handling paths

  DEPENDENCY DEBT:
  - Outdated dependencies with known vulnerabilities
  - Deprecated APIs still in use
  - Unmaintained libraries with no upgrade path
  - Version conflicts or pinned-to-ancient versions

  DOCUMENTATION DEBT:
  - Outdated README or setup instructions
  - Missing architecture decision records
  - API documentation out of sync with implementation
  - No onboarding guide for new developers

STEP 2: QUANTIFY AND PRIORITISE
  Not all debt is equal — prioritise by impact:

  CLASSIFICATION MATRIX:
  HIGH IMPACT + LOW EFFORT = Do first (quick wins)
  HIGH IMPACT + HIGH EFFORT = Plan and schedule
  LOW IMPACT + LOW EFFORT = Do opportunistically (boy scout rule)
  LOW IMPACT + HIGH EFFORT = Defer or accept

  Impact factors:
  - Developer velocity: Does this debt slow down every PR?
  - Bug rate: Is this area a frequent source of defects?
  - Onboarding: Does this confuse every new team member?
  - Security: Does this debt create vulnerability exposure?
  - Scaling: Will this block growth at the next order of magnitude?

  Maintain a debt register (spreadsheet or tracking board):
  | Item | Type | Impact | Effort | Priority | Owner | Status |
  Track debt like you track features — it deserves visibility.

STEP 3: PLAN THE REFACTORING
  Refactoring should be deliberate, not ad-hoc:

  STRATEGIES:
  - Boy Scout Rule: Leave code cleaner than you found it — small
    improvements during feature work (rename, extract, simplify)
  - Dedicated sprints: Allocate 10-20% of sprint capacity to debt
  - Strangler Fig: Gradually replace old code with new code behind
    a feature flag or interface. Old and new coexist until migration
    is complete, then remove the old path.
  - Branch by Abstraction: Introduce an abstraction layer, migrate
    callers to the abstraction, swap the implementation underneath

  BEFORE REFACTORING:
  - Ensure adequate test coverage on the code you're about to change
    If coverage is low, write characterisation tests first
  - Define "done": What does the code look like after refactoring?
  - Scope strictly: Refactor ONE thing per PR. Don't mix refactoring
    with feature work.
  - Communicate: Tell the team what you're refactoring and why, so
    they don't build on the old patterns while you're changing them

STEP 4: EXECUTE SAFE REFACTORING
  Techniques that minimise risk:

  EXTRACT METHOD/FUNCTION:
  - Identify a block of code doing a distinct thing
  - Give it a descriptive name, move it to a function
  - Replace the original block with a call to the new function
  - Run tests — behaviour should be identical

  RENAME (variable, function, class, file):
  - Use IDE's rename refactoring tool (not find-and-replace)
  - Verify all references updated, including tests and documentation
  - Single commit, clear message: "Rename X to Y for clarity"

  EXTRACT CLASS/MODULE:
  - When a class has multiple responsibilities
  - Create a new class for the extracted responsibility
  - Move methods and data together
  - Update callers to use the new class

  REPLACE CONDITIONAL WITH POLYMORPHISM:
  - When you see if/elif chains or switch statements based on type
  - Create a base class/interface with a method for the varying behaviour
  - Create subclasses implementing the specific behaviour
  - Replace the conditional with a method call on the polymorphic object

  INTRODUCE INTERFACE/PROTOCOL:
  - When concrete classes are coupled directly
  - Define an interface/protocol at the boundary
  - Make the concrete class implement the interface
  - Change callers to depend on the interface, not the concrete class

  SAFETY RULES:
  - Never refactor without tests. If tests don't exist, write them first.
  - One refactoring technique per commit
  - Run tests after every change — if tests fail, revert and try smaller steps
  - If the refactoring is large, use a feature flag to ship incrementally

STEP 5: COMMUNICATE DEBT TO STAKEHOLDERS
  Non-technical stakeholders need to understand debt impact:

  Frame debt in business terms:
  - "This slows every feature by 2 days because developers have to work
    around the old payment integration"
  - "This area caused 3 production incidents last quarter, each costing
    4 hours of engineering time"
  - "New developers take 2 extra weeks to become productive because the
    setup process is undocumented and fragile"

  Propose concrete plans:
  - "If we invest 2 sprints in refactoring the auth module, we'll reduce
    bug rate by ~40% and speed up all auth-related features"
  - Include before/after metrics where possible

  Avoid:
  - "The code is bad" (not actionable)
  - "We need to rewrite everything" (almost never true)
  - Technical jargon without business context

STEP 6: PREVENT NEW DEBT
  Build guardrails into the development process:
  - Coding standards enforced by linters and formatters in CI
  - PR review checklist includes "Does this add technical debt?"
  - Architecture decision records for significant choices
  - Dependency update automation (Dependabot, Renovate)
  - Regular debt review meetings (monthly, 30 minutes)
  - "Debt budget": Accept that some debt is intentional (fast time-to-market)
    but track it explicitly with a ticket and a plan to pay it back

TOOLS & RESOURCES
- Static analysis: SonarQube, CodeClimate, Codacy
- Dependency scanning: Dependabot, Renovate, Snyk
- Coverage: coverage.py, Istanbul, Codecov
- IDE refactoring: VS Code, JetBrains refactoring tools
- Reference: "Refactoring" by Martin Fowler
- Reference: "Working Effectively with Legacy Code" by Michael Feathers

QUALITY STANDARDS
- Debt register maintained and reviewed monthly
- 10-20% of sprint capacity allocated to debt reduction
- No new code merged with suppressed linter warnings without justification
- Refactoring PRs are separate from feature PRs
- Test coverage does not decrease on any PR
- Dependencies updated within 30 days of security advisories
- Architecture diagrams updated when structure changes
