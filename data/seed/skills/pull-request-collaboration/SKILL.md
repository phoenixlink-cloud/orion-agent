---
name: pull-request-collaboration
description: "Creating effective pull requests and collaborating through the code review process"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - development
  - coding
  - junior-developer
  - pull-requests
  - collaboration
---

# Pull Request Collaboration

The practice of submitting code changes for review through well-structured pull
requests, responding constructively to feedback, and participating as a reviewer.
Covers PR creation, description writing, review etiquette, and iterating on feedback.

STEP-BY-STEP PROCEDURE

STEP 1: PREPARE YOUR BRANCH
  Before opening a PR, ensure your work is ready for review:
  - Rebase or merge the latest target branch into your feature branch
  - Resolve all merge conflicts locally
  - Run the full test suite — all tests must pass
  - Run the linter and formatter — zero warnings
  - Review your own diff: read every changed line as if you were the reviewer
  - Remove any debugging statements, console.log, print(), or TODO hacks
  - Ensure each commit is atomic and has a clear message
  - If the PR is large (> 400 lines changed), consider splitting it into
    smaller, reviewable chunks

STEP 2: WRITE THE PR DESCRIPTION
  A good description saves the reviewer time and gets faster approval:

  TITLE: Short, descriptive summary (imperative mood)
  Examples:
  - "Add email validation to user registration"
  - "Fix off-by-one error in pagination logic"
  - "Refactor payment service to use strategy pattern"

  BODY TEMPLATE:
  ## What
  Brief description of what this PR does.

  ## Why
  Context: What problem does this solve? Link to the issue/ticket.

  ## How
  High-level approach. Mention any design decisions or trade-offs.

  ## Testing
  How was this tested? What test cases were added?

  ## Screenshots (if UI change)
  Before/after screenshots or a short screen recording.

  ## Checklist
  - [ ] Tests pass
  - [ ] Linter clean
  - [ ] Documentation updated (if needed)
  - [ ] No breaking changes (or migration guide included)

STEP 3: KEEP PRs FOCUSED AND SMALL
  Smaller PRs get reviewed faster and more thoroughly:
  - Ideal PR size: 100-300 lines of meaningful changes
  - One logical change per PR — don't mix refactoring with feature work
  - If a feature requires 1000+ lines, break it into a chain of PRs:
    1. PR 1: Add the data model / schema changes
    2. PR 2: Add the business logic and tests
    3. PR 3: Add the API endpoint / UI layer
  - Separate "move/rename" commits from "change logic" commits so the
    reviewer can tell what actually changed

STEP 4: RESPOND TO REVIEW FEEDBACK
  Treat code review as a learning opportunity, not a personal critique:
  - Read every comment carefully before responding
  - If you agree: Make the change, reply "Done" or "Fixed — good catch"
  - If you disagree: Explain your reasoning respectfully with evidence,
    not emotion. "I chose this approach because..." not "That's wrong"
  - If you're unsure: Ask for clarification: "Could you elaborate on
    what you'd suggest here?"
  - Resolve conversations after addressing them so the reviewer can see
    what's left
  - If a suggestion is out of scope, acknowledge it and create a follow-up
    ticket: "Great idea — I've created JIRA-5678 to address this separately"
  - Push fixes as new commits (don't force-push during review) so the
    reviewer can see what changed since their last review
  - Re-request review once all feedback is addressed

STEP 5: REVIEW OTHERS' CODE (AS A JUNIOR)
  Even as a junior, you add value as a reviewer:
  - Start by reading the PR description to understand the intent
  - Pull the branch locally and run it if the change is significant
  - Focus on what you CAN assess:
    * Readability: Can you understand the code?
    * Naming: Do variable/function names make sense?
    * Tests: Are edge cases covered?
    * Documentation: Is it clear what the code does?
  - Ask questions to learn: "I haven't seen this pattern before — could
    you explain why X is preferred over Y here?"
  - Be specific: "Line 42: Could this return null if the user doesn't
    exist?" is better than "This might have a bug"
  - Be kind: Phrase suggestions as questions or offers, not demands

TOOLS & RESOURCES
- Platforms: GitHub PRs, GitLab Merge Requests, Bitbucket PRs, Azure DevOps
- PR templates: Use a .github/PULL_REQUEST_TEMPLATE.md for consistency
- Review tools: GitHub suggested changes, inline comments, review summary
- CI integration: Ensure CI runs automatically on every PR
- Draft PRs: Use draft/WIP PRs for early feedback before the work is complete

QUALITY STANDARDS
- Every PR has a clear title and description with context
- PR size: < 400 lines of meaningful changes (excluding generated files)
- All CI checks pass before requesting review
- Review feedback addressed within 24 hours
- No force-pushes during active review
- All conversations resolved before merge
- PR linked to the corresponding issue/ticket
- Self-review completed before requesting peer review
