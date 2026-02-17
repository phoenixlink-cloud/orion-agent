---
name: software-architecture-design-patterns
description: "Designing robust software architectures and applying proven design patterns"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - development
  - coding
  - senior-developer
  - architecture
  - design-patterns
---

# Software Architecture & Design Patterns

The ability to design, evaluate, and evolve software architectures that balance
maintainability, scalability, and delivery speed. Covers architectural styles,
common design patterns, decision-making frameworks, and documentation practices
for communicating design intent to the team.

STEP-BY-STEP PROCEDURE

STEP 1: GATHER ARCHITECTURAL REQUIREMENTS
  Before designing, understand the forces shaping the solution:

  Functional requirements:
  - Core features and user workflows
  - Data model: entities, relationships, volumes, access patterns
  - Integration points: third-party APIs, databases, message queues
  - Multi-tenancy, localisation, or regulatory requirements

  Non-functional requirements (quality attributes):
  - Performance: Expected throughput, latency targets (p50, p95, p99)
  - Scalability: Expected growth in users, data, and traffic
  - Availability: Uptime target (99.9%? 99.99%?)
  - Security: Authentication, authorisation, data encryption needs
  - Observability: Logging, metrics, tracing, alerting
  - Cost: Infrastructure budget constraints
  - Team: Size, skill level, familiarity with technologies

  Document constraints:
  - Existing technology stack (must integrate with X)
  - Deployment environment (cloud, on-prem, hybrid)
  - Timeline and budget
  - Compliance requirements (GDPR, HIPAA, SOC2)

STEP 2: CHOOSE AN ARCHITECTURAL STYLE
  Select the style that best fits your requirements:

  MONOLITH:
  - Best for: Small teams, early-stage products, simple domains
  - Pros: Simple deployment, easy debugging, no network overhead
  - Cons: Scaling is all-or-nothing, large codebase can become unwieldy
  - When to evolve: When team grows beyond 8-10 or specific components
    need independent scaling

  MODULAR MONOLITH:
  - Best for: Medium teams wanting monolith simplicity with clear boundaries
  - Pros: Module boundaries enforce separation, easier to extract later
  - Cons: Requires discipline to maintain module boundaries

  MICROSERVICES:
  - Best for: Large teams, independent deployment needs, diverse tech stacks
  - Pros: Independent scaling, team autonomy, technology flexibility
  - Cons: Network complexity, distributed debugging, operational overhead
  - Warning: Do NOT start with microservices unless you have the team and
    infrastructure to support them. Premature microservices cause more
    problems than they solve.

  EVENT-DRIVEN:
  - Best for: Asynchronous workflows, decoupled producers/consumers
  - Pros: Loose coupling, natural audit trail, replay capability
  - Cons: Eventual consistency, harder to debug, message ordering

  SERVERLESS:
  - Best for: Bursty workloads, rapid prototyping, event-triggered tasks
  - Pros: No infrastructure management, pay-per-use, auto-scaling
  - Cons: Cold starts, vendor lock-in, execution time limits

STEP 3: APPLY DESIGN PATTERNS
  Use patterns to solve recurring structural problems:

  CREATIONAL PATTERNS:
  - Factory Method: Create objects without specifying the exact class
    Use when: You need to decouple object creation from usage
  - Builder: Construct complex objects step by step
    Use when: Object has many optional parameters or configurations
  - Singleton: Ensure only one instance exists (use sparingly!)
    Use when: Shared resource like a connection pool or config loader

  STRUCTURAL PATTERNS:
  - Adapter: Make incompatible interfaces work together
    Use when: Wrapping a third-party library with your own interface
  - Repository: Abstract data access behind a clean interface
    Use when: Decoupling business logic from database implementation
  - Facade: Simplify a complex subsystem behind a single interface
    Use when: A module has grown complex and callers need a simple entry point

  BEHAVIOURAL PATTERNS:
  - Strategy: Swap algorithms at runtime via a common interface
    Use when: Multiple ways to perform an action (e.g. payment methods)
  - Observer / Event Bus: Notify subscribers when state changes
    Use when: Components need to react to changes without tight coupling
  - Command: Encapsulate a request as an object
    Use when: You need undo/redo, queuing, or logging of operations

  APPLICATION PATTERNS:
  - CQRS: Separate read and write models
    Use when: Read and write patterns differ significantly in shape/scale
  - Saga: Manage distributed transactions across services
    Use when: Multi-step workflows that must maintain consistency

STEP 4: DESIGN FOR CHANGE
  Good architecture makes change easy and safe:

  - Depend on abstractions: Use interfaces at module boundaries so
    implementations can be swapped without changing callers
  - Separate concerns: Each layer/module has a clear responsibility
    Typical layers: Presentation > Application > Domain > Infrastructure
  - Minimise coupling: Module A should not know the internals of Module B
    Communicate through well-defined interfaces or events
  - Maximise cohesion: Related code lives together; unrelated code is
    separated even if it's used by the same feature

  Boundary rules:
  - Domain logic NEVER depends on infrastructure (no SQL in business rules)
  - Infrastructure adapters implement domain interfaces
  - Application services orchestrate domain objects and infrastructure
  - Presentation layer only calls application services

STEP 5: DOCUMENT ARCHITECTURAL DECISIONS
  Use Architecture Decision Records (ADRs):

  ADR format:
  - Title: Short description of the decision
  - Status: Proposed | Accepted | Deprecated | Superseded
  - Context: What situation prompted this decision?
  - Decision: What was decided and why?
  - Consequences: What are the trade-offs? What becomes easier/harder?

  Store ADRs in the repository (docs/adr/ or docs/decisions/)
  Number them sequentially: 001-use-postgresql.md, 002-adopt-cqrs.md

  Also maintain:
  - A high-level architecture diagram (C4 model recommended)
  - A component diagram showing module boundaries and data flow
  - A deployment diagram showing infrastructure topology

STEP 6: REVIEW AND EVOLVE
  Architecture is not a one-time decision:
  - Conduct architecture reviews quarterly or before major features
  - Track technical debt explicitly (spreadsheet, tickets, or ADRs)
  - Measure: Are the quality attributes being met? (latency, uptime, etc.)
  - Evolve incrementally: Strangler Fig pattern for gradual migration
  - Spike and prototype before committing to large architectural changes

TOOLS & RESOURCES
- Diagramming: Mermaid, PlantUML, draw.io, Excalidraw, C4 model
- ADR tools: adr-tools, MADR template
- Reference: "Clean Architecture" by Robert C. Martin
- Reference: "Fundamentals of Software Architecture" by Richards & Ford
- Reference: "Designing Data-Intensive Applications" by Martin Kleppmann

QUALITY STANDARDS
- Architecture documented with up-to-date diagrams
- All significant decisions recorded as ADRs
- Module boundaries enforced (no circular dependencies)
- Non-functional requirements measurable and measured
- New team members can understand the architecture from documentation
- No premature complexity — YAGNI (You Aren't Gonna Need It) applies
- Architecture reviewed before any major feature or migration
