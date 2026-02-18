---
name: code-review-mentorship
description: "Leading effective code reviews and mentoring junior developers through constructive feedback"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - development
  - coding
  - senior-developer
  - code-review
  - mentorship
---

# Code Review & Mentorship

The practice of reviewing code with a focus on both quality and growth. Senior
developers use code review as a teaching tool — catching defects, sharing knowledge,
raising standards, and developing junior team members through constructive feedback.

STEP-BY-STEP PROCEDURE

STEP 1: PREPARE FOR THE REVIEW
  Before reading the code, set context:
  - Read the PR description and linked ticket/issue first
  - Understand the WHAT and WHY before judging the HOW
  - Check the size: If > 500 lines, consider asking the author to split
  - Note the author's experience level — adjust feedback depth accordingly
  - Allocate focused time: Don't review during meetings or between tasks
  - Time budget: 200-400 lines per hour is a healthy pace

STEP 2: REVIEW IN LAYERS
  Work from high-level to low-level:

  LAYER 1 — ARCHITECTURE & DESIGN (most important):
  - Does the overall approach make sense for this problem?
  - Are responsibilities in the right place? (right module, right layer)
  - Are there any unnecessary abstractions or missing ones?
  - Will this scale to the expected load and data volume?
  - Does it follow the project's established patterns?

  LAYER 2 — LOGIC & CORRECTNESS:
  - Are edge cases handled? (null, empty, boundary values, error paths)
  - Are there race conditions in async or concurrent code?
  - Is error handling appropriate? (not swallowed, not overly broad)
  - Are business rules correctly implemented?
  - Are there potential security issues? (injection, auth bypass, data leaks)

  LAYER 3 — READABILITY & MAINTAINABILITY:
  - Can you understand the code without the PR description?
  - Are names descriptive and consistent with the codebase?
  - Are functions small and focused?
  - Is there duplicated logic that should be extracted?
  - Are comments explaining WHY, not WHAT?

  LAYER 4 — TESTS:
  - Are there tests for the new/changed behaviour?
  - Do tests cover happy path AND error/edge cases?
  - Are test names descriptive? Can you tell what failed from the name?
  - Are mocks used appropriately (at boundaries, not everywhere)?

  LAYER 5 — STYLE & NITS (lowest priority):
  - Let the linter/formatter handle style — don't nitpick formatting
  - Only flag style issues the tooling can't catch
  - Prefix optional suggestions with "Nit:" so the author knows it's minor

STEP 3: WRITE CONSTRUCTIVE FEEDBACK
  How you say it matters as much as what you say:

  PRINCIPLES:
  - Critique the code, never the person
  - Ask questions rather than give commands:
    "What do you think about extracting this into a helper?"
    NOT: "Extract this into a helper."
  - Explain the WHY behind suggestions:
    "If we add an index on user_id, this query drops from O(n) to O(1)
    — it's already a bottleneck on the /dashboard endpoint."
  - Praise good work: "Nice approach here — the strategy pattern makes
    this really extensible."
  - Distinguish blocking vs non-blocking feedback:
    BLOCKING: "This has a null reference on line 42 that will crash in
    production — we need a guard check here."
    NON-BLOCKING: "Nit: Consider renaming 'data' to 'user_profile' for
    clarity — not a blocker."

  FEEDBACK FORMATS:
  - Bug/Defect: "Bug: This will throw if items is empty because..."
  - Suggestion: "Suggestion: We could simplify this with a list comprehension"
  - Question: "Question: Is this intentionally different from how we handle
    it in the OrderService? I expected the same pattern."
  - Praise: "Nice: Clean separation here, very readable."
  - Learn: "FYI: Python 3.12 added a built-in for this — might simplify"

STEP 4: MENTOR THROUGH REVIEWS
  Use reviews as a growth tool for junior developers:

  - Explain patterns: Don't just say "use the strategy pattern" — link to
    a resource or show a quick example of how it would look
  - Share context: "We avoid this pattern because last quarter it caused
    a production incident when..."
  - Offer pairing: "This is a tricky area — want to pair on it for 30 min?"
  - Gradual autonomy: As a junior improves, reduce the detail of feedback
    and shift from directing to asking questions
  - Track growth: Notice when a junior starts applying feedback from
    previous reviews — acknowledge the improvement
  - Be patient: The same feedback may need to be given 2-3 times before
    it sticks. That's normal.

STEP 5: HANDLE DISAGREEMENTS
  When the author disagrees with your feedback:
  - Default to discussion, not authority
  - Ask for their reasoning — they may know something you don't
  - If it's a preference (not a defect), defer to the author
  - If it's a genuine concern, escalate to the team's agreed standard
    or call a quick sync meeting
  - If no resolution, timebox the discussion and involve a third reviewer
  - Never block a PR over style preferences — only over correctness,
    security, or significant maintainability concerns

STEP 6: MANAGE REVIEW WORKLOAD
  Sustainable reviewing at scale:
  - Respond to review requests within 4 hours (aim for same-day)
  - Review small PRs immediately — they take < 15 minutes
  - Block calendar time for larger reviews
  - Rotate review assignments so knowledge spreads across the team
  - If overloaded, communicate: "I can review this tomorrow morning —
    is that okay or do you need someone sooner?"

TOOLS & RESOURCES
- Platforms: GitHub review features (suggested changes, review summary)
- Automation: CODEOWNERS file to auto-assign reviewers
- Linting in CI: Offload style enforcement to tools, not humans
- Reference: "The Art of Readable Code" by Boswell & Foucher
- Reference: Google's Engineering Practices — Code Review Guide

QUALITY STANDARDS
- Reviews completed within one business day of request
- Feedback categorised: blocking vs non-blocking, with clear reasoning
- At least one positive comment per review (genuine, not forced)
- No personal attacks or dismissive language in any review
- Junior developers receive at least one learning-oriented comment per PR
- Review approval rate: Reviews do not become a bottleneck (< 2 round-trips)
- Knowledge sharing: No single person is the only reviewer for a module
