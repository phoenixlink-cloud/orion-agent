# Changelog

All notable changes to Orion Agent will be documented in this file.

## [6.4.0] — 2026-02-08

### Added
- Clean project structure for GitHub publishing
- Modern `src/` layout with proper packaging
- Comprehensive CI/CD pipeline

### Migrated from Orion MVP
- Three-Tier Memory Engine (session → project → institutional)
- Continuous Learning & Evolution Engine
- Table of Three multi-agent architecture (Builder + Reviewer + Governor)
- Edit Validator with confidence scoring and auto-recovery
- Integration Health Check system (30+ checks)
- Production Stack (health probes, graceful shutdown, metrics, rate limiting)
- 79 integrations (LLM, voice, image, video, messaging, social, automation, storage)
- Git Safety Net with auto-commit savepoints
- Plugin API with 8 lifecycle hooks
- Doctor diagnostic system (15 checks)
- Deep Python Context (AST analysis, import graph, call graph)
- Code Quality Analyzer
- Docker Sandbox for isolated code execution

## [6.2.0] — 2026-02-08

### Added
- Three-Tier Memory System (`core/memory_engine.py`)
- Evolution Engine (`core/evolution_engine.py`)
- Edit Validator (`core/edit_validator.py`)
- Integration Health Checker (`core/integration_health.py`)
- Production Stack (`core/production.py`)
- Architecture docs and API reference
- 160 new tests

## Previous History
See Orion_MVP git log for versions v2.2.0 through v6.2.0.
