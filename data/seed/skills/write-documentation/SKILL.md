---
name: write-documentation
description: "Generate README, API docs, and architecture documentation"
version: "1.0.0"
author: "Orion"
tags: ["quality", "documentation", "readme"]
source: "bundled"
trust_level: "verified"
---

## Documentation Writing Procedure

### 1. Assess What Exists
- Check for existing README.md, CONTRIBUTING.md, docs/ folder
- Identify gaps in current documentation
- Note the project's language, framework, and build system

### 2. README Structure
A good README includes:
1. **Title and badges** — project name, build status, version
2. **One-line description** — what this project does
3. **Quick start** — install + run in <5 commands
4. **Prerequisites** — required tools and versions
5. **Installation** — step-by-step setup
6. **Usage** — common use cases with examples
7. **Configuration** — environment variables, config files
8. **API reference** — if applicable, endpoint summary
9. **Contributing** — how to contribute
10. **License** — license type and link

### 3. API Documentation
For each endpoint or public function:
- Method/signature
- Parameters with types and descriptions
- Return type and shape
- Error responses
- Example request and response

### 4. Architecture Documentation
- High-level system diagram (text or ASCII)
- Component responsibilities
- Data flow between components
- Key design decisions and rationale

### 5. Style Guidelines
- Use clear, concise language
- Prefer code examples over long explanations
- Keep paragraphs short (3-4 sentences max)
- Use consistent heading levels
- Include copy-pasteable commands
