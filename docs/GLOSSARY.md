# Glossary

Terms and definitions used throughout the Orion Agent documentation.

## A

**AEGIS** -- Autonomous Execution Governance and Integrity System. Orion's hardened security gate that validates all operations against six invariants. Cannot be bypassed or disabled.

**Agent** -- A specialized AI component within Orion's multi-agent system. The three primary agents are Builder, Reviewer, and Governor.

**Anti-pattern** -- A code or behavior pattern that has been identified as problematic through negative user feedback (ratings 1-2). Stored in memory to avoid repeating mistakes.

**Approval gate** -- A checkpoint where Orion pauses and asks for human confirmation before proceeding. Used in `pro` mode for file modifications.

## B

**Builder** -- The code generation agent in the Table of Three. Receives user requests and produces code solutions using the configured LLM provider.

**Bridge** -- A messaging integration that allows Orion to be controlled via Telegram, Slack, or Discord. See `src/orion/bridges/`.

## C

**CLA** -- Contributor License Agreement. Required for all code contributions to Orion. See CLA.md.

**Confidence score** -- A composite score (0.0 - 1.0) assigned to memory patterns and edit validations. Higher scores indicate greater reliability.

**Consolidation** -- Periodic process that removes low-confidence, low-access patterns from memory and merges duplicates.

**Council** -- See Table of Three.

## D

**Deterministic** -- Operating by fixed rules rather than probabilistic LLM output. The Governor agent uses deterministic logic, not an LLM.

## E

**Escalation** -- Routing a request to human decision-making when the risk level or ambiguity is too high for autonomous handling.

**Evolution Engine** -- The component that tracks Orion's performance over time, analyzing approval rates, quality trends, and generating self-improvement recommendations.

## F

**FastPath** -- The direct LLM route for simple requests. Bypasses the full Table of Three deliberation for speed. Used for explanations, small edits, and simple questions.

## G

**Governance mode** -- One of three permission levels (safe, pro, project) that controls what operations Orion can perform. Enforced by AEGIS.

**Governor** -- The decision-making agent in the Table of Three. Uses deterministic logic, memory, and quality gates -- not an LLM -- to make final decisions.

## H

**Hard boundary** -- An operation category that always requires human confirmation regardless of governance mode. Includes: financial transactions, legal commitments, ethical violations, production deployments, credential exposure, user data deletion.

## I

**Institutional memory** -- Tier 3 of the memory system. Cross-project wisdom stored in SQLite. Persists for months to years.

**Invariant** -- A security rule in AEGIS that is always enforced and cannot be bypassed. AEGIS has six invariants.

## K

**Knowledge Distillation (KD)** -- The process of extracting reusable patterns from individual interactions for storage in the memory system.

## L

**LLM** -- Large Language Model. The AI model that powers code generation and analysis. Orion supports 11 LLM providers.

## M

**Mode** -- See Governance mode.

**Memory Engine** -- The three-tier memory system that enables persistent learning. Tiers: Session (RAM), Project (JSON), Institutional (SQLite).

## O

**Ollama** -- A local LLM runtime that allows running models on your own hardware without API keys or cloud dependencies.

## P

**Pattern** -- A reusable piece of knowledge extracted from interactions. Can be a success pattern (what works) or anti-pattern (what to avoid).

**Plugin** -- An extension that hooks into Orion's lifecycle events. 8 hooks available: on_request, on_route, on_build, on_review, on_govern, on_execute, on_feedback, on_error.

**Project memory** -- Tier 2 of the memory system. Workspace-specific patterns stored as JSON. Persists for days to weeks.

**Promotion** -- The process of elevating a memory pattern from a lower tier to a higher tier based on confidence and access frequency.

## R

**Reviewer** -- The code critique agent in the Table of Three. Analyzes Builder output for correctness, quality, edge cases, and security issues. Issues verdicts: APPROVE, REVISE_AND_APPROVE, or BLOCK.

**Router** -- See Scout.

## S

**Sandbox** -- An isolated execution environment. Orion has two: a workspace sandbox (file isolation) and a code sandbox (Docker-based execution isolation).

**Savepoint** -- A git commit created before Orion modifies files. Enables `/undo` to revert changes.

**Scout** -- The request routing component that analyzes complexity and risk to determine the appropriate execution path (FastPath, Council, or Escalation).

**SecureStore** -- Orion's encrypted credential storage system. Uses Fernet encryption (AES-128-CBC) with machine-specific key derivation.

**Session memory** -- Tier 1 of the memory system. Current conversation context stored in RAM. Lost when the session ends.

## T

**Table of Three** -- Orion's multi-agent deliberation system. Three agents (Builder, Reviewer, Governor) collaborate to produce higher-quality results than any single agent.

**Tier** -- One of three memory levels: Tier 1 (Session/RAM), Tier 2 (Project/JSON), Tier 3 (Institutional/SQLite).

**tree-sitter** -- A parser generator tool used by Orion for code analysis and repository mapping.

## W

**Workspace** -- The project directory that Orion operates within. All file operations are confined to this directory by AEGIS.

**Workspace confinement** -- AEGIS Invariant 1. Ensures all file operations stay within the workspace directory. Uses 6-layer defense against path traversal.

---

**Next:** [FAQ](FAQ.md) | [Documentation Index](README.md)
