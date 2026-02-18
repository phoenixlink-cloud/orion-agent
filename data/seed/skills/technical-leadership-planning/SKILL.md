---
name: technical-leadership-planning
description: "Leading technical planning, sprint execution, and cross-team coordination as a senior developer"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - development
  - coding
  - senior-developer
  - leadership
  - planning
---

# Technical Leadership & Planning

The ability to lead technical planning, guide sprint execution, coordinate across
teams, and make sound technical decisions under uncertainty. Covers estimation,
roadmapping, technical spikes, cross-team collaboration, and balancing delivery
speed with engineering quality.

STEP-BY-STEP PROCEDURE

STEP 1: TECHNICAL PLANNING & ESTIMATION
  Turn business requirements into actionable engineering work:

  BREAKING DOWN WORK:
  - Read the requirements or user stories thoroughly
  - Identify the technical components: data model, business logic, API,
    UI, infrastructure, testing, documentation
  - Break into tasks small enough to complete in 1-2 days each
  - Identify dependencies: What must be done first? What can be parallel?
  - Flag unknowns: If you don't know how long something will take,
    schedule a technical spike (timeboxed investigation) first

  ESTIMATION:
  - Use relative sizing (story points) for sprint planning, not hours
  - Base estimates on team velocity, not individual speed
  - Include testing, documentation, and review time — not just coding
  - Add uncertainty buffers: If you've never done it before, multiply by 2
  - Track accuracy: Compare estimates to actuals and calibrate over time
  - When asked "How long will this take?", give a range with confidence:
    "3-5 days, 80% confidence" is better than "4 days"

  TECHNICAL SPIKES:
  - Timebox: Usually 1-2 days maximum
  - Define the question clearly: "Can we integrate with API X using approach Y?"
  - Output: A written decision (ADR) and a rough estimate for the real work
  - Kill spikes that aren't converging — if 2 days of investigation yields
    no clarity, escalate and discuss with the team

STEP 2: SPRINT EXECUTION & DELIVERY
  Keep the team delivering consistently:

  SPRINT RITUALS (your role as a senior):
  - Planning: Help the team break down stories, identify risks, flag
    dependencies. Advocate for sustainable pace.
  - Daily standups: Keep it brief. Focus on blockers, not status updates.
    If someone is stuck, offer to pair after the standup.
  - Mid-sprint check: Are we on track? Any scope creep? Any blockers?
  - Review/demo: Present completed work to stakeholders. Celebrate wins.
  - Retrospective: Drive action items, not just complaints. Volunteer to
    own improvements.

  UNBLOCKING THE TEAM:
  - If a junior is stuck for > 1 hour, pair with them
  - If a dependency is blocked, escalate immediately — don't wait
  - If scope is unclear, clarify with the product owner before coding
  - If a task is taking 3x longer than estimated, stop and reassess:
    Is the approach wrong? Is the scope bigger than expected? Replan.

  PROTECTING QUALITY:
  - Don't let deadline pressure skip testing or reviews
  - Push back on scope, not quality: "We can ship features A and B this
    sprint and defer C, but I won't skip tests on any of them"
  - Ensure every PR is reviewed before merge — no exceptions

STEP 3: TECHNICAL DECISION-MAKING
  Make decisions efficiently and document them:

  DECISION FRAMEWORK:
  1. Define the problem clearly (one sentence)
  2. List options (minimum 2, ideally 3)
  3. Evaluate trade-offs for each option:
     - Complexity: How hard to implement and maintain?
     - Risk: What can go wrong? How reversible is it?
     - Performance: Does it meet our scale requirements?
     - Team fit: Does the team know this technology?
     - Cost: Infrastructure, licensing, ongoing maintenance
  4. Choose and document (ADR format)
  5. Communicate the decision and reasoning to the team

  PRINCIPLES:
  - Prefer reversible decisions — choose options you can change later
  - "Good enough now" beats "perfect eventually" — avoid analysis paralysis
  - Two-way door decisions (easily reversed) → decide fast, move on
  - One-way door decisions (hard to reverse) → take time, get input
  - If the team disagrees, default to the simplest option that meets
    the requirements. Complexity must be justified.

STEP 4: CROSS-TEAM COORDINATION
  Senior developers bridge teams:

  WORKING WITH OTHER ENGINEERING TEAMS:
  - Own and document your team's API contracts (request/response schemas)
  - Communicate breaking changes early — at least 2 sprints notice
  - Align on shared standards: error formats, auth patterns, versioning
  - When blocked by another team, provide a clear description of what you
    need, by when, and what the impact of delay is

  WORKING WITH PRODUCT:
  - Translate technical constraints into business terms
  - Propose technical alternatives when a requirement is costly:
    "That feature as described would take 3 sprints, but if we simplify
    the search to exact match first, we can ship in 1 sprint and iterate"
  - Proactively flag risks: "This depends on API X which has been flaky —
    I recommend we build a fallback path"

  WORKING WITH DEVOPS / INFRASTRUCTURE:
  - Define deployment requirements clearly: environment variables, secrets,
    infrastructure dependencies, scaling parameters
  - Participate in incident response: Help diagnose, fix, and write
    post-mortems for issues in your team's domain
  - Own your team's observability: logging, metrics, alerts, dashboards

STEP 5: KNOWLEDGE SHARING
  A senior's impact multiplies through the team:

  DOCUMENTATION:
  - Maintain up-to-date architecture diagrams
  - Write onboarding guides for new team members
  - Document non-obvious decisions and workarounds
  - Keep the README accurate — it's the first thing new devs read

  TEACHING:
  - Run tech talks or lunch-and-learn sessions (monthly, 30-60 min)
  - Write internal blog posts about interesting problems solved
  - Create coding guidelines and patterns documents
  - Pair with juniors regularly — not just when they're stuck

  INSTITUTIONAL KNOWLEDGE:
  - Record tribal knowledge before it's lost (especially before someone leaves)
  - Create runbooks for operational tasks (deploy, rollback, debug common issues)
  - Build shared vocabulary: Agree on what terms mean in your domain

STEP 6: TECHNICAL ROADMAPPING
  Look beyond the current sprint:

  - Maintain a 3-month technical roadmap alongside the product roadmap
  - Include: Major features, infrastructure upgrades, debt reduction,
    dependency updates, security improvements
  - Review and update monthly with the engineering manager
  - Communicate upcoming technical work to product so they can plan around it
  - Identify long-term bets: "If we invest in X now, it enables Y and Z
    in Q3" — build the case with data

TOOLS & RESOURCES
- Project management: Jira, Linear, Shortcut, GitHub Projects
- Documentation: Notion, Confluence, Markdown in repo (docs/)
- Diagramming: Mermaid, Excalidraw, draw.io
- Communication: Slack/Teams for async, video calls for complex discussions
- ADR templates: MADR format or lightweight in-repo markdown

QUALITY STANDARDS
- All sprint commitments met >= 80% of the time
- Estimates within 30% of actual for familiar work
- Technical decisions documented as ADRs within 48 hours
- No features shipped without tests and code review
- Knowledge sharing activity at least once per month
- Blockers escalated within 2 hours, not days
- Cross-team API changes communicated >= 2 sprints in advance
- Technical roadmap reviewed and updated monthly
